# SPDX-License-Identifier: Apache-2.0
"""Messaging Service contract v1 (ADR 0014): operations, states, limits and validation.

Transport-neutral and free of Home Assistant and presentation concepts. A binding parses a request
into a dict, ``validate`` checks it, and the engine answers with plain dicts. Contacts are referred
to by their contact ID only; no LXMF address ever crosses the contract (MS-12).
"""

from __future__ import annotations

import re
from typing import Any, Final

VERSION: Final = 1

OPERATIONS: Final = ("send", "message", "inbound", "ack", "contacts", "status")

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
    "expired": "Not delivered within seven days; its content has been deleted.",
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


def validate(request: Any) -> dict[str, Any]:
    """The request as the engine may act on it, or ContractError. Unknown fields are refused."""
    if not isinstance(request, dict) or request.get("op") not in OPERATIONS:
        raise ContractError("invalid")
    op = request["op"]
    allowed: dict[str, set[str]] = {
        "send": {"op", "contact", "text", "title", "idempotency_key"},
        "message": {"op", "message_id"},
        "inbound": {"op", "cursor", "wait"},
        "ack": {"op", "cursor"},
        "contacts": {"op"},
        "status": {"op"},
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
        }
    if op == "message":
        message_id = request.get("message_id")
        if not isinstance(message_id, str) or not MESSAGE_ID.match(message_id):
            raise ContractError("invalid")
        return {"op": op, "message_id": message_id}
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
