# SPDX-License-Identifier: Apache-2.0
"""Discovery over the Supervisor's Unix socket through the root relay (M1, discovery_relay.py).

A fake Supervisor listens on a Unix socket in a temporary folder, as the real one does at
/run/supervisor/api/supervisor.sock; the relay and the core's Discovery client talk to it there.
"""

from __future__ import annotations

import json
import os
import socket
import socketserver
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from meshbeacon import discovery_relay as relay_mod
from meshbeacon.api import Discovery, relay_request
from meshbeacon.supervisor import discovery_transport

HOST = "ce27fbb5-meshbeacon"
TOKEN = "K" * 43
CERT = "ab" * 32


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


@pytest.fixture
def sockets(tmp_path):
    # AF_UNIX paths are limited to 107 bytes, so use a short folder.
    base = Path(f"/tmp/mbr-{os.getpid()}-{time.monotonic_ns()}")
    base.mkdir(mode=0o700)
    supervisor = FakeSupervisor(base / "supervisor.sock")
    relay_path = base / "run" / "discovery.sock"
    stop = [False]
    thread = threading.Thread(
        target=relay_mod.serve,
        args=(relay_path, str(base / "supervisor.sock"), os.getuid(), os.getgid()),
        kwargs={"owner": os.getuid(), "stop": stop},
        daemon=True,
    )
    thread.start()
    for _ in range(100):
        if relay_path.exists():
            break
        time.sleep(0.02)
    yield supervisor, relay_path, base
    stop[0] = True
    thread.join(3)
    supervisor.close()
    for path in sorted(base.rglob("*"), reverse=True):
        path.unlink() if not path.is_dir() else path.rmdir()
    base.rmdir()


def test_announce_and_withdraw_go_over_the_socket_without_a_token(sockets, tmp_path):
    supervisor, relay_path, _ = sockets
    discovery = Discovery(None, tmp_path / "discovery.json", relay=relay_path)
    assert discovery.transport == "socket"
    assert discovery.announce(HOST, 8100, TOKEN, CERT)
    assert supervisor.requests == [
        {
            "method": "POST",
            "path": "/discovery",
            "auth": None,  # the socket identifies the app; no token is sent
            "body": {
                "service": "meshbeacon",
                "config": {"host": HOST, "port": 8100, "token": TOKEN, "cert_sha256": CERT},
            },
        }
    ]
    assert json.loads((tmp_path / "discovery.json").read_text()) == {"uuid": "0123abcd"}
    assert discovery.withdraw()
    assert supervisor.requests[-1]["method"] == "DELETE" and supervisor.requests[-1]["path"] == "/discovery/0123abcd"
    assert not (tmp_path / "discovery.json").exists()


@pytest.mark.parametrize(
    "config",
    [
        {"host": HOST, "port": 8100, "token": TOKEN},  # no fingerprint: never plain HTTP
        {"host": HOST, "port": 8100, "token": TOKEN, "cert_sha256": CERT, "messaging": {"key": "M" * 43}},
        {"host": "evil.example", "port": 8100, "token": TOKEN, "cert_sha256": CERT},
        {"host": HOST, "port": True, "token": TOKEN, "cert_sha256": CERT},
        {"host": HOST, "port": 8100, "token": "short", "cert_sha256": CERT},
        {"host": HOST, "port": 8100, "token": TOKEN, "cert_sha256": "AB" * 32},
    ],
)
def test_the_relay_sends_nothing_but_a_valid_message(sockets, config):
    supervisor, relay_path, _ = sockets
    with pytest.raises(OSError):
        relay_request(relay_path, {"op": "announce", "config": config})
    assert supervisor.requests == []


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
def test_only_the_two_operations_exist(sockets, request_):
    supervisor, relay_path, _ = sockets
    with pytest.raises(OSError):
        relay_request(relay_path, request_)  # type: ignore[arg-type]
    assert supervisor.requests == []


def test_a_supervisor_refusal_is_reported_not_hidden(sockets, tmp_path):
    supervisor, relay_path, _ = sockets
    supervisor.status = 403
    assert not Discovery(None, tmp_path / "d.json", relay=relay_path).announce(HOST, 8100, TOKEN, CERT)


def test_the_relay_socket_is_for_the_core_only(sockets):
    _, relay_path, _ = sockets
    mode = stat.S_IMODE(relay_path.stat().st_mode)
    assert mode == 0o660
    assert stat.S_IMODE(relay_path.parent.stat().st_mode) == 0o750


def test_another_user_is_ignored(tmp_path):
    base = Path(f"/tmp/mbu-{os.getpid()}-{time.monotonic_ns()}")
    base.mkdir(mode=0o700)
    supervisor = FakeSupervisor(base / "s.sock")
    relay_path = base / "r" / "d.sock"
    stop = [False]
    thread = threading.Thread(
        target=relay_mod.serve,
        args=(relay_path, str(base / "s.sock"), os.getuid() + 1, os.getgid()),  # someone else
        kwargs={"owner": os.getuid(), "stop": stop},
        daemon=True,
    )
    thread.start()
    for _ in range(100):
        if relay_path.exists():
            break
        time.sleep(0.02)
    try:
        with pytest.raises(OSError):
            relay_request(
                relay_path, {"op": "announce", "config": {"host": HOST, "port": 1, "token": TOKEN, "cert_sha256": CERT}}
            )
        assert supervisor.requests == []
    finally:
        stop[0] = True
        thread.join(3)
        supervisor.close()
        for path in sorted(base.rglob("*"), reverse=True):
            path.unlink() if not path.is_dir() else path.rmdir()
        base.rmdir()


def test_oversized_and_slow_requests_are_dropped(sockets, monkeypatch):
    supervisor, relay_path, _ = sockets
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(str(relay_path))
        sock.sendall(b"x" * (relay_mod.MAX_REQUEST + 100))
        try:
            reply = sock.recv(100)
        except ConnectionResetError:
            reply = b""
        assert reply == b""  # closed without a reply
    monkeypatch.setattr(relay_mod, "DEADLINE", 0.3)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(str(relay_path))
        sock.sendall(b'{"op": "ann')  # never finished
        started = time.monotonic()
        assert sock.recv(100) == b""
        assert time.monotonic() - started < 6
    assert supervisor.requests == []


def test_without_a_socket_the_relay_waits_and_does_nothing(monkeypatch, capsys):
    monkeypatch.delenv(relay_mod.SUPERVISOR_SOCKET_ENV, raising=False)
    paused = []
    monkeypatch.setattr(relay_mod.signal, "pause", lambda: paused.append(True))
    assert relay_mod.main() == 0
    assert paused and "compatibility path" in capsys.readouterr().out


def test_the_core_prefers_the_socket_and_then_drops_the_token():
    env = {"SUPERVISOR_TOKEN": "tok", "SUPERVISOR_SOCKET": "/run/supervisor/api/supervisor.sock", "OTHER": "1"}
    token, relay = discovery_transport(env)
    assert token is None and relay == relay_mod.RELAY_SOCKET
    assert "SUPERVISOR_TOKEN" not in env and "SUPERVISOR_SOCKET" not in env and env["OTHER"] == "1"


def test_the_core_uses_the_compatibility_path_without_a_socket():
    env = {"SUPERVISOR_TOKEN": "tok"}
    assert discovery_transport(env) == ("tok", None)
    assert env == {}
    assert discovery_transport({}) == (None, None)


def test_discovery_needs_a_transport(tmp_path):
    with pytest.raises(ValueError):
        Discovery(None, tmp_path / "d.json")
