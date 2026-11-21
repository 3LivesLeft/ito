# SPDX-License-Identifier: Apache-2.0
"""The core's control of its s6 services (services.py, ADR 0018).

s6 itself is exercised by the container tests; here a fake ``s6-svc``/``s6-svstat`` runner checks
the core's side: start once, the exit code in Popen's form, stop and kill, the FIFOs, and that the
core never falls back to running Reticulum as its own child where services are required.
"""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

import pytest

from meshbeacon import services as svc_mod
from meshbeacon.services import S6Process, Services, drain


class FakeS6:
    """Records commands and answers s6-svstat like s6 does: 'up pid exitcode signal'."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.status = "true 4242 -1 NA"

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        out = self.status if args[0].endswith("s6-svstat") else ""
        return subprocess.CompletedProcess(args, 0, out, "")


@pytest.fixture
def io_root(tmp_path):
    for name in ("reticulum", "prepare"):
        (tmp_path / "io" / name).mkdir(parents=True)
    for fifo in ("reticulum/out", "reticulum/status", "prepare/out", "prepare/result"):
        os.mkfifo(tmp_path / "io" / fifo)
    (tmp_path / "io" / "prepare" / "mode").write_text("")
    for name in ("reticulum", "rns-prepare"):
        (tmp_path / "service" / name / "supervise").mkdir(parents=True)
        os.mkfifo(tmp_path / "service" / name / "supervise" / "control")
    return tmp_path


def test_the_exit_code_reads_like_popen():
    s6 = FakeS6()
    s6.status = "false 4242 3 NA"
    assert S6Process(Path("/svc"), 0, s6).poll() == 3
    s6.status = "false 4242 -1 SIGKILL"
    assert S6Process(Path("/svc"), 0, s6).poll() == -signal.SIGKILL
    s6.status = "true 4242 -1 NA"
    assert S6Process(Path("/svc"), 0, s6).poll() is None


def test_a_live_process_of_another_user_counts_as_running(monkeypatch):
    s6 = FakeS6()
    s6.status = "false 1 0 NA"  # would say "exited", but the process is still there

    def kill(pid: int, sig: int) -> None:
        raise PermissionError  # another user's process: it exists

    monkeypatch.setattr(svc_mod.os, "kill", kill)
    assert S6Process(Path("/svc"), 1234, s6).poll() is None
    assert s6.calls == []  # no s6 call needed while the process is alive


def test_stop_and_kill_keep_the_service_down():
    s6 = FakeS6()
    process = S6Process(Path("/run/service/reticulum"), 0, s6)
    process.terminate()
    process.kill()
    assert s6.calls == [
        [svc_mod.S6_SVC, "-d", "/run/service/reticulum"],
        [svc_mod.S6_SVC, "-k", "-d", "/run/service/reticulum"],
    ]


def test_wait_times_out_like_popen():
    s6 = FakeS6()
    with pytest.raises(subprocess.TimeoutExpired):
        S6Process(Path("/svc"), 0, s6).wait(0.1)


def test_a_service_is_started_once_and_its_pid_read(io_root):
    s6 = FakeS6()
    services = Services(io_root / "service", io_root / "io", run=s6)
    process = services.start("reticulum")
    assert s6.calls[0][:4] == [svc_mod.S6_SVC, "-wu", "-T", "15000"]
    assert s6.calls[0][4:] == ["-o", str(io_root / "service" / "reticulum")]  # once: the core decides restarts
    assert process.pid == 4242 and process.returncode is None


def test_a_service_that_already_finished_reports_its_code(io_root):
    s6 = FakeS6()
    s6.status = "false 0 0 NA"
    services = Services(io_root / "service", io_root / "io", run=s6)
    assert services.start("rns-prepare").returncode == 0


def test_the_prepare_mode_is_allow_listed(io_root):
    services = Services(io_root / "service", io_root / "io", run=FakeS6())
    services.start_prepare("start")
    assert (io_root / "io" / "prepare" / "mode").read_text() == "start"
    with pytest.raises(ValueError):
        services.start_prepare("start; rm -rf /")


def test_fifos_never_block_or_end(io_root):
    services = Services(io_root / "service", io_root / "io", run=FakeS6())
    assert drain(services.node_out) == b""  # no writer yet: nothing, and no end-of-file
    with open(io_root / "io" / "reticulum" / "out", "wb") as writer:
        writer.write(b"line\n")
    assert drain(services.node_out) == b"line\n"
    assert drain(services.node_out) == b""  # the writer has gone: still not end-of-file


def test_availability_needs_supervision_and_channels(io_root):
    assert Services.available(io_root / "service", io_root / "io")
    assert not Services.available(io_root / "nothing", io_root / "io")


def test_the_core_fails_closed_without_its_services(tmp_path):
    """ADR 0018: where services are required, never start Reticulum as the core's own child."""
    import json

    from meshbeacon.paths import Paths
    from meshbeacon.supervisor import MSG_NO_ISOLATION, Supervisor

    data = tmp_path / "data"
    data.mkdir()
    (data / "options.json").write_text(json.dumps({"peers": []}))
    sup = Supervisor(Paths(data), health_port=0, require_services=True)
    assert sup.boot() is False
    assert sup.state == "needs_attention" and sup.attention == [MSG_NO_ISOLATION]
    assert sup.child is None
