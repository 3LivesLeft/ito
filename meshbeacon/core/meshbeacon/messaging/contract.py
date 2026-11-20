# SPDX-License-Identifier: Apache-2.0
"""Messaging Service contract v1 (ADR 0014): operations, states, limits and validation.

Transport-neutral and free of Home Assistant and presentation concepts. A binding parses a request
into a dict, ``validate`` checks it, and the engine answers with plain dicts. Messages are sent to
contact IDs only: a raw LXMF address is never a recipient (MS-12). Since M5 (ADR 0024) a contact's
address crosses the contract in two places only: ``contact_add`` (the user typed it) and
``conversations`` (shown to the user so that it can be checked and copied).

M5 operations, for the conversation view: ``conversations``, ``history``, ``read``, ``clear``,
``retry``, ``contact_add``, ``contact_rename``, ``contact_remove`` and ``wait`` (a long poll that
returns as soon as anything the view shows has changed).
"""

from __future__ import annotations

import re
from typing import Any, Final

VERSION: Final = 1

OPERATIONS: Final = (
    "send",
    "message",
    "inbound",
    "ack",
    "contacts",
    "status",
    "conversations",
    "history",
    "read",
    "clear",
    "retry",
    "contact_add",
    "contact_rename",
    "contact_remove",
    "wait",
)

# Outbound states (ADR 0011). Final states end the message's life in the queue.
STATES: Final = (
    "queued",
    "sending",
    "delivered",
    "stored_on_node",
    "sent_unconfirmed",
    "failed",
    "rejected",
    "expired",
)
FINAL_STATES: Final = frozenset({"delivered", "stored_on_node", "sent_unconfirmed", "failed", "rejected", "expired"})

# What each state does and does not establish (M4). No state says that the recipient's application
# accepted, showed or read a message: nothing in LXMF reports that.
STATE_MEANINGS: Final = {
    "queued": "Waiting to be sent: not yet attempted, or waiting to try again.",
    "sending": "Handed to LXMF; no outcome yet.",
    "delivered": (
        "The recipient's LXMF returned a delivery proof for this message: it reached the recipient's "
        "LXMF. It does not mean that the recipient's application accepted, "
        "showed or read it (the recipient may still refuse it under its own policy)."
    ),
    "stored_on_node": (
        "A propagation node accepted the message for storage. It has not reached the recipient, and "
        "the engine is not told whether it ever does."
    ),
    "sent_unconfirmed": "LXMF reported the message sent, without a delivery proof.",
    "failed": "Not sent and not retried (the contact was removed).",
    "rejected": "Refused before delivery: by the propagation node (stamp) or by the recipient's transfer.",
    "expired": "Not delivered within seven days. The text stays in the conversation, so it can be retried.",
}

# What an inbound message (``inbound``) has passed. Its ``contact`` is the contact whose key signed
# it, or "unknown" in "anyone" mode: a sender whose signature is valid, but not a known person.
INBOUND_GUARANTEE: Final = (
    "LXMF validated its signature against the sender's announced key, it met the stamp cost where "
    "one applies, and it passed the engine's policy (contacts, size, text, rate)."
)
# LXMF proves delivery to the sender before the engine applies its policy, so a sender may see
# "delivered" for a message that the engine then refused and counted. Refusals are never signalled.

MAX_TEXT_BYTES: Final = 8192  # inbound and outbound content (MS-10)
MAX_TITLE_BYTES: Final = 256
MAX_WAIT: Final = 25.0  # long poll (ADR 0014)

CONTACT_ID: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
IDEMPOTENCY_KEY: Final = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MESSAGE_ID: Final = re.compile(r"^[0-9a-f]{32}$")
ADDRESS: Final = re.compile(r"^[0-9a-f]{32}$")  # an LXMF delivery destination hash
NAME: Final = re.compile(r"^[^\x00-\x1f\x7f\u0080-\u009f\u2028\u2029\u202e\ufeff]{1,32}$")
HISTORY_LIMIT: Final = 100


class ContractError(ValueError):
    """A request the contract does not accept. ``code`` is safe to return to the caller."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _text(value: Any, limit: int, *, required: bool) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ContractError("invalid")
    if "\x00" in value or len(value.encode("utf-8", "surrogatepass")) > limit:
        raise ContractError("invalid")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:  # lone surrogates
        raise ContractError("invalid") from exc
    if required and not value.strip():
        raise ContractError("invalid")
    return value


def _contact_id(value: Any) -> str:
    if not isinstance(value, str) or not CONTACT_ID.match(value):
        raise ContractError("unknown_contact")
    return value


def name(value: Any) -> str:
    """A contact's display name: 1 to 32 printable characters, trimmed."""
    if not isinstance(value, str) or not NAME.match(value.strip()):
        raise ContractError("invalid_name")
    return value.strip()


def address(value: Any) -> str:
    """An LXMF address as people copy it: 32 hex characters, any case, optionally in <angle brackets>."""
    if not isinstance(value, str):
        raise ContractError("invalid_address")
    cleaned = value.strip().removeprefix("<").removesuffix(">").strip().lower()
    if not ADDRESS.match(cleaned):
        raise ContractError("invalid_address")
    return cleaned


def validate(request: Any) -> dict[str, Any]:
    """The request as the engine may act on it, or ContractError. Unknown fields are refused."""
    if not isinstance(request, dict) or request.get("op") not in OPERATIONS:
        raise ContractError("invalid")
    op = request["op"]
    allowed: dict[str, set[str]] = {
        "send": {"op", "contact", "text", "title", "idempotency_key", "auto"},
        "message": {"op", "message_id"},
        "inbound": {"op", "cursor", "wait"},
        "ack": {"op", "cursor"},
        "contacts": {"op"},
        "status": {"op"},
        "conversations": {"op"},
        "history": {"op", "contact", "before", "limit"},
        "read": {"op", "contact"},
        "clear": {"op", "contact"},
        "retry": {"op", "message_id"},
        "contact_add": {"op", "name", "address"},
        "contact_rename": {"op", "contact", "name"},
        "contact_remove": {"op", "contact"},
        "wait": {"op", "revision", "wait"},
    }
    if not set(request) <= allowed[op]:
        raise ContractError("invalid")
    if op == "send":
        contact = request.get("contact")
        key = request.get("idempotency_key")
        if not isinstance(contact, str) or not CONTACT_ID.match(contact):
            raise ContractError("unknown_contact")
        if not isinstance(key, str) or not IDEMPOTENCY_KEY.match(key):
            raise ContractError("invalid")
        return {
            "op": op,
            "contact": contact,
            "text": _text(request.get("text"), MAX_TEXT_BYTES, required=True),
            "title": _text(request.get("title"), MAX_TITLE_BYTES, required=False),
            "idempotency_key": key,
            "auto": request.get("auto") is True,  # an automatic reply (the core's only)
        }
    if op == "message":
        message_id = request.get("message_id")
        if not isinstance(message_id, str) or not MESSAGE_ID.match(message_id):
            raise ContractError("invalid")
        return {"op": op, "message_id": message_id}
    if op in ("history", "read", "clear", "contact_rename", "contact_remove"):
        _contact_id(request.get("contact"))
    if op == "history":
        before, limit = request.get("before"), request.get("limit", 50)
        if before is not None and (isinstance(before, bool) or not isinstance(before, int) or before < 1):
            raise ContractError("invalid")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= HISTORY_LIMIT:
            raise ContractError("invalid")
        return {"op": op, "contact": request["contact"], "before": before, "limit": limit}
    if op in ("read", "clear", "contact_remove"):
        return {"op": op, "contact": request["contact"]}
    if op == "contact_rename":
        return {"op": op, "contact": request["contact"], "name": name(request.get("name"))}
    if op == "contact_add":
        return {"op": op, "name": name(request.get("name")), "address": address(request.get("address"))}
    if op == "retry":
        message_id = request.get("message_id")
        if not isinstance(message_id, str) or not MESSAGE_ID.match(message_id):
            raise ContractError("invalid")
        return {"op": op, "message_id": message_id}
    if op == "wait":
        revision, wait = request.get("revision", -1), request.get("wait", 0)
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < -1:
            raise ContractError("invalid")
        if isinstance(wait, bool) or not isinstance(wait, (int, float)) or not 0 <= wait <= MAX_WAIT:
            raise ContractError("invalid")
        return {"op": op, "revision": revision, "wait": float(wait)}
    if op in ("inbound", "ack"):
        cursor = request.get("cursor", 0)
        if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
            raise ContractError("invalid")
        result: dict[str, Any] = {"op": op, "cursor": cursor}
        if op == "inbound":
            wait = request.get("wait", 0)
            if isinstance(wait, bool) or not isinstance(wait, (int, float)) or not 0 <= wait <= MAX_WAIT:
                raise ContractError("invalid")
            result["wait"] = float(wait)
        return result
    return {"op": op}
