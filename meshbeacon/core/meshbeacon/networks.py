# SPDX-License-Identifier: Apache-2.0
"""Public Reticulum network presets (ADR 0004), read from ``networks.json``.

A preset is data only: selecting one adds exactly one ``TCPClientInterface`` peer to the Reticulum
configuration, through the same validation and rendering path as the user's own peers. Nothing
here connects anywhere. ``custom`` (the default) adds nothing, so the defaults still make no
external connection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

CUSTOM = "custom"
_DATA = Path(__file__).with_name("networks.json")


@dataclass(frozen=True)
class Network:
    id: str
    name: str  # also the interface (peer) name shown in the log, the panel and the entities
    operator: str
    host: str
    port: int
    rules: str
    source: str
    documented_on: str
    release_checks_passed_on: str | None


@cache
def presets() -> dict[str, Network]:
    """The presets by id, in the order they are offered."""
    data = json.loads(_DATA.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("unsupported networks.json version")
    return {item["id"]: Network(**item) for item in data["networks"]}


def choices() -> tuple[str, ...]:
    """Every value the ``network`` option accepts: ``custom`` first, then the presets."""
    return (CUSTOM, *presets())
