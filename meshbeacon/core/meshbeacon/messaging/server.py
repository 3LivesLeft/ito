# SPDX-License-Identifier: Apache-2.0
"""The contract binding (ADR 0014): JSON lines over a Unix socket, for the core only.

``/run/meshbeacon-messaging/engine.sock`` (0660, group ``mb-msg``, in a 0750 folder
``mb-lxmf:mb-msg``; ``mb-msg`` holds only the core and the engine). Every connection's peer is
checked with ``SO_PEERCRED``: only the allowed user (the core, ``meshbeacon``) is served; anyone
else is disconnected without an answer. At most four connections at once; a request line is at
most 16 KiB; each answer is one line. Nothing here is reachable from the network or from Home
Assistant.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import stat
import struct
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

MAX_CONNECTIONS = 4
MAX_LINE = 16 * 1024
IDLE_TIMEOUT = 120.0
SOCKET_MODE = 0o660


def peer_uid(conn: socket.socket) -> int:
    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return int(struct.unpack("3i", creds)[1])


class Server:
    def __init__(self, path: Path, handle: Callable[[Any], dict[str, Any]], allowed_uids: set[int]) -> None:
        self.path = path
        self.handle = handle
        self.allowed = frozenset(allowed_uids)
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self.refused = 0
        self.sock: socket.socket | None = None
        self.stopping = threading.Event()

    def bind(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            if stat.S_ISSOCK(self.path.lstat().st_mode):
                self.path.unlink()  # left behind by a previous run
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o117)
        try:
            sock.bind(str(self.path))
        finally:
            os.umask(old)
        os.chmod(self.path, SOCKET_MODE)
        # The folder's group (mb-msg: the core and the engine). The engine belongs to it, so no
        # privilege is needed; if it does not, this fails and the engine does not start.
        folder_gid = self.path.parent.stat().st_gid
        if self.path.stat().st_gid != folder_gid:
            os.chown(self.path, -1, folder_gid)
        sock.listen(MAX_CONNECTIONS)
        self.sock = sock

    def serve(self) -> None:
        if self.sock is None:
            raise RuntimeError("bind() first")
        while not self.stopping.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                if self.stopping.is_set():
                    return
                continue
            if peer_uid(conn) not in self.allowed:
                self.refused += 1
                conn.close()
                continue
            if not self.slots.acquire(blocking=False):
                with contextlib.suppress(OSError):
                    conn.sendall(b'{"ok": false, "error": "busy"}\n')
                conn.close()
                continue
            threading.Thread(target=self._serve_one, args=(conn,), daemon=True).start()

    def _serve_one(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(IDLE_TIMEOUT)
            reader = conn.makefile("rb")
            while True:
                line = reader.readline(MAX_LINE + 1)
                if not line:
                    return
                if len(line) > MAX_LINE or not line.endswith(b"\n"):
                    conn.sendall(b'{"ok": false, "error": "invalid"}\n')
                    return
                try:
                    request = json.loads(line)
                except ValueError:
                    answer: dict[str, Any] = {"ok": False, "error": "invalid"}
                else:
                    answer = self.handle(request)
                conn.sendall(json.dumps(answer, separators=(",", ":")).encode() + b"\n")
        except OSError:
            return
        finally:
            with contextlib.suppress(OSError):
                conn.close()
            self.slots.release()

    def stop(self) -> None:
        self.stopping.set()
        if self.sock is not None:
            with contextlib.suppress(OSError):
                self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()


class Client:
    """The core's side (and the tests'): one request, one answer. Checks the server's user too."""

    def __init__(self, path: Path, *, expected_uid: int | None = None, timeout: float = 30.0) -> None:
        self.path, self.expected_uid, self.timeout = path, expected_uid, timeout

    def request(self, request: dict[str, Any]) -> dict[str, Any]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout)
            sock.connect(str(self.path))
            if self.expected_uid is not None and peer_uid(sock) != self.expected_uid:
                raise PermissionError("the messaging socket is not served by the engine's user")
            sock.sendall(json.dumps(request).encode() + b"\n")
            reader = sock.makefile("rb")
            line = reader.readline(4 * 1024 * 1024)
        answer = json.loads(line)
        if not isinstance(answer, dict):
            raise ValueError("unexpected answer")
        return answer
