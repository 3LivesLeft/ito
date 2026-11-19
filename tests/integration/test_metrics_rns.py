# SPDX-License-Identifier: Apache-2.0
"""v0.2 monitoring against real, isolated Reticulum processes (loopback only).

* The keys MeshBeacon reads exist in the pinned RNS (an RNS upgrade that changes them fails here).
* The monitoring API serves real figures only after discovery, only with the token, and never
  contains hosts, network names, passphrases or hashes.
* The Supervisor token never reaches the prepare step or Reticulum.
* In transport mode, a link between two endpoints that can reach each other only through
  MeshBeacon shows up as a relayed link (the forwarding indicator).
"""

import hashlib
import http.client
import json
import re
import ssl
import subprocess
import sys
from pathlib import Path

import pytest

from meshbeacon.node import INTERFACE_COUNTERS, NODE_COUNTERS

from .conftest import free_port, wait_for, write_options

SUPERVISOR_TOKEN = "test-supervisor-token-" + "x" * 20
HEX32 = re.compile(r"[0-9a-f]{32}")


PINNED: dict[int, str] = {}  # port -> fingerprint from the latest discovery message seen by a test


def fetch(port: int, token: str | None, fingerprint: str | None = None):
    """GET the status over HTTPS, pinning the certificate like the integration does."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # trust comes from the pinned fingerprint, checked below
    conn = http.client.HTTPSConnection("127.0.0.1", port, timeout=5, context=context)
    try:
        conn.connect()  # handshake first: the key is sent only to the pinned certificate
        peer = conn.sock.getpeercert(binary_form=True)
        expected = fingerprint or PINNED.get(port)
        if expected is not None:
            assert hashlib.sha256(peer).hexdigest() == expected, "certificate does not match the pinned one"
        conn.request("GET", "/api/v1/status", headers={"Authorization": f"Bearer {token}"} if token else {})
        response = conn.getresponse()
        body = response.read()
        return response.status, (json.loads(body) if response.status == 200 else None)
    finally:
        conn.close()


def pin(message: dict) -> tuple[str, int]:
    """Remember the fingerprint from a discovery message; return (token, port)."""
    config = message["config"]
    PINNED[config["port"]] = config["cert_sha256"]
    return config["token"], config["port"]


FAST_DISCOVERY = {"retry_initial": 0.2, "retry_max": 1.0, "reannounce": 2.0}


def start_runner(runner_factory, data, supervisor, **kw):
    return runner_factory(
        data,
        supervisor_token=SUPERVISOR_TOKEN,
        supervisor_url=supervisor.url,
        hostname=lambda: "local-meshbeacon",
        discovery_timing=FAST_DISCOVERY,
        **kw,
    )


def test_rns_provides_every_key_meshbeacon_reads(tmp_path):
    out = subprocess.run(
        [sys.executable, "-m", "tests.integration.relay_nodes", "contract", str(tmp_path / "rns"), str(free_port())],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout
    result = json.loads(out.strip().splitlines()[-1])
    assert set(NODE_COUNTERS) <= set(result["node_keys"]), "RNS no longer reports a node counter MeshBeacon reads"
    assert set(INTERFACE_COUNTERS) | {"short_name", "status", "type"} <= set(result["interface_keys"])
    assert result["transport_enabled"] is True
    assert result["tpcount"] == result["path_table_len"]


def test_api_is_off_by_default(data, supervisor, runner_factory):
    write_options(data)
    r = start_runner(runner_factory, data, supervisor)
    assert wait_for(lambda: r.out.has("Home Assistant integration: off."), timeout=30)
    assert r.sup.api_server is None and supervisor.messages == []


def test_end_to_end_metrics_via_discovery(data, peer, supervisor, runner_factory):
    write_options(
        data,
        home_assistant_integration=True,
        peers=[
            {
                "name": "Home",
                "host": "127.0.0.1",
                "port": peer.port,
                "network_name": "privnet",
                "passphrase": "s3cret-pass",
            }
        ],
    )
    r = start_runner(runner_factory, data, supervisor)
    assert wait_for(lambda: supervisor.messages, timeout=30), r.out.text()
    message = supervisor.messages[0]
    assert supervisor.auth[0] == f"Bearer {SUPERVISOR_TOKEN}"
    assert message["service"] == "meshbeacon"
    config = message["config"]
    assert config["host"] == "local-meshbeacon" and config["port"] == r.sup.api_server.port
    token, port = pin(message)
    assert len(config["cert_sha256"]) == 64

    assert fetch(port, None)[0] == 401
    assert fetch(port, "wrong")[0] == 401
    assert wait_for(lambda: (fetch(port, token)[1] or {}).get("network", {}).get("peers_connected") == 1, timeout=60)
    assert wait_for(lambda: fetch(port, token)[1]["network"]["rx_rate"] is not None, timeout=30)
    status, snap = fetch(port, token)
    assert status == 200 and snap["schema"] == 1
    assert snap["app"]["state"] == "running" and snap["app"]["connectivity"] == "online"
    assert snap["app"]["problem"] == "none" and snap["app"]["message"] is None
    assert snap["node"]["running"] is True and snap["node"]["transport_enabled"] is False
    assert snap["node"]["started_at"] is not None and snap["node"]["restarts"] == 0
    home = snap["peers"][0]
    assert home["name"] == "Home" and home["connected"] is True and home["connected_since"] is not None
    assert home["rx_bytes"] is not None and home["tx_bytes"] is not None  # reported (an idle peer may send 0)
    assert snap["network"]["relayed_links"] == 0  # transport off: never relays
    assert snap["resources"]["memory_bytes"] > 0

    # Nothing identifying or secret is served.
    text = json.dumps(snap)
    for secret in ("127.0.0.1", str(peer.port), "privnet", "s3cret-pass", SUPERVISOR_TOKEN, token):
        assert secret not in text, secret
    assert not HEX32.search(text)
    assert token not in r.out.text() and SUPERVISOR_TOKEN not in r.out.text()  # never logged

    # The Supervisor token is never handed to Reticulum.
    environ = Path(f"/proc/{r.sup.child.proc.pid}/environ").read_bytes()
    assert b"SUPERVISOR_TOKEN" not in environ and SUPERVISOR_TOKEN.encode() not in environ

    # Connectivity problems are reported with a stable code and a plain message.
    peer.stop()
    assert wait_for(lambda: fetch(port, token)[1]["app"]["problem"] == "peers_unreachable", timeout=60)
    assert "cannot reach any of your peers" in fetch(port, token)[1]["app"]["message"]
    peer.start()
    assert wait_for(lambda: fetch(port, token)[1]["peers"][0]["reconnections"] == 1, timeout=90), r.out.text()


def test_needs_attention_is_reported_with_its_code(data, supervisor, runner_factory):
    storage = data / "reticulum" / "storage"
    storage.mkdir(parents=True)
    (storage / "transport_identity").write_bytes(b"damaged")  # damaged, and no backup exists
    write_options(data, home_assistant_integration=True)
    r = start_runner(runner_factory, data, supervisor)
    assert wait_for(lambda: supervisor.messages, timeout=30)
    token, port = pin(supervisor.messages[0])
    assert wait_for(lambda: r.sup.state == "needs_attention", timeout=60), r.out.text()
    snap = fetch(port, token)[1]
    assert snap["app"]["state"] == "needs_attention" and snap["app"]["problem"] == "identity"
    assert snap["app"]["message"] and not snap["app"]["message"].startswith("✖")
    assert snap["node"]["running"] is False
    assert (storage / "transport_identity").read_bytes() == b"damaged"  # never replaced silently


def test_transport_mode_relays_a_link(data, tmp_path, supervisor, runner_factory):
    """A ↔ MeshBeacon ↔ B: B can reach A only through MeshBeacon (transport on)."""
    ports = (free_port(), free_port())
    hashfile = tmp_path / "dest.hash"
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.integration.relay_nodes",
                mode,
                str(tmp_path / mode),
                str(port),
                str(hashfile),
            ],
            stdout=subprocess.PIPE if mode == "client" else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        for mode, port in (("server", ports[0]), ("client", ports[1]))
    ]
    try:
        write_options(
            data,
            transport=True,
            home_assistant_integration=True,
            peers=[
                {"name": "A", "host": "127.0.0.1", "port": ports[0]},
                {"name": "B", "host": "127.0.0.1", "port": ports[1]},
            ],
        )
        r = start_runner(runner_factory, data, supervisor)
        assert wait_for(lambda: supervisor.messages, timeout=30)
        token, port = pin(supervisor.messages[0])

        def relayed() -> bool:
            snap = fetch(port, token)[1]
            return snap is not None and (snap["network"]["relayed_links"] or 0) >= 1

        assert wait_for(relayed, timeout=120), r.out.text()
        snap = fetch(port, token)[1]
        assert snap["node"]["transport_enabled"] is True
        assert snap["network"]["paths"] >= 1
        assert snap["network"]["announces_rx"] >= 1
        a = next(p for p in snap["peers"] if p["name"] == "A")
        b = next(p for p in snap["peers"] if p["name"] == "B")
        assert a["announces_rx"] >= 1 and b["announces_tx"] >= 1  # A's announce passed on to B
    finally:
        for p in procs:
            p.terminate()
            p.wait(10)


def test_saturated_api_never_starves_the_health_endpoint(data, supervisor, runner_factory):
    import socket

    write_options(data, home_assistant_integration=True)
    r = start_runner(runner_factory, data, supervisor)
    assert wait_for(lambda: supervisor.messages, timeout=30)
    token, port = pin(supervisor.messages[0])
    idle = [socket.create_connection(("127.0.0.1", port)) for _ in range(20)]  # far more than the limit
    try:
        for _ in range(5):
            assert r.health() == 200  # the watchdog's endpoint has its own port and server
        assert r.sup.child is not None or r.sup.state == "starting"
    finally:
        for s in idle:
            s.close()
    assert wait_for(lambda: fetch(port, token)[0] == 200, timeout=20)  # the API recovers by itself


def test_status_api_is_https_only_with_a_fresh_pinned_certificate(data, supervisor, runner_factory, tmp_path):
    import glob
    import tempfile

    fingerprints = []
    for _ in range(2):
        write_options(data, home_assistant_integration=True)
        r = start_runner(runner_factory, data, supervisor)
        assert wait_for(lambda: len(supervisor.messages) > len(fingerprints), timeout=30)
        token, port = pin(supervisor.messages[-1])
        fingerprints.append(PINNED[port])
        assert wait_for(lambda p=port, t=token: fetch(p, t)[0] == 200, timeout=30)
        # Plain HTTP is not served at all.
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        with pytest.raises((http.client.HTTPException, OSError)):
            conn.request("GET", "/api/v1/status", headers={"Authorization": f"Bearer {token}"})
            conn.getresponse()
        conn.close()
        # A client pinning any other certificate refuses to talk (no token is sent before the check).
        with pytest.raises(AssertionError, match="pinned"):
            fetch(port, token, fingerprint="0" * 64)
        # The private key does not stay on disk.
        assert not glob.glob(f"{tempfile.gettempdir()}/meshbeacon-tls-*")
        r.stop()
    assert fingerprints[0] != fingerprints[1]  # a new certificate at every start
