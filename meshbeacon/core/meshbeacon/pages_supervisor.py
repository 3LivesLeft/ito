# SPDX-License-Identifier: Apache-2.0
"""The core's side of Nomad Network pages (v0.6.0, ADR 0027).

Built only when the app option ``pages_enabled`` is on. It never imports RNS or the pages service.

- **Content** is the core's (``pages.store``): editing works whether or not the service runs.
- **The service** (s6 ``pages``, user ``mb-nomad``) starts once Reticulum has reported its first
  status and is **stopped whenever Reticulum is not running**, so that the Nomad Network daemon
  never starts without ito's shared instance (ADR 0027 point 6). Health: every 10 s a ``sync``
  over its socket (served by ``mb-nomad`` only) that also carries the hosting switch and node name;
  three missed answers count as a hang. Restarts back off (10 s to 5 min); after five failures in
  30 minutes pages pause until the app restarts. Messaging and Reticulum are never touched.
- **The dashboard** reaches it through ``handle``: an allow-list of operations, writes limited to
  60 a minute, fetches to 30, everything else to 240.
- **Status** for the snapshot: states and counts only, never an address.
"""

from __future__ import annotations

import contextlib
import subprocess
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import procinfo
from .engine_supervisor import Process, Window, request
from .pages.store import Store

SOCKET = Path("/run/meshbeacon-pages/pages.sock")
PAGES_UID = 9103
BACKOFF = (10.0, 30.0, 60.0, 120.0, 300.0)
PAUSE_AFTER, PAUSE_WINDOW = 5, 1800.0
HEALTH_INTERVAL, HEALTH_TIMEOUT, HEALTH_MISSES = 10.0, 15.0, 3
FETCH_TIMEOUT = 40.0  # the service's own limit is 30 s; under the dashboard's 45 s deadline
STOP_GRACE = 10.0
STORE_OPS = frozenset(
    {
        "page_get",
        "page_save",
        "page_delete",
        "page_publish",
        "page_unpublish",
        "site_save",
        "hosting",
        "share_knowledge",
    }
    | {"bookmark_add", "bookmark_remove"}
)
WRITE_LIMIT, FETCH_LIMIT, READ_LIMIT = (60, 60.0), (30, 60.0), (240, 60.0)
MSG_PAUSED = (
    "Pages stopped after repeated failures and are paused until the app is restarted. Reticulum is not affected."
)
EXIT_REASONS = {3: "Pages could not start: Reticulum was not reachable."}
DISABLED: dict[str, Any] = {"enabled": False, "state": "disabled", "message": None}

Link = Callable[..., dict[str, Any] | None]


def link_request(payload: dict[str, Any], timeout: float = HEALTH_TIMEOUT) -> dict[str, Any] | None:
    return request(payload, SOCKET, PAGES_UID, timeout)


class PagesSupervisor:
    def __init__(
        self,
        start: Callable[[], Process],
        say: Callable[[str], None],
        clock: Callable[[], float],
        *,
        store: Store | None = None,
        log_level: str = "normal",
        link: Link | None = None,
    ) -> None:
        self._start = start
        self.say = say
        self.clock = clock
        self.store = store or Store()
        self.log_level = log_level
        self.link: Link = link or link_request
        self.proc: Process | None = None
        self.state = "waiting"  # waiting | running | backoff | paused | stopped
        self.failures: deque[float] = deque()
        self.next_attempt = 0.0
        self.next_health = 0.0
        self.misses = 0
        self.lock = threading.Lock()
        self.probing = False
        self.result: bool | None = None
        self.reason: str | None = None
        self.healthy = False
        self.view: dict[str, Any] = {}
        self.windows = {
            "write": Window(*WRITE_LIMIT, clock),
            "fetch": Window(*FETCH_LIMIT, clock),
            "read": Window(*READ_LIMIT, clock),
        }

    # -- supervision (core loop) -----------------------------------------------------------------
    def step(self, node_ready: bool) -> None:
        now = self.clock()
        if self.state in ("paused", "stopped"):
            return
        if not node_ready:
            if self.proc is not None:  # never without ito's shared instance (ADR 0027 point 6)
                self._stop_process()
                self.state, self.healthy = "waiting", False
            return
        if self.proc is not None:
            code = self.proc.poll()
            if code is not None:
                self.proc = None
                self._failed(EXIT_REASONS.get(code, f"Pages stopped unexpectedly (exit code {code})."), now)
                return
            self._check_health(now)
            return
        if now >= self.next_attempt:
            try:
                self.proc = self._start()
            except (OSError, KeyError):
                self._failed("Pages could not be started.", now)
                return
            self.state, self.misses, self.healthy = "running", 0, False
            self.next_health = now + 2.0

    def resync(self) -> None:
        """Send the hosting switch at the next step (after the dashboard changed it)."""
        self.next_health = 0.0

    def _check_health(self, now: float) -> None:
        with self.lock:
            result, self.result = self.result, None
            probing = self.probing
        if result is not None:
            self.misses = 0 if result else self.misses + 1
            if result:
                self.healthy, self.reason = True, None
            if self.misses >= HEALTH_MISSES:
                proc, self.proc = self.proc, None
                if proc is not None:
                    proc.kill()
                self._failed("Pages stopped responding and have been restarted.", now)
                return
        if not probing and now >= self.next_health:
            self.next_health = now + HEALTH_INTERVAL
            with self.lock:
                self.probing = True
            threading.Thread(target=self._probe, daemon=True).start()

    def sync_request(self) -> dict[str, Any]:
        self.store.sync_knowledge()
        hosting, name = self.store.hosting()
        return {"op": "sync", "hosting": hosting and bool(name), "node_name": name, "log_level": self.log_level}

    def _probe(self) -> None:
        ok = False
        with contextlib.suppress(Exception):
            answer = self.link(self.sync_request())
            ok = answer is not None and answer.get("ok") is True
            if ok and answer is not None:
                raw_hosting = answer.get("hosting")
                hosting: dict[str, Any] = raw_hosting if isinstance(raw_hosting, dict) else {}
                with self.lock:
                    self.view = {
                        "connected": answer.get("connected") is True,
                        "rpc_key": answer.get("rpc_key") if isinstance(answer.get("rpc_key"), bool) else None,
                        "hosting": {
                            "state": str(hosting.get("state") or "off"),
                            "message": hosting.get("message") if isinstance(hosting.get("message"), str) else None,
                            "address": hosting.get("address") if isinstance(hosting.get("address"), str) else None,
                            "memory_bytes": hosting.get("memory_bytes")
                            if isinstance(hosting.get("memory_bytes"), int)
                            else None,
                        },
                        "nodes_known": answer.get("nodes_known") if isinstance(answer.get("nodes_known"), int) else 0,
                    }
        with self.lock:
            self.result, self.probing = ok, False

    def _failed(self, reason: str, now: float) -> None:
        self.failures.append(now)
        while self.failures and self.failures[0] <= now - PAUSE_WINDOW:
            self.failures.popleft()
        self.reason, self.healthy = reason, False
        self.say(f"⚠ {reason}")
        if len(self.failures) >= PAUSE_AFTER:
            self.state = "paused"
            self.say(f"⚠ {MSG_PAUSED}")
            return
        self.state = "backoff"
        self.next_attempt = now + BACKOFF[min(len(self.failures) - 1, len(BACKOFF) - 1)]

    def _stop_process(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(STOP_GRACE)
        except subprocess.TimeoutExpired:
            proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(STOP_GRACE)

    def stop(self) -> None:
        """At shutdown, before Reticulum: the service stops the daemon and leaves cleanly."""
        self.state = "stopped"
        self._stop_process()

    def available(self) -> bool:
        return self.state == "running" and self.healthy

    # -- the dashboard (ingress thread) ----------------------------------------------------------
    def handle(self, req: Any) -> tuple[int, dict[str, Any]]:
        if not isinstance(req, dict) or not isinstance(req.get("op"), str):
            return 400, {"ok": False, "error": "invalid"}
        op = req["op"]
        if op == "overview":
            if not self.windows["read"].allow():
                return 429, {"ok": False, "error": "rate_limited"}
            return 200, self.overview()
        if op in STORE_OPS:
            if op != "page_get" and not self.windows["write"].allow():
                return 429, {"ok": False, "error": "rate_limited"}
            answer = self.store.handle(req)
            if answer.get("ok") and op in ("hosting", "site_save"):
                self.resync()
            return (200 if answer.get("ok") else 400), answer
        if op not in ("fetch", "nodes"):
            return 400, {"ok": False, "error": "invalid"}
        if not self.windows["fetch" if op == "fetch" else "read"].allow():
            return 429, {"ok": False, "error": "rate_limited"}
        if not self.available():
            return 503, {"ok": False, "error": "unavailable"}
        payload: dict[str, Any] = {"op": op}
        if op == "fetch":
            payload.update(address=req.get("address"), path=req.get("path"))
        reply = self.link(payload, timeout=FETCH_TIMEOUT if op == "fetch" else HEALTH_TIMEOUT)
        if reply is None:
            return 503, {"ok": False, "error": "unavailable"}
        return (200 if reply.get("ok") is True else 502 if op == "fetch" else 400), reply

    def overview(self) -> dict[str, Any]:
        """Everything the Pages tab shows (dashboard only: includes the node address)."""
        with self.lock:
            view = dict(self.view)
        address = (view.get("hosting") or {}).get("address")
        return {"ok": True, "service": self.public(view), "site": self.store.view(), "address": address}

    # -- status ----------------------------------------------------------------------------------
    def public(self, view: dict[str, Any] | None = None) -> dict[str, Any]:
        """The ``pages`` section of the status snapshot: states and counts, never an address."""
        if view is None:
            with self.lock:
                view = dict(self.view)
        hosting = view.get("hosting") or {}
        wanted, _name = self.store.hosting()
        if self.state == "paused":
            state, message = "paused", MSG_PAUSED
        elif self.state == "backoff":
            state, message = "error", f"{self.reason} ito will try again shortly."
        elif self.state == "running" and self.healthy and view.get("connected"):
            state, message = "running", None
        else:
            state, message = "starting", "Pages start once Reticulum is running."
        host_state = hosting.get("state", "off") if state == "running" else ("off" if not wanted else "waiting")
        memory = None
        pid = getattr(self.proc, "pid", None)
        if isinstance(pid, int) and pid > 0:
            memory = procinfo.memory_bytes(pid)
        if isinstance(memory, int) and isinstance(hosting.get("memory_bytes"), int):
            memory += hosting["memory_bytes"]
        return {
            "enabled": True,
            "state": state,
            "message": message,
            "hosting": wanted,
            "hosting_state": host_state,
            "hosting_message": hosting.get("message") if state == "running" else None,
            "nodes_known": view.get("nodes_known", 0),
            "memory_bytes": memory,
            "restarts": len(self.failures),
        }
