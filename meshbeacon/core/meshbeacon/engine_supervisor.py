# SPDX-License-Identifier: Apache-2.0
"""The core's supervision of the optional messaging engine (M4 WP4, MS-15; D-M4-8).

Every MeshBeacon image carries the engine, but it runs only when the user ticks "Enable LXMF
messaging" (``messaging_enabled``, off by default). When it is off, this module does nothing at
all. It never imports the engine or LXMF (MS-21) and never touches Reticulum: an engine that fails,
hangs or is killed is stopped and started again on its own, and Reticulum and the status API carry
on.

- **Settings.** Before each start, the core writes the engine's settings from the validated
  options to ``/run/meshbeacon-messaging/config/settings.json`` (0640, the core's, group
  ``mb-msg``): the engine can read it and nothing else of the options. The engine never sees
  ``options.json``, which holds peer passphrases (IS-2).
- **Start.** Once Reticulum is running and has reported its first status (its shared instance is
  then up), as the ``messaging`` s6 service under its own user, ``mb-lxmf``.
- **Health.** Every 10 s, on a background thread, a ``status`` request over the engine's socket,
  which must be served by ``mb-lxmf``. Three missed answers in a row count as a hang. The engine
  reports whether the node accepts its authenticated RPC requests (ADR 0023); until it does, the
  dashboard never shows "Running", and while the node refuses them it shows a problem.
- **Link** (the M4 binding, ADR 0014). With the same answers the core reports the engine's state,
  its own address and its counters; it reads arrivals to count them and to send each contact the
  optional automatic reply (at most one per contact every six hours, so that two automatic
  responders cannot loop), then acknowledges them. **The core never logs or stores message
  content.**
- **Home Assistant binding** (M5, ADR 0024): ``forward`` passes the conversation view's requests
  from the messaging endpoint to the engine, and nothing else: an allow-list of operations, sends
  limited to 10 a minute and 200 a day, never an automatic reply, long polls of at most 8 s.
- Restarts back off (10 s to 5 min). After five failures in 30 minutes messaging pauses until the
  app is restarted; nothing else is affected.
- Output reaches the app log through the core's redaction, like Reticulum's.
"""

from __future__ import annotations

import contextlib
import grp
import json
import re
import socket
import struct
import subprocess
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from . import fsutil, procinfo
from .settings import Messaging

SOCKET = Path("/run/meshbeacon-messaging/engine.sock")
SETTINGS_FILE = Path("/run/meshbeacon-messaging/config/settings.json")
SETTINGS_GROUP = "mb-msg"  # the core and the engine only (ADR 0018)
ENGINE_UID = 9102
STAMP_COST = 8  # what strangers must spend when "accept messages from anyone" is on (MS-9)
BACKOFF = (10.0, 30.0, 60.0, 120.0, 300.0)
PAUSE_AFTER = 5
PAUSE_WINDOW = 1800.0
HEALTH_INTERVAL = 10.0
HEALTH_TIMEOUT = 5.0
HEALTH_MISSES = 3
STOP_GRACE = 10.0
MAX_LINE = 4 * 1024 * 1024
ADDRESS = re.compile(r"^[0-9a-f]{32}$")

REPLY_TEXT = "ito received your message. (This is an automatic reply.)"
AUTO_REPLY_EVERY = 6 * 3600.0  # at most one automatic reply per contact in this time (no loops)
# The Home Assistant binding (M5): what Home Assistant may ask of the engine, and how much.
HA_OPERATIONS = frozenset(
    {
        "conversations",
        "history",
        "read",
        "clear",
        "retry",
        "send",
        "message",
        "contact_add",
        "contact_rename",
        "contact_remove",
        "wait",
    }
)
HA_MAX_WAIT = 8.0  # under the listener's 10 s connection deadline
SEND_LIMITS = ((10, 60.0), (200, 86400.0))
REQUEST_LIMIT = (240, 60.0)  # every other request, per minute
REFUSAL_LOG_EVERY = 60.0  # one log line a minute at most while requests are refused
MSG_REFUSED = {
    "send": (
        "⚠ Messaging: Home Assistant sent more messages than allowed (10 a minute, 200 a day); refusing them for now."
    ),
    "request": "⚠ Messaging: Home Assistant asked for more than 240 reads a minute; refusing them for now.",
}
MSG_MESSAGING_UNAVAILABLE = "unavailable"
MSG_PAUSED = (
    "⚠ Messaging stopped after repeated failures and is paused until the app is restarted. Reticulum is not affected."
)
# What the dashboard shows for each way the engine can stop (exit codes of meshbeacon.messaging).
EXIT_REASONS = {
    2: "Messaging could not start: its settings were refused. Check the messaging options.",
    3: (
        "Messaging could not start: Reticulum was not reachable, or the messaging identity is damaged "
        "(ito never replaces it: restore the app from a backup). The app log says which."
    ),
}
MSG_RPC_REFUSED = (
    "Messaging is running, but Reticulum refuses its requests, so it cannot work properly. "
    "Restart the app; if this repeats, please report it."
)
# The key could not be created (ADR 0023). The usual cause: Home Assistant still enforces the app's
# previous AppArmor profile, which it replaces on install and update but not on "Rebuild"
# (Supervisor ``App.rebuild``), so the root init step may not write /run/meshbeacon-rpc.
MSG_RPC_KEY_MISSING = (
    "Messaging has no access key for Reticulum, so Reticulum refuses its requests. Home Assistant "
    "is probably still using the app's previous security profile: update the app to the latest "
    "version (Rebuild is not enough). Your node and messaging identities are kept."
)
DISABLED: dict[str, Any] = {"enabled": False, "state": "disabled", "message": None}

Link = Callable[..., dict[str, Any] | None]


class Window:
    """At most ``limit`` events in ``window`` seconds (in memory; reset when the app restarts)."""

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


class Process(Protocol):
    def poll(self) -> int | None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...


def request(
    payload: dict[str, Any], path: Path = SOCKET, expected_uid: int = ENGINE_UID, timeout: float = HEALTH_TIMEOUT
) -> dict[str, Any] | None:
    """One contract request; the answer only if the engine's own user served it (peer check)."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(path))
            creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            if struct.unpack("3i", creds)[1] != expected_uid:
                return None  # not the engine: refuse to talk to it (peer check, both ways)
            sock.sendall(json.dumps(payload, ensure_ascii=False).encode() + b"\n")  # UTF-8: 8 KiB of text stays ~8 KiB
            answer = json.loads(sock.makefile("rb").readline(MAX_LINE))
    except (OSError, ValueError):
        return None
    return answer if isinstance(answer, dict) else None


def probe(path: Path, expected_uid: int) -> bool:
    """One ``status`` request; True only for a well-formed answer from the engine's user."""
    answer = request({"op": "status"}, path, expected_uid)
    return answer is not None and answer.get("ok") is True


def contact_ids(messaging: Messaging) -> list[str]:
    """A stable contract ID for each contact, from its name (``a-z0-9_-``, unique)."""
    ids: list[str] = []
    for contact in messaging.contacts:
        base = re.sub(r"[^a-z0-9_-]+", "-", contact.name.lower()).strip("-_")[:28] or "contact"
        candidate, n = base, 2
        while candidate in ids or candidate == "unknown":
            candidate, n = f"{base}-{n}", n + 1
        ids.append(candidate)
    return ids


def engine_settings(messaging: Messaging) -> dict[str, Any]:
    """The engine's settings (``meshbeacon.messaging.settings``) from the validated options."""
    return {
        "display_name": messaging.display_name,
        "inbound": "anyone" if messaging.accept_anyone else "contacts",
        "stamp_cost": STAMP_COST,
        "propagation_node": messaging.propagation_node,
        "retention_days": 0,
        "contacts": [
            {"id": cid, "name": c.name, "destination": c.address}
            for cid, c in zip(contact_ids(messaging), messaging.contacts, strict=True)
        ],
    }


def write_settings(messaging: Messaging, path: Path = SETTINGS_FILE, group: str | None = SETTINGS_GROUP) -> None:
    gid = grp.getgrnam(group).gr_gid if group else None
    data = (json.dumps(engine_settings(messaging), sort_keys=True, indent=2) + "\n").encode()
    fsutil.atomic_write(path, data, mode=0o640, group=gid)


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


class EngineSupervisor:
    def __init__(
        self,
        start: Callable[[], Process],
        say: Callable[[str], None],
        clock: Callable[[], float],
        *,
        messaging: Messaging | None = None,
        health: Callable[[], bool] | None = None,
        link: Link | None = None,
        settings_writer: Callable[[Messaging], None] | None = None,
    ) -> None:
        self._start = start
        self.say = say
        self.clock = clock
        self.messaging = messaging or Messaging(enabled=True)
        self._health = health
        self.link: Link = link or request
        self.write_settings = settings_writer or write_settings
        self.proc: Process | None = None
        self.state = "waiting"  # waiting | running | backoff | paused | stopped
        self.failures: deque[float] = deque()
        self.next_attempt = 0.0
        self.next_health = 0.0
        self.misses = 0
        self.lock = threading.Lock()
        self.probing = False
        self.result: bool | None = None
        self.reason: str | None = None
        self.healthy = False  # answered since its last start
        ids = contact_ids(self.messaging)
        self.names = dict(zip(ids, (c.name for c in self.messaging.contacts), strict=True))
        self.view: dict[str, Any] = {}  # what the engine last reported (under the lock)
        self.replies: deque[str] = deque(maxlen=20)
        self.replies_sent = 0
        self.last_auto_reply: dict[str, float] = {}
        self.send_windows = [Window(n, w, clock) for n, w in SEND_LIMITS]
        self.request_window = Window(*REQUEST_LIMIT, clock)
        self.refusals_logged: dict[str, float] = {}

    # -- the core calls step() on every loop ---------------------------------------------------
    def step(self, node_ready: bool) -> None:
        now = self.clock()
        if self.state in ("paused", "stopped"):
            return
        if self.proc is not None:
            code = self.proc.poll()
            if code is not None:
                self.proc = None
                self._failed(EXIT_REASONS.get(code, f"Messaging stopped unexpectedly (exit code {code})."), now)
                return
            self._check_health(now)
            return
        if node_ready and now >= self.next_attempt:
            self._launch(now)

    def _launch(self, now: float) -> None:
        try:
            self.write_settings(self.messaging)
            self.proc = self._start()
        except (OSError, KeyError):
            self._failed("Messaging could not be started.", now)
            return
        self.state = "running"
        self.misses = 0
        self.healthy = False
        self.next_health = now + 2.0  # a first answer soon after the start

    def _check_health(self, now: float) -> None:
        with self.lock:
            result, self.result = self.result, None
            probing = self.probing
        if result is not None:
            self.misses = 0 if result else self.misses + 1
            if result:
                self.healthy, self.reason = True, None
            if self.misses >= HEALTH_MISSES:
                proc, self.proc = self.proc, None
                if proc is not None:
                    proc.kill()  # hung: no grace, and never a wait that would hold up the core
                self._failed("Messaging stopped responding and has been restarted.", now)
                return
        if not probing and now >= self.next_health:
            self.next_health = now + HEALTH_INTERVAL
            with self.lock:
                self.probing = True
            threading.Thread(target=self._probe, daemon=True).start()  # never blocks the core

    def _probe(self) -> None:
        ok = False
        with contextlib.suppress(Exception):
            status: dict[str, Any] | None = None
            if self._health is not None:
                ok = bool(self._health())
            else:
                status = self.link({"op": "status"})
                ok = status is not None and status.get("ok") is True
            if ok:
                self._sync(status)
        with self.lock:
            self.result, self.probing = ok, False

    def _sync(self, status: dict[str, Any] | None) -> None:
        """Read the engine's view, count arrivals, reply to contacts, acknowledge (link thread)."""
        if status is None:
            status = self.link({"op": "status"})
        view: dict[str, Any] = {}
        if status and status.get("ok"):
            counters = status.get("counters")
            counters = counters if isinstance(counters, dict) else {}
            address = status.get("address")
            view["address"] = address if isinstance(address, str) and ADDRESS.match(address) else None
            view["connected"] = status.get("connected") is True
            rpc = status.get("rpc")
            view["rpc"] = rpc if isinstance(rpc, bool) else None  # None: not checked yet
            has_key = status.get("rpc_key")
            view["rpc_key"] = has_key if isinstance(has_key, bool) else None
            view["received"] = _count(counters.get("inbound_received"))
            view["refused"] = sum(_count(v) for k, v in counters.items() if str(k).startswith("inbound_refused_"))
        contacts = self.link({"op": "contacts"})
        if contacts and contacts.get("ok") and isinstance(contacts.get("contacts"), list):
            items = [c for c in contacts["contacts"] if isinstance(c, dict) and isinstance(c.get("id"), str)]
            view["contacts_reachable"] = sum(1 for c in items if c.get("heard") is True)
            view["contacts_configured"] = len(items)
            # The engine's contact store is the authority (M5): dashboard contacts count too.
            self.names = {c["id"]: str(c.get("name") or c["id"])[:32] for c in items}
        arrivals = self.link({"op": "inbound", "cursor": 0, "wait": 0})
        messages = arrivals.get("messages") if arrivals and arrivals.get("ok") else None
        if isinstance(messages, list) and messages:
            self._arrived([m for m in messages if isinstance(m, dict)], view)
        if self.replies:
            answer = self.link({"op": "message", "message_id": self.replies[-1]})
            if answer and answer.get("ok") and isinstance(answer.get("state"), str):
                view["last_reply_state"] = answer["state"]
        with self.lock:
            self.view.update(view)

    def _arrived(self, messages: list[dict[str, Any]], view: dict[str, Any]) -> None:
        last = 0
        for item in messages:  # content is never read here, only who and when
            last = max(last, _count(item.get("cursor")))
            raw_contact = item.get("contact")
            contact = raw_contact if isinstance(raw_contact, str) and raw_contact in self.names else None
            received = item.get("received")
            view["last_received_at"] = received if isinstance(received, (int, float)) else None
            view["last_received_from"] = self.names[contact] if contact is not None else None
            if self.messaging.auto_reply and contact is not None and isinstance(item.get("message_id"), str):
                self._auto_reply(contact, item["message_id"])
        if last:
            self.link({"op": "ack", "cursor": last})  # deletes the content at once (MS-4)

    def _auto_reply(self, contact: str, message_id: str) -> None:
        """One automatic reply per contact per AUTO_REPLY_EVERY: a contact that also answers
        automatically gets one reply, never an endless exchange."""
        now = self.clock()
        last = self.last_auto_reply.get(contact)
        if last is not None and now - last < AUTO_REPLY_EVERY:
            return
        sent = self.link(
            {
                "op": "send",
                "contact": contact,
                "title": "",
                "text": REPLY_TEXT,
                "idempotency_key": f"reply-{message_id}"[:64],
                "auto": True,
            }
        )
        if sent and sent.get("ok") and isinstance(sent.get("message_id"), str):
            self.last_auto_reply[contact] = now
            self.replies.append(sent["message_id"])
            self.replies_sent += 1

    # -- the Home Assistant binding (M5) -------------------------------------------------------
    def available(self) -> bool:
        return self.state == "running" and self.healthy

    def forward(self, request: Any) -> tuple[int, dict[str, Any]]:
        """A request from Home Assistant's messaging endpoint: (HTTP status, answer).

        Only the conversation view's operations; never an automatic reply; sends rate-limited.
        The engine validates everything again (it is the authority). Content is never logged."""
        if not isinstance(request, dict) or request.get("op") not in HA_OPERATIONS or "auto" in request:
            return 400, {"ok": False, "error": "invalid"}
        if not self.available():
            return 503, {"ok": False, "error": MSG_MESSAGING_UNAVAILABLE}
        op = request["op"]
        timeout = HEALTH_TIMEOUT
        if op == "wait":
            wait = request.get("wait", 0)
            if isinstance(wait, bool) or not isinstance(wait, (int, float)) or not 0 <= wait <= HA_MAX_WAIT:
                return 400, {"ok": False, "error": "invalid"}
            timeout = HA_MAX_WAIT + HEALTH_TIMEOUT
        elif op == "send":
            if not all(w.allow() for w in self.send_windows):
                return self._refused("send")
        elif not self.request_window.allow():
            return self._refused("request")
        answer = self.link(request, timeout=timeout)
        if answer is None:
            return 503, {"ok": False, "error": MSG_MESSAGING_UNAVAILABLE}
        return (200 if answer.get("ok") is True else 400), answer

    def _refused(self, kind: str) -> tuple[int, dict[str, Any]]:
        """A request over its allowance: 429, and a log line at most once a minute (no content)."""
        now = self.clock()
        last = self.refusals_logged.get(kind)
        if last is None or now - last >= REFUSAL_LOG_EVERY:
            self.refusals_logged[kind] = now
            self.say(MSG_REFUSED[kind])
        return 429, {"ok": False, "error": "rate_limited"}

    def _failed(self, reason: str, now: float) -> None:
        self.failures.append(now)
        while self.failures and self.failures[0] <= now - PAUSE_WINDOW:
            self.failures.popleft()
        self.reason = reason
        self.healthy = False
        self.say(f"⚠ {reason}")
        if len(self.failures) >= PAUSE_AFTER:
            self.state = "paused"
            self.say(MSG_PAUSED)
            return
        self.state = "backoff"
        self.next_attempt = now + BACKOFF[min(len(self.failures) - 1, len(BACKOFF) - 1)]

    def _stop_process(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(STOP_GRACE)
        except subprocess.TimeoutExpired:
            proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(STOP_GRACE)

    def stop(self) -> None:
        """At shutdown, before Reticulum: the engine closes its queue and leaves cleanly."""
        self.state = "stopped"
        self._stop_process()

    def memory_bytes(self) -> int | None:
        pid = getattr(self.proc, "pid", None)
        return procinfo.memory_bytes(pid) if isinstance(pid, int) and pid > 0 else None

    def public(self) -> dict[str, Any]:
        """The ``messaging`` section of the status API: plain states and counts, never content."""
        with self.lock:
            view = dict(self.view)
        if self.state == "paused":
            state, message = "paused", MSG_PAUSED.lstrip("⚠ ")
        elif self.state == "backoff":
            state, message = "error", f"{self.reason} ito will try again shortly."
        elif self.state == "running" and self.healthy and view.get("connected") and view.get("rpc") is False:
            # Connected, but the node refuses its RPC requests (ADR 0023): never "Running".
            state, message = "error", MSG_RPC_KEY_MISSING if view.get("rpc_key") is False else MSG_RPC_REFUSED
        elif self.state == "running" and self.healthy and view.get("connected") and view.get("rpc") is True:
            state, message = "running", None
        elif self.state == "running" and self.healthy and view.get("connected"):
            state, message = "starting", "Messaging is checking its connection to Reticulum."
        elif self.state == "running" and self.healthy:
            state, message = "starting", "Messaging is waiting for Reticulum's shared instance."
        else:
            state, message = "starting", None
        return {
            "enabled": True,
            "state": state,
            "message": message,
            "address": view.get("address"),
            "contacts_configured": view.get("contacts_configured", len(self.messaging.contacts)),
            "contacts_reachable": view.get("contacts_reachable"),
            "accept_anyone": self.messaging.accept_anyone,
            "auto_reply": self.messaging.auto_reply,
            "received": view.get("received"),
            "refused": view.get("refused"),
            "replies_sent": self.replies_sent,
            "last_reply_state": view.get("last_reply_state"),
            "last_received_at": view.get("last_received_at"),
            "last_received_from": view.get("last_received_from"),
            "memory_bytes": self.memory_bytes(),
            "restarts": len(self.failures),
        }

    def snapshot(self) -> dict[str, Any]:  # for tests and logs
        return {"state": self.state, "recent_failures": len(self.failures)}
