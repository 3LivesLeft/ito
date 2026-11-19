# SPDX-License-Identifier: Apache-2.0
"""Discovery over the Supervisor's Unix socket, for an unprivileged core (M1, ADR 0006 amendment).

Newer Supervisors give each app its own socket at ``/run/supervisor/api/supervisor.sock`` and
identify the app by the socket itself, so no token travels over the internal network. The socket
is owned by root with mode 0600 (Supervisor ``api/sockets.py``), and MeshBeacon's core runs as the
unprivileged ``meshbeacon`` user, so it cannot open it.

This relay is the smallest privileged piece that bridges the two. It runs as root in its own s6
service, listens on ``/run/meshbeacon/discovery.sock`` for the core only (checked by the peer's
user ID), and does exactly two things:

- ``announce``: POST MeshBeacon's discovery message, built here from strictly validated fields
  (host, port, token, fingerprint). Nothing else can be sent, and the service is fixed.
- ``withdraw``: DELETE one earlier message by its UUID.

It holds no state, logs no request content, reads at most 8 KiB per request with a deadline, and
serves one connection at a time. It grants nothing new: the core could already send the same
message with the Supervisor token over the internal network (the compatibility path that current
releases still need). Where there is no socket, the relay does not run.
"""

from __future__ import annotations

import contextlib
import grp
import http.client
import json
import os
import pwd
import re
import signal
import socket
import struct
import sys
import time
from pathlib import Path
from typing import Any

RELAY_DIR = Path("/run/meshbeacon")
RELAY_SOCKET = RELAY_DIR / "discovery.sock"
SUPERVISOR_SOCKET_ENV = "SUPERVISOR_SOCKET"
SERVICE = "meshbeacon"
SERVICE_USER = "meshbeacon"
MAX_REQUEST = 8192
DEADLINE = 5.0
SUPERVISOR_TIMEOUT = 10.0

_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_UUID = re.compile(r"^[0-9A-Za-z]{1,64}$")


class RelayError(Exception):
    """The request was refused or could not be delivered (never carries request content)."""


def announce_config(config: Any) -> dict[str, Any] | None:
    """The only discovery message the relay will send, or None if anything is off."""
    if not isinstance(config, dict) or set(config) != {"host", "port", "token", "cert_sha256"}:
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
    return {"host": host, "port": port, "token": token, "cert_sha256": cert}


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
    try:
        creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    except OSError:
        return None
    _pid, uid, _gid = struct.unpack("3i", creds)
    return int(uid)


def _read_line(conn: socket.socket, deadline: float) -> bytes | None:
    data = b""
    while b"\n" not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or len(data) > MAX_REQUEST:
            return None
        conn.settimeout(remaining)
        chunk = conn.recv(MAX_REQUEST + 1 - len(data))
        if not chunk:
            return None
        data += chunk
    line = data.split(b"\n", 1)[0]
    return line if len(line) <= MAX_REQUEST else None


def serve_one(conn: socket.socket, supervisor_socket: str, allowed_uid: int) -> None:
    with conn:
        if peer_uid(conn) != allowed_uid:
            return  # not the core: close without a word
        try:
            line = _read_line(conn, time.monotonic() + DEADLINE)
        except OSError:  # a slow, stalled or vanished client: drop it, never the relay
            return
        if line is None:
            return
        try:
            request = json.loads(line)
        except ValueError:
            request = None
        reply = handle(request, supervisor_socket)
        with contextlib.suppress(OSError):
            conn.settimeout(DEADLINE)
            conn.sendall(json.dumps(reply).encode() + b"\n")


def listen(path: Path, gid: int, owner: int = 0) -> socket.socket:
    path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(path.parent, owner, gid)
    path.parent.chmod(0o750)
    with contextlib.suppress(FileNotFoundError):
        path.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)
    try:
        server.bind(str(path))
    finally:
        os.umask(old)
    os.chown(path, owner, gid)
    path.chmod(0o660)
    server.listen(4)
    return server


def serve(
    path: Path,
    supervisor_socket: str,
    allowed_uid: int,
    gid: int,
    *,
    owner: int = 0,
    stop: list[bool] | None = None,
) -> None:
    server = listen(path, gid, owner)
    server.settimeout(1.0)
    with server:
        while not (stop and stop[0]):
            try:
                conn, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                time.sleep(0.5)
                continue
            try:
                serve_one(conn, supervisor_socket, allowed_uid)
            except Exception:
                print("[meshbeacon] Discovery relay: a request failed and was dropped.", flush=True)


def main() -> int:
    supervisor_socket = os.environ.get(SUPERVISOR_SOCKET_ENV, "")
    if not supervisor_socket or not Path(supervisor_socket).is_socket():
        print("[meshbeacon] No Supervisor socket here; discovery uses the compatibility path.", flush=True)
        signal.pause()  # nothing to do; s6 keeps the service up without a restart loop
        return 0
    user = pwd.getpwnam(SERVICE_USER)
    serve(RELAY_SOCKET, supervisor_socket, user.pw_uid, grp.getgrnam(SERVICE_USER).gr_gid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
