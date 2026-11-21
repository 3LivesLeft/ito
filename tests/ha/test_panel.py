# SPDX-License-Identifier: Apache-2.0
"""The MeshBeacon sidebar panel (ADR 0007): registration, exposure, entity mapping and lifecycle."""

from __future__ import annotations

from pathlib import Path

import yarl
from homeassistant.components import frontend
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.meshbeacon import panel
from custom_components.meshbeacon.const import DOMAIN

from .conftest import TOKEN, URL
from .fixtures import snapshot

FRONTEND = Path(panel.__file__).parent / "frontend"


async def _set_up(hass: HomeAssistant, mock_entry, aioclient_mock, **changes):
    aioclient_mock.get(URL, json=snapshot(**changes))
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()


async def test_sidebar_entry_is_registered_for_admins_only(hass, mock_entry, aioclient_mock):
    await _set_up(hass, mock_entry, aioclient_mock)
    registered = hass.data[frontend.DATA_PANELS][panel.PANEL_URL]
    assert registered.sidebar_title == "ito"
    assert registered.sidebar_icon == "mdi:earth"
    assert registered.require_admin is True
    custom = registered.config["_panel_custom"]
    assert custom["name"] == "meshbeacon-panel"
    assert custom["embed_iframe"] is False  # same page, so Home Assistant's theme applies
    assert custom["trust_external"] is False
    assert custom["module_url"].startswith("/meshbeacon_panel/meshbeacon-panel.js?v=")
    assert TOKEN not in str(registered.config)


async def test_module_is_served_and_holds_no_data(hass, hass_client, mock_entry, aioclient_mock):
    await _set_up(hass, mock_entry, aioclient_mock)
    client = await hass_client()
    for name in (
        "meshbeacon-panel.js",
        "model.js",
        "tokens.js",
        "fonts.js",
        "brand-mark.js",
        "ui/controller.js",
        "ui/views.js",
        "ui/components.js",
        "ui/style.js",
        "ui/dom.js",
        "sources/hass.js",
        "sources/messaging.js",
        "sources/snapshot.js",
        "ui/messages.js",
    ):
        response = await client.get(f"/meshbeacon_panel/{name}")
        assert response.status == 200
        assert "javascript" in response.headers["Content-Type"]
        body = await response.text()
        assert body == (FRONTEND / name).read_text()
        for secret in (TOKEN, "Emerald", "local-meshbeacon", "ab" * 32):
            assert secret not in body
    # Only the frontend folder is served: nothing else of the integration's files, no listing.
    for path in ("%2e%2e/manifest.json", "..%2fmanifest.json", "%2e%2e/client.py", "..%2fclient.py", ""):
        response = await client.get(yarl.URL(f"/meshbeacon_panel/{path}", encoded=True))
        body = await response.text()
        assert '"domain": "meshbeacon"' not in body and "MeshBeaconClient" not in body, path
        assert response.status in (400, 403, 404), (path, response.status)


async def test_bundled_fonts_are_served_locally(hass, hass_client, mock_entry, aioclient_mock):
    await _set_up(hass, mock_entry, aioclient_mock)
    client = await hass_client()
    for weight in (400, 500, 600, 700):
        response = await client.get(f"/meshbeacon_panel/fonts/inter-5.3.0/inter-latin-{weight}-normal.woff2")
        assert response.status == 200
        assert (await response.read())[:4] == b"wOF2"


async def test_brand_images_are_served_by_home_assistant(hass, hass_client, mock_entry, aioclient_mock):
    """Local brand images (custom_components/meshbeacon/brand, Home Assistant 2026.3+)."""
    from homeassistant.setup import async_setup_component

    await _set_up(hass, mock_entry, aioclient_mock)
    assert await async_setup_component(hass, "brands", {})
    client = await hass_client()
    for image in ("icon.png", "dark_icon.png", "logo.png", "dark_logo.png", "icon@2x.png", "logo@2x.png"):
        response = await client.get(f"/api/brands/integration/meshbeacon/{image}")
        assert response.status == 200, image
        body = await response.read()
        assert body[:8] == b"\x89PNG\r\n\x1a\n", image
        assert body == (Path(panel.__file__).parent / "brand" / image).read_bytes()


async def test_websocket_maps_entities_and_peers(hass, hass_ws_client, mock_entry, aioclient_mock):
    await _set_up(hass, mock_entry, aioclient_mock)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "meshbeacon/panel"})
    result = await ws.receive_json()
    assert result["success"], result
    (node,) = result["result"]["nodes"]
    assert node["app"] == "local_meshbeacon"
    e = node["entities"]
    assert e["known_paths"] == "sensor.ito_known_paths"
    assert e["relayed_links"] == "sensor.ito_links_relayed_for_others"
    assert e["transport_mode"].startswith("binary_sensor.")
    assert "packets_received" not in e  # disabled by default: no state, so not offered
    (peer,) = node["peers"]
    assert peer["name"] == "Emerald"
    assert peer["reported"] is True
    assert peer["entities"]["connected"] == "binary_sensor.ito_emerald_connected"
    assert "receive_rate" not in peer["entities"]
    assert TOKEN not in str(result)
    for entity_id in [*e.values(), *peer["entities"].values()]:
        assert hass.states.get(entity_id) is not None


async def test_websocket_follows_enabled_entities_and_removed_peers(hass, hass_ws_client, mock_entry, aioclient_mock):
    await _set_up(hass, mock_entry, aioclient_mock)
    registry = er.async_get(hass)
    rate = registry.async_get("sensor.ito_emerald_receive_rate")
    assert rate is not None and rate.disabled_by is not None
    registry.async_update_entity(rate.entity_id, disabled_by=None)
    await hass.async_block_till_done()
    coordinator = mock_entry.runtime_data
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=snapshot(peers=[], network__peers_configured=0))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "meshbeacon/panel"})
    (node,) = (await ws.receive_json())["result"]["nodes"]
    (peer,) = node["peers"]
    assert peer["reported"] is False  # still has entities, no longer reported by the app
    assert peer["name"] == "emerald"  # the original spelling is no longer known
    assert peer["entities"]["receive_rate"] == "sensor.ito_emerald_receive_rate"


async def test_websocket_refuses_non_admins(
    hass, hass_ws_client, hass_read_only_access_token, mock_entry, aioclient_mock
):
    await _set_up(hass, mock_entry, aioclient_mock)
    ws = await hass_ws_client(hass, hass_read_only_access_token)
    await ws.send_json({"id": 1, "type": "meshbeacon/panel"})
    result = await ws.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "unauthorized"


async def test_panel_goes_with_the_last_entry_and_returns(hass, mock_entry, aioclient_mock):
    await _set_up(hass, mock_entry, aioclient_mock)
    assert panel.PANEL_URL in hass.data[frontend.DATA_PANELS]
    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert panel.PANEL_URL not in hass.data[frontend.DATA_PANELS]
    # Reload: static paths are registered once per start, so setting up again must not fail.
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert panel.PANEL_URL in hass.data[frontend.DATA_PANELS]


async def test_no_panel_without_a_loaded_entry(hass, mock_entry, aioclient_mock):
    aioclient_mock.get(URL, json=snapshot(schema=2))  # set-up fails cleanly
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert panel.PANEL_URL not in hass.data.get(frontend.DATA_PANELS, {})
    assert hass.config_entries.async_entries(DOMAIN)[0].state.recoverable


def test_module_url_changes_with_the_files(tmp_path, monkeypatch):
    for name in ("meshbeacon-panel.js", "model.js", "tokens.js"):
        (tmp_path / name).write_text((FRONTEND / name).read_text())
    monkeypatch.setattr(panel, "FRONTEND", tmp_path)
    before = panel._fingerprint()
    (tmp_path / "model.js").write_text("// changed\n")
    assert panel._fingerprint() != before
