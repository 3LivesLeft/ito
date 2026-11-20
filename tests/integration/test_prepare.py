# SPDX-License-Identifier: Apache-2.0
import json
import os
import stat
import subprocess
import sys

import pytest
from RNS.vendor.configobj import ConfigObj

from .conftest import write_options


def run_prepare(data, mode="start"):
    env = dict(os.environ, MESHBEACON_DATA=str(data))
    result = data.parent / "prepare-result.json"  # the core's channel, outside Reticulum's folders
    proc = subprocess.run(
        [sys.executable, "-m", "meshbeacon.prepare", "--mode", mode, "--result", str(result)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(result.read_text()), proc.stdout + proc.stderr


def modes(root):
    for dirpath, _dirs, files in os.walk(root):
        yield dirpath, stat.S_IMODE(os.stat(dirpath).st_mode)
        for f in files:
            p = os.path.join(dirpath, f)
            yield p, stat.S_IMODE(os.stat(p).st_mode)


def test_first_and_second_start(data):
    write_options(data, peers=[{"name": "Home", "host": "127.0.0.1", "port": 4242}])
    r1, out1 = run_prepare(data)
    assert r1["ok"] and r1["identity"] == "created"
    r2, _ = run_prepare(data)
    assert r2["ok"] and r2["identity"] == "unchanged"
    cfg = ConfigObj(str(data / "reticulum" / "config"))
    assert cfg["reticulum"]["share_instance"] == "No"
    assert list(cfg["interfaces"]) == ["Home"]
    for path, mode in modes(data / "reticulum"):
        assert mode == (0o700 if os.path.isdir(path) else 0o600), path
    # ADR 0018: the prepare step (Reticulum's user) never touches the core's folder.
    assert not (data / "meshbeacon").exists()
    fp = json.loads((data / "reticulum" / "meshbeacon-identity" / "identity.json").read_text())["fingerprint"]
    assert fp not in json.dumps(r1) + out1


def test_invalid_options_need_attention_without_touching_identity(data):
    write_options(data, peers=[{"name": "Home", "host": "bad\nhost", "port": 4242}])
    r, _ = run_prepare(data)
    assert not r["ok"]
    assert any("host" in m for m in r["attention"])
    assert not (data / "reticulum" / "storage" / "transport_identity").exists()
    assert not (data / "reticulum" / "config").exists()


def test_rpc_key_is_new_each_start(data):
    write_options(data)
    run_prepare(data)
    k1 = ConfigObj(str(data / "reticulum" / "config"))["reticulum"]["rpc_key"]
    run_prepare(data)
    k2 = ConfigObj(str(data / "reticulum" / "config"))["reticulum"]["rpc_key"]
    assert k1 != k2 and len(bytes.fromhex(k1)) == 32


def test_restart_mode_restores_damaged_identity(data):
    write_options(data)
    run_prepare(data)
    ident = data / "reticulum" / "storage" / "transport_identity"
    original = ident.read_bytes()
    ident.write_bytes(b"\x00" * 7)
    r, _ = run_prepare(data, mode="restart")
    assert r["ok"] and r["identity"] == "restored"
    assert ident.read_bytes() == original


def test_oversized_cache_cleared(data):
    write_options(data)
    run_prepare(data)
    cache = data / "reticulum" / "storage" / "cache"
    cache.mkdir(exist_ok=True)
    with open(cache / "big", "wb") as f:
        f.truncate(0)
        f.write(b"\0" * (101 * 1024 * 1024))
    r, _ = run_prepare(data)
    assert r["ok"] and not (cache / "big").exists()
    assert any("cache" in m for m in r["info"])


def test_storage_floor_stops_before_identity(data, monkeypatch):
    import shutil as _shutil

    from meshbeacon import prepare as prep
    from meshbeacon.paths import Paths

    write_options(data)
    usage = _shutil.disk_usage(data)
    monkeypatch.setattr(prep.shutil, "disk_usage", lambda _p: usage._replace(free=100 * 1024 * 1024))
    r = prep.prepare(Paths(data), mode="start")
    assert not r.ok and "200 MB" in r.attention[0]
    assert not (data / "reticulum" / "storage" / "transport_identity").exists()
    monkeypatch.setattr(prep.shutil, "disk_usage", lambda _p: usage._replace(free=500 * 1024 * 1024))
    r = prep.prepare(Paths(data), mode="start")
    assert r.ok and any("below 1 GB" in w for w in r.warnings)


@pytest.mark.slow
def test_interrupted_first_start_never_breaks_identity(tmp_path):
    """Kill the real prepare step at random points during a first start (30 times); the next start
    must always succeed, with a complete identity that is never silently replaced afterwards."""
    import random
    import signal
    import time

    rng = random.Random(42)
    for i in range(30):
        data = tmp_path / f"d{i}"
        data.mkdir()
        write_options(data)
        env = dict(os.environ, MESHBEACON_DATA=str(data))
        proc = subprocess.Popen(
            [sys.executable, "-m", "meshbeacon.prepare", "--mode", "start", "--result", str(tmp_path / f"r{i}")],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(rng.uniform(0.05, 1.5))
        proc.send_signal(signal.SIGKILL)
        proc.wait()
        ident = data / "reticulum" / "storage" / "transport_identity"
        if ident.exists():
            assert len(ident.read_bytes()) == 64, f"partial identity after kill {i}"
        before = ident.read_bytes() if ident.exists() else None
        r, _ = run_prepare(data)
        assert r["ok"], (i, r)
        if before is not None:
            assert ident.read_bytes() == before, "identity replaced after an interrupted start"


def test_the_shared_instance_follows_the_messaging_option(data):
    """D-M4-8, IS-3a: Reticulum shares its instance only while messaging is switched on, and
    switching messaging on or off never touches the node's identity."""
    write_options(data, messaging_enabled=False)
    r1, _ = run_prepare(data)
    assert r1["ok"] and ConfigObj(str(data / "reticulum" / "config"))["reticulum"]["share_instance"] == "No"
    write_options(data, messaging_enabled=True)
    r2, _ = run_prepare(data)
    assert r2["ok"] and r2["identity"] == "unchanged"
    assert ConfigObj(str(data / "reticulum" / "config"))["reticulum"]["share_instance"] == "Yes"
    write_options(data, messaging_enabled=False)
    r3, _ = run_prepare(data)
    assert r3["identity"] == "unchanged"
    assert ConfigObj(str(data / "reticulum" / "config"))["reticulum"]["share_instance"] == "No"


def test_a_selected_public_network_reaches_the_reticulum_configuration(data):
    """The network selector configures the real interface RNS reads; it is not just a label.
    (Only the configuration is written here: prepare never starts Reticulum or connects.)"""
    write_options(data, network="ratspeak_emerald", peers=[{"name": "Home", "host": "127.0.0.1", "port": 4242}])
    r, _ = run_prepare(data)
    assert r["ok"], r
    cfg = ConfigObj(str(data / "reticulum" / "config"))
    assert list(cfg["interfaces"]) == ["Ratspeak Emerald", "Home"]
    emerald = cfg["interfaces"]["Ratspeak Emerald"]
    endpoint = (emerald["type"], emerald["target_host"], emerald["target_port"])
    assert endpoint == ("TCPClientInterface", "2.ratspeak.org", "4242")


def test_an_unknown_network_needs_attention(data):
    write_options(data, network="not-a-network")
    r, _ = run_prepare(data)
    assert not r["ok"] and r["problem"] == "options"
    assert any("'network' must be one of" in m for m in r["attention"])
    assert not (data / "reticulum" / "config").exists()
