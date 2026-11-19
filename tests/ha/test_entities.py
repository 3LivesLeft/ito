# SPDX-License-Identifier: Apache-2.0
"""Entities, state classes for native history and statistics, repairs and diagnostics."""

import re
from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorStateClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.meshbeacon.const import DOMAIN
from custom_components.meshbeacon.diagnostics import async_get_config_entry_diagnostics

from .conftest import TOKEN, URL, snapshot


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def eid(hass, platform, unique):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"local_meshbeacon_{unique}")


async def test_node_and_peer_entities(hass, mock_entry, aioclient_mock):
    aioclient_mock.get(URL, json=snapshot())
    await setup(hass, mock_entry)
    assert mock_entry.state is ConfigEntryState.LOADED

    state = hass.states.get(eid(hass, "sensor", "status"))
    assert state.state == "running"
    assert hass.states.get(eid(hass, "sensor", "connectivity")).state == "online"
    received = hass.states.get(eid(hass, "sensor", "received"))
    assert received.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL_INCREASING  # long-term statistics
    assert float(received.state) == 2.0  # 2,000,000 B shown in MB
    assert hass.states.get(eid(hass, "sensor", "known_paths")).state == "42"
    assert hass.states.get(eid(hass, "sensor", "relayed_links")).state == "2"
    assert hass.states.get(eid(hass, "sensor", "reticulum_started")).state == "2025-11-18T13:53:30+00:00"
    assert hass.states.get(eid(hass, "binary_sensor", "transport_mode")).state == STATE_ON
    assert hass.states.get(eid(hass, "binary_sensor", "reticulum_running")).state == STATE_ON
    assert hass.states.get(eid(hass, "binary_sensor", "problem_detected")).state == STATE_OFF
    assert hass.states.get(eid(hass, "binary_sensor", "peer_emerald_connected")).state == STATE_ON
    assert hass.states.get(eid(hass, "sensor", "peer_emerald_reconnections")).state == "1"
    assert hass.states.get(eid(hass, "sensor", "peer_emerald_connected_since")).state == "2025-11-18T13:53:40+00:00"

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), mock_entry.entry_id)
    assert [(d.name, d.sw_version) for d in devices] == [("MeshBeacon", "0.2.0")]  # peers are not devices
    peer_state = hass.states.get(eid(hass, "binary_sensor", "peer_emerald_connected"))
    assert peer_state.name == "MeshBeacon Emerald connected"

    # Disabled by default: detailed memory figures.
    assert er.async_get(hass).async_get(eid(hass, "sensor", "core_memory")).disabled


async def test_unavailable_values_are_unknown_not_zero(hass, mock_entry, aioclient_mock):
    aioclient_mock.get(
        URL,
        json=snapshot(
            network__paths=None, network__rx_rate=None, node__transport_enabled=None, resources__cpu_percent=None
        ),
    )
    await setup(hass, mock_entry)
    assert hass.states.get(eid(hass, "sensor", "known_paths")).state == STATE_UNKNOWN
    assert hass.states.get(eid(hass, "sensor", "receive_rate")).state == STATE_UNKNOWN
    assert hass.states.get(eid(hass, "binary_sensor", "transport_mode")).state == STATE_UNKNOWN


async def test_new_peers_are_added_and_removed_peers_become_unavailable(
    hass, mock_entry, aioclient_mock, freezer: FrozenDateTimeFactory
):
    aioclient_mock.get(URL, json=snapshot())
    await setup(hass, mock_entry)
    two = snapshot()
    two["peers"] = [dict(two["peers"][0], name="Ruby")]
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=two)
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(eid(hass, "binary_sensor", "peer_ruby_connected")).state == STATE_ON
    assert hass.states.get(eid(hass, "binary_sensor", "peer_emerald_connected")).state == STATE_UNAVAILABLE


async def test_app_restart_new_key_makes_entities_unavailable_not_reauth(
    hass, mock_entry, aioclient_mock, freezer: FrozenDateTimeFactory
):
    aioclient_mock.get(URL, json=snapshot())
    await setup(hass, mock_entry)
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, status=401)
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(eid(hass, "sensor", "status")).state == STATE_UNAVAILABLE
    assert not hass.config_entries.flow.async_progress()  # no reauthentication prompt


async def test_repair_issues(hass, mock_entry, aioclient_mock, freezer: FrozenDateTimeFactory):
    registry = ir.async_get(hass)
    aioclient_mock.get(
        URL, json=snapshot(app__state="needs_attention", app__problem="identity", app__message="Identity damaged.")
    )
    await setup(hass, mock_entry)
    issue = registry.async_get_issue(DOMAIN, "needs_attention")
    assert issue is not None and issue.translation_placeholders == {"message": "Identity damaged."}
    assert hass.states.get(eid(hass, "binary_sensor", "problem_detected")).state == STATE_ON

    async def poll(data):
        aioclient_mock.clear_requests()
        aioclient_mock.get(URL, json=data)
        freezer.tick(timedelta(seconds=61))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    await poll(snapshot(app__problem="isolated", app__connectivity="isolated"))
    assert registry.async_get_issue(DOMAIN, "needs_attention") is None
    assert registry.async_get_issue(DOMAIN, "isolated") is not None

    unreachable = snapshot(app__problem="peers_unreachable", app__connectivity="offline")
    await poll(unreachable)
    assert registry.async_get_issue(DOMAIN, "isolated") is None
    assert registry.async_get_issue(DOMAIN, "peers_unreachable") is None  # within the 10-minute grace
    for _ in range(11):
        await poll(unreachable)
    assert registry.async_get_issue(DOMAIN, "peers_unreachable") is not None
    await poll(snapshot())
    assert registry.async_get_issue(DOMAIN, "peers_unreachable") is None

    await hass.config_entries.async_unload(mock_entry.entry_id)
    assert not [i for i in registry.issues.values() if i.domain == DOMAIN]


async def test_diagnostics_are_redacted(hass, mock_entry, aioclient_mock):
    aioclient_mock.get(URL, json=snapshot(app__message="Connected to Emerald."))
    await setup(hass, mock_entry)
    diag = await async_get_config_entry_diagnostics(hass, mock_entry)
    text = repr(diag)
    assert TOKEN not in text and "local-meshbeacon" not in text and "Emerald" not in text
    assert diag["entry"]["token"] == "**REDACTED**"
    assert diag["status"]["peers"][0]["name"] == "peer 1"
    assert diag["status"]["paths"] == 42


async def test_unsupported_schema_fails_setup_cleanly(hass, mock_entry, aioclient_mock):
    aioclient_mock.get(URL, json=snapshot(schema=2))
    assert not await hass.config_entries.async_setup(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.SETUP_RETRY


async def test_example_dashboard_uses_only_real_entities(hass, mock_entry, aioclient_mock):
    import yaml

    from .test_contract import ROOT

    aioclient_mock.get(URL, json=snapshot())
    await setup(hass, mock_entry)
    text = (ROOT / "docs/home-assistant/dashboard.yaml").read_text()
    yaml.safe_load(text)
    referenced = set(re.findall(r"(?:sensor|binary_sensor)\.meshbeacon_[a-z_]+", text))
    assert referenced
    missing = {e for e in referenced if hass.states.get(e) is None}
    assert not missing, missing
