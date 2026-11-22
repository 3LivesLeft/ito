# SPDX-License-Identifier: Apache-2.0
"""Bundled dashboard, accessible only through Home Assistant Supervisor Ingress."""

from __future__ import annotations

import contextlib
import hashlib
import json
import mimetypes
import re
import secrets
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import fsutil, networks
from .app_control import AppControl
from .httpserver import BoundedHTTPServer
from .recent_history import RecentHistory

ASSETS = Path("/usr/share/meshbeacon/frontend")
MAX_BODY = 65536


class Dashboard:
    def __init__(
        self,
        control: AppControl,
        messaging: Callable[[Any], tuple[int, dict[str, Any]]],
        assets: Path = ASSETS,
        *,
        pages: Callable[[Any], tuple[int, dict[str, Any]]] | None = None,
    ) -> None:
        self.control = control
        self.messaging = messaging
        self.pages = pages or (lambda _request: (409, {"ok": False, "error": "disabled"}))
        self.assets = assets
        digest = hashlib.sha256()
        for path in sorted(assets.rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(assets).as_posix().encode())
                digest.update(path.read_bytes())
        self.build = digest.hexdigest()[:20]
        self.instance = secrets.token_hex(16)
        self.lock = threading.Lock()
        self.snapshot: dict[str, Any] = {}
        self.history = RecentHistory()
        self.restarting = False
        self.restart_error = False
        self.last_write = 0.0

    def publish(self, snapshot: dict[str, Any]) -> None:
        with self.lock:
            self.snapshot = snapshot
            self.history.add(snapshot, time.time())

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {
                "snapshot": self.snapshot,
                "build": self.build,
                "instance": self.instance,
                "restart_error": self.restart_error,
            }

    def configure(self, request: Any) -> tuple[int, dict[str, Any]]:
        if not isinstance(request, dict) or request.get("op") not in {"config_save", "app_restart"}:
            return 400, {"ok": False, "error": "invalid"}
        with self.lock:
            if self.restarting or (request["op"] == "config_save" and time.monotonic() - self.last_write < 2):
                return 429, {"ok": False, "error": "busy"}
            self.last_write = time.monotonic()
            if request["op"] == "app_restart":
                self.restarting = True
                self.restart_error = False
                # Respond before Supervisor stops this container. Never block the health loop.
                timer = threading.Timer(0.5, self.restart)
                timer.daemon = True
                timer.start()
                return 202, {"ok": True}
        answer = self.control.request(request)
        return (200 if answer.get("ok") else 409 if answer.get("error") == "conflict" else 400), answer

    def restart(self) -> None:
        answer = self.control.request({"op": "app_restart"})
        with self.lock:
            self.restart_error = not answer.get("ok", False)
            self.restarting = False

    def add_sidebar(self, marker: Path) -> None:
        # Once per installation: respect a user's subsequent choice to hide the sidebar entry.
        if marker.exists():
            return
        for attempt in range(4):
            if self.control.request({"op": "sidebar_enable"}).get("ok"):
                # Sidebar is usable even if the marker cannot yet be written.
                with contextlib.suppress(OSError):
                    fsutil.atomic_write_json(marker, {"enabled": True})
                return
            time.sleep(min(2**attempt, 8))


class IngressServer:
    def __init__(
        self, dashboard: Dashboard, host: str = "0.0.0.0", port: int = 8097, *, allowed_peer: str = "172.30.32.2"
    ) -> None:
        class Handler(BaseHTTPRequestHandler):
            server_version = "ito"
            sys_version = ""

            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(10)

            def log_message(self, fmt: str, *args: Any) -> None:
                pass  # URLs contain ingress sessions; never log requests or message bodies.

            def send(
                self, status: int, body: bytes, content_type: str = "application/json", *, immutable: bool = False
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=31536000, immutable" if immutable else "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                    "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
                    "frame-ancestors 'self'; base-uri 'none'; form-action 'none'",
                )
                self.end_headers()
                self.wfile.write(body)

            def answer(self, status: int, body: dict[str, Any]) -> None:
                self.send(status, json.dumps(body, ensure_ascii=False).encode())

            def allowed(self) -> bool:
                groups = self.headers.get("X-Remote-User-Groups", "").split(",")
                if self.client_address[0] == allowed_peer and "system-admin" in groups:
                    return True
                self.answer(403, {"ok": False, "error": "forbidden"})
                return False

            def do_GET(self) -> None:
                if not self.allowed():
                    return
                path = urlsplit(self.path).path
                if path == "/api/status":
                    self.answer(200, dashboard.status())
                elif path == "/api/history":
                    with dashboard.lock:
                        values = dashboard.history.read(urlsplit(self.path).query == "range=7d")
                    self.answer(200, {"values": values})
                elif path == "/api/config":
                    answer = dashboard.control.request({"op": "config_read"})
                    answer["networks"] = [
                        {"id": n.id, "name": n.name, "rules": n.rules} for n in networks.presets().values()
                    ]
                    self.answer(200 if answer.get("ok") else 503, answer)
                elif path == "/":
                    prefix = self.headers.get("X-Ingress-Path", "")
                    if not re.fullmatch(r"/api/hassio_ingress/[A-Za-z0-9_-]+", prefix):
                        prefix = "."
                    html = (
                        (
                            '<!doctype html><html lang="en"><meta charset="utf-8">'
                            '<meta name="viewport" content="width=device-width,initial-scale=1">'
                            '<title>ito</title><link rel="stylesheet" href="PREFIX/assets/BUILD/page.css">'
                            "<body><ito-dashboard></ito-dashboard>"
                            '<script type="module" src="PREFIX/assets/BUILD/ingress.js"></script></body></html>'
                        )
                        .replace("BUILD", dashboard.build)
                        .replace("PREFIX", prefix)
                    )
                    self.send(200, html.encode(), "text/html; charset=utf-8")
                elif path.startswith(f"/assets/{dashboard.build}/"):
                    relative = path.removeprefix(f"/assets/{dashboard.build}/")
                    asset = dashboard.assets / relative
                    if (
                        not asset.resolve().is_relative_to(dashboard.assets.resolve())
                        or ".." in relative.split("/")
                        or not asset.is_file()
                        or asset.is_symlink()
                        or asset.suffix not in {".js", ".css", ".woff2", ".svg", ".png"}
                    ):
                        self.answer(404, {"ok": False, "error": "not_found"})
                    else:
                        self.send(
                            200,
                            asset.read_bytes(),
                            mimetypes.guess_type(asset.name)[0] or "application/octet-stream",
                            immutable=True,
                        )
                else:
                    self.answer(404, {"ok": False, "error": "not_found"})

            def do_POST(self) -> None:
                if not self.allowed():
                    return
                if (
                    self.headers.get("X-Ito-Request") != "1"
                    or self.headers.get("Content-Type") != "application/json"
                    or self.headers.get("Transfer-Encoding")
                ):
                    self.answer(403, {"ok": False, "error": "forbidden"})
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    limit = 32768 if self.path == "/api/config" else MAX_BODY
                    if not 0 < size <= limit:
                        raise ValueError
                    request = json.loads(self.rfile.read(size))
                except (ValueError, UnicodeError):
                    self.answer(400, {"ok": False, "error": "invalid"})
                    return
                if self.path == "/api/config":
                    status, answer = dashboard.configure(request)
                elif self.path == "/api/messaging":
                    status, answer = dashboard.messaging(request)
                elif self.path == "/api/pages":
                    status, answer = dashboard.pages(request)
                else:
                    status, answer = 404, {"ok": False, "error": "not_found"}
                self.answer(status, answer)

        self.server = BoundedHTTPServer((host, port), Handler, max_concurrent=8, deadline=45)
        self.thread = threading.Thread(target=self.server.serve_forever, name="ingress", daemon=True)
        self.port = self.server.server_port

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
