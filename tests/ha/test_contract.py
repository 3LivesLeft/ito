# SPDX-License-Identifier: Apache-2.0
"""The integration's parser accepts exactly what the core serves (one interface, ADR 0006)."""

import json
import re
from pathlib import Path

from custom_components.meshbeacon import client
from custom_components.meshbeacon.const import CONNECTIVITY, PROBLEMS, SCHEMA_VERSION, STATES
from meshbeacon import metrics, supervisor
from meshbeacon.connectivity import Connectivity

ROOT = Path(__file__).resolve().parents[2]


def core_snapshot():
    clock = [1000.0]
    c = metrics.Collector(("Home", "Away"), clock=lambda: clock[0], wall=lambda: clock[0])
    c.child_started()
    for t, rx in ((1000.0, 0), (1010.0, 500)):
        clock[0] = t
        c.update(
            {
                "transport": True,
                "rxb": rx,
                "txb": rx,
                "packets_rx": 5,
                "packets_tx": 6,
                "paths": 3,
                "relayed_links": 1,
                "interfaces": [{"name": "Home", "up": True, "rxb": rx, "txb": 1, "announces_rx": 2, "announces_tx": 0}],
            }
        )
    c.resources(1, 2, 3.0)
    app = {
        "version": "0.2.0",
        "rns_version": "1.6.0",
        "arch": "x86_64",
        "state": "running",
        "connectivity": "partial",
        "problem": "some_peers_unreachable",
        "message": "Connected to 1 of 2 peers (Home).",
    }
    return json.loads(json.dumps(c.snapshot(app)))


def test_core_output_parses_without_loss():
    status = client.parse_status(core_snapshot())
    assert status.state == "running" and status.problem == "some_peers_unreachable"
    assert status.transport_enabled is True and status.paths == 3 and status.relayed_links == 1
    assert status.rx_rate == 50.0
    home, away = status.peer("Home"), status.peer("Away")
    assert home.connected and home.connected_since == 1000.0 and home.announces_rx == 2
    assert not away.connected and away.rx_bytes is None


def test_enumerations_match_the_core():
    assert SCHEMA_VERSION == metrics.SCHEMA_VERSION
    assert PROBLEMS == supervisor.PROBLEMS
    assert set(CONNECTIVITY) == {c.value for c in Connectivity}
    states = set(re.findall(r'self\.state = "(\w+)"', (ROOT / "meshbeacon/core/meshbeacon/supervisor.py").read_text()))
    assert states == set(STATES)


def test_hostile_values_are_neutralised():
    data = core_snapshot()
    data["network"]["paths"] = -1
    data["network"]["rx_rate"] = float("inf")
    data["network"]["rx_bytes"] = True
    data["app"]["state"] = "<script>"
    data["app"]["problem"] = "made_up"
    data["peers"] = [*data["peers"], "junk", {"name": ""}, {"name": "Home"}] + [{"name": f"p{i}"} for i in range(50)]
    status = client.parse_status(data)
    assert status.paths is None and status.rx_rate is None and status.rx_bytes is None
    assert status.state == "starting" and status.problem == "unexpected"
    assert len(status.peers) <= client.MAX_PEERS and [p.name for p in status.peers].count("Home") == 1


def test_schema_errors():
    import pytest

    for bad in (None, [], {"schema": 2}, {"schema": 1}, {**core_snapshot(), "peers": {}}):
        with pytest.raises(client.SchemaError):
            client.parse_status(bad)


def test_strings_and_translation_identical():
    base = ROOT / "custom_components/meshbeacon"
    assert (base / "strings.json").read_text() == (base / "translations/en.json").read_text()
    strings = json.loads((base / "strings.json").read_text())
    assert set(strings["entity"]["sensor"]["problem"]["state"]) == set(PROBLEMS)
