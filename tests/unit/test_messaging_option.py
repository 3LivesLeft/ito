# SPDX-License-Identifier: Apache-2.0
"""The "Enable LXMF messaging" option (M4, D-M4-8): validation, the engine's settings the core
writes, the core's link to the engine (counts, the confirmation reply, acknowledgement) and what
the status API reports. Content never leaves the engine through the core."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from meshbeacon import engine_supervisor as es
from meshbeacon.messaging import settings as engine_settings_mod
from meshbeacon.settings import Contact, Messaging, ValidationError, parse_options

A = "a1" * 16
B = "b2" * 16


def test_messaging_is_off_by_default_and_keeps_its_defaults():
    m = parse_options({}).messaging
    assert m == Messaging()
    assert m.enabled is False and m.contacts == () and m.accept_anyone is False and m.auto_reply is True


def test_contacts_are_validated_and_addresses_normalised():
    m = parse_options(
        {"messaging_enabled": True, "messaging_contacts": [{"name": "My phone", "address": f" <{A.upper()}> "}]}
    ).messaging
    assert m.contacts == (Contact("My phone", A),)


@pytest.mark.parametrize(
    ("options", "words"),
    [
        ({"messaging_contacts": [{"name": "x", "address": "123"}]}, "32 hexadecimal"),
        ({"messaging_contacts": [{"name": "[bad]", "address": A}]}, "the name must be"),
        ({"messaging_contacts": [{"name": "A", "address": A}, {"name": "a", "address": B}]}, "Two messaging contacts"),
        ({"messaging_contacts": [{"name": "A", "address": A}, {"name": "B", "address": A}]}, "same address"),
        ({"messaging_contacts": [{"name": "A", "address": A, "extra": 1}]}, "expected format"),
        ({"messaging_contacts": [{"name": f"c{i}", "address": f"{i:032x}"} for i in range(21)]}, "At most 20"),
        ({"messaging_enabled": "yes"}, "must be on or off"),
        ({"messaging_propagation_node": "nope"}, "propagation node"),
        ({"messaging_display_name": "x" * 40}, "display name"),
    ],
)
def test_bad_messaging_options_are_explained(options: dict[str, Any], words: str):
    with pytest.raises(ValidationError) as caught:
        parse_options(options)
    assert any(words in p for p in caught.value.problems), caught.value.problems


def test_the_engine_settings_are_what_the_engine_accepts():
    m = Messaging(
        enabled=True,
        display_name="Home",
        contacts=(Contact("My phone", A), Contact("my-phone", B), Contact("Unknown", "c3" * 16)),
        accept_anyone=True,
        propagation_node="d4" * 16,
    )
    raw = es.engine_settings(m)
    parsed = engine_settings_mod.parse(raw)  # the engine's own allow-list is the authority
    assert parsed.inbound == "anyone" and parsed.stamp_cost == es.STAMP_COST and parsed.display_name == "Home"
    assert [c.id for c in parsed.contacts] == ["my-phone", "my-phone-2", "unknown-2"]
    assert [c.destination for c in parsed.contacts] == [A, B, "c3" * 16]
    assert parsed.propagation_node == "d4" * 16 and parsed.retention_days == 0
    assert engine_settings_mod.parse(es.engine_settings(Messaging(enabled=True))).inbound == "contacts"


def test_the_settings_file_is_readable_by_the_group_only(tmp_path: Path):
    path = tmp_path / "settings.json"
    es.write_settings(Messaging(enabled=True, contacts=(Contact("Phone", A),)), path, group=None)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o640
    assert json.loads(path.read_text())["contacts"][0]["destination"] == A
    gid = os.getgid()
    es.write_settings(Messaging(enabled=True), path, group=None)
    assert os.stat(path).st_gid == gid


class FakeEngine:
    """The engine's side of the contract, as far as the core's link uses it."""

    def __init__(self) -> None:
        self.inbound: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []
        self.acked: list[int] = []
        self.states: dict[str, str] = {}
        self.rpc: bool | None = True
        self.rpc_key: bool | None = True
        self.calls: list[dict[str, Any]] = []
        self.extra: dict[str, dict[str, Any]] = {}

    def __call__(self, req: dict[str, Any], **_kw: Any) -> dict[str, Any] | None:
        op = req["op"]
        self.calls.append(req)
        if op in getattr(self, "extra", {}):
            return self.extra[op]
        if op == "status":
            return {
                "ok": True,
                "connected": True,
                "rpc": self.rpc,
                "rpc_key": self.rpc_key,
                "address": A,
                "counters": {"inbound_received": 2, "inbound_refused_stranger": 3},
            }
        if op == "contacts":
            return {"ok": True, "contacts": [{"id": "phone", "name": "Phone", "heard": True}]}
        if op == "inbound":
            return {"ok": True, "messages": list(self.inbound)}
        if op == "ack":
            self.acked.append(req["cursor"])
            self.inbound = [m for m in self.inbound if m["cursor"] > req["cursor"]]
            return {"ok": True, "acknowledged": 1}
        if op == "send":
            self.sent.append(req)
            mid = f"{len(self.sent):032x}"
            self.states[mid] = "delivered"
            return {"ok": True, "message_id": mid, "state": "queued"}
        if op == "message":
            return {"ok": True, "state": self.states.get(req["message_id"], "queued")}
        return None


def supervisor(engine: FakeEngine, **messaging: Any) -> es.EngineSupervisor:
    m = Messaging(enabled=True, contacts=(Contact("Phone", B),), **messaging)
    sup = es.EngineSupervisor(lambda: None, lambda _s: None, lambda: 0.0, messaging=m, link=engine)  # type: ignore[arg-type, return-value]
    sup.state, sup.healthy = "running", True
    return sup


SECRET = "the content of a private message"


def test_arrivals_are_counted_confirmed_and_acknowledged_never_kept():
    engine = FakeEngine()
    engine.inbound = [
        {
            "cursor": 4,
            "message_id": "e" * 32,
            "contact": "phone",
            "title": "",
            "content": SECRET,
            "received": 1700000000.5,
        },
        {
            "cursor": 5,
            "message_id": "f" * 32,
            "contact": "unknown",
            "title": "",
            "content": SECRET,
            "received": 1700000001.0,
        },
    ]
    sup = supervisor(engine)
    sup._sync(None)
    assert engine.acked == [5] and engine.inbound == []  # acknowledged, so the engine deletes them (MS-4)
    assert [s["contact"] for s in engine.sent] == ["phone"]  # a reply to the contact only, never a stranger
    assert engine.sent[0]["text"] == es.REPLY_TEXT and engine.sent[0]["idempotency_key"] == "reply-" + "e" * 32
    sup._sync(None)  # the reply's delivery is reported
    public = sup.public()
    assert public["state"] == "running" and public["address"] == A
    assert public["received"] == 2 and public["refused"] == 3 and public["contacts_reachable"] == 1
    assert public["replies_sent"] == 1 and public["last_reply_state"] == "delivered"
    assert public["last_received_from"] is None  # the last arrival was a stranger: no name
    assert SECRET not in json.dumps(public) and SECRET not in json.dumps(sup.view)


def test_no_reply_when_the_confirmation_is_off():
    engine = FakeEngine()
    engine.inbound = [{"cursor": 1, "message_id": "e" * 32, "contact": "phone", "content": "x", "received": 1.0}]
    sup = supervisor(engine, auto_reply=False)
    sup._sync(None)
    assert engine.sent == [] and engine.acked == [1]
    assert sup.public()["last_received_from"] == "Phone"


def test_the_states_the_dashboard_shows():
    engine = FakeEngine()
    sup = supervisor(engine)
    sup.healthy = False
    assert sup.public()["state"] == "starting"
    sup.healthy = True
    sup.view["connected"] = False
    assert sup.public()["state"] == "starting" and "shared instance" in sup.public()["message"]
    sup.view["connected"], sup.view["rpc"] = True, None
    assert sup.public()["state"] == "starting" and "checking" in sup.public()["message"]
    sup.view["rpc"] = True
    assert sup.public()["state"] == "running" and sup.public()["message"] is None
    sup._failed(es.EXIT_REASONS[3], 0.0)
    public = sup.public()
    assert public["state"] == "error" and "identity" in public["message"] and "Traceback" not in public["message"]
    for _ in range(es.PAUSE_AFTER):
        sup._failed("x", 1.0)
    assert sup.public()["state"] == "paused"
    assert es.DISABLED == {"enabled": False, "state": "disabled", "message": None}


def test_an_engine_that_reticulum_refuses_is_a_problem_never_running():
    """ADR 0023: the process runs and is connected to the shared instance, but the node refuses its
    RPC requests (the 0.3.0 failure: "digest sent was rejected"). The dashboard shows a problem."""
    engine = FakeEngine()
    engine.rpc = False
    sup = supervisor(engine)
    sup._sync(None)
    public = sup.public()
    assert public["state"] == "error" and public["message"] == es.MSG_RPC_REFUSED
    engine.rpc = True  # the node accepts it again (e.g. after a restart): Running
    sup._sync(None)
    assert sup.public()["state"] == "running"
    engine.rpc = "yes"  # type: ignore[assignment]  # anything but a boolean is "not checked yet"
    sup._sync(None)
    assert sup.public()["state"] == "starting"


def test_an_engine_without_its_key_says_what_to_do():
    """0.3.1: on the Pi the key could not be created (Home Assistant kept the previous AppArmor
    profile after a Rebuild). The dashboard must say so and point to Update, not to a restart."""
    engine = FakeEngine()
    engine.rpc, engine.rpc_key = False, False
    sup = supervisor(engine)
    sup._sync(None)
    public = sup.public()
    assert public["state"] == "error" and public["message"] == es.MSG_RPC_KEY_MISSING
    assert "update the app" in public["message"] and "Rebuild is not enough" in public["message"]
    assert "Restart" not in public["message"]
    engine.rpc_key = True  # it has the key, yet is refused: the generic message
    sup._sync(None)
    assert sup.public()["message"] == es.MSG_RPC_REFUSED


def test_settings_are_written_before_every_start():
    written: list[Messaging] = []
    m = Messaging(enabled=True)
    sup = es.EngineSupervisor(
        object,
        lambda _s: None,
        lambda: 0.0,
        messaging=m,
        link=lambda _r: None,
        settings_writer=written.append,
    )  # type: ignore[arg-type, return-value]
    sup.step(node_ready=True)
    assert written == [m] and sup.state == "running"
