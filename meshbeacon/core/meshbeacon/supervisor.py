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
from .api import ApiServer, Discovery, StatusStore, container_hostname, new_token
from .connectivity import Connectivity, Snapshot, describe, evaluate, human_bytes
from .health import HealthServer, Heartbeat
from .logfilter import RateLimiter, Redactor
from .metrics import Collector
from .paths import Paths
from .policy import RestartPolicy, StartHistory, Timings
from .prepare import FREE_SPACE_FLOOR, FREE_SPACE_WARN
from .settings import Settings, ValidationError, parse_options

MSG_GAVE_UP = (
    "✖ The Reticulum service keeps failing, so MeshBeacon has stopped trying. "
    "Fix the cause shown above, then restart the app."
)
MSG_STORAGE = (
    "✖ Free storage has fallen below 200 MB, so MeshBeacon has stopped Reticulum to protect "
    "Home Assistant. Free some space and restart the app."
)
MSG_API_STARTED = (
    "Home Assistant integration: on. MeshBeacon shares its status with Home Assistant over the "
    "internal network only, protected by a key that changes at every start."
)
MSG_DISCOVERY_FAILED = (
    "⚠ MeshBeacon could not tell Home Assistant about its status interface. The node works "
    "normally; restart the app to try again."
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
        hostname: Callable[[], str] = container_hostname,
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
        self.hostname = hostname
        self.discovery_result: bool | None = None

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
            self.collector.configure(tuple(p.name for p in self.settings.peers))

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
        self.collector.child_started()
        self.publish()

    def _close_child_fds(self, child: Child) -> None:
        for fd in (child.out_fd, child.status_fd):
            with contextlib.suppress(KeyError, ValueError):
                self.selector.unregister(fd)
        with contextlib.suppress(OSError):
            os.close(child.status_fd)
        if child.proc.stdout is not None:
            child.proc.stdout.close()

    def stop_child(self) -> None:
        child, self.child = self.child, None
        if child is None:
            return
        self.collector.child_stopped()
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
        self.collector.record_failure(memory=memory)
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
        self.collector.update(status)
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
        self.collector.resources(
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
        discovery = (
            Discovery(
                token, self.paths.meshbeacon / "discovery.json", base_url=self.supervisor_url or "http://supervisor"
            )
            if token
            else None
        )
        if not self.settings.home_assistant_integration:
            if discovery is not None and (self.paths.meshbeacon / "discovery.json").exists():
                threading.Thread(target=discovery.withdraw, name="discovery", daemon=True).start()
            return
        api_token = new_token()
        try:
            self.api_store = StatusStore(api_token)
            self.api_server = ApiServer(self.api_store, self.api_host, self.api_port)
            self.api_server.start()
        except OSError:
            self.api_store = self.api_server = None
            self.say("⚠ MeshBeacon could not start its Home Assistant status interface. The node works normally.")
            return
        self.publish()
        self.say(MSG_API_STARTED)
        if discovery is None:
            self.say("⚠ Not running under the Home Assistant Supervisor, so Home Assistant cannot be told about it.")
            return
        host, port = self.hostname(), self.api_server.port

        def announce() -> None:
            self.discovery_result = discovery.announce(host, port, api_token)

        threading.Thread(target=announce, name="discovery", daemon=True).start()

    def publish(self) -> None:
        if self.api_store is not None:
            self.api_store.publish(self.build_snapshot())

    def api_housekeeping(self) -> None:
        if self.api_store is None:
            return
        if self.due("publish", self.t.status_interval / 2, first=True):
            self.publish()
        if self.discovery_result is False:
            self.say(MSG_DISCOVERY_FAILED)
        if self.discovery_result is not None:
            self.discovery_result = None
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
            if self.api_server is not None:
                self.api_server.stop()
            self.health.stop()
        return 0


def main() -> int:
    os.umask(0o077)
    with contextlib.suppress(OSError):
        os.nice(10)  # Home Assistant always wins CPU contention
    port = int(os.environ.get("MESHBEACON_HEALTH_PORT", "8099"))
    host = os.environ.get("MESHBEACON_HEALTH_HOST", "0.0.0.0")
    api_port = int(os.environ.get("MESHBEACON_API_PORT", "8100"))
    supervisor_token = os.environ.pop(SUPERVISOR_TOKEN_ENV, None) or None
    return Supervisor(
        Paths.from_env(),
        health_host=host,
        health_port=port,
        api_host=host,
        api_port=api_port,
        supervisor_token=supervisor_token,
        supervisor_url=os.environ.get("MESHBEACON_SUPERVISOR_URL"),
    ).run()


if __name__ == "__main__":
    sys.exit(main())
