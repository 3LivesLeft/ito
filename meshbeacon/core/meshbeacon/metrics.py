# SPDX-License-Identifier: Apache-2.0
"""Bounded, in-memory metrics for monitoring (v0.2, docs/research/v0.2-observability.md).

This is the only place where MeshBeacon computes metrics. The local API serves the snapshot built
here, and the Home Assistant integration only maps its fields to entities. History is kept by Home
Assistant's recorder, never here.

Everything is bounded: a fixed number of peers (validated settings, at most 10), at most
``RateWindow.MAX_SAMPLES`` samples per rate, and no per-packet or per-destination data. Values
that RNS does not provide are ``None`` ("unavailable"), never zero.

The snapshot never contains identity, destination or interface hashes, peer hosts, network names
or passphrases.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1
RATE_WINDOW = 60.0


class RateWindow:
    """Average rate of a monotonically increasing counter over a sliding window.

    A decrease means the counter was reset (Reticulum restarted), so the window starts again.
    """

    MAX_SAMPLES = 8

    def __init__(self, window: float = RATE_WINDOW) -> None:
        self.window = window
        self.samples: deque[tuple[float, float]] = deque(maxlen=self.MAX_SAMPLES)

    def add(self, now: float, value: float | None) -> None:
        if value is None:
            return
        if self.samples and value < self.samples[-1][1]:
            self.samples.clear()
        self.samples.append((now, value))
        while len(self.samples) > 2 and now - self.samples[1][0] >= self.window:
            self.samples.popleft()

    def reset(self) -> None:
        self.samples.clear()

    def rate(self) -> float | None:
        if len(self.samples) < 2:
            return None
        (t0, v0), (t1, v1) = self.samples[0], self.samples[-1]
        if t1 - t0 <= 0:
            return None
        return round((v1 - v0) / (t1 - t0), 3)


@dataclass
class PeerMetrics:
    name: str
    connected: bool = False
    connected_since: float | None = None
    reconnections: int = 0
    ever_connected: bool = False
    rx_bytes: int | None = None
    tx_bytes: int | None = None
    announces_rx: int | None = None
    announces_tx: int | None = None
    rx_rate: RateWindow = field(default_factory=RateWindow)
    tx_rate: RateWindow = field(default_factory=RateWindow)

    def disconnect(self) -> None:
        self.connected = False
        self.connected_since = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "connected": self.connected,
            "connected_since": self.connected_since,
            "rx_bytes": self.rx_bytes,
            "tx_bytes": self.tx_bytes,
            "rx_rate": self.rx_rate.rate(),
            "tx_rate": self.tx_rate.rate(),
            "announces_rx": self.announces_rx,
            "announces_tx": self.announces_tx,
            "reconnections": self.reconnections,
        }


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return max(int(value), 0)


def _sum(values: list[int | None]) -> int | None:
    known = [v for v in values if v is not None]
    return sum(known) if known else None


class Collector:
    """Turns the Reticulum child's status lines and /proc readings into a monitoring snapshot."""

    def __init__(
        self,
        peers: tuple[str, ...] = (),
        *,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self.clock = clock
        self.wall = wall
        self.app_started = wall()
        self.peers: dict[str, PeerMetrics] = {}
        self.configure(peers)
        self.reticulum_started: float | None = None
        self.transport: bool | None = None
        self.restarts = 0
        self.memory_restarts = 0
        self.node: dict[str, int | None] = {}
        self.rx_rate = RateWindow()
        self.tx_rate = RateWindow()
        self.cpu = RateWindow()
        self.core_memory: int | None = None
        self.reticulum_memory: int | None = None

    def configure(self, peers: tuple[str, ...]) -> None:
        self.peers = {name: self.peers.get(name) or PeerMetrics(name) for name in peers}

    # -- lifecycle of the Reticulum child --------------------------------------------------------
    def child_started(self) -> None:
        self.reticulum_started = self.wall()
        self._clear_runtime()

    def child_stopped(self) -> None:
        self.reticulum_started = None
        self.transport = None
        self._clear_runtime()

    def record_failure(self, *, memory: bool = False) -> None:
        """Count an automatic Reticulum restart (crash, stall or memory guard)."""
        self.restarts += 1
        if memory:
            self.memory_restarts += 1

    def _clear_runtime(self) -> None:
        self.node = {}
        self.rx_rate.reset()
        self.tx_rate.reset()
        self.reticulum_memory = None
        for peer in self.peers.values():
            peer.disconnect()
            peer.rx_bytes = peer.tx_bytes = peer.announces_rx = peer.announces_tx = None
            peer.rx_rate.reset()
            peer.tx_rate.reset()

    # -- inputs -------------------------------------------------------------------------------
    def update(self, status: dict[str, Any]) -> None:
        """Apply one status line from ``meshbeacon.node`` (already parsed JSON)."""
        now = self.clock()
        transport = status.get("transport")
        self.transport = transport if isinstance(transport, bool) else None
        self.node = {
            key: _int_or_none(status.get(key))
            for key in ("rxb", "txb", "packets_rx", "packets_tx", "paths", "relayed_links")
        }
        self.rx_rate.add(now, self.node["rxb"])
        self.tx_rate.add(now, self.node["txb"])
        seen: set[str] = set()
        for item in status.get("interfaces", []):
            if not isinstance(item, dict):
                continue
            peer = self.peers.get(str(item.get("name")))
            if peer is None or peer.name in seen:
                continue
            seen.add(peer.name)
            up = item.get("up") is True
            if up and not peer.connected:
                if peer.ever_connected:
                    peer.reconnections += 1
                peer.ever_connected = True
                peer.connected_since = self.wall()
            elif not up:
                peer.connected_since = None
            peer.connected = up
            peer.rx_bytes = _int_or_none(item.get("rxb"))
            peer.tx_bytes = _int_or_none(item.get("txb"))
            peer.announces_rx = _int_or_none(item.get("announces_rx"))
            peer.announces_tx = _int_or_none(item.get("announces_tx"))
            peer.rx_rate.add(now, peer.rx_bytes)
            peer.tx_rate.add(now, peer.tx_bytes)
        for name, peer in self.peers.items():
            if name not in seen:  # not reported by RNS: not connected, counters unavailable
                peer.disconnect()

    def resources(self, core_memory: int | None, reticulum_memory: int | None, cpu_seconds: float | None) -> None:
        """Record memory (RSS + swap, bytes) and total CPU seconds of the core and Reticulum."""
        self.core_memory = core_memory
        self.reticulum_memory = reticulum_memory
        self.cpu.add(self.clock(), cpu_seconds)

    # -- output -------------------------------------------------------------------------------
    def snapshot(self, app: dict[str, Any]) -> dict[str, Any]:
        peers = [p.as_dict() for p in self.peers.values()]
        cpu_rate = self.cpu.rate()
        memory = _sum([self.core_memory, self.reticulum_memory])
        return {
            "schema": SCHEMA_VERSION,
            "generated_at": round(self.wall(), 3),
            "app": {**app, "started_at": round(self.app_started, 3)},
            "node": {
                "running": self.reticulum_started is not None,
                "started_at": None if self.reticulum_started is None else round(self.reticulum_started, 3),
                "transport_enabled": self.transport,
                "restarts": self.restarts,
                "memory_restarts": self.memory_restarts,
            },
            "network": {
                "peers_configured": len(self.peers),
                "peers_connected": sum(1 for p in self.peers.values() if p.connected),
                "rx_bytes": self.node.get("rxb"),
                "tx_bytes": self.node.get("txb"),
                "rx_rate": self.rx_rate.rate(),
                "tx_rate": self.tx_rate.rate(),
                "packets_rx": self.node.get("packets_rx"),
                "packets_tx": self.node.get("packets_tx"),
                "paths": self.node.get("paths"),
                "relayed_links": self.node.get("relayed_links"),
                "announces_rx": _sum([p.announces_rx for p in self.peers.values()]),
                "announces_tx": _sum([p.announces_tx for p in self.peers.values()]),
            },
            "peers": peers,
            "resources": {
                "memory_bytes": memory,
                "core_memory_bytes": self.core_memory,
                "reticulum_memory_bytes": self.reticulum_memory,
                "cpu_percent": None if cpu_rate is None else round(cpu_rate * 100, 2),
            },
        }
