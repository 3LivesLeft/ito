# SPDX-License-Identifier: Apache-2.0
"""The messaging engine against the real, unmodified LXMF 1.3.0 (M4: MS-2 to MS-6, MS-8 to MS-10,
MS-16). Everything runs on 127.0.0.1 with throwaway identities; no live network is contacted.

A hub (the node's shared instance) listens on loopback; the engine runs as its own process, a
client of that shared instance, and is driven through its contract socket. Reference LXMF peers
and an ``lxmd`` propagation node connect to the hub over TCP.
"""

from __future__ import annotations

import json
import os
import queue as queue_mod
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("LXMF")

from meshbeacon.messaging.server import Client

from .conftest import free_port

pytestmark = pytest.mark.slow
PY = [sys.executable, "-u"]


def wait_for(
    check: Callable[[], Any], timeout: float = 60.0, every: float = 0.5, why: Callable[[], Any] | None = None
) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(every)
    raise AssertionError(f"timed out: {why() if why else ''}")


class Proc:
    """A child process whose stdout is JSON lines (or plain lines), read in the background."""

    def __init__(self, args: list[str], *, stdin: bool = False) -> None:
        self.p = subprocess.Popen(
            args,
            stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.lines: queue_mod.Queue[str] = queue_mod.Queue()
        self.seen: list[str] = []
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.p.stdout is not None
        for line in self.p.stdout:
            self.lines.put(line.rstrip("\n"))

    def events(self) -> list[dict[str, Any]]:
        while True:
            try:
                self.seen.append(self.lines.get_nowait())
            except queue_mod.Empty:
                break
        out = []
        for line in self.seen:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def wait_event(
        self, predicate: Callable[[dict[str, Any]], bool], timeout: float = 90.0, why: Callable[[], Any] | None = None
    ) -> dict[str, Any]:
        return wait_for(lambda: next((e for e in self.events() if predicate(e)), None), timeout, why=why)

    def send(self, command: dict[str, Any]) -> None:
        assert self.p.stdin is not None
        self.p.stdin.write(json.dumps(command) + "\n")
        self.p.stdin.flush()

    def stop(self) -> None:
        if self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(10)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait()


class Address(str):
    """A throwaway test address, kept out of pytest's failure output all the same (rule 5)."""

    def __repr__(self) -> str:
        return "<address>"


class World:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.port = free_port()
        self.instance = f"mbtest{os.getpid()}{self.port}"
        self.procs: list[Proc] = []
        self.hub = self.start(
            [*PY, "-m", "tests.integration.lxmf_nodes", "hub", str(root / "hub"), str(self.port), self.instance]
        )
        wait_for(lambda: "hub: ready" in "".join(self._lines(self.hub)), 30)
        self.engine: Proc | None = None
        self.data = root / "engine"
        self.sock = root / "engine.sock"

    @staticmethod
    def _lines(proc: Proc) -> list[str]:
        proc.events()
        return proc.seen

    def start(self, args: list[str], *, stdin: bool = False) -> Proc:
        proc = Proc(args, stdin=stdin)
        self.procs.append(proc)
        return proc

    def peer(self, name: str, *, announce: bool = True) -> tuple[Proc, str]:
        folder = self.root / name
        args = [*PY, "-m", "tests.integration.lxmf_nodes", "peer", str(folder), str(self.port)]
        proc = self.start(args + ([] if announce else ["--no-announce"]), stdin=True)
        proc.wait_event(lambda e: e.get("event") == "ready", 30)
        return proc, Address((folder / "address").read_text().strip())

    def start_engine(self, settings: dict[str, Any]) -> None:
        self.data.mkdir(exist_ok=True)
        (self.data / "messaging.json").write_text(json.dumps(settings))
        self.engine = self.start(
            [
                *PY,
                "-m",
                "meshbeacon.messaging",
                "--data",
                str(self.data),
                "--socket",
                str(self.sock),
                "--allow-uid",
                str(os.getuid()),
                "--instance-name",
                self.instance,
            ]
        )
        wait_for(lambda: self.sock.exists() or self.engine.p.poll() is not None, 60)  # type: ignore[union-attr]
        assert self.engine.p.poll() is None, self._lines(self.engine)

    def stop_engine(self) -> None:
        assert self.engine is not None
        self.engine.stop()
        self.engine = None

    def call(self, **request: Any) -> dict[str, Any]:
        return Client(self.sock, timeout=40).request(request)

    def address(self) -> str:
        return Address((self.data / "address").read_text().strip())

    def close(self) -> None:
        for proc in reversed(self.procs):
            proc.stop()


@pytest.fixture(scope="module")
def world() -> Iterator[World]:
    root = Path(tempfile.mkdtemp(prefix="mb-lxmf-"))
    w = World(root)
    try:
        yield w
    finally:
        w.close()
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="module")
def peers(world: World) -> dict[str, tuple[Proc, str]]:
    found = {
        "alice": world.peer("alice"),
        "bob": world.peer("bob"),  # announces, but is not a contact
        "carol": world.peer("carol", announce=False),  # a contact who never announces
    }
    world.start_engine(
        {
            "contacts": [
                {"id": "alice", "name": "Alice", "destination": found["alice"][1]},
                {"id": "carol", "name": "Carol", "destination": found["carol"][1]},
            ]
        }
    )
    wait_for(lambda: all(c["heard"] for c in world.call(op="contacts")["contacts"]))
    return found


def inbound(world: World, cursor: int = 0, wait: float = 0) -> list[dict[str, Any]]:
    answer = world.call(op="inbound", cursor=cursor, wait=wait)
    assert answer["ok"], answer
    return list(answer["messages"])


def counter(world: World, name: str) -> int:
    return int(world.call(op="status")["counters"].get(name, 0))


def test_the_engine_is_a_client_of_the_shared_instance(world, peers):
    status = world.call(op="status")
    assert status["ok"] and status["connected"] is True and status["version"] == 1
    assert status["identity"] == "created"
    assert "rpc_key" not in (world.data / "rns" / "config").read_text()  # IS-3a: no control of the node
    assert (world.data / "identity").stat().st_mode & 0o077 == 0
    assert (world.data / "identity.backup").read_bytes() == (world.data / "identity").read_bytes()
    contacts = world.call(op="contacts")["contacts"]
    assert [(c["id"], c["name"], c["heard"]) for c in contacts] == [("alice", "Alice", True), ("carol", "Carol", True)]
    # Carol never announces: the engine asked for her path, which taught it her public key.


def test_a_contact_message_is_received_and_deleted_on_ack(world, peers):
    alice = peers["alice"][0]
    alice.send({"cmd": "send", "to": world.address(), "title": "Hi", "content": "hello engine", "tag": "a1"})
    alice.wait_event(lambda e: e.get("event") == "delivered" and e.get("tag") == "a1")
    items = wait_for(lambda: inbound(world))
    assert [(i["contact"], i["title"], i["content"]) for i in items] == [("alice", "Hi", "hello engine")]
    assert "source" not in items[0] and all(len(str(v)) != 32 or k == "message_id" for k, v in items[0].items())
    assert world.call(op="ack", cursor=items[-1]["cursor"])["acknowledged"] == 1
    assert inbound(world) == []


def test_long_poll_returns_as_soon_as_a_message_arrives(world, peers):
    alice = peers["alice"][0]
    cursor = 0
    started = time.monotonic()
    threading.Timer(
        1.0, lambda: alice.send({"cmd": "send", "to": world.address(), "content": "poll", "tag": "p"})
    ).start()
    items = inbound(world, cursor, wait=25)
    assert [i["content"] for i in items] == ["poll"] and time.monotonic() - started < 25
    world.call(op="ack", cursor=items[-1]["cursor"])


def test_the_engine_delivers_to_a_contact_directly(world, peers):
    alice = peers["alice"][0]
    sent = world.call(op="send", contact="alice", text="hello alice", title="T", idempotency_key="key-direct-01")
    assert sent["ok"] and sent["state"] in ("queued", "sending")
    again = world.call(op="send", contact="alice", text="hello alice", title="T", idempotency_key="key-direct-01")
    assert again["message_id"] == sent["message_id"]  # idempotent: one message
    got = alice.wait_event(lambda e: e.get("event") == "received" and e["content"] == "hello alice")
    assert got["verified"] is True and got["title"] == "T"
    wait_for(lambda: world.call(op="message", message_id=sent["message_id"])["state"] == "delivered")
    assert len([e for e in alice.events() if e.get("content") == "hello alice"]) == 1


def test_strangers_are_refused_by_default(world, peers):
    bob = peers["bob"][0]
    before = counter(world, "inbound_refused_not_a_contact")
    bob.send({"cmd": "send", "to": world.address(), "content": "let me in", "tag": "b1"})
    wait_for(
        lambda: counter(world, "inbound_refused_not_a_contact") > before,
        why=lambda: world.call(op="status")["counters"],
    )
    assert all(i["content"] != "let me in" for i in inbound(world))


def test_a_contact_who_never_announces_is_still_verified(world, peers):
    carol = peers["carol"][0]
    carol.send({"cmd": "send", "to": world.address(), "content": "quiet hello", "tag": "c1"})
    items = wait_for(lambda: [i for i in inbound(world) if i["content"] == "quiet hello"])
    assert items[0]["contact"] == "carol"
    world.call(op="ack", cursor=items[-1]["cursor"])


def test_fields_are_ignored_and_bad_content_is_refused(world, peers):
    """MS-10: fields are never acted on; invalid UTF-8 and over-long text are refused."""
    alice = peers["alice"][0]
    ignored, invalid = counter(world, "inbound_fields_ignored"), counter(world, "inbound_refused_invalid")
    alice.send({"cmd": "send", "to": world.address(), "content": "with fields", "fields": {"9": "cmd"}, "tag": "f"})
    alice.send({"cmd": "send", "to": world.address(), "content_hex": "ff fe".replace(" ", ""), "tag": "u"})
    alice.send({"cmd": "send", "to": world.address(), "content": "x" * 9000, "tag": "big"})
    wait_for(lambda: counter(world, "inbound_refused_invalid") >= invalid + 2, 120)
    wait_for(lambda: counter(world, "inbound_fields_ignored") > ignored)
    items = inbound(world)
    assert [i["content"] for i in items] == ["with fields"]
    world.call(op="ack", cursor=items[-1]["cursor"])


def test_unknown_contacts_and_raw_addresses_are_refused_over_the_contract(world, peers):
    """MS-12: a send names a contact ID; an LXMF address is not one."""
    answer = world.call(op="send", contact=peers["bob"][1], text="x", idempotency_key="key-raw-0001")
    assert answer == {"ok": False, "error": "unknown_contact"}
    assert world.call(op="send", contact="bob", text="x", idempotency_key="key-raw-0002")["error"] == "unknown_contact"


def test_pending_messages_survive_a_restart_and_the_identity_is_kept(world, peers):
    """MS-3/MS-6: a message to an offline contact is resubmitted after the engine restarts."""
    address = world.address()
    identity = (world.data / "identity").read_bytes()
    alice, alice_address = peers["alice"]
    alice.stop()
    sent = world.call(op="send", contact="alice", text="while you were out", idempotency_key="key-restart-1")
    time.sleep(3)
    world.stop_engine()
    world.start_engine(json.loads((world.data / "messaging.json").read_text()))
    assert world.address() == address and (world.data / "identity").read_bytes() == identity
    assert world.call(op="status")["identity"] == "unchanged"
    state = world.call(op="message", message_id=sent["message_id"])["state"]
    assert state in ("queued", "sending")
    revived, same = world.peer("alice")  # the same identity, so the same address
    assert same == alice_address
    peers["alice"] = (revived, alice_address)
    got = revived.wait_event(lambda e: e.get("event") == "received" and e["content"] == "while you were out", 180)
    assert got["verified"] is True
    wait_for(lambda: world.call(op="message", message_id=sent["message_id"])["state"] == "delivered", 60)


def test_direct_failure_falls_back_to_a_propagation_node_and_never_says_delivered(world, peers):
    """MS-6: with alice offline, the message is handed to an lxmd propagation node and reported
    as ``stored_on_node``; alice later fetches it from the node."""
    node_dir = world.root / "lxmd"
    world.start(
        [
            *PY,
            "-m",
            "tests.integration.lxmf_nodes",
            "lxmd",
            str(node_dir),
            world.instance,
            str(world.root / "hub" / "rpc_key"),
        ]
    )
    node = wait_for(lambda: (node_dir / "node").exists() and (node_dir / "node").read_text().strip(), 30)
    settings = json.loads((world.data / "messaging.json").read_text())
    world.stop_engine()
    world.start_engine({**settings, "propagation_node": node})
    alice, alice_address = peers["alice"]
    alice.stop()
    sent = world.call(op="send", contact="alice", text="kept for you", idempotency_key="key-propagate-1")
    state = wait_for(
        lambda: (
            (s := world.call(op="message", message_id=sent["message_id"])["state"]) not in ("queued", "sending") and s
        ),
        300,
        every=2,
    )
    assert state == "stored_on_node"
    revived, _ = world.peer("alice")
    peers["alice"] = (revived, alice_address)
    revived.send({"cmd": "sync", "node": node})
    got = revived.wait_event(
        lambda e: e.get("event") == "received" and e["content"] == "kept for you",
        180,
        why=lambda: [e for e in revived.events() if e.get("event") != "ready"][-5:],
    )
    assert got["verified"] is True and got["method"] == 3  # PROPAGATED
    assert world.call(op="message", message_id=sent["message_id"])["state"] == "stored_on_node"


def test_the_engine_refuses_to_start_without_the_node(tmp_path):
    """The engine is only ever a client: with no shared instance it exits, and never becomes one."""
    data = Path(tempfile.mkdtemp(prefix="mb-lxmf-alone-"))
    try:
        result = subprocess.run(
            [
                *PY,
                "-m",
                "meshbeacon.messaging",
                "--data",
                str(data),
                "--socket",
                str(data / "s.sock"),
                "--instance-name",
                f"mbnone{os.getpid()}",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 3 and "the Reticulum node is not running" in result.stderr
        assert not (data / "s.sock").exists()
    finally:
        shutil.rmtree(data, ignore_errors=True)


def test_anyone_mode_holds_an_unheard_sender_until_its_key_arrives():
    """``inbound: anyone``: a stranger who never announced is held, asked for, verified and then
    delivered as ``unknown``; LXMF applies the stamp cost (MS-9)."""
    import LXMF

    from meshbeacon.messaging import engine

    assert engine.SOURCE_UNKNOWN == LXMF.LXMessage.SOURCE_UNKNOWN
    root = Path(tempfile.mkdtemp(prefix="mb-lxmf-anyone-"))
    w = World(root)
    try:
        dave, _ = w.peer("dave", announce=False)
        w.start_engine({"inbound": "anyone", "stamp_cost": 8})
        time.sleep(1)
        dave.send({"cmd": "send", "to": w.address(), "content": "hello stranger", "tag": "d"})
        items = wait_for(lambda: inbound(w), 120, why=lambda: w.call(op="status")["counters"])
        assert [(i["contact"], i["content"]) for i in items] == [("unknown", "hello stranger")]
        counters = w.call(op="status")["counters"]
        assert counters.get("inbound_held_unverified", 0) >= 1 or counters.get("inbound_received") == 1
    finally:
        w.close()
        shutil.rmtree(root, ignore_errors=True)
