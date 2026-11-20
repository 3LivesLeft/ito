# SPDX-License-Identifier: Apache-2.0
"""The messaging queue (ADR 0011), the contract (ADR 0014) and the development settings file."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from meshbeacon.messaging import contract
from meshbeacon.messaging import queue as queue_mod
from meshbeacon.messaging import settings as settings_mod
from meshbeacon.messaging.contract import ContractError, validate
from meshbeacon.messaging.queue import Queue, QueueFullError


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def q(tmp_path, clock):
    queue = Queue(tmp_path / "queue.db", clock=clock)
    yield queue
    queue.close()


# -- outbound -------------------------------------------------------------------------------------


def test_the_same_idempotency_key_gives_one_message(q, clock):
    first, created = q.enqueue("alice", "", "hello", "key-00000001")
    again, created_again = q.enqueue("alice", "", "hello", "key-00000001")
    assert created and not created_again and first == again
    assert len(q.pending()) == 1
    clock.now += queue_mod.IDEMPOTENCY_TTL + 1
    q.maintenance()
    third, created_third = q.enqueue("alice", "", "hello", "key-00000001")
    assert created_third and third != first  # remembered for 24 h only


def test_message_ids_are_random_and_say_nothing(q):
    ids = {q.enqueue("alice", "", "x", f"key-{n:08d}")[0] for n in range(20)}
    assert len(ids) == 20 and all(contract.MESSAGE_ID.match(i) for i in ids)


def test_pending_messages_are_capped(q):
    for n in range(queue_mod.PENDING_MAX):
        q.enqueue("alice", "", "x", f"key-{n:08d}")
    with pytest.raises(QueueFullError):
        q.enqueue("alice", "", "x", "key-overflow")


def test_states_move_forward_and_final_states_never_change(q):
    mid, _ = q.enqueue("alice", "t", "hello", "key-00000001")
    q.set_state(mid, "sending")
    q.set_state(mid, "delivered")
    q.set_state(mid, "failed", "late callback")
    message = q.get(mid)
    assert message is not None and message.state == "delivered" and message.attempts == 1
    assert message.content == "" and message.title == ""  # content is not kept once final
    assert q.counters()["outbound_delivered"] == 1


def test_pending_messages_survive_a_restart(tmp_path, clock):
    q1 = Queue(tmp_path / "queue.db", clock=clock)
    mid, _ = q1.enqueue("alice", "", "hello", "key-00000001")
    q1.set_state(mid, "sending")
    q1.close()
    q2 = Queue(tmp_path / "queue.db", clock=clock)
    assert [m.message_id for m in q2.pending()] == [mid]  # resubmitted (ADR 0011, MS-6)
    q2.close()


def test_undelivered_messages_expire_after_seven_days(q, clock):
    mid, _ = q.enqueue("alice", "", "hello", "key-00000001")
    clock.now += queue_mod.EXPIRY + 1
    q.maintenance()
    message = q.get(mid)
    assert message is not None and message.state == "expired" and message.content == ""


# -- inbound --------------------------------------------------------------------------------------


def test_acknowledged_content_is_deleted_by_default(q):
    q.receive("src-1", "alice", "", "first")
    q.receive("src-2", "alice", "", "second")
    items = q.inbound_after(0)
    assert [i["content"] for i in items] == ["first", "second"]
    q.ack(items[0]["cursor"])
    assert [i["content"] for i in q.inbound_after(0)] == ["second"]
    rows = q.db.execute("SELECT COUNT(*) FROM inbound").fetchone()[0]
    assert rows == 1  # deleted, not hidden (MS-4)


def test_retention_keeps_acknowledged_content_for_at_most_thirty_days(tmp_path, clock):
    q = Queue(tmp_path / "queue.db", retention_days=90, clock=clock)  # asked for 90: capped at 30
    q.receive("src-1", "alice", "", "kept")
    q.ack(q.inbound_after(0)[0]["cursor"])
    assert q.inbound_after(0) == []
    clock.now += 29 * 86400
    q.maintenance()
    assert q.db.execute("SELECT COUNT(*) FROM inbound").fetchone()[0] == 1
    clock.now += 2 * 86400
    q.maintenance()
    assert q.db.execute("SELECT COUNT(*) FROM inbound").fetchone()[0] == 0
    q.close()


def test_duplicates_are_stored_once(q):
    assert q.receive("src-1", "alice", "", "hello") is not None
    assert q.receive("src-1", "alice", "", "hello") is None
    assert len(q.inbound_after(0)) == 1


def test_a_full_inbound_store_drops_the_oldest_and_counts_it(q):
    for n in range(queue_mod.INBOUND_MAX + 5):
        q.receive(f"src-{n}", "alice", "", f"m{n}")
    items = q.inbound_after(0, limit=1000)
    assert len(items) == queue_mod.INBOUND_MAX
    assert items[0]["content"] == "m5"  # the five oldest were dropped
    assert q.counters()["inbound_dropped_full"] == 5


def test_the_file_stays_under_its_cap_under_a_flood(q):
    """MS-4: queue.db ≤ 16 MiB however much arrives (2 MiB of waiting content at most)."""
    big = "x" * 8000
    for n in range(3000):
        q.receive(f"src-{n}", "alice", "", big)
        if n % 100 == 0:
            q.ack(q.inbound_after(0, limit=1000)[-1]["cursor"] if q.inbound_after(0) else 0)
            q.maintenance()
    q.maintenance()
    assert q.size() <= queue_mod.FILE_MAX
    waiting = q.db.execute("SELECT COALESCE(SUM(size), 0) FROM inbound WHERE acked IS NULL").fetchone()[0]
    assert waiting <= queue_mod.INBOUND_BYTES_MAX


def test_a_corrupt_queue_is_quarantined_and_a_fresh_one_started(tmp_path, clock):
    """MS-16: never blocks the engine; the damaged file is kept for inspection."""
    path = tmp_path / "queue.db"
    path.write_bytes(b"this is not an sqlite database" * 100)
    q = Queue(path, clock=clock)
    assert q.quarantined is not None and q.quarantined.exists()
    assert q.quarantined.read_bytes().startswith(b"this is not")
    q.enqueue("alice", "", "works", "key-00000001")
    assert len(q.pending()) == 1
    q.close()


# -- the contract ---------------------------------------------------------------------------------


def test_a_valid_send_is_accepted():
    request = {"op": "send", "contact": "alice", "text": "hi", "idempotency_key": "key-00000001"}
    assert validate(request) == {**request, "title": ""}


@pytest.mark.parametrize(
    "request_",
    [
        {"op": "send", "contact": "alice", "text": "x" * 9000, "idempotency_key": "key-00000001"},
        {"op": "send", "contact": "alice", "text": "hi", "idempotency_key": "key-00000001", "fields": {}},
        {"op": "send", "contact": "alice", "text": "\ud800", "idempotency_key": "key-00000001"},
        {"op": "send", "contact": "alice", "text": "a\x00b", "idempotency_key": "key-00000001"},
        {"op": "send", "contact": "alice", "text": "   ", "idempotency_key": "key-00000001"},
        {"op": "send", "contact": "alice", "text": "hi", "idempotency_key": "short"},
        {"op": "message", "message_id": "not-an-id"},
        {"op": "inbound", "cursor": -1},
        {"op": "inbound", "cursor": 0, "wait": 60},
        {"op": "ack", "cursor": True},
        {"op": "delete_everything"},
        "send",
    ],
)
def test_the_contract_refuses_what_it_does_not_define(request_):
    with pytest.raises(ContractError):
        validate(request_)


@pytest.mark.parametrize("contact", ["Alice", "a" * 33, "", "../x", "0" * 32 + "ab"])
def test_raw_addresses_and_bad_contact_ids_are_refused(contact):
    """MS-12: only contact IDs; a 32-character LXMF address is not one (too long)."""
    with pytest.raises(ContractError) as error:
        validate({"op": "send", "contact": contact, "text": "hi", "idempotency_key": "key-00000001"})
    assert error.value.code == "unknown_contact"


# -- the development settings file -------------------------------------------------------------------


def test_defaults_without_a_file(tmp_path):
    s = settings_mod.load(tmp_path / "missing.json")
    assert s.display_name == "" and s.inbound == "contacts" and s.contacts == ()


def test_settings_are_validated_against_an_allow_list(tmp_path):
    path = tmp_path / "messaging.json"
    good = {"contacts": [{"id": "alice", "name": "Alice", "destination": "ab" * 16}]}
    path.write_text(json.dumps(good))
    s = settings_mod.load(path)
    assert s.contact("alice") is not None and s.contact_for_destination("ab" * 16).id == "alice"
    for bad in (
        {"telemetry": True},
        {"inbound": "everyone"},
        {"stamp_cost": 99},
        {"retention_days": 31},
        {"propagation_node": "zz"},
        {"display_name": "x" * 40},
        {"contacts": [{"id": "alice", "destination": "ab" * 16}, {"id": "alice", "destination": "cd" * 16}]},
        {"contacts": [{"id": "bob", "destination": "ab" * 16, "location": "x"}]},
    ):
        path.write_text(json.dumps(bad))
        with pytest.raises(settings_mod.SettingsError):
            settings_mod.load(path)


def test_the_queue_file_is_private(tmp_path, clock):
    old = os.umask(0o077)
    try:
        q = Queue(tmp_path / "queue.db", clock=clock)
        q.enqueue("alice", "", "x", "key-00000001")
        assert Path(tmp_path / "queue.db").stat().st_mode & 0o077 == 0
        q.close()
    finally:
        os.umask(old)


def test_every_state_says_what_it_does_and_does_not_establish():
    """Delivery semantics (M4): each state is documented, and none claims more than LXMF reports."""
    assert set(contract.STATE_MEANINGS) == set(contract.STATES)
    assert "does not mean" in contract.STATE_MEANINGS["delivered"]
    assert "has not reached the recipient" in contract.STATE_MEANINGS["stored_on_node"]
    for meaning in contract.STATE_MEANINGS.values():
        assert "read by" not in meaning and "accepted by the recipient" not in meaning
