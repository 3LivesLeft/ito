# SPDX-License-Identifier: Apache-2.0
"""Config entry version 2: a stable node key, apart from the app's slug (M1, nodes.py).

What must hold for the later move from the local app to the published app (D8): entity unique IDs,
entity IDs and history do not depend on the slug, and an existing v0.2 installation migrates
without any visible change.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_HASSIO, ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.meshbeacon.const import DOMAIN, ENTRY_KEYS
from custom_components.meshbeacon.diagnostics import async_get_config_entry_diagnostics

from .conftest import CERT, HOST, PORT, TOKEN, URL, snapshot

PUBLISHED = "ce27fbb5_meshbeacon"  # the slug of the app installed from this repository's URL


async def test_v1_entry_migrates_without_changing_any_entity(hass, mock_entry, aioclient_mock):
    """An existing v0.2 installation: entities registered by the v1 code keep their IDs."""
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor", DOMAIN, "local_meshbeacon_status", config_entry=mock_entry, suggested_object_id="meshbeacon_status"
    )
    renamed = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "local_meshbeacon_peer_test peer_rx_bytes",
        config_entry=mock_entry,
        suggested_object_id="my_custom_name",
    )
    before = len(er.async_entries_for_config_entry(registry, mock_entry.entry_id))
    assert mock_entry.version == 1
    aioclient_mock.get(URL, json=snapshot())
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_entry.version == 2
    assert mock_entry.data["node_key"] == "local_meshbeacon"
    assert mock_entry.data["app_slug"] == "local_meshbeacon"
    assert mock_entry.unique_id == "local_meshbeacon"
    assert registry.async_get(old.entity_id).unique_id == "local_meshbeacon_status"
    assert registry.async_get(renamed.entity_id).entity_id == "sensor.my_custom_name"  # user's ID kept
    assert hass.states.get(old.entity_id).state == "running"  # the existing ID, not a new ito_ one
    after = er.async_entries_for_config_entry(registry, mock_entry.entry_id)
    assert all(item.unique_id.startswith("local_meshbeacon_") for item in after)
    assert len({item.unique_id for item in after}) == len(after) >= before  # no duplicates


async def test_v1_migration_keeps_the_device_and_its_user_settings(hass, mock_entry, aioclient_mock):
    """M1.2 (review L-6): the device registered by the v1 code is the one the v2 code uses. Its ID,
    the user's name and area, and the link from every entity to it survive the migration."""
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    old_device = devices.async_get_or_create(
        config_entry_id=mock_entry.entry_id, identifiers={(DOMAIN, "local_meshbeacon")}, name="MeshBeacon"
    )
    devices.async_update_device(old_device.id, name_by_user="Loft node", area_id="loft")
    status = entities.async_get_or_create(
        "sensor",
        DOMAIN,
        "local_meshbeacon_status",
        config_entry=mock_entry,
        device_id=old_device.id,
        suggested_object_id="meshbeacon_status",
    )
    aioclient_mock.get(URL, json=snapshot())
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_entry.version == 2
    mine = dr.async_entries_for_config_entry(devices, mock_entry.entry_id)
    assert [d.id for d in mine] == [old_device.id]  # no second device
    device = devices.async_get(old_device.id)
    assert device.identifiers == {(DOMAIN, "local_meshbeacon")}
    assert device.name_by_user == "Loft node" and device.area_id == "loft"
    for item in er.async_entries_for_config_entry(entities, mock_entry.entry_id):
        assert item.device_id == old_device.id, item.entity_id
    assert entities.async_get(status.entity_id).device_id == old_device.id


async def test_entities_follow_the_node_key_not_the_app_slug(hass, entry_data, aioclient_mock):
    """After a future move the entry talks to another app, but every entity stays the same."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=PUBLISHED,
        version=2,
        data={**entry_data, "host": PUBLISHED.replace("_", "-"), "node_key": "local_meshbeacon", "app_slug": PUBLISHED},
        title="MeshBeacon",
    )
    entry.add_to_hass(hass)
    aioclient_mock.get(f"https://{PUBLISHED.replace('_', '-')}:{PORT}/api/v1/status", json=snapshot())
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    items = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert items and all(item.unique_id.startswith("local_meshbeacon_") for item in items)
    assert not any(item.unique_id.startswith(PUBLISHED) for item in items)
    assert hass.states.get("sensor.ito_status").state == "running"


async def test_key_refresh_matches_the_app_slug_after_a_move(
    hass, entry_data, aioclient_mock, freezer: FrozenDateTimeFactory
):
    host = PUBLISHED.replace("_", "-")
    url = f"https://{host}:{PORT}/api/v1/status"
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=PUBLISHED,
        version=2,
        data={**entry_data, "host": host, "node_key": "local_meshbeacon", "app_slug": PUBLISHED},
        title="MeshBeacon",
    )
    entry.add_to_hass(hass)
    aioclient_mock.get(url, json=snapshot())
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    new = "N" * 43

    def restarted():
        aioclient_mock.clear_requests()
        aioclient_mock.get(url, json=snapshot())

    messages = [
        SimpleNamespace(
            addon="local_meshbeacon",
            service=DOMAIN,
            config={"host": HOST, "port": PORT, "token": "O" * 43, "cert_sha256": CERT},
        ),
        SimpleNamespace(
            addon=PUBLISHED, service=DOMAIN, config={"host": host, "port": PORT, "token": new, "cert_sha256": CERT}
        ),
    ]

    async def list_messages():
        restarted()
        return messages

    aioclient_mock.clear_requests()
    aioclient_mock.get(url, status=401)
    with patch(
        "homeassistant.components.hassio.get_supervisor_client",
        return_value=SimpleNamespace(discovery=SimpleNamespace(list=list_messages)),
    ):
        freezer.tick(timedelta(seconds=61))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert entry.data["token"] == new  # from the current app, never from the old local one
    assert entry.data["node_key"] == "local_meshbeacon"


async def test_an_entry_from_a_newer_integration_is_refused(hass, entry_data):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="local_meshbeacon", version=3, data=entry_data)
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_migration_drops_unknown_keys(hass, entry_data, aioclient_mock):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="local_meshbeacon", version=1, data={**entry_data, "messaging_key": "M" * 43}
    )
    entry.add_to_hass(hass)
    aioclient_mock.get(URL, json=snapshot())
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert set(entry.data) <= ENTRY_KEYS
    assert "messaging_key" not in entry.data


async def test_no_extra_discovery_field_is_ever_stored(hass, aioclient_mock):
    """D7: a credential in a discovery message (for example a future messaging key) never reaches
    Home Assistant's storage, neither on first set-up nor on rediscovery, nor in diagnostics."""
    secret = "M" * 43
    config = {"host": HOST, "port": PORT, "token": TOKEN, "cert_sha256": CERT, "messaging": {"key": secret}}
    data = HassioServiceInfo(config=config, name="MeshBeacon", slug="local_meshbeacon", uuid="abc123")
    aioclient_mock.get(URL, json=snapshot())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_HASSIO}, data=data)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert set(entry.data) <= ENTRY_KEYS and secret not in str(entry.data)
    again = HassioServiceInfo(
        config={**config, "token": "N" * 43}, name="MeshBeacon", slug="local_meshbeacon", uuid="abc124"
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_HASSIO}, data=again)
    assert result["reason"] == "already_configured"
    assert set(entry.data) <= ENTRY_KEYS and secret not in str(entry.data)
    await hass.async_block_till_done()
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert secret not in str(diagnostics) and "N" * 43 not in str(diagnostics) and TOKEN not in str(diagnostics)
