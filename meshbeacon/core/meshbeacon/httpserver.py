# SPDX-License-Identifier: Apache-2.0
"""A small, bounded threading HTTP server for the internal health and status endpoints.

Three limits protect the core against floods and slow clients (v0.2 security review):

* at most ``max_concurrent`` connections are served at once; further connections are closed at
  once rather than queued, so threads and memory stay bounded;
* the handler's socket timeout limits how long a client may stay silent;
* an absolute ``deadline`` per connection, enforced by shutting the socket down, so a client that
  trickles one byte at a time cannot hold a slot for longer than the deadline.

Connection errors caused by clients are counted, never printed, so they cannot flood the log.
"""

from __future__ import annotations

import contextlib
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        *,
        max_concurrent: int,
        deadline: float,
    ) -> None:
        self.slots = threading.BoundedSemaphore(max_concurrent)
        self.deadline = deadline
        self.rejected = 0
        self.errors = 0
        super().__init__(address, handler)

    def handle_error(self, request: Any, client_address: Any) -> None:
        # The default prints a traceback to stderr, i.e. into the app log: a misbehaving client
        # (dropped connection, deadline expiry) could then flood the log. Count instead.
        self.errors += 1

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self.slots.acquire(blocking=False):
            self.rejected += 1
            self.shutdown_request(request)  # busy: close at once rather than queue
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        def expire() -> None:
            with contextlib.suppress(OSError):
                request.shutdown(socket.SHUT_RDWR)  # unblocks the handler's read or write

        timer = threading.Timer(self.deadline, expire)
        timer.daemon = True
        timer.start()
        try:
            super().process_request_thread(request, client_address)
        finally:
            timer.cancel()
            self.slots.release()
