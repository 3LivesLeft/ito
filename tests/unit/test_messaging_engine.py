# SPDX-License-Identifier: Apache-2.0
"""The engine's inbound policy, the contract dispatch and the socket's peer check, without LXMF.

The real-LXMF behaviour is covered by tests/integration/test_messaging_lxmf.py.
"""

from __future__ import annotations

import os
import socket
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from meshbeacon.messaging import engine as engine_mod
from meshbeacon.messaging import msgidentity
from meshbeacon.messaging.engine import Engine
from meshbeacon.messaging.server import Client, Server
from meshbeacon.messaging.settings import parse

ALICE = "a1" * 16
STRANGER = "5e" * 16


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


@dataclass
class FakeMessage:
    source: str = ALICE
    content: bytes = b"hello"
    title: bytes = b""
    signature_validated: bool = True
    unverified_reason: int | None = None
    fields: dict[int, Any] = field(default_factory=dict)
    n: int = 0

    @property
    def source_hash(self) -> bytes:
        return bytes.fromhex(self.source)

    @property
    def hash(self) -> bytes:
        return bytes([self.n % 256]) * 32

    packed = b"packed"

    def get_fields(self) -> dict[int, Any]:
        return self.fields


@pytest.fixture
def clock() -> Clock:
    return Clock()


def make(tmp_path: Path, clock: Clock, **settings: Any) -> Engine:
    raw = {"contacts": [{"id": "alice", "name": "Alice", "destination": ALICE}], **settings}
    engine = Engine(tmp_path, parse(raw), clock=clock)
    engine.requested: list[bytes] = []  # type: ignore[misc]
    engine._request_path = engine.requested.append  # type: ignore[method-assign]
    return engine


def counters(engine: Engine) -> dict[str, int]:
    return engine.queue.counters()


def test_a_contact_message_is_stored(tmp_path, clock):
    e = make(tmp_path, clock)
    e._on_inbound(FakeMessage(title=b"T"))
    items = e.queue.inbound_after(0)
    assert [(i["contact"], i["title"], i["content"]) for i in items] == [("alice", "T", "hello")]


def test_strangers_are_refused_by_default(tmp_path, clock):
    e = make(tmp_path, clock)
    e._on_inbound(FakeMessage(source=STRANGER))
    assert counters(e) == {"inbound_refused_not_a_contact": 1} and e.requested == []


def test_anyone_mode_accepts_strangers_as_unknown(tmp_path, clock):
    e = make(tmp_path, clock, inbound="anyone")
    e._on_inbound(FakeMessage(source=STRANGER))
    assert e.queue.inbound_after(0)[0]["contact"] == "unknown"


def test_an_invalid_signature_is_refused_at_once(tmp_path, clock):
    e = make(tmp_path, clock)
    e._on_inbound(FakeMessage(signature_validated=False, unverified_reason=0x02))
    assert counters(e) == {"inbound_refused_unverified": 1} and not e.held


def test_an_unheard_contact_is_held_and_asked_for(tmp_path, clock):
    e = make(tmp_path, clock)
    e._on_inbound(FakeMessage(signature_validated=False, unverified_reason=engine_mod.SOURCE_UNKNOWN))
    assert len(e.held) == 1 and e.requested == [bytes.fromhex(ALICE)]
    assert e.queue.inbound_after(0) == []


def test_held_messages_are_capped(tmp_path, clock):
    e = make(tmp_path, clock)
    for n in range(engine_mod.HOLD_MAX + 3):
        e._on_inbound(FakeMessage(signature_validated=False, unverified_reason=engine_mod.SOURCE_UNKNOWN, n=n))
    assert len(e.held) == engine_mod.HOLD_MAX and counters(e)["inbound_refused_unverified"] == 3


@pytest.mark.parametrize(
    ("message", "why"),
    [
        (FakeMessage(content=b"\xff\xfe"), "inbound_refused_invalid"),
        (FakeMessage(content=b"x" * 8193), "inbound_refused_invalid"),
        (FakeMessage(content=b"a\x00b"), "inbound_refused_invalid"),
        (FakeMessage(title=b"t" * 257), "inbound_refused_invalid"),
    ],
)
def test_bad_content_is_refused(tmp_path, clock, message, why):
    e = make(tmp_path, clock)
    e._on_inbound(message)
    assert counters(e) == {why: 1} and e.queue.inbound_after(0) == []


def test_fields_are_counted_and_never_kept(tmp_path, clock):
    e = make(tmp_path, clock)
    e._on_inbound(FakeMessage(fields={0x09: b"command"}))
    assert counters(e)["inbound_fields_ignored"] == 1
    assert set(e.queue.inbound_after(0)[0]) == {"cursor", "message_id", "contact", "title", "content", "received"}


def test_a_flood_from_one_sender_is_rate_limited(tmp_path, clock):
    e = make(tmp_path, clock)
    for n in range(30):
        e._on_inbound(FakeMessage(n=n))
    assert len(e.queue.inbound_after(0)) == engine_mod.RATE_PER_SENDER[0]
    assert counters(e)["inbound_refused_rate"] == 30 - engine_mod.RATE_PER_SENDER[0]
    clock.now += engine_mod.RATE_PER_SENDER[1] + 1
    e._on_inbound(FakeMessage(n=99))
    assert len(e.queue.inbound_after(0, limit=100)) == engine_mod.RATE_PER_SENDER[0] + 1


def test_a_broken_message_never_stops_the_engine(tmp_path, clock):
    e = make(tmp_path, clock)
    e._on_inbound(object())
    assert counters(e) == {"inbound_refused_error": 1}


def test_the_contract_hides_failures_and_addresses(tmp_path, clock):
    e = make(tmp_path, clock)
    assert e.handle({"op": "nope"}) == {"ok": False, "error": "invalid"}
    assert e.handle({"op": "send", "contact": "bob", "text": "x", "idempotency_key": "key-00000001"}) == {
        "ok": False,
        "error": "unknown_contact",
    }
    assert e.handle({"op": "message", "message_id": "0" * 32}) == {"ok": False, "error": "unknown_message"}
    e.handle = Engine.handle.__get__(e)  # type: ignore[method-assign]
    e._dispatch = lambda req: 1 / 0  # type: ignore[method-assign,assignment]
    assert e.handle({"op": "status"}) == {"ok": False, "error": "internal"}


def test_send_is_idempotent_and_queued(tmp_path, clock):
    e = make(tmp_path, clock)
    first = e.handle({"op": "send", "contact": "alice", "text": "hi", "idempotency_key": "key-00000001"})
    again = e.handle({"op": "send", "contact": "alice", "text": "hi", "idempotency_key": "key-00000001"})
    assert first["ok"] and first == again and first["state"] == "queued"
    assert list(e.due) == [first["message_id"]]


def test_the_stranger_id_is_reserved(tmp_path):
    with pytest.raises(ValueError):
        parse({"contacts": [{"id": "unknown", "destination": ALICE}]})


# -- the messaging identity ---------------------------------------------------------------------


def test_identity_is_created_kept_restored_and_never_replaced_when_both_are_damaged(tmp_path):
    pytest.importorskip("RNS")
    _, what = msgidentity.load_or_create(tmp_path)
    original = (tmp_path / "identity").read_bytes()
    assert what == "created" and (tmp_path / "identity").stat().st_mode & 0o077 == 0
    assert msgidentity.load_or_create(tmp_path)[1] == "unchanged"
    (tmp_path / "identity").write_bytes(b"damaged")
    assert msgidentity.load_or_create(tmp_path)[1] == "restored"
    assert (tmp_path / "identity").read_bytes() == original
    (tmp_path / "identity").write_bytes(b"damaged")
    (tmp_path / "identity.backup").write_bytes(b"also damaged")
    with pytest.raises(msgidentity.IdentityError):
        msgidentity.load_or_create(tmp_path)
    assert (tmp_path / "identity").read_bytes() == b"damaged"  # kept for manual recovery


# -- the socket ---------------------------------------------------------------------------------


def serve(tmp_path: Path, allowed: set[int]) -> tuple[Server, Path]:
    path = Path(os.path.realpath(tmp_path)) / "e.sock"
    server = Server(path, lambda req: {"ok": True, "echo": req}, allowed)
    server.bind()
    threading.Thread(target=server.serve, daemon=True).start()
    return server, path


def test_the_socket_serves_only_the_allowed_user(tmp_path):
    server, path = serve(tmp_path, {os.getuid()})
    try:
        assert oct(path.stat().st_mode & 0o777) == "0o660"
        assert Client(path, expected_uid=os.getuid()).request({"op": "status"}) == {
            "ok": True,
            "echo": {"op": "status"},
        }
        with pytest.raises(PermissionError):
            Client(path, expected_uid=os.getuid() + 1).request({"op": "status"})
    finally:
        server.stop()
    server, path = serve(tmp_path, {os.getuid() + 1})
    try:
        with socket.socket(socket.AF_UNIX) as s:
            s.connect(str(path))
            try:
                s.sendall(b'{"op": "status"}\n')
                answer = s.recv(100)
            except (ConnectionResetError, BrokenPipeError):
                answer = b""
            assert answer == b""  # disconnected without an answer
        assert server.refused == 1
    finally:
        server.stop()


def test_the_socket_refuses_long_lines_and_bad_json(tmp_path):
    server, path = serve(tmp_path, {os.getuid()})
    try:
        with socket.socket(socket.AF_UNIX) as s:
            s.connect(str(path))
            s.sendall(b"not json\n")
            assert s.makefile("rb").readline() == b'{"ok":false,"error":"invalid"}\n'
        with socket.socket(socket.AF_UNIX) as s:
            s.connect(str(path))
            s.sendall(b"x" * (17 * 1024) + b"\n")
            assert b"invalid" in s.makefile("rb").readline()
    finally:
        server.stop()
