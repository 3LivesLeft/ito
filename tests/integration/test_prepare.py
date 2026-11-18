# SPDX-License-Identifier: Apache-2.0
import json
import os
import stat
import subprocess
import sys

from RNS.vendor.configobj import ConfigObj

from .conftest import write_options


def run_prepare(data, mode="start"):
    env = dict(os.environ, MESHBEACON_DATA=str(data))
    result = data / "meshbeacon" / "r.json"
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
    for path, mode in modes(data / "meshbeacon"):
        assert mode == (0o700 if os.path.isdir(path) else 0o600), path
    fp = json.loads((data / "meshbeacon" / "identity.json").read_text())["fingerprint"]
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
