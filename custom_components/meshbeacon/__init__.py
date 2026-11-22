# SPDX-License-Identifier: Apache-2.0
"""MeshBeacon: monitoring and LXMF messaging for the MeshBeacon Reticulum app (ADRs 0006, 0024).

The integration polls the app's token-authenticated status interface on Home Assistant's internal
network. It is set up only through Supervisor discovery, never imports Reticulum, and offers no
way to control the node. With LXMF messaging on, administrators can read and send messages in the
panel's Messages view (conversations.py); that is the only write path, and it reaches contacts only.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .compatibility import has_app_dashboard
from .const import CONF_APP_SLUG, CONF_NODE_KEY, DOMAIN, ENTRY_KEYS, ENTRY_VERSION
from .coordinator import MeshBeaconConfigEntry, MeshBeaconCoordinator
from .panel import async_hide_panel_if_unused, async_setup_panel_support, async_show_panel

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    await async_setup_panel_support(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Version 1 → 2: keep the node's identity apart from the app's slug (nodes.py).

    Both new values are the old unique ID, so every entity keeps its unique ID, entity ID and
    history. A newer entry (written by a later version of this integration) is refused rather than
    guessed at: going back is done by restoring a backup (docs/marketplace.md).
    """
    if entry.version > ENTRY_VERSION:
        _LOGGER.error("This ito entry was written by a newer version of the integration; update it")
        return False
    if entry.version == 1:
        old = entry.unique_id or entry.entry_id
        data = {k: v for k, v in entry.data.items() if k in ENTRY_KEYS}
        data.setdefault(CONF_NODE_KEY, old)
        data.setdefault(CONF_APP_SLUG, entry.unique_id or old)
        hass.config_entries.async_update_entry(entry, data=data, version=2, minor_version=1)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MeshBeaconConfigEntry) -> bool:
    integration = await async_get_integration(hass, DOMAIN)
    coordinator = MeshBeaconCoordinator(hass, entry, str(integration.version) if integration.version else None)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_show_panel(hass, app_dashboard=has_app_dashboard(coordinator.data.version))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MeshBeaconConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data.messaging.close()
        entry.runtime_data.clear_issues()
        async_hide_panel_if_unused(hass, entry)
    return unloaded
