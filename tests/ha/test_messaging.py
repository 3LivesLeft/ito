# SPDX-License-Identifier: Apache-2.0
"""M5 (ADR 0024): the Messages view's path through Home Assistant.

Administrators only; the messaging key is held in memory only and never reaches the browser,
storage or diagnostics; requests are validated before they leave Home Assistant; live updates
carry no content; nothing is recorded."""

from __future__ import annotations

import json
from typing import Any

import pytest
from homeassistant.config_entries import SOURCE_HASSIO
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from custom_components.meshbeacon import conversations as messaging
from custom_components.meshbeacon.const import DOMAIN, ENTRY_KEYS
from custom_components.meshbeacon.diagnostics import async_get_config_entry_diagnostics

from .conftest import CERT, HOST, PORT, TOKEN, URL, snapshot

KEY = "K" * 43
MURL = f"https://{HOST}:{PORT}/api/v1/messaging"
SECRET = "a private message 🔒"
CLICK = "click-0001"  # one press of Send (an idempotency key, not a secret)


async def _set_up(hass: HomeAssistant, mock_entry, aioclient_mock, *, key: str | None = KEY) -> None:
    aioclient_mock.get(URL, json=snapshot())
    if key:
        messaging.remember_key(hass, "local_meshbeacon", {"messaging_key": key})
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()


def _posts(aioclient_mock) -> list[tuple[dict[str, Any], dict[str, str]]]:
    return [
        (json.loads(data), dict(headers))
        for method, url, data, headers in aioclient_mock.mock_calls
        if method == "POST"
    ]


async def _call(hass, hass_ws_client, entry, kind: str, **fields: Any) -> dict[str, Any]:
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": f"meshbeacon/messaging/{kind}", "entry_id": entry.entry_id, **fields})
    return await ws.receive_json()


async def test_the_messaging_key_is_kept_in_memory_only(hass, aioclient_mock):
    config = {"host": HOST, "port": PORT, "token": TOKEN, "cert_sha256": CERT, "messaging_key": KEY}
    data = HassioServiceInfo(config=config, name="MeshBeacon", slug="local_meshbeacon", uuid="abc123")
    aioclient_mock.get(URL, json=snapshot())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_HASSIO}, data=data)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    await hass.async_block_till_done()
    assert hass.data[messaging.KEYS] == {"local_meshbeacon": KEY}
    assert set(entry.data) <= ENTRY_KEYS and KEY not in str(entry.data)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert KEY not in str(diagnostics)
    # Messaging switched off: the app's next message has no key, and it is forgotten.
    off = HassioServiceInfo(
        config={**config, "messaging_key": None}, name="MeshBeacon", slug="local_meshbeacon", uuid="b"
    )
    await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_HASSIO}, data=off)
    assert "local_meshbeacon" not in hass.data[messaging.KEYS]


async def test_a_key_from_a_message_that_points_elsewhere_is_never_kept(hass):
    config = {"host": "evil", "port": PORT, "token": TOKEN, "cert_sha256": CERT, "messaging_key": KEY}
    data = HassioServiceInfo(config=config, name="MeshBeacon", slug="local_meshbeacon", uuid="abc123")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_HASSIO}, data=data)
    assert result["reason"] == "invalid_discovery"
    assert not hass.data.get(messaging.KEYS)


@pytest.mark.parametrize(
    ("kind", "fields"), [("conversations", {}), ("send", {"contact": "a", "text": "x", "idempotency_key": "k" * 16})]
)
async def test_non_admins_are_refused(  # noqa: PLR0917 - pytest fixtures
    hass, hass_ws_client, hass_read_only_access_token, mock_entry, aioclient_mock, kind, fields
):
    await _set_up(hass, mock_entry, aioclient_mock)
    ws = await hass_ws_client(hass, hass_read_only_access_token)
    await ws.send_json({"id": 1, "type": f"meshbeacon/messaging/{kind}", "entry_id": mock_entry.entry_id, **fields})
    result = await ws.receive_json()
    assert not result["success"] and result["error"]["code"] == "unauthorized"
    assert _posts(aioclient_mock) == []


async def test_a_send_goes_to_the_app_with_the_messaging_key_only(hass, hass_ws_client, mock_entry, aioclient_mock):
    await _set_up(hass, mock_entry, aioclient_mock)
    aioclient_mock.post(MURL, json={"ok": True, "message_id": "e" * 32, "state": "queued"})
    result = await _call(
        hass, hass_ws_client, mock_entry, "send", contact="alice", text=SECRET, **{"idempotency_key": CLICK}
    )
    assert result["success"] and result["result"] == {"message_id": "e" * 32, "state": "queued"}
    [(body, headers)] = _posts(aioclient_mock)
    assert body == {"op": "send", "contact": "alice", "text": SECRET, "idempotency_key": CLICK}
    assert headers["Authorization"] == f"Bearer {KEY}" and TOKEN not in str(headers)


@pytest.mark.parametrize(
    ("kind", "fields", "error"),
    [
        ("send", {"contact": "alice", "text": "x" * 8193, "idempotency_key": CLICK}, "too_long"),
        ("send", {"contact": "alice", "text": "   ", "idempotency_key": CLICK}, "invalid"),
        ("send", {"contact": "a" * 40, "text": "x", "idempotency_key": CLICK}, "unknown_contact"),
        ("send", {"contact": "alice", "text": "x", "idempotency_key": "no"}, "invalid"),
        ("history", {"contact": "../x"}, "unknown_contact"),
        ("retry", {"message_id": "not-an-id"}, "invalid"),
        ("contact_add", {"name": "", "address": "x"}, "invalid_name"),
    ],
)
async def test_requests_are_validated_before_they_leave_home_assistant(  # noqa: PLR0917 - pytest fixtures
    hass, hass_ws_client, mock_entry, aioclient_mock, kind, fields, error
):
    await _set_up(hass, mock_entry, aioclient_mock)
    result = await _call(hass, hass_ws_client, mock_entry, kind, **fields)
    assert not result["success"] and result["error"]["code"] == error
    assert _posts(aioclient_mock) == []


async def test_the_apps_refusal_is_passed_on_as_a_plain_code(hass, hass_ws_client, mock_entry, aioclient_mock):
    await _set_up(hass, mock_entry, aioclient_mock)
    aioclient_mock.post(MURL, status=429, json={"ok": False, "error": "rate_limited"})
    result = await _call(
        hass, hass_ws_client, mock_entry, "send", contact="alice", text="x", **{"idempotency_key": CLICK}
    )
    assert result["error"]["code"] == "rate_limited"


async def test_messaging_off_in_the_app_is_reported_as_such(hass, hass_ws_client, mock_entry, aioclient_mock):
    await _set_up(hass, mock_entry, aioclient_mock, key=None)
    result = await _call(hass, hass_ws_client, mock_entry, "conversations")
    assert result["error"]["code"] == "not_enabled" and _posts(aioclient_mock) == []


async def test_an_unreachable_app_is_reported_as_such(hass, hass_ws_client, mock_entry, aioclient_mock):
    await _set_up(hass, mock_entry, aioclient_mock)
    aioclient_mock.post(MURL, exc=TimeoutError())
    result = await _call(hass, hass_ws_client, mock_entry, "conversations")
    assert result["error"]["code"] == "unreachable"


async def test_live_updates_carry_no_content_and_stop_when_nobody_listens(
    hass, hass_ws_client, mock_entry, aioclient_mock
):
    await _set_up(hass, mock_entry, aioclient_mock)
    aioclient_mock.post(MURL, json={"ok": True, "revision": 3, "boot": "b"})
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 5, "type": "meshbeacon/messaging/subscribe", "entry_id": mock_entry.entry_id})
    assert (await ws.receive_json())["success"]
    event = await ws.receive_json()
    assert event["type"] == "event" and event["event"] == {"type": "changed"}
    hub = mock_entry.runtime_data.messaging
    assert hub._task is not None
    await ws.send_json({"id": 6, "type": "unsubscribe_events", "subscription": 5})
    await ws.receive_json()
    await hass.async_block_till_done()
    assert hub._task is None and hub._listeners == []
    assert all(body["op"] == "wait" and body["wait"] <= 8 for body, _ in _posts(aioclient_mock))


async def test_message_text_never_reaches_the_state_machine_or_the_log(
    hass, hass_ws_client, mock_entry, aioclient_mock, caplog
):
    await _set_up(hass, mock_entry, aioclient_mock)
    caplog.set_level("DEBUG")
    aioclient_mock.post(
        MURL,
        json={"ok": True, "messages": [{"seq": 1, "message_id": "e" * 32, "direction": "in", "text": SECRET}]},
    )
    result = await _call(hass, hass_ws_client, mock_entry, "history", contact="alice")
    assert result["result"]["messages"][0]["text"] == SECRET
    assert SECRET not in caplog.text
    for state in hass.states.async_all():
        assert SECRET not in str(state.as_dict())
