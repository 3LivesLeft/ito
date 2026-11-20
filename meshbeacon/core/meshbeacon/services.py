# SPDX-License-Identifier: Apache-2.0
"""Reticulum and its prepare step as s6 services under their own user (ADR 0018, gate IS-1).

In the app image, Reticulum (``reticulum``) and the prepare step (``rns-prepare``) are s6 services
that start *down* and run as ``mb-rns``. The root init step and the core's start step grant the
core's group control of exactly these services (``s6-svperms``). The core keeps every decision
(when to start, the restart policy of ADR 0005, the memory watchdog, log redaction) and acts
through ``s6-svc`` and ``s6-svstat``:

- ``S6Process`` offers the part of ``subprocess.Popen`` the supervisor uses (``pid``, ``poll``,
  ``wait``, ``terminate``, ``kill``), so the supervisor treats both kinds of child the same way.
- Output and status arrive through FIFOs in ``/run/meshbeacon-io/<service>/`` that the root init
  step created (root:meshbeacon, 0660). The service's run script opens them as root before it drops
  to ``mb-rns``, so Reticulum's user can open none of them itself. The core holds each FIFO open for
  reading *and* writing, so a service that exits never leaves it at end-of-file.

Outside the app image (development and tests) the supervisor starts its children directly, as
before; nothing here is used then.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

SERVICE_ROOT = Path("/run/service")
IO_ROOT = Path("/run/meshbeacon-io")
S6_SVC = "/command/s6-svc"
S6_SVSTAT = "/command/s6-svstat"
MODES = ("start", "restart")

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)


def open_fifo(path: Path) -> int:
    """Open a FIFO for reading without ever blocking or reaching end-of-file (see above)."""
    return os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)


class S6Process:
    """One run of an s6 service, as the supervisor sees a child process."""

    stdout = None  # output arrives through a FIFO the supervisor reads

    def __init__(self, service: Path, pid: int, run: Runner, exited: int | None = None) -> None:
        self.service = service
        self.pid = pid
        self._run = run
        self.returncode: int | None = exited

    def _status(self) -> tuple[bool, int, int | None]:
        """(up, pid, exit code in Popen's form: negative for a signal; None while unknown)."""
        out = self._run([S6_SVSTAT, "-o", "up,pid,exitcode,signal", str(self.service)]).stdout.split()
        if len(out) != 4:
            return True, self.pid, None  # cannot tell: assume still running
        up, pid, code, sig = out[0] == "true", int(out[1]), int(out[2]), out[3]
        if up:
            return True, pid, None
        if code >= 0:
            return False, pid, code
        with contextlib.suppress(KeyError):
            return False, pid, -int(signal.Signals[sig])
        return False, pid, -1

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        if self.pid > 0:
            try:
                os.kill(self.pid, 0)  # another user's process: EPERM means it is alive
            except ProcessLookupError:
                pass
            except PermissionError:
                return None
            else:
                return None
        up, _pid, code = self._status()
        if not up and code is not None:
            self.returncode = code
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        deadline = None if timeout is None else time.monotonic() + timeout
        while (code := self.poll()) is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(str(self.service), timeout or 0)
            time.sleep(0.05)
        return code

    def terminate(self) -> None:
        self._run([S6_SVC, "-d", str(self.service)])  # SIGTERM, and keep it down

    def kill(self) -> None:
        self._run([S6_SVC, "-k", "-d", str(self.service)])  # SIGKILL, and keep it down


class Services:
    """The core's view of the s6 services it controls, and their FIFOs."""

    def __init__(self, service_root: Path = SERVICE_ROOT, io_root: Path = IO_ROOT, run: Runner = _run) -> None:
        self.service_root = service_root
        self.io_root = io_root
        self._run = run
        self.node_out = open_fifo(io_root / "reticulum" / "out")
        self.node_status = open_fifo(io_root / "reticulum" / "status")
        self.prepare_out = open_fifo(io_root / "prepare" / "out")
        self.prepare_result = open_fifo(io_root / "prepare" / "result")
        # The messaging engine's output, only in a development image that carries it (M4).
        engine_out = io_root / "messaging" / "out"
        self.engine_out = open_fifo(engine_out) if engine_out.exists() else None

    def has(self, name: str) -> bool:
        return (self.service_root / name / "supervise" / "control").exists()

    @classmethod
    def available(cls, service_root: Path = SERVICE_ROOT, io_root: Path = IO_ROOT) -> bool:
        return all(
            (service_root / name / "supervise" / "control").exists() for name in ("reticulum", "rns-prepare")
        ) and all((io_root / d / f).exists() for d, f in (("reticulum", "out"), ("prepare", "result")))

    def start(self, name: str, timeout: float = 15.0) -> S6Process:
        """Run the service once (no automatic restart: the core decides) and return its process."""
        service = self.service_root / name
        ms = str(int(timeout * 1000))
        result = self._run([S6_SVC, "-wu", "-T", ms, "-o", str(service)])
        if result.returncode != 0:
            raise OSError(f"s6 could not start {name}")
        process = S6Process(service, 0, self._run)
        up, pid, code = process._status()
        process.pid = pid if pid > 0 else 0
        if not up and code is not None:
            process.returncode = code  # it has already finished
        return process

    def start_prepare(self, mode: str) -> S6Process:
        if mode not in MODES:
            raise ValueError("unknown prepare mode")
        (self.io_root / "prepare" / "mode").write_text(mode)
        drain(self.prepare_result)  # nothing left over from an earlier run
        return self.start("rns-prepare")


def drain(fd: int, limit: int = 1 << 20) -> bytes:
    """Everything that can be read from a non-blocking descriptor now (at most ``limit`` bytes)."""
    data = b""
    while len(data) < limit:
        try:
            chunk = os.read(fd, 65536)
        except BlockingIOError:
            break
        if not chunk:
            break
        data += chunk
    return data
