# SPDX-License-Identifier: Apache-2.0
"""Redaction and rate limiting for everything written to the app log."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable

MAX_LINE = 1000
REDACTED = "<redacted>"

# RNS prints identity/destination hashes as <32 hex characters> (prettyhexrep). Redact those, any
# longer hex run (keys) and long base64 runs (keys encoded as base64).
# Any run of 32+ hex digits: covers RNS's <hash> form as well as bare hashes and keys.
_PATTERNS = (re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{32,}(?![0-9A-Fa-f])"),)
_BASE64 = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{43,}={0,2}")


def _looks_like_base64(match: re.Match[str]) -> str:
    text = match.group(0)
    # Encoded keys mix cases and digits; file paths and words do not.
    if any(c.isupper() for c in text) and any(c.islower() for c in text) and any(c.isdigit() for c in text):
        return REDACTED
    return text


class Redactor:
    def __init__(self, secrets: Iterable[str] = ()) -> None:
        self.secrets = tuple(sorted((s for s in secrets if s), key=len, reverse=True))

    def __call__(self, line: str) -> str:
        line = line.replace("\r", " ").replace("\x1b", " ")
        for secret in self.secrets:
            line = line.replace(secret, REDACTED)
        for pattern in _PATTERNS:
            line = pattern.sub(REDACTED, line)
        line = _BASE64.sub(_looks_like_base64, line)
        if len(line) > MAX_LINE:
            line = line[:MAX_LINE] + " …(truncated)"
        return line


class RateLimiter:
    """Token bucket: ``rate`` lines per second with a ``burst`` allowance."""

    def __init__(self, rate: float = 20.0, burst: float = 100.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.rate = rate
        self.burst = burst
        self.clock = clock
        self.tokens = burst
        self.last = clock()
        self.suppressed = 0

    def allow(self) -> bool:
        now = self.clock()
        self.tokens = min(self.burst, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        self.suppressed += 1
        return False

    def take_suppressed(self) -> int:
        count, self.suppressed = self.suppressed, 0
        return count
