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
  message is handed to that node and reported as ``stored_on_node``: never as ``delivered``.
  ``delivered`` means a delivery proof from the recipient's LXMF, no more (``STATE_MEANINGS``). An
  unknown path is requested and retried; failures back off until the queue's seven-day expiry.
  Pending messages are resubmitted after a restart (at least once: the recipient may see a
  duplicate if the engine stopped between sending and the receipt).
* **Announce.** The delivery destination is announced at start and every six hours so that
  contacts can reach it. The display name is empty unless one is configured (ADR 0009).
* **Contacts and conversations (M5, ADR 0024).** The contact store in ``queue.db`` is the only
  authority: contacts from the app's options are imported into it at start, and the dashboard edits
  it. Inbound policy reads it, so a contact added in the dashboard is admitted at once and a removed
  one is refused at once; verification and stamps are unchanged. Every change the conversation view
  shows raises ``revision``, which ends a ``wait`` long poll.
"""

from __future__ import annotations

import contextlib
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import fsutil
from . import contract, msgidentity
from .contract import ContractError
from .queue import ContactError, Outbound, Queue, QueueFullError, StoredContact
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
RPC_CHECK_INTERVAL = 30.0  # how often the engine checks that the node accepts its RPC requests
RPC_CHECK_TIMEOUT = 15.0  # a check still waiting after this long counts as refused
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
        self.queue.import_contacts([(c.id, c.name, c.destination) for c in settings.contacts])
        self.configured = frozenset(c.destination for c in settings.contacts)
        self.contacts: dict[str, StoredContact] = {}
        self._load_contacts()
        self.revision = 0  # raised by every change the conversation view shows (``wait``)
        self.boot = secrets.token_hex(8)
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
        self.identity_hash: bytes | None = None
        self.rpc_ok: bool | None = None  # None until the first check has finished
        self.rpc_since: float | None = None  # when the check in progress began (monotonic)
        self.has_rpc_key: bool | None = None  # whether it was given the node's key (set at start)
        self.rpc_refusal = ""

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
        self.identity_hash = identity.hash
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
        threading.Thread(target=self._watch_rpc, name="rpc-check", daemon=True).start()
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

    # -- RPC with the node (ADR 0023) --------------------------------------------------------
    def check_rpc(self) -> bool | None:
        """One authenticated request to the node's shared instance: the read-only blackhole check
        of the engine's own identity (``Reticulum.is_blackholed``, public API). True only when the
        node accepted the request and answered; a wrong key raises ``AuthenticationError``.
        None while the engine is not connected to the shared instance (nothing to check)."""
        import multiprocessing

        self.rpc_refusal = ""
        if self.reticulum is None or self.identity_hash is None or not self.connected():
            return None
        try:
            self.reticulum.is_blackholed(self.identity_hash)
        except multiprocessing.AuthenticationError:
            self.rpc_refusal = "its shared-instance authentication was refused"
            return False
        except Exception:
            self.rpc_refusal = "it did not answer"
            return False
        return True

    def _watch_rpc(self) -> None:
        while not self.stopping.is_set():
            self.rpc_since = time.monotonic()
            ok = self.check_rpc()
            self.rpc_since = None
            if ok is not None and ok != self.rpc_ok:
                # Plain words, never a key, an address or exception text (rule 5).
                print(
                    "meshbeacon-messaging: Reticulum accepts the engine's requests"
                    if ok
                    else f"meshbeacon-messaging: Reticulum refused the engine's requests ({self.rpc_refusal})",
                    flush=True,
                )
            self.rpc_ok = ok
            self.stopping.wait(RPC_CHECK_INTERVAL if ok is not None else TICK * 5)

    def rpc(self) -> bool | None:
        """Whether the node accepts the engine's RPC requests; None before the first answer."""
        since = self.rpc_since
        if since is not None and time.monotonic() - since > RPC_CHECK_TIMEOUT:
            return False  # the node has not answered for too long
        return self.rpc_ok

    def announce(self) -> None:
        if self.router is not None and self.delivery is not None:
            self.router.announce(self.delivery.hash)
            self.last_announce = self.clock()

    # -- contacts -----------------------------------------------------------------------------
    def _load_contacts(self) -> None:
        self.contacts = {c.id: c for c in self.queue.contacts()}

    def contact(self, contact_id: str) -> StoredContact | None:
        return self.contacts.get(contact_id)

    def contact_for_destination(self, destination: str) -> StoredContact | None:
        return next((c for c in self.contacts.values() if c.destination == destination), None)

    def changed(self) -> None:
        """Something the conversation view shows has changed: wake every ``wait``."""
        with self.lock:  # re-entrant
            self.revision += 1
            self.arrived.notify_all()

    def request_contact_paths(self) -> None:
        """Learn the contacts' public keys, so that their signatures can be checked (a message from
        a contact the engine has not heard from yet would arrive unverified and be refused)."""
        self.last_contact_paths = self.clock()
        for contact in list(self.contacts.values()):
            self._request_path_if_unknown(contact.destination)

    def _request_path_if_unknown(self, destination: str) -> None:
        import RNS

        destination_hash = bytes.fromhex(destination)
        if RNS.Identity.recall(destination_hash) is None:
            self._request_path(destination_hash)

    def knows(self, contact_id: str) -> bool:
        import RNS

        contact = self.contact(contact_id)
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

        contact = self.contact(message.contact)
        if contact is None:  # removed from the contacts since it was queued
            self.set_state(message.message_id, "failed", "unknown_contact")
            return
        destination_hash = bytes.fromhex(contact.destination)
        recipient = RNS.Identity.recall(destination_hash)
        if recipient is None:  # not heard yet: ask the network, then try again (both methods need it)
            self._request_path(destination_hash)
            self.due[message.message_id] = self.clock() + PATH_WAIT
            return
        destination = RNS.Destination(recipient, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, "delivery")
        method = LXMF.LXMessage.PROPAGATED if propagated else LXMF.LXMessage.DIRECT
        # In "anyone" mode strangers must pay the stamp cost; a contact gets a ticket with every
        # message, so that its replies are not charged (MS-9; LXMF's public include_ticket).
        lxm = LXMF.LXMessage(
            destination,
            self.delivery,
            message.content,
            message.title,
            desired_method=method,
            include_ticket=self.settings.inbound == "anyone",
        )
        lxm.register_delivery_callback(lambda m, mid=message.message_id: self._on_outbound_done(mid, m))
        lxm.register_failed_callback(lambda m, mid=message.message_id: self._on_outbound_failed(mid, m))
        self.set_state(message.message_id, "sending", propagated=propagated)
        self.in_flight[message.message_id] = lxm
        self.router.handle_outbound(lxm)

    def _on_outbound_done(self, message_id: str, lxm: Any) -> None:
        import LXMF

        with self.lock:
            self.in_flight.pop(message_id, None)
            self.failures.pop(message_id, None)
            if lxm.state == LXMF.LXMessage.DELIVERED:
                self.set_state(message_id, "delivered")
            elif lxm.state == LXMF.LXMessage.SENT and lxm.method == LXMF.LXMessage.PROPAGATED:
                self.set_state(message_id, "stored_on_node", propagated=True)
            else:  # pragma: no cover - LXMF calls this only for the two states above
                self.set_state(message_id, "sent_unconfirmed")

    def _on_outbound_failed(self, message_id: str, lxm: Any) -> None:
        import LXMF

        with self.lock:
            self.in_flight.pop(message_id, None)
            message = self.queue.get(message_id)
            if message is None or message.state not in ("queued", "sending"):
                return
            if lxm.state == LXMF.LXMessage.REJECTED:
                by_node = lxm.method == LXMF.LXMessage.PROPAGATED
                self.set_state(message_id, "rejected", "refused_by_node" if by_node else "transfer_refused")
                return
            if lxm.method != LXMF.LXMessage.PROPAGATED and self.settings.propagation_node:
                self._submit(message, propagated=True)  # direct failed: hand it to the node
                return
            failures = self.failures.get(message_id, 0)
            self.failures[message_id] = failures + 1
            self.set_state(message_id, "queued", "retrying")
            self.due[message_id] = self.clock() + BACKOFF[min(failures, len(BACKOFF) - 1)]

    def set_state(self, message_id: str, state: str, reason: str | None = None, **kwargs: Any) -> None:
        self.queue.set_state(message_id, state, reason, **kwargs)
        self.changed()

    def send(self, contact_id: str, title: str, text: str, key: str, *, auto: bool = False) -> dict[str, Any]:
        with self.lock:
            if self.contact(contact_id) is None:
                raise ContractError("unknown_contact")
            try:
                message_id, created = self.queue.enqueue(contact_id, title, text, key, auto=auto)
            except QueueFullError as exc:
                raise ContractError("queue_full") from exc
            if created:
                self.due[message_id] = self.clock()
                self.changed()
            message = self.queue.get(message_id)
            return {"message_id": message_id, "state": message.state if message else "queued"}

    def retry(self, message_id: str) -> dict[str, Any]:
        """Try a waiting message now, or send a failed, refused or expired one again."""
        entry = self.queue.history_entry(message_id)
        if entry is None or entry["direction"] != "out":
            raise ContractError("unknown_message")
        if entry["state"] in ("queued", "sending"):
            if message_id not in self.in_flight:
                self.due[message_id] = self.clock()
            return {"message_id": message_id, "state": entry["state"]}
        if self.contact(entry["contact"]) is None:
            raise ContractError("unknown_contact")
        try:
            new_id = self.queue.requeue(message_id)
        except ContactError as exc:
            raise ContractError(exc.code) from exc
        except QueueFullError as exc:
            raise ContractError("queue_full") from exc
        self.failures.pop(message_id, None)
        self.due[new_id] = self.clock()
        self.changed()
        return {"message_id": new_id, "state": "queued"}

    # -- the conversation view (M5) -----------------------------------------------------------
    def conversations(self) -> list[dict[str, Any]]:
        summary = self.queue.conversations()
        out = [
            {
                "id": c.id,
                "name": c.name,
                "address": c.destination,  # shown to the user, to check and copy (ADR 0024)
                "origin": c.origin,
                "heard": self.knows(c.id),
                "unread": summary.get(c.id, {}).get("unread", 0),
                "last": summary.get(c.id, {}).get("last"),
            }
            for c in self.contacts.values()
        ]
        if STRANGER in summary:  # "anyone" mode: senders who are not contacts, in one list
            out.append(
                {"id": STRANGER, "name": "", "address": None, "origin": "unknown", "heard": False, **summary[STRANGER]}
            )
        return out

    def contact_add(self, name: str, address: str) -> dict[str, Any]:
        if self.delivery is not None and address == self.delivery.hash.hex():
            raise ContractError("own_address")
        try:
            contact_id = self.queue.add_contact(name, address)
        except ContactError as exc:
            raise ContractError(exc.code) from exc
        self._load_contacts()
        self.changed()
        with contextlib.suppress(Exception):  # learn its key now, so its first message is verified
            self._request_path_if_unknown(address)
        return {"contact": contact_id}

    def contact_rename(self, contact_id: str, name: str) -> dict[str, Any]:
        try:
            self.queue.rename_contact(contact_id, name)
        except ContactError as exc:
            raise ContractError(exc.code) from exc
        self._load_contacts()
        self.changed()
        return {"contact": contact_id}

    def contact_remove(self, contact_id: str) -> dict[str, Any]:
        contact = self.contact(contact_id)
        if contact is None:
            raise ContractError("unknown_contact")
        self.queue.remove_contact(contact_id, remember=contact.destination in self.configured)
        for message_id in list(self.due) + list(self.in_flight):  # nothing more is sent to it
            entry = self.queue.get(message_id)
            if entry is not None and entry.contact == contact_id:
                self.in_flight.pop(message_id, None)
                self.due.pop(message_id, None)
        self._load_contacts()
        self.changed()
        return {"contact": contact_id}

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
        contact = self.contact_for_destination(source)
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
            self.changed()

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
            return self.send(req["contact"], req["title"], req["text"], req["idempotency_key"], auto=req["auto"])
        with self.lock:
            if op in ("history", "read", "clear") and req["contact"] != STRANGER and not self.contact(req["contact"]):
                raise ContractError("unknown_contact")
            if op == "conversations":
                return {"conversations": self.conversations(), "revision": self.revision, "boot": self.boot}
            if op == "history":
                return {"messages": self.queue.history(req["contact"], req["before"], req["limit"])}
            if op == "read":
                done = self.queue.mark_read(req["contact"])
                if done:
                    self.changed()
                return {"read": done}
            if op == "clear":
                done = self.queue.clear_history(req["contact"])
                self.changed()
                return {"cleared": done}
            if op == "retry":
                return self.retry(req["message_id"])
            if op == "contact_add":
                return self.contact_add(req["name"], req["address"])
            if op == "contact_rename":
                return self.contact_rename(req["contact"], req["name"])
            if op == "contact_remove":
                return self.contact_remove(req["contact"])
            if op == "wait":
                deadline = time.monotonic() + req["wait"]
                while self.revision == req["revision"] and not self.stopping.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self.arrived.wait(min(remaining, 1.0))
                return {"revision": self.revision, "boot": self.boot}
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
                        {"id": c.id, "name": c.name, "heard": self.knows(c.id)} for c in self.contacts.values()
                    ]
                }
            return {
                "version": contract.VERSION,
                "connected": self.connected(),
                # The node accepts the engine's authenticated RPC requests (ADR 0023).
                "rpc": self.rpc(),
                "rpc_key": self.has_rpc_key,
                "identity": self.identity_event,
                # The engine's own LXMF address, for the user to give to contacts (D-M4-8). Never a
                # contact's address: those stay inside the engine (MS-12).
                "address": self.delivery.hash.hex() if self.delivery is not None else None,
                **self.queue.counts(),
                "counters": self.queue.counters(),
            }
