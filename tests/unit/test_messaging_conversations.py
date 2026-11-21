# SPDX-License-Identifier: Apache-2.0
"""M5 (ADR 0024): the contact store, conversation history and the conversation-view operations of
the engine, without LXMF. Real-LXMF behaviour is in tests/integration/test_messaging_lxmf.py."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from meshbeacon.messaging import contract
from meshbeacon.messaging import queue as queue_mod
from meshbeacon.messaging.engine import Engine
from meshbeacon.messaging.settings import parse

from .test_messaging_engine import ALICE, STRANGER, Clock, FakeMessage

BOB = "b0" * 16


@pytest.fixture
def clock() -> Clock:
    return Clock()


def make(tmp_path: Path, clock: Clock, contacts: list[dict[str, str]] | None = None, **settings: Any) -> Engine:
    if contacts is None:
        contacts = [{"id": "alice", "name": "Alice", "destination": ALICE}]
    engine = Engine(tmp_path, parse({"contacts": contacts, **settings}), clock=clock)
    engine._request_path = lambda _h: None  # type: ignore[method-assign]
    engine._request_path_if_unknown = lambda _d: None  # type: ignore[method-assign]
    return engine


def call(engine: Engine, **request: Any) -> dict[str, Any]:
    answer = engine.handle(request)
    assert answer["ok"], answer
    return answer


def conversation(engine: Engine, contact: str = "alice") -> list[dict[str, Any]]:
    return call(engine, op="history", contact=contact)["messages"]


def summary(engine: Engine, contact: str = "alice") -> dict[str, Any]:
    with_knows = engine.knows
    engine.knows = lambda _c: False  # type: ignore[method-assign] # RNS is not running here
    try:
        items = call(engine, op="conversations")["conversations"]
    finally:
        engine.knows = with_knows  # type: ignore[method-assign]
    return next(c for c in items if c["id"] == contact)


# -- inbound ------------------------------------------------------------------------------------


def test_received_messages_are_kept_in_order_with_unread_counts(tmp_path, clock):
    e = make(tmp_path, clock)
    for n, text in enumerate(["first", "second ✓ ünïcødé 🛰️", "third"]):
        clock.now += 1
        e._on_inbound(FakeMessage(content=text.encode(), n=n))
    messages = conversation(e)
    assert [m["text"] for m in messages] == ["first", "second ✓ ünïcødé 🛰️", "third"]
    assert all(m["direction"] == "in" and m["unread"] for m in messages)
    assert [m["at"] for m in messages] == sorted(m["at"] for m in messages)
    assert summary(e)["unread"] == 3 and summary(e)["last"]["text"] == "third"
    assert call(e, op="read", contact="alice")["read"] == 3
    assert summary(e)["unread"] == 0


def test_a_message_received_twice_is_kept_once_even_after_the_core_acknowledged_it(tmp_path, clock):
    e = make(tmp_path, clock)
    e._on_inbound(FakeMessage(n=7))
    e.queue.ack(10)  # the core acknowledges (and the inbound table forgets) arrivals every 10 s
    e._on_inbound(FakeMessage(n=7))
    assert len(conversation(e)) == 1 and e.queue.counters()["inbound_received"] == 1


def test_refused_messages_never_reach_the_conversation(tmp_path, clock):
    e = make(tmp_path, clock)
    e._on_inbound(FakeMessage(source=STRANGER))
    e._on_inbound(FakeMessage(signature_validated=False, unverified_reason=0x02, n=2))
    e._on_inbound(FakeMessage(content=b"\xff", n=3))
    assert conversation(e) == [] and e.queue.conversations() == {}


def test_history_survives_a_restart(tmp_path, clock):
    e = make(tmp_path, clock)
    e._on_inbound(FakeMessage(content=b"kept"))
    call(e, op="send", contact="alice", text="reply", idempotency_key="key-00000001")
    e.queue.close()
    again = make(tmp_path, clock)
    assert [(m["direction"], m["text"]) for m in conversation(again)] == [("in", "kept"), ("out", "reply")]


def test_history_is_paged_newest_last(tmp_path, clock):
    e = make(tmp_path, clock)
    for n in range(7):
        e._on_inbound(FakeMessage(content=f"m{n}".encode(), n=n))
    page = call(e, op="history", contact="alice", limit=3)["messages"]
    assert [m["text"] for m in page] == ["m4", "m5", "m6"]
    older = call(e, op="history", contact="alice", limit=3, before=page[0]["seq"])["messages"]
    assert [m["text"] for m in older] == ["m1", "m2", "m3"]


def test_history_is_bounded_oldest_first(tmp_path, clock, monkeypatch):
    monkeypatch.setattr(queue_mod, "HISTORY_MAX", 5)
    e = make(tmp_path, clock)
    for n in range(8):
        e._on_inbound(FakeMessage(content=f"m{n}".encode(), n=n))
    e.queue.maintenance()
    assert [m["text"] for m in conversation(e)] == ["m3", "m4", "m5", "m6", "m7"]


# -- outbound -----------------------------------------------------------------------------------


def test_a_send_appears_in_the_conversation_once_whatever_the_retries(tmp_path, clock):
    e = make(tmp_path, clock)
    first = call(e, op="send", contact="alice", text="hello", idempotency_key="click-0000001")
    again = call(e, op="send", contact="alice", text="hello", idempotency_key="click-0000001")
    assert first["message_id"] == again["message_id"]
    [message] = conversation(e)
    assert (message["direction"], message["text"], message["state"]) == ("out", "hello", "queued")


def test_delivery_states_are_mirrored_into_the_conversation(tmp_path, clock):
    e = make(tmp_path, clock)
    mid = call(e, op="send", contact="alice", text="hello", idempotency_key="key-00000001")["message_id"]
    for state in ("sending", "delivered"):
        e.set_state(mid, state)
        assert conversation(e)[0]["state"] == state
    assert conversation(e)[0]["text"] == "hello"  # the conversation keeps the text


def test_an_expired_message_keeps_its_text_and_can_be_sent_again(tmp_path, clock):
    e = make(tmp_path, clock)
    mid = call(e, op="send", contact="alice", text="late", idempotency_key="key-00000001")["message_id"]
    clock.now += queue_mod.EXPIRY + 1
    e.queue.maintenance()
    [expired] = conversation(e)
    assert expired["state"] == "expired" and expired["text"] == "late"
    retried = call(e, op="retry", message_id=mid)
    assert retried["message_id"] != mid and retried["message_id"] in e.due
    [message] = conversation(e)
    assert (message["message_id"], message["state"], message["text"]) == (retried["message_id"], "queued", "late")


def test_delivered_messages_cannot_be_retried(tmp_path, clock):
    e = make(tmp_path, clock)
    mid = call(e, op="send", contact="alice", text="x", idempotency_key="key-00000001")["message_id"]
    e.set_state(mid, "delivered")
    assert e.handle({"op": "retry", "message_id": mid}) == {"ok": False, "error": "not_retryable"}


def test_retry_of_a_waiting_message_tries_it_now(tmp_path, clock):
    e = make(tmp_path, clock)
    mid = call(e, op="send", contact="alice", text="x", idempotency_key="key-00000001")["message_id"]
    e.set_state(mid, "queued", "retrying")
    e.due[mid] = clock.now + 3600
    assert call(e, op="retry", message_id=mid)["message_id"] == mid and e.due[mid] == clock.now


def test_automatic_replies_are_marked_as_such(tmp_path, clock):
    e = make(tmp_path, clock)
    call(e, op="send", contact="alice", text="auto", idempotency_key="reply-0000001", auto=True)
    assert conversation(e)[0]["auto"] is True


# -- contacts -----------------------------------------------------------------------------------


def test_configured_contacts_are_imported_and_a_dashboard_contact_is_admitted_at_once(tmp_path, clock):
    e = make(tmp_path, clock)
    assert summary(e)["origin"] == "configuration" and summary(e)["address"] == ALICE
    e._on_inbound(FakeMessage(source=BOB))
    assert e.queue.counters()["inbound_refused_not_a_contact"] == 1
    added = call(e, op="contact_add", name="Bob's phone", address=f"<{BOB.upper()}>")
    assert added["contact"] == "bob-s-phone"
    e._on_inbound(FakeMessage(source=BOB, n=1))
    assert [m["text"] for m in conversation(e, "bob-s-phone")] == ["hello"]


@pytest.mark.parametrize(
    ("request_", "error"),
    [
        ({"op": "contact_add", "name": "Bob", "address": "b0" * 15}, "invalid_address"),
        ({"op": "contact_add", "name": "Bob", "address": "zz" * 16}, "invalid_address"),
        ({"op": "contact_add", "name": "", "address": BOB}, "invalid_name"),
        ({"op": "contact_add", "name": "x" * 33, "address": BOB}, "invalid_name"),
        ({"op": "contact_add", "name": "a\nb", "address": BOB}, "invalid_name"),
        ({"op": "contact_add", "name": "Alice again", "address": ALICE}, "contact_exists"),
        ({"op": "contact_rename", "contact": "nobody", "name": "X"}, "unknown_contact"),
        ({"op": "history", "contact": "nobody"}, "unknown_contact"),
        ({"op": "history", "contact": "alice", "limit": 1000}, "invalid"),
        ({"op": "send", "contact": ALICE, "text": "x", "idempotency_key": "key-00000001"}, "unknown_contact"),
        ({"op": "wait", "revision": 0, "wait": 60}, "invalid"),
    ],
)
def test_contact_and_view_requests_are_validated(tmp_path, clock, request_, error):
    assert make(tmp_path, clock).handle(request_) == {"ok": False, "error": error}


def test_the_engine_will_not_add_its_own_address(tmp_path, clock):
    e = make(tmp_path, clock)
    e.delivery = type("D", (), {"hash": bytes.fromhex(BOB)})()
    assert e.handle({"op": "contact_add", "name": "Me", "address": BOB}) == {"ok": False, "error": "own_address"}


def test_a_rename_survives_a_restart_and_the_options_do_not_undo_it(tmp_path, clock):
    e = make(tmp_path, clock)
    call(e, op="contact_rename", contact="alice", name="Alice (Sideband)")
    e.queue.close()
    assert summary(make(tmp_path, clock))["name"] == "Alice (Sideband)"


def test_removing_a_contact_refuses_it_and_deletes_its_conversation(tmp_path, clock):
    e = make(tmp_path, clock)
    e._on_inbound(FakeMessage())
    mid = call(e, op="send", contact="alice", text="pending", idempotency_key="key-00000001")["message_id"]
    call(e, op="contact_remove", contact="alice")
    assert e.queue.conversations() == {} and mid not in e.due
    message = e.queue.get(mid)
    assert message is not None and message.state == "failed" and message.content == ""
    e._on_inbound(FakeMessage(n=5))
    assert e.queue.counters()["inbound_refused_not_a_contact"] == 1


def test_a_configured_contact_removed_in_the_dashboard_stays_removed_until_the_options_change(tmp_path, clock):
    e = make(tmp_path, clock)
    call(e, op="contact_remove", contact="alice")
    e.queue.close()
    e = make(tmp_path, clock)  # still in the options: not imported again
    assert e.contacts == {}
    e.queue.close()
    make(tmp_path, clock, contacts=[]).queue.close()  # taken out of the options: forgotten
    e = make(tmp_path, clock)  # added back to the options: imported again
    assert [c.name for c in e.contacts.values()] == ["Alice"]


def test_a_contact_taken_out_of_the_options_is_kept(tmp_path, clock):
    make(tmp_path, clock).queue.close()
    e = make(tmp_path, clock, contacts=[])
    assert [c.id for c in e.contacts.values()] == ["alice"]


def test_clearing_a_conversation_keeps_messages_still_to_be_sent(tmp_path, clock):
    e = make(tmp_path, clock)
    e._on_inbound(FakeMessage())
    call(e, op="send", contact="alice", text="pending", idempotency_key="key-00000001")
    call(e, op="clear", contact="alice")
    assert [m["text"] for m in conversation(e)] == ["pending"]


# -- the long poll --------------------------------------------------------------------------------


def test_wait_returns_at_once_on_a_different_revision_and_on_change(tmp_path, clock):
    e = make(tmp_path, clock)
    revision = call(e, op="conversations")["revision"]
    assert call(e, op="wait", revision=revision - 1, wait=10)["revision"] == revision
    timer = threading.Timer(0.3, lambda: e._on_inbound(FakeMessage()))
    started = time.monotonic()
    timer.start()
    answer = call(e, op="wait", revision=revision, wait=10)
    assert answer["revision"] > revision and time.monotonic() - started < 5
    assert call(e, op="wait", revision=answer["revision"], wait=0.2)["revision"] == answer["revision"]


def test_the_contract_lists_every_operation_it_validates():
    for op in contract.OPERATIONS:
        with pytest.raises(contract.ContractError):
            contract.validate({"op": op, "unexpected": 1})
