# SPDX-License-Identifier: Apache-2.0
"""The core's supervision of the messaging engine (M4 WP4; MS-15).

Used only in a development image that carries messaging: production images contain no engine, no
``messaging`` service and no marker, and then this module does nothing at all (MS-1). It never
imports the engine or LXMF (MS-21) and never touches Reticulum: an engine that fails, hangs or is
killed is stopped and started again on its own, and Reticulum and the status API carry on.

- The engine starts once Reticulum is running and has reported its first status (its shared
  instance is then up), as the ``messaging`` s6 service under its own user, ``mb-lxmf``.
- Health: every 30 s, on a background thread, a ``status`` request over the engine's socket,
  which must be served by ``mb-lxmf``. Three missed answers in a row count as a hang.
- Restarts back off (10 s to 5 min). After five failures in 30 minutes messaging pauses until the
  app is restarted; nothing else is affected.
- Output reaches the app log through the core's redaction, like Reticulum's.
"""

from __future__ import annotations

import contextlib
import json
import socket
import struct
import subprocess
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

MARKER = Path("/etc/meshbeacon/messaging")  # only in the messaging development image
SOCKET = Path("/run/meshbeacon-messaging/engine.sock")
ENGINE_UID = 9102
BACKOFF = (10.0, 30.0, 60.0, 120.0, 300.0)
PAUSE_AFTER = 5
PAUSE_WINDOW = 1800.0
HEALTH_INTERVAL = 30.0
HEALTH_TIMEOUT = 5.0
HEALTH_MISSES = 3
STOP_GRACE = 10.0

MSG_PAUSED = (
    "⚠ Messaging stopped after repeated failures and is paused until the app is restarted. Reticulum is not affected."
)


class Process(Protocol):
    def poll(self) -> int | None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...


def probe(path: Path, expected_uid: int, timeout: float = HEALTH_TIMEOUT) -> bool:
    """One ``status`` request; True only for a well-formed answer from the engine's user."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(path))
            creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            if struct.unpack("3i", creds)[1] != expected_uid:
                return False  # not the engine: refuse to talk to it (peer check, both ways)
            sock.sendall(b'{"op": "status"}\n')
            answer = json.loads(sock.makefile("rb").readline(65536))
    except (OSError, ValueError):
        return False
    return isinstance(answer, dict) and answer.get("ok") is True


class EngineSupervisor:
    def __init__(
        self,
        start: Callable[[], Process],
        say: Callable[[str], None],
        clock: Callable[[], float],
        *,
        health: Callable[[], bool] | None = None,
    ) -> None:
        self._start = start
        self.say = say
        self.clock = clock
        self.health = health or (lambda: probe(SOCKET, ENGINE_UID))
        self.proc: Process | None = None
        self.state = "waiting"  # waiting | running | backoff | paused | stopped
        self.failures: deque[float] = deque()
        self.next_attempt = 0.0
        self.next_health = 0.0
        self.misses = 0
        self.lock = threading.Lock()
        self.probing = False
        self.result: bool | None = None

    @classmethod
    def enabled(cls, marker: Path = MARKER) -> bool:
        return marker.exists()

    # -- the core calls step() on every loop ---------------------------------------------------
    def step(self, node_ready: bool) -> None:
        now = self.clock()
        if self.state in ("paused", "stopped"):
            return
        if self.proc is not None:
            code = self.proc.poll()
            if code is not None:
                self.proc = None
                self._failed(f"Messaging stopped unexpectedly (exit code {code}).", now)
                return
            self._check_health(now)
            return
        if node_ready and now >= self.next_attempt:
            self._launch(now)

    def _launch(self, now: float) -> None:
        try:
            self.proc = self._start()
        except OSError:
            self._failed("Messaging could not be started.", now)
            return
        self.state = "running"
        self.misses = 0
        self.next_health = now + HEALTH_INTERVAL

    def _check_health(self, now: float) -> None:
        with self.lock:
            result, self.result = self.result, None
            probing = self.probing
        if result is not None:
            self.misses = 0 if result else self.misses + 1
            if self.misses >= HEALTH_MISSES:
                proc, self.proc = self.proc, None
                if proc is not None:
                    proc.kill()  # hung: no grace, and never a wait that would hold up the core
                self._failed("Messaging stopped responding and has been restarted.", now)
                return
        if not probing and now >= self.next_health:
            self.next_health = now + HEALTH_INTERVAL
            with self.lock:
                self.probing = True
            threading.Thread(target=self._probe, daemon=True).start()  # never blocks the core

    def _probe(self) -> None:
        ok = False
        with contextlib.suppress(Exception):
            ok = bool(self.health())
        with self.lock:
            self.result, self.probing = ok, False

    def _failed(self, reason: str, now: float) -> None:
        self.failures.append(now)
        while self.failures and self.failures[0] <= now - PAUSE_WINDOW:
            self.failures.popleft()
        self.say(f"⚠ {reason}")
        if len(self.failures) >= PAUSE_AFTER:
            self.state = "paused"
            self.say(MSG_PAUSED)
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
        """At shutdown, before Reticulum: the engine closes its queue and leaves cleanly."""
        self.state = "stopped"
        self._stop_process()

    def snapshot(self) -> dict[str, Any]:  # for tests and logs; never sent to Home Assistant
        return {"state": self.state, "recent_failures": len(self.failures)}
