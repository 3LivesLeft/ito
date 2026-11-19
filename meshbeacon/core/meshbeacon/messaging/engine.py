# SPDX-License-Identifier: Apache-2.0
"""The messaging engine (M4, ADRs 0009 to 0011): LXMF over the node's shared Reticulum instance.

Runs as its own user (``mb-lxmf``, ADR 0018) and uses only LXMF's and RNS's public API. It never
imports Home Assistant and never needs it: the contract (ADR 0014) is the only way in.

Policy, as decided in the M4 plan:

* **Inbound.** Only messages whose signature LXMF validated are accepted. With ``inbound:
  contacts`` (the default) only configured contacts get through; with ``anyone`` strangers do
  too, but LXMF enforces the stamp cost. Content must be valid UTF-8 within the contract's limits;
  LXMF fields (attachments, telemetry, commands …) are never acted on, only counted. Each sender,
  and the engine as a whole, is rate-limited. Every refusal is counted, never logged with an
  address (rule 5).
* **Outbound.** Direct delivery first. If it fails and a propagation node is configured, the
  message is handed to that node and reported as ``stored_on_node``: never as ``delivered``. An
  unknown path is requested and retried; failures back off until the queue's seven-day expiry.
  Pending messages are resubmitted after a restart (at least once: the recipient may see a
  duplicate if the engine stopped between sending and the receipt).
* **Announce.** The delivery destination is announced at start and every six hours so that
  contacts can reach it. The display name is empty unless one is configured (ADR 0009).
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import fsutil
from . import contract, msgidentity
from .contract import ContractError
from .queue import Outbound, Queue, QueueFullError
from .settings import STRANGER, Settings

APP_NAME = "lxmf"
ANNOUNCE_INTERVAL = 6 * 3600.0
CONTACT_PATH_INTERVAL = 1800.0  # ask for contacts the engine has not heard from
MAINTENANCE_INTERVAL = 3600.0
TICK = 1.0
PATH_WAIT = 15.0  # after a path request
BACKOFF = (60.0, 300.0, 900.0, 3600.0)  # after a failed attempt; the last repeats until expiry
RATE_PER_SENDER = (20, 60.0)  # at most 20 messages a minute from one sender
RATE_TOTAL = (60, 60.0)  # and 60 a minute in all
HOLD_MAX = 50  # messages waiting for their sender's key, at most
HOLD_FOR = 120.0
SOURCE_UNKNOWN = 0x01  # LXMF.LXMessage.SOURCE_UNKNOWN (checked against LXMF in the tests)


class EngineError(Exception):
    """The engine cannot start (no shared instance, damaged identity …): a safe, generic message."""


class RateLimiter:
    def __init__(self, limit: int, window: float, clock: Callable[[], float]) -> None:
        self.limit, self.window, self.clock = limit, window, clock
        self.events: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = self.clock()
        events = self.events.setdefault(key, deque())
        while events and events[0] <= now - self.window:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(now)
        if len(self.events) > 1000:  # forget idle senders
            for stale in [k for k, v in self.events.items() if not v]:
                del self.events[stale]
        return True


def _decode(data: Any, limit: int) -> str | None:
    """UTF-8 text within ``limit`` bytes and free of NUL, or None."""
    if data is None:
        return ""
    if isinstance(data, str):
        data = data.encode("utf-8", "surrogatepass")
    if not isinstance(data, bytes) or len(data) > limit or b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


class Engine:
    def __init__(
        self,
        data: Path,
        settings: Settings,
        *,
        rns_config: Path | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.data = data
        self.settings = settings
        self.rns_config = rns_config if rns_config is not None else data / "rns"
        self.clock = clock
        self.lock = threading.RLock()
        self.arrived = threading.Condition(self.lock)
        self.queue = Queue(data / "queue.db", retention_days=settings.retention_days, clock=clock)
        self.per_sender = RateLimiter(*RATE_PER_SENDER, clock)
        self.total = RateLimiter(*RATE_TOTAL, clock)
        self.due: dict[str, float] = {}  # message ID -> when to try again
        self.in_flight: dict[str, Any] = {}  # message ID -> LXMessage
        self.failures: dict[str, int] = {}
        self.held: dict[str, tuple[float, bytes, bytes]] = {}
        self.reticulum: Any = None
        self.router: Any = None
        self.delivery: Any = None
        self.identity_event = ""
        self.stopping = threading.Event()
        self.last_announce = 0.0
        self.last_maintenance = 0.0
        self.last_contact_paths = 0.0

    # -- start and stop ---------------------------------------------------------------------
    def start(self) -> None:
        import LXMF
        import RNS

        try:
            identity, self.identity_event = msgidentity.load_or_create(self.data)
        except msgidentity.IdentityError as exc:
            raise EngineError("the messaging identity is damaged; nothing was replaced") from exc
        try:
            # Only ever a client: if the node's shared instance is not running, RNS refuses to
            # start rather than become a shared instance itself (public constructor argument).
            self.reticulum = RNS.Reticulum(configdir=str(self.rns_config), require_shared_instance=True)
        except SystemError as exc:
            raise EngineError("the Reticulum node is not running") from exc
        anyone = self.settings.inbound == "anyone"
        self.router = LXMF.LXMRouter(
            storagepath=str(self.data),
            autopeer=False,
            enforce_stamps=anyone,
        )
        self.delivery = self.router.register_delivery_identity(
            identity,
            display_name=self.settings.display_name or None,
            stamp_cost=self.settings.stamp_cost if anyone and self.settings.stamp_cost else None,
        )
        self.router.register_delivery_callback(self._on_inbound)
        if self.settings.propagation_node:
            self.router.set_outbound_propagation_node(bytes.fromhex(self.settings.propagation_node))
        # The engine's own address, for the developer (M4) and later the interface (M5): a private
        # file, like the identity it is derived from. Never logged.
        fsutil.atomic_write(self.data / "address", self.delivery.hash.hex().encode() + b"\n")
        with self.lock:
            now = self.clock()
            for message in self.queue.pending():
                self.due[message.message_id] = now  # resubmitted after a restart (ADR 0011)
        self.announce()

    def stop(self) -> None:
        self.stopping.set()
        if self.router is not None:
            with contextlib.suppress(Exception):
                self.router.exit_handler()
        with self.lock:
            self.queue.close()

    def connected(self) -> bool:
        return bool(self.reticulum is not None and self.reticulum.is_connected_to_shared_instance)

    def announce(self) -> None:
        if self.router is not None and self.delivery is not None:
            self.router.announce(self.delivery.hash)
            self.last_announce = self.clock()

    def request_contact_paths(self) -> None:
        """Learn the contacts' public keys, so that their signatures can be checked (a message from
        a contact the engine has not heard from yet would arrive unverified and be refused)."""
        import RNS

        self.last_contact_paths = self.clock()
        for contact in self.settings.contacts:
            destination_hash = bytes.fromhex(contact.destination)
            if RNS.Identity.recall(destination_hash) is None:
                RNS.Transport.request_path(destination_hash)

    def knows(self, contact_id: str) -> bool:
        import RNS

        contact = self.settings.contact(contact_id)
        return contact is not None and RNS.Identity.recall(bytes.fromhex(contact.destination)) is not None

    # -- the job loop ------------------------------------------------------------------------
    def run(self) -> None:
        while not self.stopping.is_set():
            self.tick()
            self.stopping.wait(TICK)

    def tick(self) -> None:
        now = self.clock()
        if now - self.last_announce >= ANNOUNCE_INTERVAL:
            self.announce()
        if now - self.last_contact_paths >= CONTACT_PATH_INTERVAL:
            self.request_contact_paths()
        with self.lock:
            if now - self.last_maintenance >= MAINTENANCE_INTERVAL:
                self.queue.maintenance()
                self.last_maintenance = now
            if self.held:
                self._recheck_held(now)
            for message_id in [m for m, at in self.due.items() if at <= now]:
                del self.due[message_id]
                message = self.queue.get(message_id)
                if message is not None and message.state in ("queued", "sending"):
                    self._submit(message)

    # -- outbound -----------------------------------------------------------------------------
    def _submit(self, message: Outbound, *, propagated: bool = False) -> None:
        import LXMF
        import RNS

        contact = self.settings.contact(message.contact)
        if contact is None:  # removed from the contacts since it was queued
            self.queue.set_state(message.message_id, "failed", "unknown_contact")
            return
        destination_hash = bytes.fromhex(contact.destination)
        recipient = RNS.Identity.recall(destination_hash)
        if recipient is None:  # not heard yet: ask the network, then try again (both methods need it)
            RNS.Transport.request_path(destination_hash)
            self.due[message.message_id] = self.clock() + PATH_WAIT
            return
        destination = RNS.Destination(recipient, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, "delivery")
        method = LXMF.LXMessage.PROPAGATED if propagated else LXMF.LXMessage.DIRECT
        lxm = LXMF.LXMessage(destination, self.delivery, message.content, message.title, desired_method=method)
        lxm.register_delivery_callback(lambda m, mid=message.message_id: self._on_outbound_done(mid, m))
        lxm.register_failed_callback(lambda m, mid=message.message_id: self._on_outbound_failed(mid, m))
        self.queue.set_state(message.message_id, "sending", propagated=propagated)
        self.in_flight[message.message_id] = lxm
        self.router.handle_outbound(lxm)

    def _on_outbound_done(self, message_id: str, lxm: Any) -> None:
        import LXMF

        with self.lock:
            self.in_flight.pop(message_id, None)
            self.failures.pop(message_id, None)
            if lxm.state == LXMF.LXMessage.DELIVERED:
                self.queue.set_state(message_id, "delivered")
            elif lxm.state == LXMF.LXMessage.SENT and lxm.method == LXMF.LXMessage.PROPAGATED:
                self.queue.set_state(message_id, "stored_on_node", propagated=True)
            else:  # pragma: no cover - LXMF calls this only for the two states above
                self.queue.set_state(message_id, "sent_unconfirmed")

    def _on_outbound_failed(self, message_id: str, lxm: Any) -> None:
        import LXMF

        with self.lock:
            self.in_flight.pop(message_id, None)
            message = self.queue.get(message_id)
            if message is None or message.state not in ("queued", "sending"):
                return
            if lxm.state == LXMF.LXMessage.REJECTED:
                self.queue.set_state(message_id, "rejected", "rejected_by_recipient")
                return
            if lxm.method != LXMF.LXMessage.PROPAGATED and self.settings.propagation_node:
                self._submit(message, propagated=True)  # direct failed: hand it to the node
                return
            failures = self.failures.get(message_id, 0)
            self.failures[message_id] = failures + 1
            self.queue.set_state(message_id, "queued", "retrying")
            self.due[message_id] = self.clock() + BACKOFF[min(failures, len(BACKOFF) - 1)]

    def send(self, contact_id: str, title: str, text: str, key: str) -> dict[str, Any]:
        with self.lock:
            if self.settings.contact(contact_id) is None:
                raise ContractError("unknown_contact")
            try:
                message_id, created = self.queue.enqueue(contact_id, title, text, key)
            except QueueFullError as exc:
                raise ContractError("queue_full") from exc
            if created:
                self.due[message_id] = self.clock()
            message = self.queue.get(message_id)
            return {"message_id": message_id, "state": message.state if message else "queued"}

    # -- inbound ------------------------------------------------------------------------------
    def _refuse(self, why: str) -> None:
        self.queue.count(f"inbound_refused_{why}")

    def _on_inbound(self, lxm: Any) -> None:
        with self.lock:
            try:
                self._accept(lxm)
            except Exception:
                self._refuse("error")

    def _accept(self, lxm: Any, *, recheck: bool = False) -> None:
        source = lxm.source_hash.hex()
        contact = self.settings.contact_for_destination(source)
        if contact is None and self.settings.inbound != "anyone":
            self._refuse("not_a_contact")  # by the claimed sender alone: no need to verify
            return
        if lxm.signature_validated is not True:
            if lxm.unverified_reason == SOURCE_UNKNOWN and not recheck and len(self.held) < HOLD_MAX:
                # Not heard from yet: ask for the sender's key and check again shortly, rather than
                # lose a message its sender already sees as delivered.
                self.held[lxm.hash.hex()] = (self.clock() + HOLD_FOR, lxm.packed, lxm.source_hash)
                self._request_path(lxm.source_hash)
                self.queue.count("inbound_held_unverified")
                return
            self._refuse("unverified")
            return
        if not self.total.allow("*") or not self.per_sender.allow(source):
            self._refuse("rate")
            return
        title = _decode(lxm.title, contract.MAX_TITLE_BYTES)
        content = _decode(lxm.content, contract.MAX_TEXT_BYTES)
        if title is None or content is None:
            self._refuse("invalid")
            return
        if lxm.get_fields():
            self.queue.count("inbound_fields_ignored")  # never acted on (ADR 0010)
        if self.queue.receive(lxm.hash.hex(), contact.id if contact else STRANGER, title, content):
            self.arrived.notify_all()

    def _request_path(self, destination_hash: bytes) -> None:
        import RNS

        RNS.Transport.request_path(destination_hash)

    def _recheck_held(self, now: float) -> None:
        """Held messages whose sender's key has arrived are unpacked again (public LXMF API) and
        go through the whole policy once more; the rest are refused when their time is up."""
        import LXMF
        import RNS

        for key, (expires, packed, source_hash) in list(self.held.items()):
            if RNS.Identity.recall(source_hash) is not None:
                del self.held[key]
                try:
                    self._accept(LXMF.LXMessage.unpack_from_bytes(packed), recheck=True)
                except Exception:
                    self._refuse("error")
            elif expires <= now:
                del self.held[key]
                self._refuse("unverified")

    # -- the contract ------------------------------------------------------------------------
    def handle(self, request: Any) -> dict[str, Any]:
        """Answer one contract request (ADR 0014). Never raises; errors carry a safe code only."""
        try:
            req = contract.validate(request)
            return {"ok": True, **self._dispatch(req)}
        except ContractError as exc:
            return {"ok": False, "error": exc.code}
        except Exception:
            return {"ok": False, "error": "internal"}

    def _dispatch(self, req: dict[str, Any]) -> dict[str, Any]:
        op = req["op"]
        if op == "send":
            return self.send(req["contact"], req["title"], req["text"], req["idempotency_key"])
        with self.lock:
            if op == "message":
                message = self.queue.get(req["message_id"])
                if message is None:
                    raise ContractError("unknown_message")
                return {
                    "message_id": message.message_id,
                    "contact": message.contact,
                    "state": message.state,
                    "created": message.created,
                    "updated": message.updated,
                }
            if op == "inbound":
                deadline = time.monotonic() + req["wait"]
                items = self.queue.inbound_after(req["cursor"])
                while not items and not self.stopping.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self.arrived.wait(min(remaining, 1.0))
                    items = self.queue.inbound_after(req["cursor"])
                return {"messages": items}
            if op == "ack":
                return {"acknowledged": self.queue.ack(req["cursor"])}
            if op == "contacts":
                return {
                    "contacts": [
                        {"id": c.id, "name": c.name, "heard": self.knows(c.id)} for c in self.settings.contacts
                    ]
                }
            return {
                "version": contract.VERSION,
                "connected": self.connected(),
                "identity": self.identity_event,
                **self.queue.counts(),
                "counters": self.queue.counters(),
            }
