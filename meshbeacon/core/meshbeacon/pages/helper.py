# SPDX-License-Identifier: Apache-2.0
"""The pages service (ADR 0027): user ``mb-nomad``, a client of ito's shared Reticulum instance.

Uses only RNS's public API, and runs the unmodified Nomad Network daemon as a separate program.

- **Browse.** ``fetch`` requests one page from a Nomad Network node: the address must be 32 hex
  characters naming a ``nomadnetwork.node`` destination, the path ``/page/<name>.mu``. At most two at
  once and 30 a minute; 30 s and 256 KiB at most; the answer is returned as plain text, never
  interpreted here. Links are kept open for two minutes for the next page (at most four).
- **Discover.** An announce handler for ``nomadnetwork.node`` keeps the 500 most recently heard
  nodes (name, first and last heard), saved in the service's own folder. A node is never called
  reachable because it was heard: ``nodes`` reports when it was last heard, whether a path is known
  now, and when a fetch last succeeded or failed.
- **Host.** While the core asks for it (``sync``), ``nomadnet --daemon`` runs as a child, with its
  own identity (checked first, never replaced: rule 13) and the configuration from
  ``nomadconfig``. It restarts with back-off and pauses after five failures in 30 minutes. Above
  64 MiB of daemon storage hosting stops (F4).

Messages never contain addresses, keys or page content (rule 5).
"""

from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import fsutil, procinfo
from ..identity import from_bytes
from . import nomadconfig
from .store import ADDRESS, valid_node_name, valid_path

APP, ASPECT = "nomadnetwork", "node"
MAX_NODES = 500
MAX_ANSWER = 256 * 1024
FETCH_TIMEOUT = 30.0
FETCH_CONCURRENT = 2
FETCH_RATE = (30, 60.0)
LINK_IDLE = 120.0
MAX_LINKS = 4
REACHABLE_FOR = 600.0  # a successful fetch counts as "reachable" for this long
HEARD_RECENTLY = 1800.0
SAVE_EVERY = 300.0
STORAGE_EVERY = 300.0
STORAGE_LIMIT = 64 * 1024 * 1024
BACKOFF = (10.0, 30.0, 60.0, 120.0, 300.0)
PAUSE_AFTER, PAUSE_WINDOW = 5, 1800.0
STOP_GRACE = 10.0
_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f\u2028\u2029\u202e\ufeff]")

MSG = {
    "identity": (
        "Page hosting stopped: its identity file is damaged. ito never replaces it; restore the app from a backup."
    ),
    "storage": "Page hosting stopped: Nomad Network's storage passed 64 MiB. Switch hosting off and on to try again.",
    "paused": "Page hosting stopped after repeated failures. Switch hosting off and on to try again.",
    "config": "Page hosting could not start: the node name was refused.",
    "failed": "Nomad Network stopped unexpectedly; ito will try again shortly.",
}


def clean_text(data: bytes) -> str:
    """Untrusted page bytes as text: UTF-8 (invalid bytes replaced), no control characters."""
    return _CONTROL.sub("", data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n"))


def clean_name(data: Any) -> str | None:
    if not isinstance(data, bytes) or not data or len(data) > 256:
        return None
    text = _CONTROL.sub("", data.decode("utf-8", "replace").replace("\n", " ")).strip()
    return text[:64] or None


class Window:
    def __init__(self, limit: int, window: float, clock: Callable[[], float]) -> None:
        self.limit, self.window, self.clock = limit, window, clock
        self.events: deque[float] = deque()

    def allow(self) -> bool:
        now = self.clock()
        while self.events and self.events[0] <= now - self.window:
            self.events.popleft()
        if len(self.events) >= self.limit:
            return False
        self.events.append(now)
        return True


class Directory:
    """Heard Nomad Network nodes; RNS calls ``received_announce`` on its own thread."""

    aspect_filter = f"{APP}.{ASPECT}"

    def __init__(self, path: Path, clock: Callable[[], float] = time.time) -> None:
        self.path, self.clock = path, clock
        self.lock = threading.Lock()
        self.nodes: dict[str, dict[str, Any]] = {}
        self.dirty = False
        raw = fsutil.read_json(path)
        for item in raw if isinstance(raw, list) else []:
            if isinstance(item, dict) and isinstance(item.get("address"), str) and ADDRESS.match(item["address"]):
                name = item.get("name")
                self.nodes[item["address"]] = {
                    "name": name[:64] if isinstance(name, str) and not _CONTROL.search(name) else None,
                    "first_heard": float(item.get("first_heard") or 0),
                    "last_heard": float(item.get("last_heard") or 0),
                    "last_ok": None,
                    "last_failed": None,
                }

    def received_announce(self, destination_hash: bytes, announced_identity: Any, app_data: bytes | None) -> None:
        address = destination_hash.hex()
        now = self.clock()
        with self.lock:
            node = self.nodes.get(address)
            if node is None:
                if len(self.nodes) >= MAX_NODES:
                    oldest = min(self.nodes, key=lambda a: self.nodes[a]["last_heard"])
                    del self.nodes[oldest]
                node = self.nodes[address] = {
                    "name": None,
                    "first_heard": now,
                    "last_heard": now,
                    "last_ok": None,
                    "last_failed": None,
                }
            node["last_heard"] = now
            name = clean_name(app_data)
            if name:  # an announce without a name keeps the one heard before (F8)
                node["name"] = name
            self.dirty = True

    def result(self, address: str, ok: bool) -> None:
        with self.lock:
            node = self.nodes.get(address)
            if node is not None:
                node["last_ok" if ok else "last_failed"] = self.clock()

    def save(self) -> None:
        with self.lock:
            if not self.dirty:
                return
            items = [
                {"address": a, "name": n["name"], "first_heard": n["first_heard"], "last_heard": n["last_heard"]}
                for a, n in self.nodes.items()
            ]
            self.dirty = False
        fsutil.atomic_write_json(self.path, items)

    def view(self, has_path: Callable[[bytes], bool], own: str | None) -> list[dict[str, Any]]:
        now = self.clock()
        with self.lock:
            items = [(a, dict(n)) for a, n in self.nodes.items()]
        out = []
        for address, node in items:
            path = False
            with contextlib.suppress(Exception):
                path = bool(has_path(bytes.fromhex(address)))
            last_ok = node["last_ok"]
            out.append(
                {
                    "address": address,
                    "name": node["name"],
                    "first_heard": node["first_heard"],
                    "last_heard": node["last_heard"],
                    "heard_recently": now - node["last_heard"] < HEARD_RECENTLY,
                    "path_known": path,
                    "reachable": bool(last_ok and now - last_ok < REACHABLE_FOR),
                    "last_failed": node["last_failed"],
                    "own": address == own,
                }
            )
        out.sort(key=lambda n: -n["last_heard"])
        return out


class Browser:
    """Fetches pages with RNS's public link-request API."""

    def __init__(
        self, directory: Directory, clock: Callable[[], float] = time.monotonic, *, timeout: float = FETCH_TIMEOUT
    ) -> None:
        self.directory = directory
        self.clock = clock
        self.timeout = timeout
        self.slots = threading.BoundedSemaphore(FETCH_CONCURRENT)
        self.rate = Window(*FETCH_RATE, clock)
        self.rate_lock = threading.Lock()
        self.links: dict[str, tuple[Any, float]] = {}
        self.links_lock = threading.Lock()
        self.counters = {"fetched": 0, "failed": 0}

    def fetch(self, address: Any, path: Any) -> dict[str, Any]:
        if not isinstance(address, str) or not ADDRESS.match(address) or not valid_path(path):
            return {"ok": False, "error": "invalid"}
        with self.rate_lock:
            if not self.rate.allow():
                return {"ok": False, "error": "rate_limited"}
        if not self.slots.acquire(blocking=False):
            return {"ok": False, "error": "busy"}
        try:
            answer = self._fetch(address, path)
        except Exception:
            answer = {"ok": False, "error": "failed"}
        finally:
            self.slots.release()
        ok = answer.get("ok") is True
        self.counters["fetched" if ok else "failed"] += 1
        if answer.get("error") != "invalid":
            self.directory.result(address, ok)
        return answer

    def _fetch(self, address: str, path: str) -> dict[str, Any]:
        import RNS

        deadline = self.clock() + self.timeout
        target = bytes.fromhex(address)
        if not RNS.Transport.has_path(target):
            RNS.Transport.request_path(target)
            while not RNS.Transport.has_path(target):
                if self.clock() >= deadline:
                    return {"ok": False, "error": "no_path"}
                time.sleep(0.2)
        identity = RNS.Identity.recall(target)
        if identity is None:
            return {"ok": False, "error": "no_path"}
        destination = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, APP, ASPECT)
        if destination.hash != target:
            return {"ok": False, "error": "not_a_node"}
        link = self._link(address, destination)
        while link.status != RNS.Link.ACTIVE:
            if link.status == RNS.Link.CLOSED or self.clock() >= deadline:
                self._drop(address)
                return {"ok": False, "error": "unreachable"}
            time.sleep(0.1)
        done = threading.Event()
        result: dict[str, Any] = {}

        def response(receipt: Any) -> None:
            result["data"] = receipt.response
            done.set()

        def failed(_receipt: Any) -> None:
            done.set()

        remaining = max(1.0, deadline - self.clock())
        receipt = link.request(path, data=None, response_callback=response, failed_callback=failed, timeout=remaining)
        if receipt is False or receipt is None:
            return {"ok": False, "error": "unreachable"}
        if not done.wait(remaining + 1):
            return {"ok": False, "error": "timeout"}
        data = result.get("data")
        if isinstance(data, str):
            data = data.encode("utf-8", "replace")
        if not isinstance(data, bytes):
            return {"ok": False, "error": "not_found" if "data" in result else "timeout"}
        if len(data) > MAX_ANSWER:
            return {"ok": False, "error": "too_large"}
        return {"ok": True, "content": clean_text(data), "size": len(data)}

    def _link(self, address: str, destination: Any) -> Any:
        import RNS

        with self.links_lock:
            held = self.links.get(address)
            if held is not None and held[0].status != RNS.Link.CLOSED:
                self.links[address] = (held[0], self.clock())
                return held[0]
            while len(self.links) >= MAX_LINKS:
                oldest = min(self.links, key=lambda a: self.links[a][1])
                with contextlib.suppress(Exception):
                    self.links.pop(oldest)[0].teardown()
            link = RNS.Link(destination)
            self.links[address] = (link, self.clock())
            return link

    def _drop(self, address: str) -> None:
        with self.links_lock:
            held = self.links.pop(address, None)
        if held is not None:
            with contextlib.suppress(Exception):
                held[0].teardown()

    def tidy(self) -> None:
        now = self.clock()
        with self.links_lock:
            stale = [a for a, (_link, used) in self.links.items() if now - used > LINK_IDLE]
        for address in stale:
            self._drop(address)

    def close(self) -> None:
        for address in list(self.links):
            self._drop(address)


class Host:
    """The upstream daemon as a child process, while the core asks for hosting."""

    def __init__(
        self,
        data: Path,
        pages: Path,
        rns_config: Path,
        *,
        clock: Callable[[], float] = time.monotonic,
        command: list[str] | None = None,
    ) -> None:
        self.data, self.pages, self.rns_config, self.clock = data, pages, rns_config, clock
        self.config = data / "nomadnet"
        self.files = data / "files"
        self.pid_file = data / "nomadnet.pid"
        self.command = command or [sys.executable, "-I", "-u", "-m", "nomadnet.nomadnet"]
        self.proc: subprocess.Popen[bytes] | None = None
        self.wanted = False
        self.node_name = ""
        self.log_level = "normal"
        self.state = "off"  # off | starting | running | backoff | paused | stopped(error)
        self.message: str | None = None
        self.failures: deque[float] = deque()
        self.next_attempt = 0.0
        self.started_at = 0.0
        self.address: str | None = None
        self.last_storage = 0.0
        self.lock = threading.Lock()

    # -- identity (rule 13) ----------------------------------------------------------------------
    def identity(self) -> Any | None:
        """The daemon's identity: created on the first start, else checked; restored from its
        verified backup if damaged (as messaging's, ADR 0009); never replaced by a new one."""
        import RNS

        storage = self.config / "storage"
        fsutil.ensure_dir(storage)
        path, backup = storage / "identity", storage / "identity.backup"
        try:
            data: bytes | None = path.read_bytes()
        except FileNotFoundError:
            data = None
        if data is None or from_bytes(data) is None:
            with contextlib.suppress(FileNotFoundError):
                saved = backup.read_bytes()
                if from_bytes(saved) is not None:
                    fsutil.atomic_write(path, saved)
                    data = saved
        if data is None:
            data = bytes(RNS.Identity().get_private_key())
            fsutil.atomic_write(path, data)
        identity = from_bytes(data)
        if identity is None:
            return None
        if not backup.exists() or backup.read_bytes() != data:
            fsutil.atomic_write(backup, data)
        self.address = RNS.Destination.hash(identity, APP, ASPECT).hex()
        return identity

    # -- control ---------------------------------------------------------------------------------
    def sync(self, wanted: bool, node_name: str, log_level: str) -> None:
        with self.lock:
            changed = (node_name, log_level) != (self.node_name, self.log_level)
            self.node_name, self.log_level = node_name, log_level
            if wanted and not self.wanted:  # switched (back) on: a fresh start, even after a pause
                self.failures.clear()
                self.state, self.message, self.next_attempt = "starting", None, 0.0
            self.wanted = wanted
            if not wanted:
                self._stop()
                self.state, self.message = "off", None
            elif changed and self.proc is not None:
                self._stop()
                self.state, self.next_attempt = "starting", 0.0

    def step(self, connected: bool) -> None:
        with self.lock:
            now = self.clock()
            if not self.wanted:
                return
            if not connected:  # never start (or keep) the daemon without ito's shared instance (F5)
                if self.proc is not None:
                    self._stop()
                    self.state = "starting"
                return
            if self.proc is not None:
                code = self.proc.poll()
                if code is None:
                    if self.state == "starting" and now - self.started_at > 5:
                        self.state = "running"
                    if now - self.last_storage >= STORAGE_EVERY:
                        self.last_storage = now
                        if fsutil.tree_size(self.config) > STORAGE_LIMIT:
                            self._stop()
                            # Stays stopped until the user switches hosting off and on (sync).
                            self.state, self.message = "error", MSG["storage"]
                    return
                self.proc = None
                self._failed(now)
                return
            if self.state in ("paused", "error") or now < self.next_attempt:
                return
            self._launch(now)

    def _launch(self, now: float) -> None:
        if self.identity() is None:
            self.state, self.message = "error", MSG["identity"]  # until hosting is switched off and on
            return
        try:
            fsutil.ensure_dir(self.files)
            text = nomadconfig.render(self.node_name, self.pages, self.files, self.log_level)
        except (nomadconfig.ConfigError, OSError):
            self.state, self.message = "error", MSG["config"]
            return
        fsutil.atomic_write(self.config / "config", text.encode())
        self.reap_stale()
        command = [*self.command, "--daemon", "--console", "--config", str(self.config)]
        command += ["--rnsconfig", str(self.rns_config)]
        try:
            self.proc = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin", "HOME": str(self.data), "PYTHONUNBUFFERED": "1"},
                cwd=str(self.data),
            )
        except OSError:
            self._failed(now)
            return
        with contextlib.suppress(OSError):
            fsutil.atomic_write(self.pid_file, f"{self.proc.pid}\n".encode())
        self.started_at = now
        self.state, self.message = "starting", None

    def reap_stale(self) -> None:
        """A daemon left over from a helper that was killed (SIGKILL leaves the child running):
        stop it, so that two daemons never share one identity and storage."""
        try:
            pid = int(self.pid_file.read_text().strip())
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        except (OSError, ValueError):
            return
        if b"nomadnet.nomadnet" in cmdline and str(self.config).encode() in cmdline:
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)
        self.pid_file.unlink(missing_ok=True)

    def _failed(self, now: float) -> None:
        self.failures.append(now)
        while self.failures and self.failures[0] <= now - PAUSE_WINDOW:
            self.failures.popleft()
        if len(self.failures) >= PAUSE_AFTER:
            self.state, self.message = "paused", MSG["paused"]
            return
        self.state, self.message = "backoff", MSG["failed"]
        self.next_attempt = now + BACKOFF[min(len(self.failures) - 1, len(BACKOFF) - 1)]

    def _stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None or proc.poll() is not None:
            return
        self.pid_file.unlink(missing_ok=True)
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(STOP_GRACE)
        except subprocess.TimeoutExpired:
            proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(STOP_GRACE)

    def stop(self) -> None:
        with self.lock:
            self._stop()

    def view(self) -> dict[str, Any]:
        with self.lock:
            pid = self.proc.pid if self.proc is not None else None
            return {
                "state": self.state,
                "message": self.message,
                "address": self.address,
                "restarts": len(self.failures),
                "memory_bytes": procinfo.memory_bytes(pid) if pid else None,
            }


class Helper:
    def __init__(
        self,
        data: Path,
        pages: Path,
        rns_config: Path,
        *,
        host_command: list[str] | None = None,
        fetch_timeout: float = FETCH_TIMEOUT,
    ) -> None:
        self.data = data
        self.reticulum: Any = None
        self.directory = Directory(data / "nodes.json")
        self.browser = Browser(self.directory, timeout=fetch_timeout)
        self.host = Host(data, pages, rns_config, command=host_command)
        self.rns_config = rns_config
        self.stopping = threading.Event()
        self.last_save = time.monotonic()
        self.has_rpc_key: bool | None = None

    def start(self) -> None:
        import RNS

        self.host.reap_stale()
        self.reticulum = RNS.Reticulum(configdir=str(self.rns_config), require_shared_instance=True)
        RNS.Transport.register_announce_handler(self.directory)
        # The node address is shown in the dashboard before hosting starts (identity created once).
        with contextlib.suppress(Exception):
            if (self.host.config / "storage" / "identity").exists():
                self.host.identity()

    def connected(self) -> bool:
        return bool(self.reticulum is not None and self.reticulum.is_connected_to_shared_instance)

    def handle(self, request: Any) -> dict[str, Any]:
        if not isinstance(request, dict):
            return {"ok": False, "error": "invalid"}
        op = request.get("op")
        if op == "status":
            return self.status()
        if op == "sync":
            wanted, name, level = request.get("hosting"), request.get("node_name", ""), request.get("log_level")
            bad_name = wanted and not valid_node_name(name)
            if not isinstance(wanted, bool) or bad_name or level not in nomadconfig.LOGLEVELS:
                return {"ok": False, "error": "invalid"}
            self.host.sync(wanted, name if isinstance(name, str) else "", level)
            return self.status()
        if op == "fetch":
            return self.browser.fetch(request.get("address"), request.get("path"))
        if op == "nodes":
            import RNS

            return {"ok": True, "nodes": self.directory.view(RNS.Transport.has_path, self.host.address)}
        return {"ok": False, "error": "invalid"}

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "connected": self.connected(),
            "rpc_key": self.has_rpc_key,
            "hosting": self.host.view(),
            "nodes_known": len(self.directory.nodes),
            "counters": dict(self.browser.counters),
        }

    def run(self) -> None:
        while not self.stopping.is_set():
            self.tick()
            self.stopping.wait(1.0)

    def tick(self) -> None:
        self.host.step(self.connected())
        self.browser.tidy()
        if time.monotonic() - self.last_save >= SAVE_EVERY:
            self.last_save = time.monotonic()
            with contextlib.suppress(OSError):
                self.directory.save()

    def stop(self) -> None:
        self.stopping.set()
        self.host.stop()
        self.browser.close()
        with contextlib.suppress(OSError):
            self.directory.save()
