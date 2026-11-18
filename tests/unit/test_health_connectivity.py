# SPDX-License-Identifier: Apache-2.0
import urllib.error
import urllib.request

import pytest

from meshbeacon.connectivity import Connectivity, describe, evaluate
from meshbeacon.health import HealthServer, Heartbeat


@pytest.fixture
def server():
    now = [0.0]
    hb = Heartbeat(clock=lambda: now[0])
    srv = HealthServer(hb, "127.0.0.1", 0, max_age=60)
    srv.start()
    yield srv, hb, now
    srv.stop()


def get(port, path="/health"):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_health_ok_while_heartbeat_fresh(server):
    srv, _hb, now = server
    assert get(srv.port) == (200, b"ok\n")
    now[0] = 59
    assert get(srv.port)[0] == 200


def test_health_fails_only_when_unresponsive(server):
    srv, hb, now = server
    now[0] = 61
    assert get(srv.port)[0] == 503
    hb.beat()
    assert get(srv.port)[0] == 200


def test_health_other_paths_404(server):
    srv, _, _ = server
    assert get(srv.port, "/")[0] == 404


def test_connectivity_states():
    assert evaluate((), None).state is Connectivity.ISOLATED
    peers = ("A", "B")
    assert evaluate(peers, None).state is Connectivity.UNKNOWN
    st = {"interfaces": [{"name": "A", "up": False}, {"name": "B", "up": False}]}
    assert evaluate(peers, st).state is Connectivity.OFFLINE
    st["interfaces"][0]["up"] = True
    s = evaluate(peers, st)
    assert s.state is Connectivity.PARTIAL and s.up == ("A",)
    st["interfaces"][1]["up"] = True
    assert evaluate(peers, st).state is Connectivity.ONLINE


def test_descriptions_are_plain_language():
    assert "not connected to anyone" in describe(evaluate((), None))
    s = evaluate(("Home",), {"interfaces": [{"name": "Home", "up": True}]})
    assert describe(s) == "Connected to Home. Your node is online."
