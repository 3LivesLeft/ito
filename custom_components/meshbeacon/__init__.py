# SPDX-License-Identifier: Apache-2.0
"""MeshBeacon: monitoring for the MeshBeacon Reticulum app (read-only; ADR 0006).

The integration polls the app's token-authenticated status interface on Home Assistant's internal
network. It is set up only through Supervisor discovery, never imports Reticulum, and offers no
way to control the node.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import MeshBeaconConfigEntry, MeshBeaconCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: MeshBeaconConfigEntry) -> bool:
    coordinator = MeshBeaconCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MeshBeaconConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data.clear_issues()
    return unloaded
