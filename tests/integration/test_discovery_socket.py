# SPDX-License-Identifier: Apache-2.0
"""Socket-mode discovery with the real supervisor and a real Reticulum child (review M-1, L-1).

Loopback and temporary Unix sockets only. The relay runs in this test process; the container tests
repeat this with the real users and the root-only relay.
"""

from __future__ import annotations

import os
import socket
import stat
import threading
import time
from pathlib import Path

import pytest

from meshbeacon import api as api_mod
from meshbeacon import discovery_relay as relay_mod
from meshbeacon.api import RelayLink
from tests.unit.test_discovery_relay import FakeSupervisor, remove, short_dir

from .conftest import wait_for, write_options
from .test_metrics_rns import FAST_DISCOVERY


@pytest.fixture
def relay(monkeypatch):
    monkeypatch.setattr(api_mod, "RELAY_PEER_UID", os.getuid())
    base = short_dir()
    supervisor = FakeSupervisor(base / "supervisor.sock")
    path = base / "run" / "discovery.sock"
    stop = [False]
    thread = threading.Thread(
        target=relay_mod.serve,
        args=(path, str(base / "supervisor.sock")),
        kwargs={"allowed_uid": os.getuid(), "owner": os.getuid(), "stop": stop},
        daemon=True,
    )
    thread.start()
    assert wait_for(path.exists, timeout=5)
    yield supervisor, path
    stop[0] = True
    thread.join(3)
    supervisor.close()
    remove(base)


def socket_inodes(pid: int) -> set[int]:
    found = set()
    for name in os.listdir(f"/proc/{pid}/fd"):
        try:
            info = os.stat(f"/proc/{pid}/fd/{name}")
        except OSError:
            continue
        if stat.S_ISSOCK(info.st_mode):
            found.add(info.st_ino)
    return found


def test_reticulum_cannot_reach_the_relay_link(data, relay, runner_factory):
    """The core announces through its link; the Reticulum child holds no part of it."""
    supervisor, path = relay
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(path))
    inode = os.fstat(sock.fileno()).st_ino
    link = RelayLink(sock)
    write_options(data, home_assistant_integration=True)
    r = runner_factory(
        data,
        discovery_relay=link,
        socket_mode=True,
        hostname=lambda: "local-meshbeacon",
        discovery_timing=FAST_DISCOVERY,
    )
    assert wait_for(lambda: supervisor.requests, timeout=30), r.out.text()
    assert supervisor.requests[0]["auth"] is None
    assert r.out.has("Supervisor's local socket")
    assert wait_for(lambda: r.sup.child is not None and r.sup.state == "running", timeout=60), r.out.text()
    child = r.sup.child.proc.pid
    assert inode in socket_inodes(os.getpid())  # the core holds it ...
    assert inode not in socket_inodes(child)  # ... Reticulum does not
    environ = Path(f"/proc/{child}/environ").read_bytes()
    assert b"MESHBEACON_RELAY_FD" not in environ and b"SUPERVISOR_SOCKET" not in environ


def test_socket_mode_without_a_link_never_falls_back_to_tcp(data, supervisor, runner_factory):
    """No downgrade: a Supervisor socket but no relay link means no discovery, and no token used."""
    write_options(data, home_assistant_integration=True)
    r = runner_factory(
        data,
        supervisor_token="should-not-be-used",
        supervisor_url=supervisor.url,
        socket_mode=True,
        hostname=lambda: "local-meshbeacon",
        discovery_timing=FAST_DISCOVERY,
    )
    assert wait_for(lambda: r.out.has("link to the Supervisor's local socket could not be set up"), timeout=30), (
        r.out.text()
    )
    time.sleep(1.0)
    assert supervisor.attempts == 0 and supervisor.messages == []
