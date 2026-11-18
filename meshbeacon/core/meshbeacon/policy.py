# SPDX-License-Identifier: Apache-2.0
"""Bounded recovery policy (ADR 0005, architecture §4.2).

Pure logic with an injectable clock, so that it can be tested exhaustively.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Timings:
    backoff_initial: float = 1.0
    backoff_max: float = 300.0
    breaker_failures: int = 5
    breaker_window: float = 15 * 60
    breaker_cooldown: float = 15 * 60
    breaker_max_openings: int = 3
    stable_after: float = 10 * 60
    starts_max: int = 5
    starts_window: float = 30 * 60
    status_interval: float = 10.0
    status_stall: float = 120.0
    heartbeat_max_age: float = 60.0
    stop_grace: float = 10.0
    prepare_timeout: float = 180.0
    report_interval: float = 30 * 60
    isolated_reminder: float = 6 * 60 * 60
    attention_reminder: float = 6 * 60 * 60
    resource_check: float = 10.0
    storage_check: float = 60 * 60
    cpu_window: float = 10 * 60
    cpu_threshold: float = 0.8


@dataclass
class RestartPolicy:
    """Decides when (and whether) to start the RNS child again after a transient failure.

    * Exponential back-off between attempts.
    * After ``breaker_failures`` failures within ``breaker_window`` the breaker opens: one more
      attempt is made after ``breaker_cooldown`` (half-open). A failure of that attempt opens it
      again.
    * After ``breaker_max_openings`` openings without a stable run, MeshBeacon gives up until the
      user restarts the app.
    * A run lasting ``stable_after`` resets everything (``record_stable``).
    """

    timings: Timings
    failures: list[float] = field(default_factory=list)
    consecutive: int = 0
    openings: int = 0
    open_until: float | None = None
    half_open: bool = False
    gave_up: bool = False

    def record_failure(self, now: float) -> None:
        self.consecutive += 1
        self.failures = [t for t in self.failures if now - t < self.timings.breaker_window] + [now]
        if self.half_open or len(self.failures) >= self.timings.breaker_failures:
            self.half_open = False
            self.openings += 1
            self.failures = []
            if self.openings >= self.timings.breaker_max_openings:
                self.gave_up = True
                self.open_until = None
            else:
                self.open_until = now + self.timings.breaker_cooldown

    def attempt_started(self) -> None:
        if self.open_until is not None:
            self.open_until = None
            self.half_open = True

    def record_stable(self) -> None:
        self.failures = []
        self.consecutive = 0
        self.openings = 0
        self.open_until = None
        self.half_open = False

    @property
    def breaker_open(self) -> bool:
        return self.open_until is not None

    def next_start(self, last_failure: float) -> float | None:
        """Earliest time for the next attempt, or None if MeshBeacon has given up."""
        if self.gave_up:
            return None
        if self.open_until is not None:
            return self.open_until
        delay = float(self.timings.backoff_initial * 2.0 ** max(self.consecutive - 1, 0))
        return last_failure + min(delay, self.timings.backoff_max)


@dataclass
class StartHistory:
    """Persisted record of app starts, used to detect whole-app restart loops."""

    timings: Timings
    starts: list[float] = field(default_factory=list)
    options_hash: str = ""

    @classmethod
    def from_json(cls, timings: Timings, value: Any) -> StartHistory:
        if not isinstance(value, dict):
            return cls(timings)
        starts = [float(t) for t in value.get("starts", []) if isinstance(t, (int, float))]
        return cls(timings, starts=starts, options_hash=str(value.get("options_hash", "")))

    def to_json(self) -> dict[str, Any]:
        return {"starts": self.starts, "options_hash": self.options_hash}

    def begin(self, now: float, options_hash: str) -> tuple[bool, float | None]:
        """Register a start. Returns (safe_mode, retry_after)."""
        if options_hash != self.options_hash:
            self.starts = []
            self.options_hash = options_hash
        self.starts = sorted(t for t in self.starts if 0 <= now - t < self.timings.starts_window)
        if len(self.starts) >= self.timings.starts_max - 1:
            retry_after = self.starts[0] + self.timings.starts_window
            return True, retry_after
        self.starts.append(now)
        return False, None

    def mark_stable(self) -> None:
        self.starts = []
