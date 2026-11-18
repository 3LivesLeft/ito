# SPDX-License-Identifier: Apache-2.0
"""Redacted diagnostics download. The key and host are removed, and peer names are replaced,
because diagnostics are often attached to public bug reports."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN
from .coordinator import MeshBeaconConfigEntry

TO_REDACT = {CONF_TOKEN, CONF_HOST}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: MeshBeaconConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    status: dict[str, Any] | None = None
    if coordinator.data is not None:
        data = coordinator.data
        peers = tuple(replace(p, name=f"peer {i + 1}") for i, p in enumerate(data.peers))
        status = asdict(replace(data, peers=peers, message="**REDACTED**" if data.message else None))
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "status": status,
    }
