# SPDX-License-Identifier: Apache-2.0
"""Discovery over the Supervisor's Unix socket through the root relay (discovery_relay.py).

A fake Supervisor listens on a Unix socket in a temporary folder, as the real one does at
/run/supervisor/api/supervisor.sock. These tests run unprivileged, so the relay is told to accept
the test's own user where it would accept only root; tests that check the root-only rule keep the
real value (0) and prove that an ordinary user, like the Reticulum child, is refused (review M-1).
The container tests repeat the important ones with the real users.
"""

from __future__ import annotations

import json
import os
import socket
import socketserver
import stat
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from meshbeacon import api as api_mod
from meshbeacon import discovery_relay as relay_mod
from meshbeacon import relay_link as link_mod
from meshbeacon.api import Discovery, RelayLink, RelayRefusedError
from meshbeacon.supervisor import discovery_transport

HOST = "ce27fbb5-meshbeacon"
TOKEN = "K" * 43
CERT = "ab" * 32
VALID = {"host": HOST, "port": 8100, "token": TOKEN, "cert_sha256": CERT}
ME = os.getuid()


class FakeSupervisor:
    def __init__(self, path: Path, status: int = 200) -> None:
        self.requests: list[dict[str, object]] = []
        self.status = status
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length)) if length else None
                outer.requests.append(
                    {"method": self.command, "path": self.path, "auth": self.headers.get("Authorization"), "body": body}
                )
                reply = json.dumps({"result": "ok", "data": {"uuid": "0123abcd"}}).encode()
                self.send_response(outer.status)
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            do_POST = do_DELETE = _reply  # noqa: N815 - http.server handler names

            def address_string(self) -> str:  # a Unix socket has no peer address
                return "supervisor"

            def log_message(self, *args: object) -> None:
                pass

        self.server = socketserver.ThreadingUnixStreamServer(str(path), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def short_dir() -> Path:
    # AF_UNIX paths are limited to 107 bytes, so use a short folder.
    base = Path(f"/tmp/mbr-{os.getpid()}-{time.monotonic_ns()}")
    base.mkdir(mode=0o700)
    return base


def remove(base: Path) -> None:
    for path in sorted(base.rglob("*"), reverse=True):
        path.unlink() if path.is_symlink() or not path.is_dir() else path.rmdir()
    base.rmdir()


class Relay:
    def __init__(self, base: Path, allowed_uid: int) -> None:
        self.supervisor = FakeSupervisor(base / "supervisor.sock")
        self.path = base / "run" / "discovery.sock"
        self.stop = [False]
        self.thread = threading.Thread(
            target=relay_mod.serve,
            args=(self.path, str(base / "supervisor.sock")),
            kwargs={"allowed_uid": allowed_uid, "owner": ME, "stop": self.stop},
            daemon=True,
        )
        self.thread.start()
        for _ in range(100):
            if self.path.exists():
                break
            time.sleep(0.02)

    def link(self) -> RelayLink:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(str(self.path))
        return RelayLink(sock)

    def close(self) -> None:
        self.stop[0] = True
        self.thread.join(3)
        self.supervisor.close()


@pytest.fixture
def relay(monkeypatch):
    monkeypatch.setattr(api_mod, "RELAY_PEER_UID", ME)
    base = short_dir()
    r = Relay(base, allowed_uid=ME)
    yield r
    r.close()
    remove(base)


@pytest.fixture
def root_only_relay():
    """The relay exactly as deployed: it accepts root only."""
    base = short_dir()
    r = Relay(base, allowed_uid=0)
    yield r
    r.close()
    remove(base)


def test_announce_and_withdraw_go_over_one_link_without_a_token(relay, tmp_path):
    discovery = Discovery(None, tmp_path / "discovery.json", relay=relay.link())
    assert discovery.transport == "socket"
    assert discovery.announce(HOST, 8100, TOKEN, CERT)
    assert relay.supervisor.requests == [
        {
            "method": "POST",
            "path": "/discovery",
            "auth": None,  # the socket identifies the app; no token is sent
            "body": {"service": "meshbeacon", "config": VALID},
        }
    ]
    assert json.loads((tmp_path / "discovery.json").read_text()) == {"uuid": "0123abcd"}
    assert discovery.withdraw()  # the same link serves later requests
    assert relay.supervisor.requests[-1]["method"] == "DELETE"
    assert relay.supervisor.requests[-1]["path"] == "/discovery/0123abcd"
    assert not (tmp_path / "discovery.json").exists()


@pytest.mark.parametrize(
    "config",
    [
        {"host": HOST, "port": 8100, "token": TOKEN},  # no fingerprint: never plain HTTP
        {**VALID, "messaging": {"key": "M" * 43}},
        {**VALID, "host": "evil.example"},
        {**VALID, "port": True},
        {**VALID, "token": "short"},
        {**VALID, "cert_sha256": "AB" * 32},
    ],
)
def test_the_relay_sends_nothing_but_a_valid_message(relay, config):
    link = relay.link()
    with pytest.raises(RelayRefusedError):
        link.request({"op": "announce", "config": config})
    assert relay.supervisor.requests == []
    assert not link.broken  # a refusal is an answer; the link stays usable
    link.request({"op": "announce", "config": VALID})
    assert len(relay.supervisor.requests) == 1


@pytest.mark.parametrize(
    "request_",
    [
        {"op": "post", "path": "/addons/self/options", "body": {}},  # no other Supervisor call
        {"op": "withdraw", "uuid": "../addons/self/options"},
        {"op": "withdraw", "uuid": ""},
        [],
        "announce",
    ],
)
def test_only_the_two_operations_exist(relay, request_):
    with pytest.raises(RelayRefusedError):
        relay.link().request(request_)  # type: ignore[arg-type]
    assert relay.supervisor.requests == []


def test_a_supervisor_refusal_is_reported_not_hidden(relay, tmp_path):
    relay.supervisor.status = 403
    assert not Discovery(None, tmp_path / "d.json", relay=relay.link()).announce(HOST, 8100, TOKEN, CERT)


def test_the_relay_socket_is_for_its_owner_alone(relay):
    """M-1: socket 0600 in a 0700 folder (root's in production): no other user can even connect."""
    assert stat.S_IMODE(relay.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(relay.path.parent.stat().st_mode) == 0o700


@pytest.mark.skipif(ME == 0, reason="needs an unprivileged user (the Reticulum child is never root)")
def test_a_non_root_process_cannot_use_the_relay(root_only_relay):
    """M-1: the deployed relay accepts root only. The Reticulum child (an ordinary user) is closed
    on without a word, so it can neither announce nor withdraw, even if it reaches the socket."""
    for request in ({"op": "announce", "config": VALID}, {"op": "withdraw", "uuid": "0123abcd"}):
        link = root_only_relay.link()
        with pytest.raises(RelayRefusedError):
            link.request(request, timeout=5)
        assert link.broken
    assert root_only_relay.supervisor.requests == []


def test_the_core_accepts_a_link_only_to_root():
    """The core adopts the inherited descriptor only if root is at the other end."""
    one, two = socket.socketpair()
    with one, two:
        if ME != 0:
            assert RelayLink.from_fd(os.dup(one.fileno())) is None  # an ordinary user's socket
    r, w = os.pipe()
    try:
        assert RelayLink.from_fd(r) is None  # not a socket
    finally:
        os.close(w)
    assert RelayLink.from_fd(987654) is None  # not open


def test_reticulum_never_inherits_the_link(relay):
    """M-1: the link is made non-inheritable, and children are started the way the supervisor starts
    Reticulum (close_fds, one status pipe passed); the child sees no socket to the relay."""
    link_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    link_sock.connect(str(relay.path))
    fd = link_sock.detach()
    os.set_inheritable(fd, True)  # as relay_link hands it over
    env = {"SUPERVISOR_SOCKET": "/run/supervisor/api/supervisor.sock", link_mod.RELAY_FD_ENV: str(fd)}
    token, link, socket_mode = discovery_transport(env)
    assert token is None and socket_mode and link is not None and env == {}
    assert not os.get_inheritable(fd)
    inode = os.fstat(fd).st_ino
    read_fd, write_fd = os.pipe()
    probe = (
        "import os, stat\n"
        "found = []\n"
        "for name in os.listdir('/proc/self/fd'):\n"
        "    try:\n"
        "        info = os.fstat(int(name))\n"
        "    except OSError:\n"
        "        continue\n"
        "    if stat.S_ISSOCK(info.st_mode):\n"
        "        found.append(info.st_ino)\n"
        f"print({inode} in found)\n"
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", probe], pass_fds=(write_fd,), capture_output=True, text=True, check=True
    )
    os.close(read_fd)
    os.close(write_fd)
    assert out.stdout.strip() == "False"
    link.close()


def test_stalled_connections_never_block_the_core(relay, monkeypatch):
    """L-2: silent and half-sent connections neither block the core's link nor hold a slot for ever."""
    monkeypatch.setattr(relay_mod, "DEADLINE", 0.5)
    link = relay.link()
    silent = []
    for _ in range(relay_mod.MAX_CLIENTS - 2):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(str(relay.path))
        silent.append(s)
    half = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    half.connect(str(relay.path))
    half.sendall(b'{"op": "ann')  # never finished
    started = time.monotonic()
    link.request({"op": "announce", "config": VALID})
    assert time.monotonic() - started < 2  # served at once, not after the others
    half.settimeout(5)
    started = time.monotonic()
    assert half.recv(100) == b""  # the unfinished request is dropped after the deadline
    assert time.monotonic() - started < 3
    time.sleep(1.0)  # longer than the deadline: an idle, finished link is kept
    link.request({"op": "withdraw", "uuid": "0123abcd"})
    for s in silent:
        s.close()
    half.close()


def test_connections_beyond_the_limit_are_closed(relay):
    held = [relay.link() for _ in range(relay_mod.MAX_CLIENTS)]
    held[0].request({"op": "announce", "config": VALID})  # make sure all are accepted
    extra = relay.link()
    with pytest.raises(RelayRefusedError):
        extra.request({"op": "announce", "config": VALID}, timeout=5)
    for link in held:
        link.close()


def test_oversized_requests_are_dropped(relay):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(str(relay.path))
        sock.sendall(b"x" * (relay_mod.MAX_REQUEST + 100))
        try:
            reply = sock.recv(100)
        except ConnectionResetError:
            reply = b""
        assert reply == b""  # closed without a reply
    assert relay.supervisor.requests == []


# -- L-3: safe set-up of the relay's run-time folder ----------------------------------------------


def test_a_symlinked_relay_folder_is_refused():
    base = short_dir()
    try:
        target = base / "elsewhere"
        target.mkdir(mode=0o755)
        (base / "run").symlink_to(target)
        with pytest.raises(relay_mod.RelayError):
            relay_mod.listen(base / "run" / "discovery.sock", owner=ME)
        assert stat.S_IMODE(target.stat().st_mode) == 0o755  # nothing changed through the link
        assert not (target / "discovery.sock").exists()
    finally:
        remove(base)


def test_a_relay_folder_with_another_owner_is_refused():
    base = short_dir()
    try:
        (base / "run").mkdir(mode=0o700)
        with pytest.raises(relay_mod.RelayError):
            relay_mod.listen(base / "run" / "discovery.sock", owner=ME + 1)
    finally:
        remove(base)


def test_an_unexpected_file_at_the_socket_path_is_kept_and_refused():
    base = short_dir()
    try:
        (base / "run").mkdir(mode=0o700)
        (base / "run" / "discovery.sock").write_text("not a socket")
        with pytest.raises(relay_mod.RelayError):
            relay_mod.listen(base / "run" / "discovery.sock", owner=ME)
        assert (base / "run" / "discovery.sock").read_text() == "not a socket"
    finally:
        remove(base)


def test_a_writable_parent_folder_is_refused():
    base = short_dir()
    try:
        base.chmod(0o777)
        with pytest.raises(relay_mod.RelayError):
            relay_mod.listen(base / "run" / "discovery.sock", owner=ME)
    finally:
        base.chmod(0o700)
        remove(base)


def test_an_old_relay_folder_is_tightened():
    """The previous layout (0750, the service user's group) is reset to the owner alone."""
    base = short_dir()
    try:
        (base / "run").mkdir(mode=0o750)
        server = relay_mod.listen(base / "run" / "discovery.sock", owner=ME)
        server.close()
        assert stat.S_IMODE((base / "run").stat().st_mode) == 0o700
    finally:
        remove(base)


def test_the_relay_fails_closed_without_a_restart_loop(monkeypatch, capsys, tmp_path):
    sock = tmp_path / "s"
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(sock))
    monkeypatch.setenv(relay_mod.SUPERVISOR_SOCKET_ENV, str(sock))

    def unsafe(*args, **kwargs):
        raise relay_mod.RelayError("unsafe parent folder")

    monkeypatch.setattr(relay_mod, "serve", unsafe)
    paused = []
    monkeypatch.setattr(relay_mod.signal, "pause", lambda: paused.append(True))
    assert relay_mod.main() == 0
    assert paused and "has not started" in capsys.readouterr().out
    server.close()


def test_without_a_socket_the_relay_waits_and_does_nothing(monkeypatch, capsys):
    monkeypatch.delenv(relay_mod.SUPERVISOR_SOCKET_ENV, raising=False)
    paused = []
    monkeypatch.setattr(relay_mod.signal, "pause", lambda: paused.append(True))
    assert relay_mod.main() == 0
    assert paused and "compatibility path" in capsys.readouterr().out


# -- the core's choice of transport ----------------------------------------------------------------


def test_socket_mode_never_uses_the_token_even_without_a_link():
    """No downgrade: with a socket, a missing or rejected link means no discovery, never TCP."""
    for fd in (None, "987654", "not-a-number"):
        env = {"SUPERVISOR_TOKEN": "tok", "SUPERVISOR_SOCKET": "/run/supervisor/api/supervisor.sock", "OTHER": "1"}
        if fd is not None:
            env[link_mod.RELAY_FD_ENV] = fd
        assert discovery_transport(env) == (None, None, True)
        assert env == {"OTHER": "1"}


def test_the_core_uses_the_compatibility_path_without_a_socket():
    """The token comes only from the one-time pipe, never from the environment (M1.2)."""
    token = "T" * 40
    fd = link_mod.token_pipe(token.encode())
    env = {"SUPERVISOR_TOKEN": "from-the-environment", link_mod.RELAY_FD_ENV: "5", link_mod.TOKEN_FD_ENV: str(fd)}
    assert discovery_transport(env) == (token, None, False)
    assert env == {}
    with pytest.raises(OSError):
        os.fstat(fd)  # read once and closed
    assert discovery_transport({"SUPERVISOR_TOKEN": "from-the-environment" * 2}) == (None, None, False)
    assert discovery_transport({}) == (None, None, False)


def test_discovery_needs_a_transport(tmp_path):
    with pytest.raises(ValueError):
        Discovery(None, tmp_path / "d.json")


# -- relay_link: the root start step --------------------------------------------------------------


def _capture_exec(monkeypatch):
    calls: list[tuple[str, list[str], dict[str, str]]] = []
    monkeypatch.setattr(link_mod.os, "execve", lambda path, argv, env: calls.append((path, argv, env)))
    return calls


def test_relay_link_hands_the_core_a_link_to_root(relay, monkeypatch):
    monkeypatch.setattr(link_mod, "peer_uid", lambda sock: 0)  # the relay is root in production
    calls = _capture_exec(monkeypatch)
    monkeypatch.setenv(link_mod.RELAY_FD_ENV, "stale")
    link_mod.main(["--relay", str(relay.path), "--", "/command/s6-setuidgid", "meshbeacon", "python3"])
    [(path, argv, env)] = calls
    assert path == "/command/s6-setuidgid" and argv == ["/command/s6-setuidgid", "meshbeacon", "python3"]
    fd = int(env[link_mod.RELAY_FD_ENV])
    assert fd >= 3 and os.get_inheritable(fd)
    link = RelayLink.from_fd(fd)
    assert link is not None
    link.request({"op": "announce", "config": VALID})
    assert relay.supervisor.requests


def test_relay_link_refuses_a_relay_that_is_not_root(relay, monkeypatch, capsys):
    if ME == 0:
        monkeypatch.setattr(link_mod, "peer_uid", lambda sock: 9100)
    calls = _capture_exec(monkeypatch)
    link_mod.main(["--relay", str(relay.path), "--", "/bin/true"])
    [(_path, _argv, env)] = calls
    assert link_mod.RELAY_FD_ENV not in env
    assert "did not answer" in capsys.readouterr().out


def test_relay_link_always_starts_the_core(monkeypatch, capsys, tmp_path):
    """A missing relay never stops the node (ADR 0005): the core starts without the link."""
    monkeypatch.setattr(link_mod, "WAIT", 0.6)
    monkeypatch.setattr(link_mod, "SLOW", 0.2)
    calls = _capture_exec(monkeypatch)
    started = time.monotonic()
    link_mod.main(["--relay", str(tmp_path / "missing.sock"), "--", "/bin/true"])
    assert time.monotonic() - started < 5  # bounded: never waits indefinitely
    assert calls and link_mod.RELAY_FD_ENV not in calls[0][2]
    out = capsys.readouterr().out
    assert "Waiting for the discovery relay" in out and "did not answer" in out


def test_relay_link_waits_for_a_slow_relay(relay, monkeypatch, tmp_path):
    """Slow hardware: a relay that appears after a few seconds is still found (bounded wait)."""
    monkeypatch.setattr(link_mod, "peer_uid", lambda sock: 0)
    late = tmp_path / "late.sock"

    def appear() -> None:
        time.sleep(1.0)
        late.symlink_to(relay.path)  # the relay's socket shows up late

    threading.Thread(target=appear, daemon=True).start()
    calls = _capture_exec(monkeypatch)
    link_mod.main(["--relay", str(late), "--", "/bin/true"])
    assert link_mod.RELAY_FD_ENV in calls[0][2]
    os.close(int(calls[0][2][link_mod.RELAY_FD_ENV]))


def test_relay_link_usage():
    assert link_mod.main(["only-one"]) == 2
    assert link_mod.main(["--relay", "/x", "--token-file", "/y", "--", "/bin/true"]) == 2
    assert link_mod.main(["--relay", "--", "/bin/true"]) == 2
    assert link_mod.main(["--other", "x", "--", "/bin/true"]) == 2
