# SPDX-License-Identifier: Apache-2.0
"""End-to-end behaviour of the supervisor with real RNS processes on loopback."""

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from meshbeacon.policy import Timings

from .conftest import FAST, free_port, wait_for, write_options


def child_sockets(pid: int) -> list[str]:
    """Socket inodes held by a process, resolved against /proc/net tables."""
    inodes = set()
    for fd in Path(f"/proc/{pid}/fd").iterdir():
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        m = re.match(r"socket:\[(\d+)\]", target)
        if m:
            inodes.add(m.group(1))
    found = []
    for table in ("tcp", "tcp6", "udp", "udp6", "unix", "raw", "raw6"):
        try:
            lines = Path(f"/proc/{pid}/net/{table}").read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            cols = line.split()
            inode = cols[9] if table != "unix" else cols[6]
            if inode in inodes:
                found.append(f"{table}:{line.strip()}")
    return found


def test_defaults_isolated_no_sockets_and_warning(data, runner_factory):
    write_options(data)
    r = runner_factory(data)
    assert wait_for(lambda: r.sup.child is not None and r.out.has("not connected to anyone"))
    time.sleep(3)
    assert r.sup.child is not None
    assert child_sockets(r.sup.child.proc.pid) == []  # no network or local sockets at all
    assert r.health() == 200


def test_connects_reconnects_without_restarting(data, peer, runner_factory):
    write_options(data, peers=[{"name": "Home", "host": "127.0.0.1", "port": peer.port}])
    r = runner_factory(data)
    assert wait_for(lambda: r.out.has("Connected to Home. Your node is online."), timeout=60), r.out.text()
    pid = r.sup.child.proc.pid
    peer.stop()
    assert wait_for(lambda: r.out.has("cannot reach any of your peers"), timeout=60), r.out.text()
    assert r.health() == 200  # connectivity is not health
    peer.start()
    assert wait_for(lambda: r.out.text().count("Connected to Home.") >= 2, timeout=90), r.out.text()
    assert r.sup.child.proc.pid == pid  # never restarted for a connectivity problem
    assert r.health() == 200


def test_crash_loop_is_bounded_and_health_stays_ok(data, runner_factory, monkeypatch):
    monkeypatch.setenv("FAKE_NODE", "crash")
    write_options(data)
    r = runner_factory(data, node_module="tests.integration.fake_nodes")
    assert wait_for(lambda: r.out.has("stopped trying"), timeout=60), r.out.text()
    launches = r.out.text().count("crashing on purpose")
    assert 3 <= launches <= 10
    time.sleep(2)
    assert r.out.text().count("crashing on purpose") == launches  # no further attempts
    assert r.sup.child is None and r.sup.state == "needs_attention"
    assert r.health() == 200
    assert r.out.has("will try again")  # breaker opened before giving up


def test_stalled_child_is_restarted(data, runner_factory, monkeypatch):
    monkeypatch.setenv("FAKE_NODE", "hang")
    write_options(data)
    timings = Timings(**{**FAST.__dict__, "status_stall": 2.0})
    r = runner_factory(data, node_module="tests.integration.fake_nodes", timings=timings)
    assert wait_for(lambda: r.out.has("stopped responding"), timeout=30), r.out.text()


def test_memory_guard(data, runner_factory, monkeypatch):
    monkeypatch.setenv("FAKE_NODE", "hog")
    write_options(data, memory_limit_mb=128)
    r = runner_factory(data, node_module="tests.integration.fake_nodes")
    assert wait_for(lambda: r.out.has("more memory than its limit"), timeout=60), r.out.text()


def test_damaged_identity_without_backup_never_starts_rns(data, runner_factory):
    write_options(data)
    r = runner_factory(data)
    assert wait_for(lambda: r.sup.child is not None)
    r.stop()
    storage = data / "reticulum" / "storage"
    (storage / "transport_identity").write_bytes(b"x" * 10)
    (data / "reticulum" / "meshbeacon-identity" / "identity.backup").unlink()
    r2 = runner_factory(data)
    assert wait_for(lambda: r2.out.has("has NOT created a new one"), timeout=60), r2.out.text()
    assert r2.sup.child is None
    assert (storage / "transport_identity").read_bytes() == b"x" * 10
    assert r2.health() == 200


def test_identity_corrupted_while_running_is_restored_before_rns_restart(data, runner_factory):
    write_options(data)
    r = runner_factory(data)
    assert wait_for(lambda: r.sup.child is not None)
    ident = data / "reticulum" / "storage" / "transport_identity"
    original = ident.read_bytes()
    ident.write_bytes(b"\xff" * 64)  # valid-looking but different key
    os.kill(r.sup.child.proc.pid, signal.SIGKILL)
    assert wait_for(lambda: r.out.has("restored from ito's verified backup copy"), timeout=60), r.out.text()
    assert wait_for(lambda: r.sup.child is not None and r.sup.child.proc.poll() is None)
    assert ident.read_bytes() == original


def test_safe_mode_after_repeated_app_starts(data, runner_factory):
    write_options(data)
    import hashlib

    h = hashlib.sha256((data / "options.json").read_bytes()).hexdigest()
    (data / "meshbeacon").mkdir(mode=0o700, exist_ok=True)
    now = time.time()
    (data / "meshbeacon" / "starts.json").write_text(
        json.dumps({"starts": [now - 40 + i for i in range(4)], "options_hash": h})
    )
    r = runner_factory(data)
    assert wait_for(lambda: r.out.has("paused to avoid a restart loop"), timeout=30), r.out.text()
    assert r.sup.child is None and r.health() == 200


def test_detailed_logs_contain_no_secrets_or_hashes(data, peer, runner_factory, monkeypatch):
    # Without PYTHONUNBUFFERED (as in the app image, where -I ignores it) RNS output must still
    # arrive promptly: regression test for block-buffered child output.
    monkeypatch.delenv("PYTHONUNBUFFERED", raising=False)
    secret = "correct horse battery"
    write_options(
        data,
        log_level="detailed",
        transport=True,
        peers=[
            {"name": "Home", "host": "127.0.0.1", "port": peer.port, "network_name": "testnet", "passphrase": secret}
        ],
    )
    r = runner_factory(data)
    assert wait_for(lambda: r.out.has("[reticulum]"), timeout=60)
    time.sleep(8)
    text = r.out.text()
    fp = json.loads((data / "reticulum" / "meshbeacon-identity" / "identity.json").read_text())["fingerprint"]
    key_hex = (data / "reticulum" / "storage" / "transport_identity").read_bytes().hex()
    from RNS.vendor.configobj import ConfigObj

    rpc_key = ConfigObj(str(data / "reticulum" / "config"))["reticulum"]["rpc_key"]
    for needle in (secret, fp, key_hex, key_hex[:32], rpc_key):
        assert needle not in text
    assert not re.search(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", text)
    assert "<redacted>" in text  # RNS did print hashes at this level, and they were removed


@pytest.mark.slow
def test_real_process_sigterm_and_health(data, tmp_path):
    write_options(data)
    port = free_port()
    env = dict(
        os.environ, MESHBEACON_DATA=str(data), MESHBEACON_HEALTH_PORT=str(port), MESHBEACON_HEALTH_HOST="127.0.0.1"
    )
    proc = subprocess.Popen([sys.executable, "-m", "meshbeacon.supervisor"], env=env, stdout=subprocess.PIPE, text=True)
    import urllib.request

    def healthy():
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
                return resp.status == 200
        except OSError:
            return False

    assert wait_for(healthy, timeout=30)
    time.sleep(3)
    proc.send_signal(signal.SIGTERM)
    assert proc.wait(timeout=20) == 0
    out = proc.stdout.read()
    assert "Stopping ito." in out


def test_rns_child_dies_with_supervisor(data, tmp_path):
    write_options(data)
    port = free_port()
    env = dict(
        os.environ, MESHBEACON_DATA=str(data), MESHBEACON_HEALTH_PORT=str(port), MESHBEACON_HEALTH_HOST="127.0.0.1"
    )
    proc = subprocess.Popen([sys.executable, "-m", "meshbeacon.supervisor"], env=env, stdout=subprocess.DEVNULL)

    def node_pids():
        # Scan /proc directly: minimal images (such as CI's python:3.13-slim) have no pgrep.
        wanted = ["meshbeacon.node", "--config", str(data / "reticulum")]
        pids = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                argv = (entry / "cmdline").read_bytes().decode(errors="replace").split("\0")
            except OSError:
                continue
            if all(w in argv for w in wanted):
                pids.append(int(entry.name))
        return pids

    assert wait_for(lambda: len(node_pids()) == 1, timeout=60)
    proc.kill()  # simulate a crash of the core
    proc.wait()
    assert wait_for(lambda: node_pids() == [], timeout=20), "orphaned Reticulum process survived"


def test_slow_preparation_keeps_health_ok(data, runner_factory, monkeypatch):
    """A prepare step slower than the heartbeat limit must not make the health check fail, or the
    Supervisor watchdog would restart the app while it is simply starting up (review item 2)."""
    monkeypatch.setenv("FAKE_PREPARE_SLEEP", "6")
    write_options(data)
    timings = Timings(**{**FAST.__dict__, "heartbeat_max_age": 2.0})
    r = runner_factory(data, prepare_module="tests.integration.fake_prepare", timings=timings)
    codes = []
    deadline = time.monotonic() + 7
    while time.monotonic() < deadline:
        codes.append(r.health())
        time.sleep(0.5)
    assert set(codes) == {200}, codes
    assert wait_for(lambda: r.sup.child is not None, timeout=30)


def test_preparation_timeout_needs_attention_without_unhealthy(data, runner_factory, monkeypatch):
    monkeypatch.setenv("FAKE_PREPARE_SLEEP", "30")
    write_options(data)
    timings = Timings(**{**FAST.__dict__, "heartbeat_max_age": 2.0, "prepare_timeout": 3.0})
    r = runner_factory(data, prepare_module="tests.integration.fake_prepare", timings=timings)
    codes = []
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        codes.append(r.health())
        time.sleep(0.5)
    assert set(codes) == {200}, codes
    assert wait_for(lambda: r.out.has("could not finish preparing"), timeout=10), r.out.text()
    assert r.sup.child is None and r.health() == 200
