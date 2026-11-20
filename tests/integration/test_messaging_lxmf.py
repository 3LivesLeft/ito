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
    assert got["fields"] == []  # MS-3: no telemetry, location, icon or any other field
    alice.send({"cmd": "announced", "to": world.address()})
    announced = alice.wait_event(lambda e: e.get("event") == "announced", 20)
    assert announced["display_name"] is None and announced["stamp_cost"] is None  # MS-3: nothing by default
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
    accepted as ``unknown``."""
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
        assert counters.get("inbound_held_unverified", 0) >= 1 and counters.get("inbound_received") == 1
    finally:
        w.close()
        shutil.rmtree(root, ignore_errors=True)


def test_anyone_mode_rejects_messages_without_a_valid_stamp():
    """MS-9, negative and positive, against the unmodified LXMF 1.3.0.

    With ``inbound: anyone`` and a stamp cost of 10, a stranger's message whose stamp is weaker
    than 10 is not accepted, and the same stranger's properly stamped message is. A contact
    holding the engine's ticket is not charged: its weakly stamped reply is accepted. The weak
    stamp comes from LXMF's public ``stamp_cost`` argument (cost 1); only a message whose reported
    ``stamp_value`` is really below 10 counts as a negative case (a cost-1 stamp reaches 10 about
    once in 500 tries, and is then sent again).

    Delivery semantics: the stranger's LXMF reports the rejected message as delivered. Transport
    delivery is not application acceptance (contract.STATE_MEANINGS).
    """
    required = 10
    root = Path(tempfile.mkdtemp(prefix="mb-lxmf-stamps-"))
    w = World(root)
    try:
        eve, _ = w.peer("eve")  # a stranger, heard (announces), so nothing is held
        alice, alice_address = w.peer("alice")
        w.start_engine(
            {
                "inbound": "anyone",
                "stamp_cost": required,
                "contacts": [{"id": "alice", "name": "Alice", "destination": alice_address}],
            }
        )
        wait_for(lambda: all(c["heard"] for c in w.call(op="contacts")["contacts"]))
        time.sleep(6)  # both peers have heard the engine's announce, with its stamp cost
        eve.send({"cmd": "cost", "to": w.address()})
        assert eve.wait_event(lambda e: e.get("event") == "cost", 20)["cost"] == required

        weak = None
        for attempt in range(3):
            tag = f"weak{attempt}"
            eve.send({"cmd": "send", "to": w.address(), "content": tag, "stamp_cost": 1, "tag": tag})
            outcome = eve.wait_event(lambda e, tag=tag: e.get("tag") == tag, 120)
            if outcome["stamp_value"] is not None and outcome["stamp_value"] < required:
                weak = (tag, outcome)
                break
        assert weak is not None, "could not make a weak stamp"
        time.sleep(10)  # time for the engine to have accepted it, if it were going to
        assert all(i["content"] != weak[0] for i in inbound(w)), "an under-stamped message was accepted"
        print(f"MS-9: stamp value {weak[1]['stamp_value']} < {required}: refused; sender saw {weak[1]['event']!r}")

        eve.send({"cmd": "send", "to": w.address(), "content": "proper stamp", "tag": "good"})
        good = eve.wait_event(lambda e: e.get("tag") == "good", 300)
        assert good["stamp_value"] >= required
        items = wait_for(lambda: [i for i in inbound(w) if i["content"] == "proper stamp"], 60)
        assert items[0]["contact"] == "unknown"

        # The engine writes to alice, which hands her a ticket; her weakly stamped reply is accepted.
        sent = w.call(op="send", contact="alice", text="here is a ticket", idempotency_key="key-ticket-01")
        ticket = alice.wait_event(lambda e: e.get("event") == "received" and e["content"] == "here is a ticket", 60)
        assert ticket["fields"] == [0x0C]  # LXMF.FIELD_TICKET only (anyone mode, contacts only)
        wait_for(lambda: w.call(op="message", message_id=sent["message_id"])["state"] == "delivered", 60)
        alice.send({"cmd": "send", "to": w.address(), "content": "ticketed reply", "stamp_cost": 1, "tag": "t"})
        ticketed = alice.wait_event(lambda e: e.get("tag") == "t", 120)
        items = wait_for(lambda: [i for i in inbound(w) if i["content"] == "ticketed reply"], 60)
        assert items[0]["contact"] == "alice"
        print(f"MS-9: the contact's reply used a ticket (stamp value {ticketed['stamp_value']}) and was accepted")
        assert all(i["content"] != weak[0] for i in inbound(w))
    finally:
        w.close()
        shutil.rmtree(root, ignore_errors=True)


def test_anyone_mode_rejects_messages_with_no_stamp_at_all():
    """MS-9, negative: a message that carries **no** proof-of-work stamp is not accepted.

    The engine (``inbound: anyone``, cost 8) announces its cost and the stranger's unmodified LXMF
    1.3.0 hears it. The stranger then forgets that cost (``LXMRouter.update_stamp_cost``, public, on
    the stranger's own router), so LXMF sends without a stamp, as a sender that never heard or
    ignores the cost would. The test proves the message really left with no stamp (``LXMessage.stamp``
    is ``None``), that the engine never offers it, and, as a control, that the same stranger's
    properly stamped message on the same path is accepted. Nothing in the engine is changed or
    patched; LXMF's own ``enforce_stamps`` refuses it.
    """
    required = 8
    root = Path(tempfile.mkdtemp(prefix="mb-lxmf-nostamp-"))
    w = World(root)
    try:
        eve, _ = w.peer("eve")  # a stranger, heard (announces), so nothing is held
        w.start_engine({"inbound": "anyone", "stamp_cost": required})
        time.sleep(6)  # eve has heard the engine's announce, with its stamp cost
        eve.send({"cmd": "cost", "to": w.address()})
        assert eve.wait_event(lambda e: e.get("event") == "cost", 20)["cost"] == required

        eve.send({"cmd": "send", "to": w.address(), "content": "no stamp", "unstamped": True, "tag": "none"})
        bare = eve.wait_event(lambda e: e.get("tag") == "none", 120)
        assert bare["stamped"] is False and bare["stamp_value"] is None, "the message was stamped after all"
        time.sleep(10)  # time for the engine to have accepted it, if it were going to
        assert all(i["content"] != "no stamp" for i in inbound(w)), "a message with no stamp was accepted"
        assert counter(w, "inbound_received") == 0
        print(f"MS-9: a message with no stamp was refused; the sender's LXMF saw {bare['event']!r}")

        # Control: the same stranger, the same path, a proper stamp. Accepted.
        eve.send({"cmd": "send", "to": w.address(), "content": "proper stamp", "stamp_cost": required, "tag": "ok"})
        good = eve.wait_event(lambda e: e.get("tag") == "ok", 300)
        assert good["stamped"] is True and good["stamp_value"] >= required
        items = wait_for(lambda: [i for i in inbound(w) if i["content"] == "proper stamp"], 60)
        assert items[0]["contact"] == "unknown"
        assert all(i["content"] != "no stamp" for i in inbound(w))
    finally:
        w.close()
        shutil.rmtree(root, ignore_errors=True)


class WriteCounter:
    """File writes in a folder tree, counted with Linux inotify (MS-19). Events are read every
    0.2 s, so repeated writes to one file within that window count once: a "write" here is a
    burst of writes to one file, the unit that matters for SD-card wear."""

    IN_MODIFY, IN_CREATE, IN_MOVED_TO, IN_DELETE = 0x2, 0x100, 0x80, 0x200

    def __init__(self, root: Path) -> None:
        import ctypes
        import ctypes.util

        self.libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        self.fd = self.libc.inotify_init1(os.O_NONBLOCK)
        assert self.fd >= 0
        mask = self.IN_MODIFY | self.IN_CREATE | self.IN_MOVED_TO | self.IN_DELETE
        self.paths: dict[int, str] = {}
        for folder in [root, *[p for p in root.rglob("*") if p.is_dir()]]:
            wd = self.libc.inotify_add_watch(self.fd, str(folder).encode(), mask)
            self.paths[wd] = str(folder.relative_to(root))
        self.events: list[tuple[float, str]] = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self) -> None:
        import struct

        while not self.stop.is_set():
            try:
                data = os.read(self.fd, 65536)
            except BlockingIOError:
                time.sleep(0.2)
                continue
            offset = 0
            while offset < len(data):
                wd, _mask, _cookie, size = struct.unpack_from("iIII", data, offset)
                name = data[offset + 16 : offset + 16 + size].rstrip(b"\0").decode()
                self.events.append((time.monotonic(), f"{self.paths.get(wd, '?')}/{name}"))
                offset += 16 + size
            time.sleep(0.2)

    def rate(self, since: float, until: float) -> float:
        return sum(1 for t, _ in self.events if since <= t < until) / (until - since)

    def close(self) -> None:
        self.stop.set()
        self.thread.join(2)
        os.close(self.fd)


def test_sd_card_writes_stay_at_or_below_one_a_second():
    """MS-19: the engine's file writes, idle and under steady two-way traffic (one message each
    way every 20 s), averaged over a minute each."""
    root = Path(tempfile.mkdtemp(prefix="mb-lxmf-writes-"))
    w = World(root)
    counter = None
    try:
        alice, alice_address = w.peer("alice")
        w.start_engine({"contacts": [{"id": "alice", "name": "Alice", "destination": alice_address}]})
        wait_for(lambda: w.call(op="contacts")["contacts"][0]["heard"])
        time.sleep(10)  # settle: first-start writes (identity, stores) are not steady state
        counter = WriteCounter(w.data)
        start = time.monotonic()
        time.sleep(60)
        idle_end = time.monotonic()
        cursor = 0
        for n in range(3):
            w.call(op="send", contact="alice", text=f"out {n}", idempotency_key=f"key-writes-{n:04d}")
            alice.send({"cmd": "send", "to": w.address(), "content": f"in {n}", "tag": f"w{n}"})
            time.sleep(20)
            items = inbound(w, cursor)
            if items:
                cursor = items[-1]["cursor"]
                w.call(op="ack", cursor=cursor)
        busy_end = time.monotonic()
        idle, busy = counter.rate(start, idle_end), counter.rate(idle_end, busy_end)
        files = sorted({p for _, p in counter.events})
        print(f"MS-19: {idle:.2f} writes/s idle, {busy:.2f} writes/s with traffic; files written: {files}")
        assert idle <= 1.0 and busy <= 1.0
    finally:
        if counter is not None:
            counter.close()
        w.close()
        shutil.rmtree(root, ignore_errors=True)


def test_sigterm_stops_the_engine_cleanly():
    """s6 stops the engine with SIGTERM: it closes its socket and queue, lets LXMF persist, exits 0."""
    root = Path(tempfile.mkdtemp(prefix="mb-lxmf-term-"))
    w = World(root)
    try:
        w.start_engine({})
        engine = w.engine
        assert engine is not None
        engine.p.terminate()
        assert engine.p.wait(30) == 0
        engine.events()
        assert "meshbeacon-messaging: stopped" in engine.seen, engine.seen
        assert not w.sock.exists()
        w.engine = None
    finally:
        w.close()
        shutil.rmtree(root, ignore_errors=True)
