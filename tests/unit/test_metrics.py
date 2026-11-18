# SPDX-License-Identifier: Apache-2.0
"""The metrics collector: bounded, honest about unavailable values, no identifiers (v0.2)."""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from meshbeacon.metrics import SCHEMA_VERSION, Collector, RateWindow
from meshbeacon.node import summarise


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def status(*ifaces, **node):
    base = {"rxb": 0, "txb": 0, "packets_rx": 0, "packets_tx": 0, "paths": 0, "relayed_links": 0, "transport": False}
    base.update(node)
    return {"interfaces": list(ifaces), **base}


def iface(name, *, up=True, rxb=0, txb=0, arx=0, atx=0):
    return {"name": name, "up": up, "rxb": rxb, "txb": txb, "announces_rx": arx, "announces_tx": atx}


def make(peers=("Home", "Away")):
    clock = Clock()
    c = Collector(peers, clock=clock, wall=clock)
    return c, clock


def test_rate_window_average_and_reset():
    w = RateWindow(60)
    assert w.rate() is None
    w.add(0, 0)
    assert w.rate() is None  # one sample is not a rate
    w.add(10, 1000)
    assert w.rate() == 100.0
    w.add(20, 500)  # counter went down: Reticulum restarted
    assert w.rate() is None
    w.add(None, None)  # type: ignore[arg-type]  # unavailable values are ignored
    assert len(w.samples) == 1


def test_rate_window_is_bounded():
    w = RateWindow(60)
    for i in range(10_000):
        w.add(i * 10.0, i * 100.0)
    assert len(w.samples) <= RateWindow.MAX_SAMPLES
    assert w.rate() == 10.0


def test_peer_uptime_reconnections_and_counters():
    c, clock = make()
    c.child_started()
    c.update(status(iface("Home", up=False)))
    p = c.peers["Home"]
    assert not p.connected and p.connected_since is None and p.reconnections == 0
    clock.t = 1010
    c.update(status(iface("Home", rxb=100, txb=50, arx=2, atx=1)))
    assert p.connected and p.connected_since == 1010 and p.reconnections == 0  # first connection is not a reconnection
    clock.t = 1020
    c.update(status(iface("Home", rxb=300, txb=150, arx=3, atx=1)))
    assert p.connected_since == 1010  # unchanged while it stays up
    assert p.rx_rate.rate() == 15.0 and p.tx_rate.rate() == 7.5  # 300 B and 150 B over 20 s
    clock.t = 1030
    c.update(status(iface("Home", up=False, rxb=300, txb=150)))
    assert p.connected_since is None
    clock.t = 1040
    c.update(status(iface("Home", rxb=400, txb=200)))
    assert p.reconnections == 1 and p.connected_since == 1040
    snap = c.snapshot({})
    assert snap["network"]["peers_connected"] == 1 and snap["network"]["peers_configured"] == 2
    away = next(x for x in snap["peers"] if x["name"] == "Away")
    assert away["connected"] is False and away["rx_bytes"] is None  # not reported: unavailable, not zero


def test_unknown_interfaces_are_ignored_and_names_not_duplicated():
    c, _ = make(("Home",))
    c.child_started()
    c.update(status(iface("Stranger"), iface("Home", rxb=5), iface("Home", rxb=999)))
    snap = c.snapshot({})
    assert [p["name"] for p in snap["peers"]] == ["Home"]
    assert snap["peers"][0]["rx_bytes"] == 5


def test_missing_values_are_unavailable_never_zero():
    c, _ = make(("Home",))
    c.child_started()
    c.update({"interfaces": [{"name": "Home", "up": True}], "transport": "yes"})
    snap = c.snapshot({})
    net = snap["network"]
    for key in ("rx_bytes", "tx_bytes", "packets_rx", "packets_tx", "paths", "relayed_links", "rx_rate"):
        assert net[key] is None, key
    assert snap["node"]["transport_enabled"] is None  # not a bool: unknown
    assert snap["peers"][0]["announces_rx"] is None


def test_restarts_and_child_lifecycle():
    c, clock = make(("Home",))
    c.child_started()
    assert c.snapshot({})["node"]["started_at"] == 1000
    c.update(status(iface("Home", rxb=10), transport=True))
    assert c.snapshot({})["node"]["transport_enabled"] is True
    c.child_stopped()
    c.record_failure(memory=True)
    snap = c.snapshot({})
    assert snap["node"] == {
        "running": False,
        "started_at": None,
        "transport_enabled": None,
        "restarts": 1,
        "memory_restarts": 1,
    }
    assert snap["peers"][0]["connected"] is False and snap["peers"][0]["rx_bytes"] is None
    clock.t = 2000
    c.child_started()
    c.record_failure()
    assert c.snapshot({})["node"]["restarts"] == 2
    assert c.snapshot({})["node"]["memory_restarts"] == 1


def test_resources_and_cpu():
    c, clock = make(())
    c.resources(10 * 2**20, 40 * 2**20, 1.0)
    clock.t += 10
    c.resources(10 * 2**20, 41 * 2**20, 1.5)
    r = c.snapshot({})["resources"]
    assert r["memory_bytes"] == 51 * 2**20
    assert r["cpu_percent"] == 5.0
    c.resources(None, None, None)
    r = c.snapshot({})["resources"]
    assert r["memory_bytes"] is None


def test_reconfigure_keeps_known_peers():
    c, _ = make(("Home",))
    c.peers["Home"].reconnections = 3
    c.configure(("Home", "New"))
    assert c.peers["Home"].reconnections == 3 and set(c.peers) == {"Home", "New"}


def test_snapshot_schema_and_serialisable():
    c, _ = make()
    snap = c.snapshot({"version": "x"})
    assert snap["schema"] == SCHEMA_VERSION
    assert set(snap) == {"schema", "generated_at", "app", "node", "network", "peers", "resources"}
    json.dumps(snap, allow_nan=False)


def test_node_summary_reads_only_allow_listed_fields():
    secret = bytes(range(32))
    stats = {
        "interfaces": [
            {
                "type": "TCPClientInterface",
                "short_name": "Home",
                "name": "TCPInterface[Home/<lan-ip>:4242]",  # contains the host: never read
                "hash": secret,
                "status": True,
                "rxb": 10,
                "txb": 20,
                "arxc": 3,
                "atxc": 4,
                "ifac_netname": "private-network",
                "ifac_signature": secret,
            },
            {"type": "AutoInterface", "short_name": "lan", "status": True},
        ],
        "transport_id": secret,
        "network_id": secret,
        "rxb": 1,
        "txb": 2,
        "rxpkts": 3,
        "txpkts": 4,
        "tpcount": 5,
        "tlinks": 6,
        "probe_responder": secret,
    }
    out = summarise(stats, True)
    text = json.dumps(out)
    assert "private-network" not in text and "<lan-ip>" not in text and "4242" not in text
    assert out["interfaces"] == [
        {"name": "Home", "up": True, "rxb": 10, "txb": 20, "announces_rx": 3, "announces_tx": 4}
    ]
    assert (out["paths"], out["relayed_links"], out["packets_rx"], out["transport"]) == (5, 6, 3, True)
    assert summarise({}, None)["paths"] is None
    assert summarise({"rxb": True, "txb": -5})["rxb"] is None  # booleans are not counts
    assert summarise({"txb": -5})["txb"] == 0


HOSTILE_NUMBERS = st.sampled_from([float("nan"), float("inf"), float("-inf"), -0.0, 1e308, -1.5, 0.5])


# Generation is kept cheap (at most 12 entries, above the 10-peer limit; hostile floats drawn from a
# fixed set): CI's health check failed once when generating up to 30 entries with arbitrary floats on
# a busy runner (v0.2 review).
@settings(max_examples=100, deadline=None)
@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "name": st.sampled_from(["Home", "Away", "x", ""]),
                "up": st.one_of(st.booleans(), st.none(), st.integers(-1, 2)),
                "rxb": st.one_of(st.none(), st.integers(-10, 10**12), st.text(max_size=3), HOSTILE_NUMBERS),
                "txb": st.one_of(st.none(), st.integers(0, 10**12)),
            }
        ),
        max_size=12,
    ),
    st.dictionaries(
        st.sampled_from(["rxb", "paths", "transport", "relayed_links"]),
        st.one_of(st.none(), st.integers(), st.text(max_size=2)),
    ),
)
def test_hostile_status_lines_never_crash_or_grow(ifaces, node):
    c, clock = make()
    c.child_started()
    for _ in range(3):
        clock.t += 10
        c.update({"interfaces": ifaces, **node})
    snap = c.snapshot({})
    assert len(snap["peers"]) == 2
    json.dumps(snap, allow_nan=False)
