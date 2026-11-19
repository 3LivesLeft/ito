# SPDX-License-Identifier: Apache-2.0
"""Engine settings and contacts (M4: a development-only file, D-M4-4).

``/data/messaging/messaging.json``, owned by the engine's user. In M4 there is no user-facing
option: messaging is absent from production images, and a test or developer writes this file.
The user-facing configuration arrives with M5. Every field is validated against an allow-list.

    {
      "display_name": "",                   # empty by default (ADR 0009); announced only if set
      "inbound": "contacts",                # "contacts" (default) or "anyone" (stamp cost applies)
      "stamp_cost": 8,                      # for "anyone": what strangers must spend (MS-9)
      "propagation_node": null,             # 32 hex characters, or null
      "retention_days": 0,                  # acknowledged content kept for 0 to 30 days
      "contacts": [{"id": "alice", "name": "Alice", "destination": "<32 hex characters>"}]
    }
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contract import CONTACT_ID

HEX_HASH = re.compile(r"^[0-9a-f]{32}$")
NAME = re.compile(r"^[^\x00-\x1f\x7f]{0,32}$")
MAX_CONTACTS = 100
STAMP_COST_RANGE = (0, 24)


class SettingsError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Contact:
    id: str
    name: str
    destination: str  # hex; never leaves the engine (MS-12)


@dataclass(frozen=True)
class Settings:
    display_name: str = ""
    inbound: str = "contacts"
    stamp_cost: int = 8
    propagation_node: str | None = None
    retention_days: int = 0
    contacts: tuple[Contact, ...] = field(default_factory=tuple)

    def contact(self, contact_id: str) -> Contact | None:
        return next((c for c in self.contacts if c.id == contact_id), None)

    def contact_for_destination(self, destination: str) -> Contact | None:
        return next((c for c in self.contacts if c.destination == destination), None)


def parse(raw: Any) -> Settings:
    problems: list[str] = []
    if not isinstance(raw, dict):
        raise SettingsError(["the settings must be an object"])
    known = {"display_name", "inbound", "stamp_cost", "propagation_node", "retention_days", "contacts"}
    problems += [f"unknown setting {k!r}" for k in sorted(set(raw) - known)]
    display = raw.get("display_name", "")
    if not isinstance(display, str) or not NAME.match(display):
        problems.append("display_name must be at most 32 printable characters")
    inbound = raw.get("inbound", "contacts")
    if inbound not in ("contacts", "anyone"):
        problems.append("inbound must be 'contacts' or 'anyone'")
    cost = raw.get("stamp_cost", 8)
    if isinstance(cost, bool) or not isinstance(cost, int) or not STAMP_COST_RANGE[0] <= cost <= STAMP_COST_RANGE[1]:
        problems.append("stamp_cost must be a whole number from 0 to 24")
    node = raw.get("propagation_node")
    if node is not None and (not isinstance(node, str) or not HEX_HASH.match(node)):
        problems.append("propagation_node must be 32 hex characters or null")
    retention = raw.get("retention_days", 0)
    if isinstance(retention, bool) or not isinstance(retention, int) or not 0 <= retention <= 30:
        problems.append("retention_days must be a whole number from 0 to 30")
    contacts: list[Contact] = []
    items = raw.get("contacts", [])
    if not isinstance(items, list) or len(items) > MAX_CONTACTS:
        problems.append(f"contacts must be a list of at most {MAX_CONTACTS}")
        items = []
    seen_ids: set[str] = set()
    seen_destinations: set[str] = set()
    for index, item in enumerate(items):
        where = f"contact {index + 1}"
        if not isinstance(item, dict) or set(item) - {"id", "name", "destination"}:
            problems.append(f"{where}: only id, name and destination are allowed")
            continue
        cid, name, dest = item.get("id"), item.get("name", ""), item.get("destination")
        if not isinstance(cid, str) or not CONTACT_ID.match(cid) or cid in seen_ids:
            problems.append(f"{where}: id must be unique, lower case, 1 to 32 of a-z 0-9 _ -")
            continue
        if not isinstance(name, str) or not NAME.match(name):
            problems.append(f"{where}: name must be at most 32 printable characters")
            continue
        if not isinstance(dest, str) or not HEX_HASH.match(dest) or dest in seen_destinations:
            problems.append(f"{where}: destination must be 32 unique hex characters")
            continue
        seen_ids.add(cid)
        seen_destinations.add(dest)
        contacts.append(Contact(cid, name, dest))
    if problems:
        raise SettingsError(problems)
    return Settings(display, inbound, cost, node, retention, tuple(contacts))


def load(path: Path) -> Settings:
    """The settings, or the defaults (no contacts) when the file does not exist."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Settings()
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise SettingsError(["the settings file is not valid JSON"]) from exc
    return parse(raw)
