# SPDX-License-Identifier: Apache-2.0
"""Read-only, token-authenticated local monitoring API and Supervisor discovery (ADR 0006).

* Started only when the ``home_assistant_integration`` option is on; otherwise no listener exists.
* Listens on a separate internal port from the watchdog's health endpoint, so that a flood of API
  requests can never starve ``/health``. No port is published.
* One endpoint, ``GET /api/v1/status``, which serves a snapshot that the core has already built.
  There are no write or control endpoints.
* Bounded: at most ``MAX_CONCURRENT`` requests at a time (others are closed at once), a socket
  timeout, GET only, no request bodies.
* The bearer token is 256 random bits, created in memory at every start, compared in constant
  time, never written to disk and never logged. It reaches Home Assistant only through Supervisor
  discovery, which only Home Assistant Core can read.
"""

from __future__ import annotations

import hmac
import json
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import fsutil

API_PATH = "/api/v1/status"
DISCOVERY_SERVICE = "meshbeacon"
SUPERVISOR_URL = "http://supervisor"
MAX_CONCURRENT = 4
SOCKET_TIMEOUT = 5.0


def new_token() -> str:
    return secrets.token_urlsafe(32)


class StatusStore:
    """Thread-safe holder of the latest serialised snapshot and the request counters."""

    def __init__(self, token: str) -> None:
        self._token = token.encode()
        self._lock = threading.Lock()
        self._body: bytes | None = None
        self.refused = 0
        self.served = 0

    def publish(self, snapshot: dict[str, Any]) -> None:
        body = json.dumps(snapshot, separators=(",", ":"), allow_nan=False).encode()
        with self._lock:
            self._body = body

    def body(self) -> bytes | None:
        with self._lock:
            return self._body

    def authorised(self, header: str | None) -> bool:
        scheme, _, presented = (header or "").partition(" ")
        ok = scheme.lower() == "bearer" and hmac.compare_digest(presented.strip().encode(), self._token)
        with self._lock:
            if ok:
                self.served += 1
            else:
                self.refused += 1
        return ok

    def take_refused(self) -> int:
        with self._lock:
            count, self.refused = self.refused, 0
            return count


def make_handler(store: StatusStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "MeshBeacon"
        sys_version = ""
        timeout = SOCKET_TIMEOUT

        def do_GET(self) -> None:
            if self.path != API_PATH:
                self._send(404, b'{"error":"not_found"}')
            elif not store.authorised(self.headers.get("Authorization")):
                self._send(401, b'{"error":"unauthorised"}', {"WWW-Authenticate": "Bearer"})
            elif (body := store.body()) is None:
                self._send(503, b'{"error":"starting"}')
            else:
                self._send(200, body)

        def _send(self, code: int, body: bytes, extra: dict[str, str] | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return  # never log requests (they carry the token)

    return Handler


class BoundedHTTPServer(ThreadingHTTPServer):
    """A threading HTTP server that serves at most ``max_concurrent`` connections at a time."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], max_concurrent: int) -> None:
        self.slots = threading.BoundedSemaphore(max_concurrent)
        super().__init__(address, handler)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)  # busy: close at once rather than queue
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class ApiServer:
    def __init__(self, store: StatusStore, host: str, port: int, max_concurrent: int = MAX_CONCURRENT) -> None:
        self.httpd = BoundedHTTPServer((host, port), make_handler(store), max_concurrent)
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="api", daemon=True)

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


# -- Supervisor discovery ------------------------------------------------------------------------
Opener = Callable[[urllib.request.Request, float], Any]


def _open(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - fixed http://supervisor URL


class Discovery:
    """Announces the API to Home Assistant through the Supervisor (no ``hassio_api`` needed).

    The UUID of the message (not secret) is remembered in ``state_path`` so that the message can be
    withdrawn when the user switches the integration option off.
    """

    def __init__(
        self,
        supervisor_token: str,
        state_path: Path,
        *,
        base_url: str = SUPERVISOR_URL,
        opener: Opener = _open,
        attempts: int = 3,
        timeout: float = 10.0,
        backoff: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._supervisor_token = supervisor_token
        self.state_path = state_path
        self.base_url = base_url
        self.opener = opener
        self.attempts = attempts
        self.timeout = timeout
        self.backoff = backoff
        self.sleep = sleep

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(  # noqa: S310 - fixed http://supervisor URL
            self.base_url + path,
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self._supervisor_token}", "Content-Type": "application/json"},
        )
        with self.opener(request, self.timeout) as response:
            raw = response.read(65536)
        value = json.loads(raw) if raw else {}
        return value if isinstance(value, dict) else {}

    def announce(self, host: str, port: int, api_token: str) -> bool:
        payload = {"service": DISCOVERY_SERVICE, "config": {"host": host, "port": port, "token": api_token}}
        for attempt in range(self.attempts):
            try:
                reply = self._request("POST", "/discovery", payload)
                uuid = (reply.get("data") or {}).get("uuid")
                if isinstance(uuid, str):
                    fsutil.atomic_write_json(self.state_path, {"uuid": uuid})
                return True
            except (OSError, ValueError, urllib.error.URLError):
                if attempt + 1 < self.attempts:
                    self.sleep(self.backoff * (attempt + 1))
        return False

    def withdraw(self) -> bool:
        """Remove a previously sent message, if one was recorded. True if nothing remains to do."""
        state = fsutil.read_json(self.state_path)
        uuid = state.get("uuid") if isinstance(state, dict) else None
        if not isinstance(uuid, str) or not uuid.isalnum():
            self.state_path.unlink(missing_ok=True)
            return True
        try:
            self._request("DELETE", f"/discovery/{uuid}")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:  # already gone counts as done
                return False
        except (OSError, ValueError):
            return False
        self.state_path.unlink(missing_ok=True)
        return True


def container_hostname() -> str:
    """The app's hostname on the Supervisor's internal network (slug with '-'), e.g. local-meshbeacon."""
    return socket.gethostname()
