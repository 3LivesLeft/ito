# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the Home Assistant integration tests (pytest-homeassistant-custom-component)."""

import pytest

from custom_components.meshbeacon.const import DOMAIN

from .fixtures import snapshot  # noqa: F401 - re-exported for the tests

HOST = "local-meshbeacon"
PORT = 8100
TOKEN = "T" * 43
CERT = "ab" * 32
URL = f"https://{HOST}:{PORT}/api/v1/status"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture
def entry_data():
    return {"host": HOST, "port": PORT, "token": TOKEN, "cert_sha256": CERT}


@pytest.fixture
def mock_entry(hass, entry_data):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, unique_id="local_meshbeacon", data=entry_data, title="MeshBeacon")
    entry.add_to_hass(hass)
    return entry
