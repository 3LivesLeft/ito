# SPDX-License-Identifier: Apache-2.0
"""The MeshBeacon sidebar panel (ADR 0007).

A custom panel served by this integration: one plain JavaScript module with no third-party code,
no build step and no network requests of its own. It shows what the integration's entities already
hold and draws history from Home Assistant's own recorder, so nothing is collected or stored twice.

Exposure:

* The panel and its websocket command are for **administrators only** (``REQUIRE_ADMIN``).
* The module is a static file. Like every Home Assistant frontend file it can be fetched without
  logging in, so it contains no data: values reach the page only through Home Assistant's
  authenticated websocket connection.
* ``meshbeacon/panel`` returns only entity IDs and peer names for the integration's own entries;
  it reads nothing from the app and changes nothing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import probatio
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http.server import StaticPathConfig
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import require_admin, websocket_command
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from . import conversations
from .const import DOMAIN
from .coordinator import MeshBeaconConfigEntry
from .nodes import app_slug, node_key

PANEL_URL = DOMAIN  # /meshbeacon
STATIC_URL = f"/{DOMAIN}_panel"
FRONTEND = Path(__file__).parent / "frontend"
MODULE = "meshbeacon-panel.js"
ELEMENT = "meshbeacon-panel"
TITLE = "ito"
ICON = "mdi:earth"  # closest Material Design Icon to the ito mark (docs/branding.md)
REQUIRE_ADMIN = True
WS_TYPE = f"{DOMAIN}/panel"

_STATIC_DONE = f"{DOMAIN}_static_registered"


def _fingerprint() -> str:
    """Version tag for the module URL, so browsers never keep a stale copy after an update."""
    digest = hashlib.sha256()
    for path in sorted(p for p in FRONTEND.rglob("*") if p.is_file()):
        digest.update(path.relative_to(FRONTEND).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


async def async_setup_panel_support(hass: HomeAssistant) -> None:
    """Once per Home Assistant start: the static files and the websocket command."""
    if hass.data.get(_STATIC_DONE):
        return
    hass.data[_STATIC_DONE] = await hass.async_add_executor_job(_fingerprint)
    versioned_url = f"{STATIC_URL}/{hass.data[_STATIC_DONE]}"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(versioned_url, str(FRONTEND), True),
            StaticPathConfig(STATIC_URL, str(FRONTEND), False),
        ]
    )
    websocket_api.async_register_command(hass, ws_panel)
    conversations.async_register(hass)


async def async_show_panel(hass: HomeAssistant) -> None:
    """Add the sidebar entry (idempotent: a second MeshBeacon entry shares the same panel)."""
    if PANEL_URL in hass.data.get(frontend.DATA_PANELS, {}):
        return
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name=ELEMENT,
        sidebar_title=TITLE,
        sidebar_icon=ICON,
        module_url=f"{STATIC_URL}/{hass.data[_STATIC_DONE]}/{MODULE}",
        require_admin=REQUIRE_ADMIN,
        config={"domain": DOMAIN},
    )


@callback
def async_hide_panel_if_unused(hass: HomeAssistant, unloading: MeshBeaconConfigEntry) -> None:
    """Remove the sidebar entry when the last loaded MeshBeacon entry goes away."""
    others = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != unloading.entry_id and e.state is ConfigEntryState.LOADED
    ]
    if not others:
        frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)


def _node_summary(hass: HomeAssistant, entry: MeshBeaconConfigEntry) -> dict[str, Any]:
    """Map each enabled entity of ``entry`` to its role. Disabled entities are left out (they have
    no state or history), so the panel simply does not show them."""
    registry = er.async_get(hass)
    node = node_key(entry)
    coordinator = getattr(entry, "runtime_data", None)
    reported = {p.name.casefold(): p.name for p in coordinator.data.peers} if coordinator and coordinator.data else {}
    entities: dict[str, str] = {}
    peers: dict[str, dict[str, Any]] = {}
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        if item.disabled_by is not None or not item.translation_key or not item.unique_id.startswith(f"{node}_"):
            continue
        key = item.translation_key
        if not key.startswith("peer_"):
            entities[key] = item.entity_id
            continue
        role = key.removeprefix("peer_")
        prefix, suffix = f"{node}_peer_", f"_{role}"
        if not item.unique_id.endswith(suffix):
            continue
        folded = item.unique_id[len(prefix) : -len(suffix)]
        peer = peers.setdefault(
            folded, {"name": reported.get(folded, folded), "reported": folded in reported, "entities": {}}
        )
        peer["entities"][role] = item.entity_id
    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "app": app_slug(entry),
        "entities": entities,
        "peers": sorted(peers.values(), key=lambda p: (not p["reported"], p["name"].casefold())),
    }


@require_admin
@websocket_command({probatio.Required("type"): WS_TYPE})
@callback
def ws_panel(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
    """Which entities the panel should show, per loaded MeshBeacon entry. Read-only."""
    nodes = [
        _node_summary(hass, entry)
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    connection.send_result(msg["id"], {"nodes": nodes})
