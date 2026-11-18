# SPDX-License-Identifier: Apache-2.0
"""MeshBeacon: monitoring for the MeshBeacon Reticulum app (read-only; ADR 0006).

The integration polls the app's token-authenticated status interface on Home Assistant's internal
network. It is set up only through Supervisor discovery, never imports Reticulum, and offers no
way to control the node.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import MeshBeaconConfigEntry, MeshBeaconCoordinator
from .panel import async_hide_panel_if_unused, async_setup_panel_support, async_show_panel

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    await async_setup_panel_support(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MeshBeaconConfigEntry) -> bool:
    coordinator = MeshBeaconCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_show_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MeshBeaconConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data.clear_issues()
        async_hide_panel_if_unused(hass, entry)
    return unloaded
