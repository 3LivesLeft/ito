# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the Home Assistant integration tests (pytest-homeassistant-custom-component)."""

import copy

import pytest

from custom_components.meshbeacon.const import DOMAIN

HOST = "local-meshbeacon"
PORT = 8100
TOKEN = "T" * 43
URL = f"http://{HOST}:{PORT}/api/v1/status"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


def snapshot(**changes):
    """A schema-1 snapshot like the one the core serves (see test_contract for the real one)."""
    data = {
        "schema": 1,
        "generated_at": 1763474700.0,
        "app": {
            "version": "0.2.0",
            "rns_version": "1.6.0",
            "arch": "aarch64",
            "state": "running",
            "connectivity": "online",
            "problem": "none",
            "message": None,
            "started_at": 1763474000.0,
        },
        "node": {
            "running": True,
            "started_at": 1763474010.0,
            "transport_enabled": True,
            "restarts": 0,
            "memory_restarts": 0,
        },
        "network": {
            "peers_configured": 1,
            "peers_connected": 1,
            "rx_bytes": 2_000_000,
            "tx_bytes": 1_000_000,
            "rx_rate": 120.5,
            "tx_rate": 60.0,
            "packets_rx": 900,
            "packets_tx": 800,
            "paths": 42,
            "relayed_links": 2,
            "announces_rx": 300,
            "announces_tx": 20,
        },
        "peers": [
            {
                "name": "Emerald",
                "connected": True,
                "connected_since": 1763474020.0,
                "rx_bytes": 2_000_000,
                "tx_bytes": 1_000_000,
                "rx_rate": 120.5,
                "tx_rate": 60.0,
                "announces_rx": 300,
                "announces_tx": 20,
                "reconnections": 1,
            }
        ],
        "resources": {
            "memory_bytes": 41 * 2**20,
            "core_memory_bytes": 12 * 2**20,
            "reticulum_memory_bytes": 29 * 2**20,
            "cpu_percent": 0.2,
        },
    }
    data = copy.deepcopy(data)
    for path, value in changes.items():
        section, _, key = path.partition("__")
        if key:
            data[section][key] = value
        else:
            data[section] = value
    return data


@pytest.fixture
def entry_data():
    return {"host": HOST, "port": PORT, "token": TOKEN}


@pytest.fixture
def mock_entry(hass, entry_data):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, unique_id="local_meshbeacon", data=entry_data, title="MeshBeacon")
    entry.add_to_hass(hass)
    return entry
