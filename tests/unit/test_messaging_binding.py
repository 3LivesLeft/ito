# SPDX-License-Identifier: Apache-2.0
"""M5 (ADR 0024): the core's Home Assistant messaging binding and the automatic-reply loop guard."""

from __future__ import annotations

from typing import Any

import pytest

from meshbeacon import engine_supervisor as es

from .test_messaging_option import FakeEngine, supervisor


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make(clock: Clock | None = None) -> tuple[es.EngineSupervisor, FakeEngine]:
    engine = FakeEngine()
    sup = supervisor(engine)
    if clock is not None:
        sup.clock = clock
        sup.send_windows = [es.Window(n, w, clock) for n, w in es.SEND_LIMITS]
        sup.request_window = es.Window(*es.REQUEST_LIMIT, clock)
    return sup, engine


def send(n: int) -> dict[str, Any]:
    return {"op": "send", "contact": "phone", "text": "hi", "idempotency_key": f"key-{n:08d}"}


@pytest.mark.parametrize(
    "request_",
    [
        {"op": "inbound", "cursor": 0},  # the core's own operations, never Home Assistant's
        {"op": "ack", "cursor": 99},
        {"op": "status"},
        {"op": "contacts"},
        {"op": "send", "contact": "phone", "text": "x", "idempotency_key": "key-00000001", "auto": True},
        {"op": "wait", "revision": 0, "wait": 25},  # longer than the listener allows
        {"op": "nope"},
        ["op", "send"],
    ],
)
def test_only_the_conversation_views_operations_pass(request_):
    sup, engine = make()
    code, answer = sup.forward(request_)
    assert code == 400 and answer == {"ok": False, "error": "invalid"} and engine.calls == []


def test_a_request_is_passed_on_and_the_engines_answer_returned():
    sup, engine = make()
    engine.extra["conversations"] = {"ok": True, "conversations": []}
    assert sup.forward({"op": "conversations"}) == (200, {"ok": True, "conversations": []})
    engine.extra["history"] = {"ok": False, "error": "unknown_contact"}
    assert sup.forward({"op": "history", "contact": "x"}) == (400, {"ok": False, "error": "unknown_contact"})


def test_nothing_is_passed_on_while_the_engine_is_not_running():
    sup, engine = make()
    sup.healthy = False
    assert sup.forward({"op": "conversations"}) == (503, {"ok": False, "error": "unavailable"})
    sup.healthy, sup.state = True, "backoff"
    assert sup.forward({"op": "conversations"})[0] == 503 and engine.calls == []


def test_an_engine_that_does_not_answer_is_unavailable():
    sup, engine = make()
    engine.extra["conversations"] = None  # type: ignore[assignment]
    assert sup.forward({"op": "conversations"}) == (503, {"ok": False, "error": "unavailable"})


def test_sends_are_rate_limited_per_minute_and_per_day():
    clock = Clock()
    sup, engine = make(clock)
    assert all(sup.forward(send(n))[0] == 200 for n in range(10))
    assert sup.forward(send(10)) == (429, {"ok": False, "error": "rate_limited"})
    sent = 10
    for minute in range(1, 40):
        clock.now = minute * 61.0
        for _ in range(10):
            if sup.forward(send(sent + 1000))[0] == 200:
                sent += 1
    assert sent == 200  # the daily limit
    assert len(engine.sent) == 200


def test_automatic_replies_are_marked_and_limited_to_one_per_contact_every_six_hours():
    clock = Clock()
    sup, engine = make(clock)

    def arrive(n: int) -> None:
        engine.inbound = [{"cursor": n, "message_id": f"{n:032x}", "contact": "phone", "content": "x", "received": 1.0}]
        sup._sync(None)

    arrive(1)
    arrive(2)  # another automatic responder answering ours: no second reply, so no loop
    assert len(engine.sent) == 1 and engine.sent[0]["auto"] is True
    clock.now += es.AUTO_REPLY_EVERY + 1
    arrive(3)
    assert len(engine.sent) == 2


def test_contacts_added_in_the_dashboard_get_names_and_count():
    sup, engine = make()
    engine.extra["contacts"] = {
        "ok": True,
        "contacts": [{"id": "phone", "name": "Phone", "heard": True}, {"id": "bob", "name": "Bob", "heard": False}],
    }
    engine.inbound = [{"cursor": 1, "message_id": "e" * 32, "contact": "bob", "content": "x", "received": 1.0}]
    sup._sync(None)
    public = sup.public()
    assert public["contacts_configured"] == 2 and public["contacts_reachable"] == 1
    assert public["last_received_from"] == "Bob" and engine.sent[0]["contact"] == "bob"


@pytest.mark.parametrize("text", ["😀" * 2048, "\n" * 8191 + "x", "ж" * 4096], ids=["emoji", "newlines", "cyrillic"])
def test_a_full_size_message_in_any_script_crosses_every_hop(tmp_path, text):
    """8 KiB of UTF-8, however JSON escapes it, fits the API body and the engine socket line, and
    comes back intact in the conversation (review finding: \\u escaping tripled the size)."""
    import http.client
    import json as json_mod
    import os
    import threading

    from meshbeacon.api import MESSAGING_PATH, ApiServer, StatusStore, new_token
    from meshbeacon.messaging.engine import Engine
    from meshbeacon.messaging.server import Server
    from meshbeacon.messaging.settings import parse

    assert len(text.encode()) <= 8192
    engine = Engine(tmp_path, parse({"contacts": [{"id": "phone", "name": "Phone", "destination": "a1" * 16}]}))
    sock = tmp_path / "engine.sock"
    server = Server(sock, engine.handle, {os.getuid()})
    server.bind()
    threading.Thread(target=server.serve, daemon=True).start()
    sup, _ = make()
    sup.link = lambda req, timeout=5.0: es.request(req, sock, os.getuid(), timeout)
    key = new_token()
    api = ApiServer(StatusStore(new_token(), key, sup.forward), "127.0.0.1", 0)
    api.start()
    try:
        send = {"op": "send", "contact": "phone", "text": text, "idempotency_key": "full-size-01"}
        body = json_mod.dumps(send).encode()
        assert len(body) > 16 * 1024  # what Home Assistant's default encoding would send
        conn = http.client.HTTPConnection("127.0.0.1", api.port, timeout=10)
        conn.request("POST", MESSAGING_PATH, body=body, headers={"Authorization": f"Bearer {key}"})
        response = conn.getresponse()
        assert response.status == 200, response.read()
        conn.close()
        status, answer = sup.forward({"op": "history", "contact": "phone"})
        assert status == 200 and answer["messages"][-1]["text"] == text
    finally:
        api.stop()
        server.stop()
        engine.stop()
