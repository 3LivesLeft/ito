# SPDX-License-Identifier: Apache-2.0
"""Fixtures for real, isolated Reticulum instances. Everything binds to 127.0.0.1; nothing here
connects to any public network (roadmap LP-19)."""

from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from meshbeacon.paths import Paths
from meshbeacon.policy import Timings
from meshbeacon.supervisor import Supervisor

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "meshbeacon" / "core"
os.environ["PYTHONPATH"] = os.pathsep.join([str(CORE), str(REPO)])

pytestmark = pytest.mark.integration


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_for(predicate, timeout=30.0, interval=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class TestPeer:
    """A separate rnsd acting as the 'manually configured peer' (loopback only)."""

    def __init__(self, base: Path, port: int) -> None:
        self.dir = base / "peer"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.port = port
        (self.dir / "config").write_text(
            "[reticulum]\n  enable_transport = Yes\n  share_instance = No\n[logging]\n  loglevel = 2\n"
            "[interfaces]\n  [[Test server]]\n    type = TCPServerInterface\n    enabled = yes\n"
            f"    listen_ip = 127.0.0.1\n    listen_port = {port}\n"
        )
        self.proc: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "RNS.Utilities.rnsd", "--config", str(self.dir)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


class Output(io.TextIOBase):
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.lock = threading.Lock()
        self._partial = ""

    def write(self, s: str) -> int:
        with self.lock:
            text = self._partial + s
            *done, self._partial = text.split("\n")
            self.lines.extend(done)
        return len(s)

    def flush(self) -> None:
        pass

    def text(self) -> str:
        with self.lock:
            return "\n".join(self.lines)

    def has(self, needle: str) -> bool:
        return needle in self.text()


FAST = Timings(
    backoff_initial=0.1,
    backoff_max=0.5,
    breaker_failures=3,
    breaker_window=60,
    breaker_cooldown=0.5,
    breaker_max_openings=2,
    stable_after=3600,
    status_interval=1.0,
    status_stall=8.0,
    stop_grace=5.0,
    resource_check=0.5,
)


class Runner:
    def __init__(self, data: Path, timings: Timings = FAST, node_module: str = "meshbeacon.node") -> None:
        self.paths = Paths(data)
        self.out = Output()
        self.sup = Supervisor(
            self.paths,
            timings=timings,
            out=self.out,
            health_host="127.0.0.1",
            health_port=0,
            python=[sys.executable],
            node_module=node_module,
        )
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        self.sup.health.start()
        try:
            self.sup.boot()
            while not self._stop.is_set():
                self.sup.step(0.2)
        finally:
            self.sup.stop_child()
            self.sup.health.stop()

    def start(self) -> Runner:
        self.thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self.thread.join(30)

    def health(self) -> int:
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.sup.health.port}/health", timeout=5) as r:
                return int(r.status)
        except urllib.error.HTTPError as e:
            return int(e.code)


@pytest.fixture
def data(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir(mode=0o700)
    return d


def write_options(data: Path, **options) -> None:
    (data / "options.json").write_text(json.dumps(options))


@pytest.fixture
def peer(tmp_path: Path):
    p = TestPeer(tmp_path, free_port())
    p.start()
    yield p
    p.stop()


@pytest.fixture
def runner_factory():
    runners: list[Runner] = []

    def make(data: Path, **kw) -> Runner:
        r = Runner(data, **kw)
        runners.append(r)
        return r.start()

    yield make
    for r in runners:
        r.stop()
