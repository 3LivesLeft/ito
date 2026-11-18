# SPDX-License-Identifier: Apache-2.0
"""v0.2 review: monitoring is reliable on its own and can never disturb Reticulum.

Discovery failures, Supervisor restarts, start-up order, token rotation, switching the
integration off and on, internal monitoring errors, and sustained API floods with slow clients.
Real, isolated Reticulum processes on loopback only.
"""

import os
import socket
import threading
import time
from pathlib import Path

import pytest

from meshbeacon import procinfo

from .conftest import wait_for, write_options
from .test_metrics_rns import fetch, start_runner


def peer_options(peer, **extra):
    return {
        "home_assistant_integration": True,
        "peers": [{"name": "Home", "host": "127.0.0.1", "port": peer.port}],
        **extra,
    }


def test_discovery_recovers_by_itself_when_the_supervisor_fails_at_first(data, peer, supervisor, runner_factory):
    supervisor.failures = 3
    write_options(data, **peer_options(peer))
    r = start_runner(runner_factory, data, supervisor)
    assert wait_for(lambda: supervisor.messages, timeout=30), r.out.text()
    assert supervisor.attempts >= 4
    text = r.out.text()
    assert text.count("could not reach the Home Assistant Supervisor") == 1  # once per outage, not per retry
    assert wait_for(lambda: r.out.has("can now see MeshBeacon's status again"), timeout=10)
    assert wait_for(lambda: r.out.has("Connected to Home."), timeout=60)  # Reticulum never waited for it


def test_supervisor_not_running_at_start_then_restarting(data, peer, supervisor, runner_factory):
    """Start-up order: MeshBeacon before the Supervisor; later the Supervisor restarts."""
    supervisor.down()
    write_options(data, **peer_options(peer))
    r = start_runner(runner_factory, data, supervisor)
    assert wait_for(lambda: r.out.has("Connected to Home."), timeout=60), r.out.text()
    assert supervisor.messages == []
    supervisor.up()
    assert wait_for(lambda: supervisor.messages, timeout=30), r.out.text()
    token = supervisor.messages[0]["config"]["token"]
    # Supervisor restart: down for a while, then up; the message is refreshed with the same token.
    supervisor.down()
    time.sleep(3)
    count = len(supervisor.messages)
    supervisor.up()
    assert wait_for(lambda: len(supervisor.messages) > count, timeout=30)
    assert {m["config"]["token"] for m in supervisor.messages} == {token}
    pid = r.sup.child.proc.pid
    assert fetch(r.sup.api_server.port, token)[0] == 200 and r.sup.child.proc.pid == pid


def test_token_rotates_each_start_and_disable_withdraws(tmp_path, data, supervisor, runner_factory):
    tokens = []
    for _ in range(3):
        write_options(data, home_assistant_integration=True)
        r = start_runner(runner_factory, data, supervisor)
        assert wait_for(lambda: len(supervisor.messages) > len(tokens), timeout=30)
        tokens.append(supervisor.messages[-1]["config"]["token"])
        r.stop()
    assert len(set(tokens)) == 3  # a new key at every start
    assert (data / "meshbeacon" / "discovery.json").exists()

    write_options(data, home_assistant_integration=False)  # switched off
    r = start_runner(runner_factory, data, supervisor)
    assert wait_for(lambda: supervisor.deleted == ["/discovery/abc123"], timeout=30)
    assert wait_for(lambda: not (data / "meshbeacon" / "discovery.json").exists(), timeout=10)
    assert r.sup.api_server is None
    r.stop()

    write_options(data, home_assistant_integration=True)  # and on again
    r = start_runner(runner_factory, data, supervisor)
    assert wait_for(lambda: len(supervisor.messages) == 4, timeout=30)
    assert supervisor.messages[-1]["config"]["token"] not in tokens


def test_old_tokens_stop_working(data, supervisor, runner_factory):
    write_options(data, home_assistant_integration=True)
    r = start_runner(runner_factory, data, supervisor)
    assert wait_for(lambda: supervisor.messages, timeout=30)
    first = supervisor.messages[0]["config"]["token"]
    r.stop()
    r = start_runner(runner_factory, data, supervisor)
    assert wait_for(lambda: len(supervisor.messages) == 2, timeout=30)
    port = r.sup.api_server.port
    assert wait_for(lambda: fetch(port, supervisor.messages[1]["config"]["token"])[0] == 200, timeout=30)
    assert fetch(port, first)[0] == 401  # a stale discovery message's key is useless


def test_monitoring_errors_never_reach_reticulum(data, peer, supervisor, runner_factory, monkeypatch):
    write_options(data, **peer_options(peer))
    r = start_runner(runner_factory, data, supervisor)
    assert wait_for(lambda: r.out.has("Connected to Home.") and supervisor.messages, timeout=60), r.out.text()
    pid = r.sup.child.proc.pid

    def broken(*_a, **_k):
        raise RuntimeError("simulated")

    monkeypatch.setattr(r.sup.collector, "snapshot", broken)
    for name in ("update", "resources", "child_started", "child_stopped", "record_failure"):
        monkeypatch.setattr(r.sup.collector, name, broken)
    time.sleep(5)
    assert r.out.text().count("status reporting for Home Assistant hit an unexpected problem") <= 1
    assert r.thread.is_alive() and r.sup.child is not None and r.sup.child.proc.pid == pid
    assert r.health() == 200
    assert r.sup.state == "running"


def _rss_kb(pid: int) -> int:
    return (procinfo.memory_bytes(pid) or 0) // 1024


def _threads(pid: int) -> int:
    return len(os.listdir(f"/proc/{pid}/task"))


@pytest.mark.slow
def test_sustained_flood_and_slow_clients(data, peer, supervisor, runner_factory):
    """30 s of hostile traffic on both internal ports: the watchdog is always answered, Reticulum
    stays connected and is never restarted, and the core's threads and memory stay bounded."""
    write_options(data, **peer_options(peer))
    r = start_runner(runner_factory, data, supervisor)
    assert wait_for(lambda: r.out.has("Connected to Home.") and supervisor.messages, timeout=60), r.out.text()
    token, api_port = supervisor.messages[0]["config"]["token"], r.sup.api_server.port
    health_port = r.sup.health.port
    pid, core = r.sup.child.proc.pid, os.getpid()  # the runner's supervisor lives in this process
    rss_before, threads_before = _rss_kb(core), _threads(core)
    stop = threading.Event()
    counts = {"ok": 0, "refused": 0, "errors": 0}

    def hammer(auth):
        while not stop.is_set():
            try:
                status = fetch(api_port, auth)[0]
                counts["ok" if status == 200 else "refused"] += 1
            except OSError:
                counts["errors"] += 1

    def trickle(port):
        while not stop.is_set():
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=30) as s:
                    while not stop.is_set():
                        s.sendall(b"G")
                        time.sleep(1)
            except OSError:
                time.sleep(0.1)

    workers = [threading.Thread(target=hammer, args=(a,), daemon=True) for a in [token] * 4 + ["wrong"] * 8]
    workers += [threading.Thread(target=trickle, args=(p,), daemon=True) for p in [api_port] * 10 + [health_port] * 10]
    for w in workers:
        w.start()
    health, peak_threads, peak_rss = [], 0, 0
    end = time.monotonic() + 30
    while time.monotonic() < end:
        health.append(r.health())
        peak_threads = max(peak_threads, _threads(core) - len(workers))
        peak_rss = max(peak_rss, _rss_kb(core))
        time.sleep(1)
    stop.set()
    for w in workers:
        w.join(15)
    print(
        f"flood: {counts}; health {health.count(200)}/{len(health)} ok; core threads "
        f"{threads_before} → peak {peak_threads}; core RSS {rss_before // 1024} → peak {peak_rss // 1024} MiB"
    )
    assert counts["ok"] > 0 and counts["refused"] > 0
    assert health.count(200) == len(health)  # the watchdog's checks were all answered
    assert r.sup.child is not None and r.sup.child.proc.pid == pid  # Reticulum never restarted
    assert r.sup.snapshot is not None and r.sup.snapshot.up == ("Home",)  # and stayed connected
    assert peak_threads <= threads_before + 4 + 16 + 4 + 16  # bounded by both servers' limits and timers
    assert peak_rss - rss_before < 30 * 1024
    assert "Traceback" not in r.out.text()
    assert wait_for(lambda: fetch(api_port, token)[0] == 200, timeout=20)  # recovers at once
    assert Path(f"/proc/{pid}").exists()
