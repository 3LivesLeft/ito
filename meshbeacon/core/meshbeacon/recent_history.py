# SPDX-License-Identifier: Apache-2.0
"""Small, memory-only dashboard history: one day at five minutes, one week at one hour."""

from __future__ import annotations

from collections import deque
from typing import Any

FIELDS = {
    "receive_rate": ("network", "rx_rate", 1000),
    "send_rate": ("network", "tx_rate", 1000),
    "peers_connected": ("network", "peers_connected", 1),
    "known_paths": ("network", "paths", 1),
    "cpu": ("resources", "cpu_percent", 1),
    "memory": ("resources", "memory_bytes", 1048576),
}


class RecentHistory:
    def __init__(self) -> None:
        self.short: deque[tuple[int, dict[str, float | None]]] = deque(maxlen=288)
        self.long: deque[tuple[int, dict[str, float | None]]] = deque(maxlen=168)

    def add(self, snapshot: dict[str, Any], now: float) -> None:
        values = {}
        for key, (section, field, scale) in FIELDS.items():
            value = snapshot.get(section, {}).get(field)
            values[key] = value / scale if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        for samples, interval in ((self.short, 300), (self.long, 3600)):
            bucket = int(now // interval) * interval * 1000
            if not samples or samples[-1][0] != bucket:
                samples.append((bucket, values))

    def read(self, weekly: bool) -> dict[str, list[dict[str, Any]]]:
        samples = self.long if weekly else self.short
        return {key: [{"t": stamp, "v": values[key]} for stamp, values in samples] for key in FIELDS}
