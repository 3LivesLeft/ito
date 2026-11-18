# SPDX-License-Identifier: Apache-2.0
"""v0.2 security review: discovery spoofing, key leakage, rotation and self-healing."""

import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from aiohttp import ClientError
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_HASSIO, ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.meshbeacon.const import DOMAIN
from custom_components.meshbeacon.diagnostics import async_get_config_entry_diagnostics

from .conftest import HOST, PORT, TOKEN, URL, snapshot


def info(slug="local_meshbeacon", name="MeshBeacon", **config):
    base = {"host": slug.replace("_", "-"), "port": PORT, "token": TOKEN}
    base.update(config)
    return HassioServiceInfo(config=base, name=name, slug=slug, uuid="abc123")


async def start_flow(hass, data):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_HASSIO}, data=data)


@pytest.mark.parametrize(
    ("slug", "host"),
    [
        ("core_mosquitto", "core-mosquitto"),  # another app declaring the service
        ("a0d7b954_evil", "a0d7b954-evil"),
        ("local_meshbeacon", "core-mosquitto"),  # redirect to another app
        ("local_meshbeacon", "homeassistant"),  # redirect to Core itself
        ("local_meshbeacon", "192.0.2.10"),  # redirect anywhere else
        ("a0d7b954_meshbeacon", "local-meshbeacon"),  # one MeshBeacon pointing at another
    ],
)
async def test_discovery_cannot_redirect_the_integration(hass, slug, host):
    result = await start_flow(hass, info(slug=slug, host=host))
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "invalid_discovery"


async def test_lookalike_app_needs_confirmation_and_cannot_touch_the_real_entry(hass, mock_entry, aioclient_mock):
    """An app from another repository with the same slug name gets its own confirmation dialog,
    showing where it came from; the existing entry and its key are untouched."""
    result = await start_flow(hass, info(slug="a0d7b954_meshbeacon", name="Not MeshBeacon", token="E" * 43))
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "hassio_confirm"
    assert result["description_placeholders"] == {"app": "Not MeshBeacon", "slug": "a0d7b954_meshbeacon"}
    assert mock_entry.data["token"] == TOKEN and mock_entry.data["host"] == HOST


async def test_flow_listing_and_logs_never_show_the_key(hass, aioclient_mock, caplog):
    caplog.set_level(logging.DEBUG)
    aioclient_mock.get(f"http://{HOST}:{PORT}/api/v1/status", exc=ClientError("boom"))
    result = await start_flow(hass, info())
    progress = hass.config_entries.flow.async_progress()
    assert TOKEN not in repr(progress)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "cannot_connect"}
    assert TOKEN not in caplog.text


@pytest.mark.parametrize(
    "reply",
    [
        {"status": 401},
        {"status": 500},
        {"exc": ClientError("connection reset")},
        {"exc": TimeoutError()},
        {"text": "not json"},
        {"json": {"schema": 99}},
    ],
)
async def test_failures_never_log_the_key(hass, mock_entry, aioclient_mock, caplog, reply):
    caplog.set_level(logging.DEBUG)
    aioclient_mock.get(URL, **reply)
    with patch("homeassistant.components.hassio.get_supervisor_client", side_effect=RuntimeError):
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.SETUP_RETRY
    assert TOKEN not in caplog.text
    diag = await async_get_config_entry_diagnostics(hass, mock_entry)
    assert TOKEN not in repr(diag)


async def test_repeated_rotation(hass, mock_entry, aioclient_mock):
    aioclient_mock.get(URL, json=snapshot())
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    for i in range(5):
        token = chr(ord("A") + i) * 43
        result = await start_flow(hass, info(token=token))
        await hass.async_block_till_done()
        assert result["reason"] == "already_configured"
        assert mock_entry.data["token"] == token
        assert mock_entry.state is ConfigEntryState.LOADED
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert hass.states.get("sensor.meshbeacon_status").state == "running"


def message(addon, host, token, port=PORT):
    return SimpleNamespace(addon=addon, service=DOMAIN, config={"host": host, "port": port, "token": token})


def fake_supervisor(messages, on_list=None):
    async def list_messages():
        if on_list:
            on_list()
        return messages

    return SimpleNamespace(discovery=SimpleNamespace(list=list_messages))


async def test_missed_push_heals_itself_from_the_supervisor(
    hass, mock_entry, aioclient_mock, freezer: FrozenDateTimeFactory
):
    aioclient_mock.get(URL, json=snapshot())
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    new = "N" * 43

    def app_restarted():  # the app now accepts only the new key
        aioclient_mock.clear_requests()
        aioclient_mock.get(URL, json=snapshot())

    messages = [
        SimpleNamespace(
            addon="core_other", service=DOMAIN, config={"host": "core-other", "port": 1, "token": "X" * 43}
        ),
        SimpleNamespace(addon="local_meshbeacon", service=DOMAIN, config={"host": HOST, "port": PORT, "token": new}),
    ]
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, status=401)
    with patch(
        "homeassistant.components.hassio.get_supervisor_client", return_value=fake_supervisor(messages, app_restarted)
    ):
        freezer.tick(timedelta(seconds=61))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert mock_entry.data["token"] == new
    assert hass.states.get("sensor.meshbeacon_status").state == "running"
    assert aioclient_mock.mock_calls[-1][3]["Authorization"] == f"Bearer {new}"


async def test_self_healing_rejects_spoofed_messages(hass, mock_entry, aioclient_mock, freezer: FrozenDateTimeFactory):
    aioclient_mock.get(URL, json=snapshot())
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    spoofed = [
        SimpleNamespace(
            addon="local_meshbeacon", service=DOMAIN, config={"host": "evil", "port": PORT, "token": "S" * 43}
        ),
        SimpleNamespace(
            addon="a0d7b954_meshbeacon", service=DOMAIN, config={"host": HOST, "port": PORT, "token": "T2" * 22}
        ),
    ]
    calls = []
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, status=401)
    with patch(
        "homeassistant.components.hassio.get_supervisor_client",
        return_value=fake_supervisor(spoofed, lambda: calls.append(1)),
    ):
        for _ in range(3):  # also: at most one Supervisor look-up per five minutes
            freezer.tick(timedelta(seconds=61))
            async_fire_time_changed(hass)
            await hass.async_block_till_done()
    assert mock_entry.data["token"] == TOKEN
    assert hass.states.get("sensor.meshbeacon_status").state == "unavailable"
    assert len(calls) == 1
    assert not hass.config_entries.flow.async_progress()  # never a reauthentication prompt
