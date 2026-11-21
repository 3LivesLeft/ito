# SPDX-License-Identifier: Apache-2.0
"""Narrow self-management operations for the app dashboard (ADR 0026).

Both the root socket relay and older Supervisor token transport use this same validation.
Only this app's options, sidebar entry and restart are reachable. No arbitrary proxy.
"""

from __future__ import annotations

import copy
import hashlib
import http.client
import json
import threading
import urllib.request
from collections.abc import Callable
from typing import Any

from .api import RelayLink, RelayRefusedError
from .settings import ALLOWED_TOP_LEVEL, ValidationError, parse_options

Request = Callable[[str, str, dict[str, Any] | None], tuple[int, dict[str, Any]]]
OPERATIONS = frozenset({"config_read", "config_save", "app_restart", "sidebar_enable"})
EDITABLE = ALLOWED_TOP_LEVEL - {"replace_identity"}


def revision(options: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()


def perform(request: dict[str, Any], call: Request) -> dict[str, Any]:
    """Validate before any write. Never return Supervisor errors containing options or secrets."""

    def api(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        status, answer = call(method, "/addons/self/" + path, payload)
        if status != 200 or answer.get("result") != "ok":
            raise OSError("Supervisor request failed")
        data = answer.get("data", {})
        if not isinstance(data, dict):
            raise OSError("Invalid Supervisor response")
        return data

    op = request.get("op")
    if op == "sidebar_enable" and set(request) == {"op"}:
        api("POST", "options", {"ingress_panel": True})
        return {"ok": True}
    if op == "app_restart" and set(request) == {"op"}:
        api("POST", "restart")
        return {"ok": True}
    if op not in {"config_read", "config_save"}:
        return {"ok": False, "error": "invalid"}
    raw = api("GET", "info").get("options")
    resolved = api("GET", "options/config")
    if not isinstance(raw, dict):
        raise OSError("Missing options")
    if op == "config_read":
        visible = copy.deepcopy(resolved)
        visible.pop("replace_identity", None)
        for peer in visible.get("peers", []):
            peer["has_passphrase"] = bool(peer.pop("passphrase", None))
        return {"ok": True, "options": visible, "revision": revision(raw)}
    patch = request.get("patch")
    if not isinstance(patch, dict) or set(patch) - EDITABLE:
        return {"ok": False, "error": "invalid"}
    if request.get("revision") != revision(raw):
        return {"ok": False, "error": "conflict"}
    raw_patch, resolved_patch = copy.deepcopy(patch), copy.deepcopy(patch)
    if isinstance(patch.get("peers"), list):
        for peers, original in ((raw_patch["peers"], raw), (resolved_patch["peers"], resolved)):
            for peer in peers:
                if not isinstance(peer, dict):
                    continue
                keep = peer.pop("keep_passphrase", None)
                if keep is not None:
                    match = next((p for p in original.get("peers", []) if p.get("name") == keep), None)
                    if match is None or "passphrase" in peer:
                        return {"ok": False, "error": "invalid"}
                    if "passphrase" in match:
                        peer["passphrase"] = match["passphrase"]
    try:
        parse_options({**resolved, **resolved_patch})
    except ValidationError as exc:
        return {"ok": False, "error": "validation", "problems": exc.problems}
    api("POST", "options", {"options": {**raw, **raw_patch}})
    return {"ok": True}


class AppControl:
    """Serialises dashboard changes. Credentials stay in this process and never reach browsers."""

    def __init__(self, relay: RelayLink | None, token: str | None, *, socket_mode: bool) -> None:
        self.relay = relay
        self.token = None if socket_mode or relay is not None else token
        self.lock = threading.Lock()

    def _call(self, method: str, path: str, payload: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
        if not self.token:
            raise OSError("No Supervisor connection")
        request = urllib.request.Request(
            "http://supervisor" + path,
            data=None if payload is None else json.dumps(payload).encode(),
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            value = json.loads(response.read(65536))
            if not isinstance(value, dict):
                raise OSError("Invalid Supervisor response")
            return response.status, value

    def request(self, request: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            try:
                if self.relay is not None:
                    return self.relay.request(request, timeout=40)
                return perform(request, self._call)
            except (OSError, ValueError, http.client.HTTPException, RelayRefusedError):
                return {"ok": False, "error": "unavailable"}
