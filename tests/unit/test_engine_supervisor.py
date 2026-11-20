# SPDX-License-Identifier: Apache-2.0
"""The core's supervision of the messaging engine (M4 WP4, MS-15), with fake processes."""

from __future__ import annotations

import contextlib
import os
import socket
import threading
import time
from pathlib import Path

from meshbeacon import engine_supervisor as es
from meshbeacon.engine_supervisor import EngineSupervisor


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeProcess:
    def __init__(self) -> None:
        self.code: int | None = None
        self.signals: list[str] = []

    def poll(self) -> int | None:
        return self.code

    def wait(self, timeout: float | None = None) -> int:
        self.code = 0 if self.code is None else self.code
        return self.code

    def terminate(self) -> None:
        self.signals.append("term")
        self.code = 0

    def kill(self) -> None:
        self.signals.append("kill")
        self.code = -9


class Harness:
    def __init__(self, health: bool = True) -> None:
        self.clock = Clock()
        self.said: list[str] = []
        self.started: list[FakeProcess] = []
        self.healthy = health
        self.e = EngineSupervisor(self.start, self.said.append, self.clock, health=lambda: self.healthy)

    def start(self) -> FakeProcess:
        p = FakeProcess()
        self.started.append(p)
        return p

    def step(self, ready: bool = True, advance: float = 0.0) -> None:
        self.clock.now += advance
        self.e.step(ready)
        # let a health probe thread finish
        deadline = time.monotonic() + 2
        while self.e.probing and time.monotonic() < deadline:
            time.sleep(0.01)


def test_the_engine_waits_for_reticulum():
    h = Harness()
    h.step(ready=False)
    assert h.started == [] and h.e.state == "waiting"
    h.step(ready=True)
    assert len(h.started) == 1 and h.e.state == "running"


def test_a_crash_restarts_only_the_engine_with_back_off():
    h = Harness()
    h.step()
    h.started[0].code = 1
    h.step()
    assert h.e.state == "backoff" and any("exit code 1" in s for s in h.said)
    h.step(advance=es.BACKOFF[0] - 1)
    assert len(h.started) == 1  # still waiting
    h.step(advance=1)
    assert len(h.started) == 2 and h.e.state == "running"


def test_five_failures_in_thirty_minutes_pause_messaging():
    h = Harness()
    for n in range(es.PAUSE_AFTER):
        h.step(advance=400)  # past any back-off
        assert len(h.started) == n + 1
        h.started[-1].code = 3
        h.step()
    assert h.e.state == "paused" and h.said[-1] == es.MSG_PAUSED
    h.step(advance=10_000)
    assert len(h.started) == es.PAUSE_AFTER  # stays paused until the app restarts


def test_failures_outside_the_window_do_not_pause():
    h = Harness()
    for _ in range(es.PAUSE_AFTER + 2):
        h.step(advance=es.PAUSE_WINDOW / 3)
        h.started[-1].code = 1
        h.step()
    assert h.e.state == "backoff"


def test_a_hung_engine_is_killed_after_three_missed_answers():
    h = Harness(health=False)
    h.step()
    for _ in range(es.HEALTH_MISSES):
        h.step(advance=es.HEALTH_INTERVAL)
    h.step()
    assert h.started[0].signals == ["kill"] and h.e.state == "backoff"
    assert any("stopped responding" in s for s in h.said)


def test_a_healthy_engine_is_left_alone():
    h = Harness(health=True)
    h.step()
    for _ in range(10):
        h.step(advance=es.HEALTH_INTERVAL)
    assert h.started[0].signals == [] and h.e.misses == 0


def test_a_slow_health_check_never_blocks_the_core():
    gate = threading.Event()
    h = Harness()
    h.e.health = lambda: gate.wait(5)  # type: ignore[assignment,return-value]
    h.step()
    started = time.monotonic()
    h.clock.now += es.HEALTH_INTERVAL
    h.e.step(True)
    assert time.monotonic() - started < 0.5
    gate.set()


def test_stop_is_graceful_and_final():
    h = Harness()
    h.step()
    h.e.stop()
    assert h.started[0].signals == ["term"] and h.e.state == "stopped"
    h.step(advance=1000)
    assert len(h.started) == 1


def test_a_failed_start_counts_as_a_failure():
    h = Harness()

    def broken() -> FakeProcess:
        raise OSError("no")

    h.e._start = broken  # type: ignore[method-assign]
    h.step()
    assert h.e.state == "backoff" and "could not be started" in h.said[-1]


def test_disabled_without_the_marker(tmp_path):
    assert EngineSupervisor.enabled(tmp_path / "absent") is False
    (tmp_path / "marker").write_text("")
    assert EngineSupervisor.enabled(tmp_path / "marker") is True


def test_the_probe_talks_only_to_the_expected_user(tmp_path):
    path = Path(os.path.realpath(tmp_path)) / "e.sock"
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(path))
    server.listen(4)

    def answer() -> None:
        for _ in range(2):
            conn, _ = server.accept()
            with conn, contextlib.suppress(OSError):  # the probe hangs up on the wrong user
                if conn.makefile("rb").readline():
                    conn.sendall(b'{"ok": true}\n')

    threading.Thread(target=answer, daemon=True).start()
    try:
        assert es.probe(path, os.getuid()) is True
        assert es.probe(path, os.getuid() + 1) is False  # someone else serves it: no request sent
    finally:
        server.close()
    assert es.probe(path, os.getuid()) is False  # nobody there


def test_module_never_imports_the_engine_or_lxmf():
    text = Path(es.__file__).read_text()
    assert "import LXMF" not in text and "from .messaging" not in text and "import RNS" not in text
