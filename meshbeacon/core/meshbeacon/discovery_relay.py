# SPDX-License-Identifier: Apache-2.0
"""Discovery over the Supervisor's Unix socket, for an unprivileged core (ADR 0006 amendment, M1.2).

Newer Supervisors give each app its own socket at ``/run/supervisor/api/supervisor.sock`` and
identify the app by the socket itself, so no token travels over the internal network. The socket
is owned by root with mode 0600 (Supervisor ``api/sockets.py``), and MeshBeacon's core runs as the
unprivileged ``meshbeacon`` user, so it cannot open it.

This relay is the smallest privileged piece that bridges the two. It runs as root in its own s6
service and does exactly two things:

- ``announce``: POST MeshBeacon's discovery message, built here from strictly validated fields
  (host, port, token, fingerprint). Nothing else can be sent, and the service is fixed.
- ``withdraw``: DELETE one earlier message by its UUID.

**Who can reach it (M1.2, threat T72).** The relay's socket is root's alone: mode 0600 in a 0700
folder, and the relay also drops any peer that is not root. The core does not connect to it
itself. Its root start step (:mod:`meshbeacon.relay_link`) opens the connection and hands it to
the core before it drops to the ``meshbeacon`` user. The Reticulum child runs as the same user as
the core but never receives that connection (it is not inheritable, and children are started with
``close_fds``), and it cannot open the socket, so it can neither announce nor withdraw.

It holds no state, logs no request content, reads at most 8 KiB per request, drops a request that
is not finished within a few seconds, and serves at most a few connections at once, so one stalled
connection never blocks another. Where there is no Supervisor socket, the relay does not run.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import re
import selectors
import signal
import socket
import stat
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RELAY_DIR = Path("/run/meshbeacon")
RELAY_SOCKET = RELAY_DIR / "discovery.sock"
SUPERVISOR_SOCKET_ENV = "SUPERVISOR_SOCKET"
SERVICE = "meshbeacon"
MAX_REQUEST = 8192
MAX_CLIENTS = 4
DEADLINE = 5.0  # for a request that has started to arrive; an idle, authorised link may wait
SUPERVISOR_TIMEOUT = 10.0

_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_UUID = re.compile(r"^[0-9A-Za-z]{1,64}$")


class RelayError(Exception):
    """The relay cannot start safely (never carries request content)."""


def announce_config(config: Any) -> dict[str, Any] | None:
    """The only discovery message the relay will send, or None if anything is off."""
    base = {"host", "port", "token", "cert_sha256"}
    if not isinstance(config, dict) or set(config) not in (base, base | {"messaging_key"}):
        return None
    host, port, token, cert = config["host"], config["port"], config["token"], config["cert_sha256"]
    if not isinstance(host, str) or not _HOST.match(host):
        return None
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        return None
    if not isinstance(token, str) or not _TOKEN.match(token):
        return None
    if not isinstance(cert, str) or not _FINGERPRINT.match(cert):
        return None  # never plain HTTP
    result: dict[str, Any] = {"host": host, "port": port, "token": token, "cert_sha256": cert}
    if "messaging_key" in config:  # M5 (ADR 0024): only while LXMF messaging is on
        key = config["messaging_key"]
        if not isinstance(key, str) or not _TOKEN.match(key) or key == token:
            return None
        result["messaging_key"] = key
    return result


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._path)
        self.sock = sock


def supervisor_request(
    supervisor_socket: str, method: str, path: str, payload: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    """One request to the Supervisor over its socket. No token: the socket identifies the app."""
    connection = _UnixConnection(supervisor_socket, SUPERVISOR_TIMEOUT)
    try:
        body = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"} if body is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read(65536)
        status = response.status
    finally:
        connection.close()
    try:
        value = json.loads(raw) if raw else {}
    except ValueError:
        value = {}
    return status, value if isinstance(value, dict) else {}


def handle(request: Any, supervisor_socket: str) -> dict[str, Any]:
    """Carry out one validated request; the reply never echoes its content."""
    if not isinstance(request, dict):
        return {"ok": False, "error": "invalid"}
    op = request.get("op")
    try:
        if op == "announce":
            config = announce_config(request.get("config"))
            if config is None:
                return {"ok": False, "error": "invalid"}
            status, reply = supervisor_request(
                supervisor_socket, "POST", "/discovery", {"service": SERVICE, "config": config}
            )
            uuid = (reply.get("data") or {}).get("uuid") if isinstance(reply.get("data"), dict) else None
            if status != 200:
                return {"ok": False, "error": f"supervisor:{status}"}
            return {"ok": True, "uuid": uuid if isinstance(uuid, str) and _UUID.match(uuid) else None}
        if op == "withdraw":
            uuid = request.get("uuid")
            if not isinstance(uuid, str) or not _UUID.match(uuid):
                return {"ok": False, "error": "invalid"}
            status, _ = supervisor_request(supervisor_socket, "DELETE", f"/discovery/{uuid}")
            if status in (200, 404):  # already gone counts as done
                return {"ok": True}
            return {"ok": False, "error": f"supervisor:{status}"}
    except (OSError, http.client.HTTPException):
        return {"ok": False, "error": "unreachable"}
    return {"ok": False, "error": "invalid"}


def peer_uid(conn: socket.socket) -> int | None:
    """The user ID of the process at the other end, as the kernel recorded it at connect time."""
    try:
        creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    except OSError:
        return None
    _pid, uid, _gid = struct.unpack("3i", creds)
    return int(uid)


def _safe_directory(directory: Path, owner: int) -> None:
    """Create ``directory`` for ``owner`` alone (0700), refusing anything unexpected (review L-3).

    The parent must be a real folder that only its owner can write to. ``directory`` itself must be
    a real folder (never a symbolic link, which ``O_NOFOLLOW`` refuses) owned by ``owner``; its mode
    is then set through the open descriptor, so nothing can be swapped in between.
    """
    parent = os.lstat(directory.parent)
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid not in (0, owner) or parent.st_mode & 0o022:
        raise RelayError("unsafe parent folder")
    with contextlib.suppress(FileExistsError):
        os.mkdir(directory, 0o700)
    try:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise RelayError("relay folder is not a folder") from exc
    try:
        info = os.fstat(fd)
        if info.st_uid != owner:
            raise RelayError("relay folder has an unexpected owner")
        os.fchmod(fd, 0o700)
        with contextlib.suppress(PermissionError):  # tests run as an unprivileged user
            os.fchown(fd, owner, 0 if owner == 0 else -1)
    finally:
        os.close(fd)


def listen(path: Path, owner: int = 0) -> socket.socket:
    """Bind the relay's socket, readable and writable by ``owner`` (root) only."""
    _safe_directory(path.parent, owner)
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        pass
    else:
        if not stat.S_ISSOCK(existing.st_mode):
            raise RelayError("unexpected file where the relay socket belongs")
        path.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)  # created as 0600: nothing to change afterwards
    try:
        server.bind(str(path))
    finally:
        os.umask(old)
    server.listen(MAX_CLIENTS)
    return server


@dataclass
class _Client:
    sock: socket.socket
    buf: bytes = b""
    started: float | None = None  # when the unfinished request began to arrive


def _reply(client: _Client, reply: dict[str, Any]) -> bool:
    try:
        client.sock.settimeout(DEADLINE)
        client.sock.sendall(json.dumps(reply).encode() + b"\n")
        client.sock.setblocking(False)
    except OSError:
        return False
    return True


def _feed(client: _Client, data: bytes, supervisor_socket: str, now: float) -> bool:
    """Handle every complete request in ``data``. False: drop the connection."""
    client.buf += data
    if client.started is None:
        client.started = now
    while b"\n" in client.buf:
        line, client.buf = client.buf.split(b"\n", 1)
        if len(line) > MAX_REQUEST:
            return False
        try:
            request = json.loads(line)
        except ValueError:
            request = None
        if not _reply(client, handle(request, supervisor_socket)):
            return False
        client.started = time.monotonic() if client.buf else None
    return len(client.buf) <= MAX_REQUEST


def serve(
    path: Path,
    supervisor_socket: str,
    *,
    allowed_uid: int = 0,
    owner: int = 0,
    stop: list[bool] | None = None,
) -> None:
    server = listen(path, owner)
    server.setblocking(False)
    selector = selectors.DefaultSelector()
    selector.register(server, selectors.EVENT_READ, None)
    clients: dict[int, _Client] = {}

    def drop(client: _Client) -> None:
        clients.pop(client.sock.fileno(), None)
        with contextlib.suppress(KeyError, ValueError):
            selector.unregister(client.sock)
        client.sock.close()

    with server:
        while not (stop and stop[0]):
            for key, _events in selector.select(timeout=0.5):
                try:
                    if key.data is None:
                        try:
                            conn, _ = server.accept()
                        except (BlockingIOError, InterruptedError):
                            continue
                        if peer_uid(conn) != allowed_uid or len(clients) >= MAX_CLIENTS:
                            conn.close()  # not root, or too many at once: close without a word
                            continue
                        conn.setblocking(False)
                        client = _Client(conn)
                        clients[conn.fileno()] = client
                        selector.register(conn, selectors.EVENT_READ, client)
                        continue
                    client = key.data
                    try:
                        data = client.sock.recv(MAX_REQUEST + 1)
                    except (BlockingIOError, InterruptedError):
                        continue
                    except OSError:
                        data = b""
                    if not data or not _feed(client, data, supervisor_socket, time.monotonic()):
                        drop(client)
                except Exception:  # one bad connection never stops the relay
                    if isinstance(key.data, _Client):
                        drop(key.data)
                    print("[meshbeacon] Discovery relay: a request failed and was dropped.", flush=True)
            now = time.monotonic()
            for client in list(clients.values()):
                if client.started is not None and now - client.started > DEADLINE:
                    drop(client)  # a stalled or slow request
        for client in list(clients.values()):
            drop(client)
        selector.close()


def main() -> int:
    supervisor_socket = os.environ.get(SUPERVISOR_SOCKET_ENV, "")
    if not supervisor_socket or not Path(supervisor_socket).is_socket():
        print("[meshbeacon] No Supervisor socket here; discovery uses the compatibility path.", flush=True)
        signal.pause()  # nothing to do; s6 keeps the service up without a restart loop
        return 0
    try:
        serve(RELAY_SOCKET, supervisor_socket)
    except RelayError:
        print(
            "[meshbeacon] The discovery relay found something unexpected in its run-time folder and has "
            "not started. Home Assistant will not be told about MeshBeacon; restart the app.",
            flush=True,
        )
        signal.pause()  # fail closed, without a restart loop
    return 0


if __name__ == "__main__":
    sys.exit(main())
