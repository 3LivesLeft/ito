# SPDX-License-Identifier: Apache-2.0
"""Set-up only through Supervisor discovery; rediscovery rotates the key in place."""

import pytest
from homeassistant.config_entries import SOURCE_HASSIO, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from custom_components.meshbeacon.const import DOMAIN

from .conftest import CERT, HOST, PORT, TOKEN, URL, snapshot


def info(**config):
    base = {"host": HOST, "port": PORT, "token": TOKEN, "cert_sha256": CERT}
    base.update(config)
    return HassioServiceInfo(config=base, name="MeshBeacon", slug="local_meshbeacon", uuid="abc123")


async def test_discovery_confirm_creates_entry(hass, aioclient_mock):
    aioclient_mock.get(URL, json=snapshot())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_HASSIO}, data=info())
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "hassio_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"host": HOST, "port": PORT, "token": TOKEN, "cert_sha256": CERT}
    assert result["result"].unique_id == "local_meshbeacon"
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {TOKEN}"


async def test_discovery_cannot_connect(hass, aioclient_mock):
    aioclient_mock.get(URL, status=401)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_HASSIO}, data=info())
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "cannot_connect"}


@pytest.mark.parametrize(
    "config",
    [
        {"host": "bad host"},
        {"host": "x" * 300},
        {"port": 0},
        {"port": "8100"},
        {"port": True},
        {"token": "short"},
        {"token": "T" * 40 + "/../"},
        {"token": None},
        {"cert_sha256": None},  # never plain HTTP
        {"cert_sha256": "AB" * 32},
        {"cert_sha256": "ab" * 31},
    ],
)
async def test_discovery_rejects_unusable_details(hass, config):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_HASSIO}, data=info(**config))
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "invalid_discovery"


async def test_rediscovery_updates_token_of_existing_entry(hass, mock_entry, aioclient_mock):
    aioclient_mock.get(URL, json=snapshot())
    new_token = "N" * 43
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_HASSIO}, data=info(token=new_token)
    )
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert mock_entry.data["token"] == new_token


async def test_manual_setup_is_not_offered(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "discovery_only"
