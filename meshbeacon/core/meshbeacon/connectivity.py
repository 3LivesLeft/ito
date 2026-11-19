# SPDX-License-Identifier: Apache-2.0
"""Network connectivity model — deliberately separate from process health (architecture §4.4)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Connectivity(StrEnum):
    ISOLATED = "isolated"
    OFFLINE = "offline"
    PARTIAL = "partial"
    ONLINE = "online"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Snapshot:
    state: Connectivity
    up: tuple[str, ...]
    configured: int
    rxb: int = 0
    txb: int = 0


def evaluate(configured: tuple[str, ...], status: dict[str, Any] | None) -> Snapshot:
    if not configured:
        return Snapshot(Connectivity.ISOLATED, (), 0)
    if status is None:
        return Snapshot(Connectivity.UNKNOWN, (), len(configured))
    wanted = set(configured)
    up = tuple(sorted(i["name"] for i in status.get("interfaces", []) if i.get("up") and i.get("name") in wanted))
    if not up:
        state = Connectivity.OFFLINE
    elif len(up) < len(configured):
        state = Connectivity.PARTIAL
    else:
        state = Connectivity.ONLINE
    return Snapshot(state, up, len(configured), int(status.get("rxb") or 0), int(status.get("txb") or 0))


def human_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "kB", "MB", "GB"):
        if value < 1000 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{value:.1f} GB"  # pragma: no cover


def describe(s: Snapshot) -> str:
    if s.state is Connectivity.ISOLATED:
        return (
            "⚠ MeshBeacon is running, but it is not connected to anyone. "
            "Add a peer in the Configuration tab to join a Reticulum network."
        )
    if s.state is Connectivity.OFFLINE:
        return (
            "⚠ MeshBeacon is running, but cannot reach any of your peers. Check your internet "
            "connection and the peer details. It will keep trying automatically."
        )
    if s.state is Connectivity.UNKNOWN:
        return "Waiting for Reticulum to report its connection status…"
    names = ", ".join(s.up)
    if s.state is Connectivity.PARTIAL:
        return f"Connected to {len(s.up)} of {s.configured} peers ({names}). Your node is online."
    return (
        f"Connected to {names}. Your node is online."
        if s.configured == 1
        else (f"Connected to all {s.configured} peers ({names}). Your node is online.")
    )
