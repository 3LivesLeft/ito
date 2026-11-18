# SPDX-License-Identifier: Apache-2.0
"""Supervisor-compatible health endpoint (architecture §4.4–§4.5, ADR 0005).

Answers ``200 ok`` whenever the core's main loop is responsive — including while Reticulum is
restarting or MeshBeacon is waiting for the user (``needs_attention``). It fails only when the
core is unresponsive, which is the one case a whole-app restart can fix. The response reveals
nothing about identities, peers or state.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler

from .httpserver import BoundedHTTPServer

# Bounds (v0.2 security review). Generous enough that the Supervisor's check, every 120 s, is served
# even while another client misbehaves; small enough that a flood cannot exhaust threads or memory.
HEALTH_MAX_CONCURRENT = 16
HEALTH_SOCKET_TIMEOUT = 5.0
HEALTH_DEADLINE = 5.0


class Heartbeat:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._last = clock()
        self._lock = threading.Lock()

    def beat(self) -> None:
        with self._lock:
            self._last = self.clock()

    def age(self) -> float:
        with self._lock:
            return self.clock() - self._last


def make_handler(heartbeat: Heartbeat, max_age: float) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "MeshBeacon"
        sys_version = ""
        timeout = HEALTH_SOCKET_TIMEOUT

        def do_GET(self) -> None:
            if self.path != "/health":
                self._send(404, b"not found\n")
            elif heartbeat.age() <= max_age:
                self._send(200, b"ok\n")
            else:
                self._send(503, b"unresponsive\n")

        def _send(self, code: int, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return  # never log requests

    return Handler


class HealthServer:
    def __init__(self, heartbeat: Heartbeat, host: str, port: int, max_age: float) -> None:
        self.httpd = BoundedHTTPServer(
            (host, port),
            make_handler(heartbeat, max_age),
            max_concurrent=HEALTH_MAX_CONCURRENT,
            deadline=HEALTH_DEADLINE,
        )
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="health", daemon=True)

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
