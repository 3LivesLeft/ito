# SPDX-License-Identifier: Apache-2.0
"""The long-running MeshBeacon core: supervises the RNS child with bounded recovery.

Runs as the unprivileged ``meshbeacon`` user. Deliberately does not import RNS (see
:mod:`meshbeacon.prepare` and :mod:`meshbeacon.node`), so its own memory use stays small.
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import json
import os
import platform
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import IO, Any

from . import __version__, fsutil, procinfo
from .api import ApiServer, Discovery, RelayLink, StatusStore, TlsError, container_hostname, make_tls, new_token
from .connectivity import Connectivity, Snapshot, describe, evaluate, human_bytes
from .health import HealthServer, Heartbeat
from .logfilter import RateLimiter, Redactor
from .metrics import Collector
from .paths import Paths
from .policy import RestartPolicy, StartHistory, Timings
from .prepare import FREE_SPACE_FLOOR, FREE_SPACE_WARN
from .relay_link import RELAY_FD_ENV, TOKEN, TOKEN_FD_ENV
from .services import Services, drain
from .settings import Settings, ValidationError, parse_options

MSG_GAVE_UP = (
    "✖ The Reticulum service keeps failing, so MeshBeacon has stopped trying. "
    "Fix the cause shown above, then restart the app."
)
MSG_STORAGE = (
    "✖ Free storage has fallen below 200 MB, so MeshBeacon has stopped Reticulum to protect "
    "Home Assistant. Free some space and restart the app."
)
MSG_DISCOVERY_SOCKET = "Home Assistant is told about MeshBeacon through the Supervisor's local socket."
MSG_DISCOVERY_UNAVAILABLE = (
    "⚠ Home Assistant cannot be told about MeshBeacon: the link to the Supervisor's local socket could "
    "not be set up. The node works normally; restart the app to try again."
)
MSG_NO_ISOLATION = (
    "✖ MeshBeacon could not set up the separate Reticulum service it runs under its own user, so it "
    "has not started Reticulum. Restart the app; if this repeats, please report it."
)
MSG_RELAY_LOST = (
    "⚠ The link to the discovery relay was lost (the relay restarted). Home Assistant keeps showing "
    "MeshBeacon's status until the next app start, but MeshBeacon cannot refresh it: restart the app "
    "to restore the link."
)
MSG_DISCOVERY_TCP = (
    "Home Assistant is told about MeshBeacon over the Supervisor's internal network (this Supervisor "
    "has no app socket yet)."
)
MSG_API_STARTED = (
    "Home Assistant integration: on. MeshBeacon shares its status with Home Assistant over the "
    "internal network only, protected by a key that changes at every start."
)
MSG_DISCOVERY_FAILED = (
    "⚠ MeshBeacon could not reach the Home Assistant Supervisor to share its status. The node works "
    "normally, and MeshBeacon will keep trying by itself."
)
MSG_DISCOVERY_OK = (
    "Home Assistant has been told about MeshBeacon's status. In Home Assistant, open Settings → "
    'Devices & services and add "MeshBeacon" when it is shown as discovered. If it is not shown, '
    "install the MeshBeacon integration first and restart Home Assistant (see the app's "
    "Documentation tab)."
)
MSG_DISCOVERY_RECOVERED = "Home Assistant can now see MeshBeacon's status again."
MSG_MONITORING_ERROR = (
    "⚠ MeshBeacon's status reporting for Home Assistant hit an unexpected problem ({name}). "
    "Reticulum is not affected. If this repeats, please report it."
)
# Problem codes shown in Home Assistant (docs/research/v0.2-observability.md §1). Keep in step with
# custom_components/meshbeacon/const.py PROBLEMS.
PROBLEMS = (
    "none",
    "isolated",
    "peers_unreachable",
    "some_peers_unreachable",
    "reticulum_restarting",
    "reticulum_failing",
    "restart_loop_paused",
    "options",
    "storage",
    "identity",
    "configuration",
    "data_folder",
    "preparation_failed",
    "unexpected",
)
SUPERVISOR_TOKEN_ENV = "SUPERVISOR_TOKEN"  # noqa: S105 - the variable name, not a secret
SUPERVISOR_SOCKET_ENV = "SUPERVISOR_SOCKET"


@functools.cache
def installed_rns_version() -> str | None:
    """The installed RNS version (looked up once: the lookup scans site-packages)."""
    try:
        return metadata.version("rns")
    except metadata.PackageNotFoundError:
        return None


class LineBuffer:
    """Accumulates bytes from a non-blocking fd and yields complete, bounded lines."""

    def __init__(self, limit: int = 8192) -> None:
        self.buf = b""
        self.limit = limit

    def feed(self, data: bytes) -> list[str]:
        self.buf += data
        lines: list[str] = []
        while b"\n" in self.buf:
            raw, self.buf = self.buf.split(b"\n", 1)
            lines.append(raw.decode("utf-8", "replace"))
        if len(self.buf) > self.limit:  # unterminated flood: emit and drop
            lines.append(self.buf[: self.limit].decode("utf-8", "replace"))
            self.buf = b""
        return lines


@dataclass
class Child:
    proc: subprocess.Popen[bytes]
    started: float
    out_fd: int
    status_fd: int
    out_buf: LineBuffer
    status_buf: LineBuffer
    last_status: float
    stable: bool = False
    owns_fds: bool = True  # False for an s6 service: its FIFOs stay open for the next run


def default_python() -> list[str]:
    """Python command for child processes.

    In the app image the core is installed in site-packages, so children run in isolated mode
    (``-I``: PYTHON* variables, the user site and the working directory are ignored). From a source
    checkout (development and tests) isolated mode could not import the package, so it is not used.
    """
    import sysconfig

    installed = Path(__file__).resolve().is_relative_to(Path(sysconfig.get_paths()["purelib"]).resolve())
    return [sys.executable, "-I"] if installed else [sys.executable]


def module_command(python: list[str], module: str) -> list[str]:
    # -u: RNS logs with print(); without it, output to our pipe would be block-buffered (and -I
    # ignores PYTHONUNBUFFERED), delaying log lines or losing them if the process crashes.
    return [*python, "-u", "-m", module]


class Supervisor:
    def __init__(
        self,
        paths: Paths,
        *,
        timings: Timings | None = None,
        out: IO[str] | None = None,
        health_host: str = "0.0.0.0",  # container-internal; no port is published
        health_port: int = 8099,
        python: list[str] | None = None,
        node_module: str = "meshbeacon.node",
        prepare_module: str = "meshbeacon.prepare",
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        api_host: str = "0.0.0.0",  # container-internal; no port is published
        api_port: int = 8100,
        supervisor_token: str | None = None,
        supervisor_url: str | None = None,
        discovery_relay: RelayLink | None = None,
        socket_mode: bool = False,
        services: Services | None = None,
        require_services: bool = False,
        hostname: Callable[[], str] = container_hostname,
        discovery_timing: dict[str, float] | None = None,
    ) -> None:
        self.paths = paths
        self.t = timings or Timings()
        self.out = out or sys.stdout
        self.python = python or default_python()
        self.node_module = node_module
        self.prepare_module = prepare_module
        self.clock = clock
        self.wall = wall
        self.heartbeat = Heartbeat(clock)
        self.health = HealthServer(self.heartbeat, health_host, health_port, self.t.heartbeat_max_age)
        self.redact = Redactor()
        self.limiter = RateLimiter(clock=clock)
        self.policy = RestartPolicy(self.t)
        self.settings: Settings | None = None
        self.child: Child | None = None
        self.stopping = False
        self.attention: list[str] | None = None
        self.last_failure = 0.0
        self.next_attempt: float | None = None
        self.snapshot: Snapshot | None = None
        self.cpu_samples: deque[tuple[float, float]] = deque()
        self.timers: dict[str, float] = {}
        self.selector = selectors.DefaultSelector()
        self.state = "starting"
        self.problem_code = "none"
        self.collector = Collector(clock=clock, wall=wall)
        self.api_host = api_host
        self.api_port = api_port
        self.api_store: StatusStore | None = None
        self.api_server: ApiServer | None = None
        self._supervisor_token = supervisor_token
        self.supervisor_url = supervisor_url
        self.discovery_relay = discovery_relay
        # ADR 0018: in the app image, Reticulum and the prepare step are s6 services under their
        # own user; otherwise (development, tests) they are this process's children.
        self.services = services
        # True in the app image: never fall back to running Reticulum as this process's child.
        self.require_services = require_services
        # True where the Supervisor provides the app socket: then the token is never used, even if
        # the relay link is missing (no fall-back to the internal network).
        self.socket_mode = socket_mode or discovery_relay is not None
        self.hostname = hostname
        self.discovery_results: list[bool] = []  # appended by the discovery thread
        self.discovery_ok: bool | None = None
        self.discovery_stop = threading.Event()
        self.discovery_timing = discovery_timing or {}  # shorter back-off in tests only

    # -- output ------------------------------------------------------------------------------
    def say(self, message: str) -> None:
        for line in message.splitlines() or [""]:
            self.out.write(f"[meshbeacon] {self.redact(line)}\n")
        self.out.flush()

    def forward(self, source: str, line: str) -> None:
        if not line.strip():
            return
        if self.limiter.allow():
            self.out.write(f"[{source}] {self.redact(line)}\n")
            self.out.flush()

    def flush_suppressed(self) -> None:
        count = self.limiter.take_suppressed()
        if count:
            self.say(f"({count} Reticulum log lines suppressed to protect storage.)")

    def due(self, name: str, interval: float, *, first: bool = False) -> bool:
        now = self.clock()
        last = self.timers.get(name)
        if last is None:
            self.timers[name] = now
            return first
        if now - last >= interval:
            self.timers[name] = now
            return True
        return False

    # -- lifecycle ---------------------------------------------------------------------------
    def options_hash(self) -> str:
        try:
            return hashlib.sha256(self.paths.options.read_bytes()).hexdigest()
        except OSError:
            return ""

    def load_settings(self) -> None:
        try:
            self.settings = parse_options(json.loads(self.paths.options.read_text(encoding="utf-8")))
        except FileNotFoundError:
            self.settings = parse_options({})
        except (OSError, ValueError, ValidationError):
            self.settings = None
        if self.settings is not None:
            self.redact = Redactor(self.settings.secrets)
            self.monitor(self.collector.configure, tuple(p.name for p in self.settings.peers))

    def startup_report(self) -> None:
        try:
            rns_version = metadata.version("rns")
        except metadata.PackageNotFoundError:
            rns_version = "unknown"
        self.say(f"MeshBeacon {__version__} starting (Reticulum {rns_version}, {platform.machine()}).")
        s = self.settings
        if s is not None:
            self.say(f"Transport mode: {'on — sharing your connection with others' if s.transport else 'off'}.")
            if s.peers:
                for p in s.peers:
                    self.say(f"Peer configured: {p.name} ({p.host}, port {p.port}).")
            self.say(f"Log detail: {s.log_level}. Memory limit for Reticulum: {s.memory_limit_mb} MB.")
            if not s.home_assistant_integration:
                self.say("Home Assistant integration: off.")

    def enter_attention(self, messages: list[str], problem: str) -> None:
        self.state = "needs_attention"
        self.problem_code = problem if problem in PROBLEMS else "unexpected"
        self.attention = messages
        self.stop_child()
        for m in messages:
            self.say(m)
        self.timers["attention"] = self.clock()
        self.publish()  # state changes reach Home Assistant without waiting for the next interval

    def history(self) -> StartHistory:
        return StartHistory.from_json(self.t, fsutil.read_json(self.paths.start_history))

    def save_history(self, history: StartHistory) -> None:
        try:
            fsutil.atomic_write_json(self.paths.start_history, history.to_json())
        except OSError:
            self.say("⚠ MeshBeacon could not save its start history (storage problem).")

    def child_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["MESHBEACON_DATA"] = str(self.paths.data)
        env["MESHBEACON_OPTIONS"] = str(self.paths.options)
        env.pop(SUPERVISOR_TOKEN_ENV, None)  # never handed to prepare or Reticulum
        env.pop(SUPERVISOR_SOCKET_ENV, None)
        env.pop(RELAY_FD_ENV, None)
        env.pop(TOKEN_FD_ENV, None)
        return env

    def wait_responsive(self, proc: subprocess.Popen[bytes], timeout: float) -> bool:
        """Wait for ``proc`` while keeping the heartbeat fresh; False if it ran out of time.

        Waiting for a bounded subprocess is not "unresponsive", so the Supervisor watchdog must not
        see a stale heartbeat while it happens (review item 2).
        """
        deadline = self.clock() + timeout
        while True:
            self.heartbeat.beat()
            try:
                proc.wait(timeout=0.5)
                return True
            except subprocess.TimeoutExpired:
                if self.clock() >= deadline:
                    return False

    def run_prepare(self, mode: str) -> dict[str, Any] | None:
        if self.services is not None:
            return self._run_prepare_service(mode)
        result_path = self.paths.prepare_result
        result_path.unlink(missing_ok=True)
        with tempfile.TemporaryFile() as output:  # a file, so a chatty child can never block on a pipe
            proc = subprocess.Popen(
                [*module_command(self.python, self.prepare_module), "--mode", mode, "--result", str(result_path)],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                env=self.child_env(),
            )
            finished = self.wait_responsive(proc, self.t.prepare_timeout)
            if not finished:
                proc.kill()
                proc.wait()
            output.seek(0)
            for line in output.read(256 * 1024).decode("utf-8", "replace").splitlines()[:200]:
                self.forward("prepare", line)
        if not finished:
            return None
        value = fsutil.read_json(result_path)
        result_path.unlink(missing_ok=True)
        return value if isinstance(value, dict) else None

    def _run_prepare_service(self, mode: str) -> dict[str, Any] | None:
        """The prepare step as the ``rns-prepare`` service, as Reticulum's user (ADR 0018)."""
        assert self.services is not None  # noqa: S101 - checked by the caller
        services = self.services
        output = drain(services.prepare_out)  # nothing left over from an earlier run
        try:
            proc = services.start_prepare(mode)
        except (OSError, ValueError):
            return None
        deadline = self.clock() + self.t.prepare_timeout
        finished = True
        while proc.poll() is None:
            self.heartbeat.beat()
            output += drain(services.prepare_out, 256 * 1024)  # never let a chatty step block
            if self.clock() >= deadline:
                proc.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(self.t.stop_grace)
                finished = False
                break
            time.sleep(0.2)
        output += drain(services.prepare_out, 256 * 1024)
        for line in output[: 256 * 1024].decode("utf-8", "replace").splitlines()[:200]:
            self.forward("prepare", line)
        raw = drain(services.prepare_result, 64 * 1024)
        if not finished or not raw:
            return None
        try:
            value = json.loads(raw.decode("utf-8", "replace").strip().splitlines()[-1])
        except (ValueError, IndexError):
            return None
        return value if isinstance(value, dict) else None

    def prepare_or_attention(self, mode: str) -> bool:
        result = self.run_prepare(mode)
        if result is None:
            self.enter_attention(
                [
                    "✖ MeshBeacon could not finish preparing Reticulum, so it has not started it. "
                    "Restart the app; if this repeats, please report it."
                ],
                "preparation_failed",
            )
            return False
        for message in result.get("info", []):
            self.say(str(message))
        for message in result.get("warnings", []):
            self.say(f"⚠ {message}")
        if not result.get("ok"):
            messages = [str(m) for m in result.get("attention", [])]
            self.enter_attention(
                [m if m.startswith("  ") else f"✖ {m}" for m in messages], str(result.get("problem") or "unexpected")
            )
            return False
        return True

    # -- child process -----------------------------------------------------------------------
    def start_child(self) -> None:
        if self.services is not None:
            self._start_child_service()
            return
        read_fd, write_fd = os.pipe()
        cmd = [
            *module_command(self.python, self.node_module),
            "--config",
            str(self.paths.reticulum),
            "--status-fd",
            str(write_fd),
            "--interval",
            str(self.t.status_interval),
            "--parent",
            str(os.getpid()),
        ]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            pass_fds=(write_fd,),
            env=self.child_env(),
        )
        os.close(write_fd)
        if proc.stdout is None:  # pragma: no cover - stdout=PIPE always provides it
            raise RuntimeError("child has no stdout pipe")
        out_fd = proc.stdout.fileno()
        for fd in (out_fd, read_fd):
            os.set_blocking(fd, False)
        now = self.clock()
        self.child = Child(proc, now, out_fd, read_fd, LineBuffer(), LineBuffer(), now)
        self.selector.register(out_fd, selectors.EVENT_READ, "out")
        self.selector.register(read_fd, selectors.EVENT_READ, "status")
        self.policy.attempt_started()
        self.cpu_samples.clear()
        self.state = "running"
        self.monitor(self.collector.child_started)
        self.publish()

    def _start_child_service(self) -> None:
        """Reticulum as the ``reticulum`` s6 service, as its own user (ADR 0018)."""
        assert self.services is not None  # noqa: S101 - checked by the caller
        services = self.services
        for fd in (services.node_out, services.node_status):
            drain(fd)  # lines from an earlier run were already handled
        try:
            proc = services.start("reticulum")
        except OSError:
            self.child_failed("The Reticulum service could not be started.")
            return
        now = self.clock()
        self.child = Child(
            proc,  # type: ignore[arg-type]  # the part of Popen the supervisor uses
            now,
            services.node_out,
            services.node_status,
            LineBuffer(),
            LineBuffer(),
            now,
            owns_fds=False,
        )
        self.selector.register(services.node_out, selectors.EVENT_READ, "out")
        self.selector.register(services.node_status, selectors.EVENT_READ, "status")
        self.policy.attempt_started()
        self.cpu_samples.clear()
        self.state = "running"
        self.monitor(self.collector.child_started)
        self.publish()

    def _close_child_fds(self, child: Child) -> None:
        for fd in (child.out_fd, child.status_fd):
            with contextlib.suppress(KeyError, ValueError):
                self.selector.unregister(fd)
        if not child.owns_fds:
            return  # an s6 service's FIFOs: kept open for its next run
        with contextlib.suppress(OSError):
            os.close(child.status_fd)
        if child.proc.stdout is not None:
            child.proc.stdout.close()

    def stop_child(self) -> None:
        child, self.child = self.child, None
        if child is None:
            return
        self.monitor(self.collector.child_stopped)
        if child.proc.poll() is None:
            child.proc.terminate()
            if not self.wait_responsive(child.proc, self.t.stop_grace):
                child.proc.kill()
                child.proc.wait()
        self._drain(child)
        self._close_child_fds(child)

    def _drain(self, child: Child) -> None:
        for fd, buf, source in ((child.out_fd, child.out_buf, "out"), (child.status_fd, child.status_buf, "status")):
            try:
                while data := os.read(fd, 65536):
                    self._handle_lines(source, buf.feed(data))
            except (BlockingIOError, OSError):
                pass

    def child_failed(self, reason: str, *, memory: bool = False) -> None:
        self.stop_child()
        now = self.clock()
        self.last_failure = now
        self.policy.record_failure(now)
        self.state = "restarting"
        self.say(f"⚠ {reason}")
        if self.policy.gave_up:
            self.enter_attention([MSG_GAVE_UP], "reticulum_failing")
            return
        self.monitor(self.collector.record_failure, memory=memory)
        self.publish()
        self.next_attempt = self.policy.next_start(now)
        if self.policy.breaker_open:
            minutes = round(self.t.breaker_cooldown / 60)
            self.say(
                f"⚠ The Reticulum service keeps failing. MeshBeacon will try again in {minutes} minutes. "
                "See the lines above for the cause."
            )
        else:
            self.say("Restarting the Reticulum service automatically…")

    def _handle_lines(self, source: str, lines: list[str]) -> None:
        for line in lines:
            if source == "out":
                self.forward("reticulum", line)
            else:
                self._handle_status(line)

    def _handle_status(self, line: str) -> None:
        if self.child is not None:
            self.child.last_status = self.clock()
        try:
            status = json.loads(line)
        except ValueError:
            return
        if not isinstance(status, dict) or self.settings is None:
            return
        self.monitor(self.collector.update, status)
        snap = evaluate(tuple(p.name for p in self.settings.peers), status)
        # Announce changes only. (With no peers, boot has already reported the isolated state.)
        if self.snapshot is None or snap.state is not self.snapshot.state or snap.up != self.snapshot.up:
            self.say(describe(snap))
        self.snapshot = snap

    # -- periodic checks ---------------------------------------------------------------------
    def check_child(self) -> None:
        child = self.child
        if child is None:
            return
        now = self.clock()
        code = child.proc.poll()
        if code is not None:
            self._drain(child)
            self.child_failed(f"The Reticulum service stopped unexpectedly (exit code {code}).")
            return
        if now - child.last_status > self.t.status_stall:
            self.child_failed("The Reticulum service stopped responding and has been restarted.")
            return
        if not child.stable and now - child.started >= self.t.stable_after:
            child.stable = True
            self.policy.record_stable()
            history = self.history()
            history.mark_stable()
            self.save_history(history)
        if self.due("resources", self.t.resource_check):
            self.check_resources(child)

    def check_resources(self, child: Child) -> None:
        if self.settings is None:
            return
        mem = procinfo.memory_bytes(child.proc.pid)
        limit = self.settings.memory_limit_mb * 1024 * 1024
        if mem is not None and mem > limit:
            self.child_failed(
                f"The Reticulum service used more memory than its limit ({mem // 1048576} MB > "
                f"{self.settings.memory_limit_mb} MB) and has been restarted.",
                memory=True,
            )
            return
        cpu = procinfo.cpu_seconds(child.proc.pid)
        core_cpu = procinfo.cpu_seconds(os.getpid())
        self.monitor(
            self.collector.resources,
            procinfo.memory_bytes(os.getpid()),
            mem,
            None if cpu is None or core_cpu is None else cpu + core_cpu,
        )
        if cpu is not None:
            now = self.clock()
            self.cpu_samples.append((now, cpu))
            while self.cpu_samples and now - self.cpu_samples[0][0] > self.t.cpu_window:
                self.cpu_samples.popleft()
            t0, c0 = self.cpu_samples[0]
            busy = now - t0 >= self.t.cpu_window * 0.95 and (cpu - c0) / max(now - t0, 1e-6) > self.t.cpu_threshold
            if busy and self.due("cpu_warning", 3600, first=True):
                self.say(
                    "⚠ The Reticulum service has been using most of a CPU core for 10 minutes. "
                    "It runs at low priority, so Home Assistant is not slowed down, but this may "
                    "indicate heavy network traffic (for example with transport mode on)."
                )

    def check_storage(self) -> None:
        if not self.due("storage", self.t.storage_check):
            return
        free = shutil.disk_usage(self.paths.data).free
        if free < FREE_SPACE_FLOOR:
            self.enter_attention([MSG_STORAGE], "storage")
        elif free < FREE_SPACE_WARN and self.due("storage_warning", 6 * 3600, first=True):
            self.say("⚠ Free storage is below 1 GB. MeshBeacon will stop Reticulum below 200 MB.")

    def periodic_report(self) -> None:
        snapshot = self.snapshot
        if (
            snapshot is not None
            and snapshot.state is Connectivity.ISOLATED
            and self.due("isolated", self.t.isolated_reminder)
        ):
            self.say(describe(snapshot))
        if not self.due("report", self.t.report_interval):
            return
        snap = self.snapshot
        parts = []
        if snap is not None:
            parts.append(f"connectivity {snap.state.value}")
            if snap.configured:
                parts.append(f"{len(snap.up)} of {snap.configured} peers connected")
            parts.append(f"sent {human_bytes(snap.txb)}, received {human_bytes(snap.rxb)} since start")
        core_mem = procinfo.memory_bytes(os.getpid()) or 0
        child_mem = procinfo.memory_bytes(self.child.proc.pid) if self.child else None
        memory = f"memory {core_mem // 1048576} MB core"
        if child_mem:
            memory += f" + {child_mem // 1048576} MB Reticulum"
        parts.append(memory)
        self.say("Status: " + "; ".join(parts) + ".")

    # -- monitoring (v0.2) --------------------------------------------------------------------
    def problem(self) -> tuple[str, str | None]:
        """A stable problem code and the plain-language message that goes with it."""
        if self.state == "needs_attention":
            text = " ".join(m.strip().lstrip("✖⚠ ").strip() for m in (self.attention or []))
            return self.problem_code, self.redact(text) or None
        if self.state == "restarting":
            return "reticulum_restarting", "The Reticulum service is restarting automatically."
        snap = self.snapshot
        if snap is None or self.child is None:
            return "none", None
        code = {
            Connectivity.ISOLATED: "isolated",
            Connectivity.OFFLINE: "peers_unreachable",
            Connectivity.PARTIAL: "some_peers_unreachable",
        }.get(snap.state, "none")
        return code, None if code == "none" else self.redact(describe(snap).lstrip("⚠ "))

    def build_snapshot(self) -> dict[str, Any]:
        code, message = self.problem()
        snap = self.snapshot
        return self.collector.snapshot(
            {
                "version": __version__,
                "rns_version": installed_rns_version(),
                "arch": platform.machine(),
                "state": self.state,
                "connectivity": snap.state.value if snap is not None else Connectivity.UNKNOWN.value,
                "problem": code,
                "message": message,
            }
        )

    def setup_integration(self) -> None:
        """Start the monitoring API and announce it, or withdraw an earlier announcement."""
        token = self._supervisor_token
        self._supervisor_token = None  # keep only inside the discovery helper
        if self.settings is None:
            return
        state = self.paths.meshbeacon / "discovery.json"
        discovery: Discovery | None = None
        if self.discovery_relay is not None:
            # The Supervisor's own socket, through the relay: nothing crosses the internal network.
            discovery = Discovery(None, state, relay=self.discovery_relay)
        elif token and not self.socket_mode:
            # Compatibility path for Supervisors without app sockets (2026.11.0 and older).
            discovery = Discovery(token, state, base_url=self.supervisor_url or "http://supervisor")
        if not self.settings.home_assistant_integration:
            if discovery is not None and (self.paths.meshbeacon / "discovery.json").exists():
                threading.Thread(target=discovery.withdraw, name="discovery", daemon=True).start()
            return
        api_token = new_token()
        try:
            tls, fingerprint = make_tls(self.python, self.child_env())
            self.api_store = StatusStore(api_token)
            self.api_server = ApiServer(self.api_store, self.api_host, self.api_port, tls=tls)
            self.api_server.start()
        except (OSError, TlsError):  # never falls back to plain HTTP
            self.api_store = self.api_server = None
            self.say("⚠ MeshBeacon could not start its Home Assistant status interface. The node works normally.")
            return
        self.publish()
        self.say(MSG_API_STARTED)
        if discovery is not None:
            self.say(MSG_DISCOVERY_SOCKET if discovery.transport == "socket" else MSG_DISCOVERY_TCP)
        if discovery is None:
            self.say(
                MSG_DISCOVERY_UNAVAILABLE
                if self.socket_mode
                else "⚠ Not running under the Home Assistant Supervisor, so Home Assistant cannot be told about it."
            )
            return
        host, port = self.hostname(), self.api_server.port

        def announce() -> None:
            try:
                discovery.keep_announced(
                    host,
                    port,
                    api_token,
                    self.discovery_stop,
                    self.discovery_results.append,
                    cert_sha256=fingerprint,
                    **self.discovery_timing,
                )
            except Exception:  # never let monitoring take anything else down
                self.discovery_results.append(False)

        threading.Thread(target=announce, name="discovery", daemon=True).start()

    def monitor(self, fn: Callable[..., object], *args: Any, **kwargs: Any) -> None:
        """Run a metrics update. Monitoring is never allowed to interrupt supervision of Reticulum."""
        try:
            fn(*args, **kwargs)
        except Exception as exc:
            if self.due("monitoring_error", 3600, first=True):
                self.say(MSG_MONITORING_ERROR.format(name=type(exc).__name__))

    def publish(self) -> None:
        """Rebuild the snapshot served to Home Assistant. Failures never reach Reticulum."""
        if self.api_store is None:
            return
        try:
            self.api_store.publish(self.build_snapshot())
        except Exception as exc:  # monitoring must never interrupt the node
            if self.due("monitoring_error", 3600, first=True):
                self.say(MSG_MONITORING_ERROR.format(name=type(exc).__name__))

    def api_housekeeping(self) -> None:
        if self.api_store is None:
            return
        try:
            self._api_housekeeping()
        except Exception as exc:  # monitoring must never interrupt the node
            if self.due("monitoring_error", 3600, first=True):
                self.say(MSG_MONITORING_ERROR.format(name=type(exc).__name__))

    def _api_housekeeping(self) -> None:
        assert self.api_store is not None  # noqa: S101 - checked by the caller
        if self.due("publish", self.t.status_interval / 2, first=True):
            self.publish()
        while self.discovery_results:
            ok = self.discovery_results.pop(0)
            if ok and self.discovery_ok is None:
                self.say(MSG_DISCOVERY_OK)
            elif ok and self.discovery_ok is False:
                self.say(MSG_DISCOVERY_RECOVERED)
            elif not ok and self.discovery_ok is not False:
                lost = self.discovery_relay is not None and self.discovery_relay.broken
                self.say(MSG_RELAY_LOST if lost else MSG_DISCOVERY_FAILED)  # once per outage, not per retry
            self.discovery_ok = ok
        if self.due("api_refused", 3600):
            refused = self.api_store.take_refused()
            if refused:
                self.say(f"⚠ {refused} requests to the status interface were refused in the last hour (wrong key).")

    # -- main loop ---------------------------------------------------------------------------
    def _on_signal(self, signum: int, _frame: object) -> None:
        self.stopping = True

    def step(self, timeout: float = 1.0) -> None:
        self.heartbeat.beat()
        for key, _mask in self.selector.select(timeout):
            if self.child is None:
                break
            buf = self.child.out_buf if key.data == "out" else self.child.status_buf
            try:
                data = os.read(key.fd, 65536)
            except BlockingIOError:
                continue
            if data:
                self._handle_lines(key.data, buf.feed(data))
        self.flush_suppressed()
        self.api_housekeeping()
        if self.attention is not None:
            if self.due("attention", self.t.attention_reminder):
                for m in self.attention:
                    self.say(m)
            return
        self.check_child()
        self.check_storage()
        if self.attention is not None:
            return
        if self.child is None and self.next_attempt is not None and self.clock() >= self.next_attempt:
            self.next_attempt = None
            if self.prepare_or_attention("restart"):
                self.start_child()
        self.periodic_report()

    def boot(self) -> bool:
        """Start-up sequence. Returns False if MeshBeacon is waiting for the user."""
        self.load_settings()
        self.startup_report()
        self.setup_integration()
        try:
            fsutil.ensure_dir(self.paths.meshbeacon)
        except OSError:
            self.enter_attention(
                ["✖ MeshBeacon cannot write to its data folder. Restart the app; if this repeats, reinstall it."],
                "data_folder",
            )
            return False
        history = self.history()
        safe, retry_after = history.begin(self.wall(), self.options_hash())
        self.save_history(history)
        if safe:
            when = time.strftime("%H:%M", time.localtime(retry_after or self.wall()))
            self.enter_attention(
                [
                    "✖ MeshBeacon has been restarted many times in a short period, so it has paused "
                    f"to avoid a restart loop. Restart it after {when}, or change any option to try "
                    "again now."
                ],
                "restart_loop_paused",
            )
            return False
        if self.require_services and self.services is None:
            self.enter_attention([MSG_NO_ISOLATION], "unexpected")  # fail closed (ADR 0018)
            return False
        if not self.prepare_or_attention("start"):
            return False
        self.load_settings()
        if self.settings is None:  # pragma: no cover - prepare validated the same file
            self.enter_attention(["✖ The app options could not be read."], "options")
            return False
        if not self.settings.peers:
            self.snapshot = evaluate((), None)
            self.say(describe(self.snapshot))
        self.start_child()
        return True

    def run(self) -> int:
        os.umask(0o077)
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)
        self.health.start()
        try:
            self.boot()
            while not self.stopping:
                self.step()
        finally:
            self.say("Stopping MeshBeacon.")
            self.stop_child()
            self.discovery_stop.set()
            if self.api_server is not None:
                self.api_server.stop()
            self.health.stop()
        return 0


def read_token_fd(fd: int) -> str | None:
    """The Supervisor token from the one-time pipe the root start step filled (relay_link.py).

    Reads it once and closes the pipe at once, whatever it holds. Anything other than a pipe, or a
    malformed token, gives None.
    """
    try:
        if not stat.S_ISFIFO(os.fstat(fd).st_mode):
            return None
        os.set_blocking(fd, False)  # the write end is already closed: never wait
        data = b""
        while len(data) <= 4096:
            try:
                chunk = os.read(fd, 4097 - len(data))
            except BlockingIOError:
                break
            if not chunk:
                break
            data += chunk
    except OSError:
        return None
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)
    token = data.strip().decode("ascii", "replace")
    return token if TOKEN.match(token) else None


def discovery_transport(
    environ: dict[str, str] | os._Environ[str],
) -> tuple[str | None, RelayLink | None, bool]:
    """(token, relay link, socket mode): how this start reaches the Supervisor for discovery.

    Removes every related variable from ``environ``, so that no child process inherits it, and
    never takes the token from the environment: the root start step (relay_link.py) passes it
    through a one-time pipe (``MESHBEACON_TOKEN_FD``), so it is never in any process environment.

    Newer Supervisors give the app its own socket (``SUPERVISOR_SOCKET``): then the root start step
    has opened a link to the root relay (``MESHBEACON_RELAY_FD``) instead, no token is passed at all,
    and a missing link never falls back to the internal network. Otherwise the token is used over
    the internal network (the compatibility path for Supervisor 2026.11.0 and older).
    """
    environ.pop(SUPERVISOR_TOKEN_ENV, None)  # never used from the environment (M1.2)
    socket_mode = bool(environ.pop(SUPERVISOR_SOCKET_ENV, None))
    relay_fd = environ.pop(RELAY_FD_ENV, "")
    token_fd = environ.pop(TOKEN_FD_ENV, "")
    token = read_token_fd(int(token_fd)) if token_fd.isdecimal() else None
    if socket_mode:
        link = RelayLink.from_fd(int(relay_fd)) if relay_fd.isdecimal() else None
        return None, link, True
    return token, None, False


def main() -> int:
    # First, before any secret is read and before any child exists: no other process of this user
    # (the Reticulum child) may read this one's memory, environment or descriptors (threat T72).
    procinfo.set_not_dumpable()
    os.umask(0o077)
    with contextlib.suppress(OSError):
        os.nice(10)  # Home Assistant always wins CPU contention
    port = int(os.environ.get("MESHBEACON_HEALTH_PORT", "8099"))
    host = os.environ.get("MESHBEACON_HEALTH_HOST", "0.0.0.0")
    api_port = int(os.environ.get("MESHBEACON_API_PORT", "8100"))
    supervisor_token, relay, socket_mode = discovery_transport(os.environ)
    require_services = os.environ.pop("MESHBEACON_S6", "") == "1"
    services = None
    if require_services:
        for _ in range(150):  # the services start beside the core: wait at most 15 s
            if Services.available():
                services = Services()
                break
            time.sleep(0.1)
    return Supervisor(
        Paths.from_env(),
        health_host=host,
        health_port=port,
        api_host=host,
        api_port=api_port,
        supervisor_token=supervisor_token,
        supervisor_url=os.environ.get("MESHBEACON_SUPERVISOR_URL"),
        discovery_relay=relay,
        socket_mode=socket_mode,
        services=services,
        require_services=require_services,
    ).run()


if __name__ == "__main__":
    sys.exit(main())
