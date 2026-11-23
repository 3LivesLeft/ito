# SPDX-License-Identifier: Apache-2.0
"""ito's pages service against the real, unmodified Nomad Network 1.5.0 and RNS 1.6.0 (ADR 0027).

Everything runs on 127.0.0.1 with throwaway identities; no live network is contacted. A hub plays
ito's node (a shared instance); the pages service is its client, driven through its socket, as the
core drives it. A remote ``nomadnet`` daemon and a plain Reticulum fetcher connect to the hub over
TCP, as other people's nodes and browsers would.
"""

from __future__ import annotations

import os
import secrets
import signal
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("nomadnet")

from meshbeacon.messaging.server import Client
from meshbeacon.pages import store as store_mod

from .conftest import free_port
from .nomad_nodes import REMOTE_INDEX, REMOTE_SECOND
from .test_messaging_lxmf import Proc, wait_for

pytestmark = pytest.mark.slow
PY = [sys.executable, "-u"]


class World:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.port = free_port()
        self.instance = f"mbpages{os.getpid()}{self.port}"
        self.procs: list[Proc] = []
        self.hub = self.start(
            [*PY, "-m", "tests.integration.lxmf_nodes", "hub", str(root / "hub"), str(self.port), self.instance]
        )
        wait_for(lambda: any("hub: ready" in line for line in self.lines(self.hub)), 30)
        self.store = store_mod.Store(root / "pages", group=None)
        self.service: Proc | None = None
        self.socket = root / "run" / "pages.sock"
        self.socket.parent.mkdir(mode=0o700)

    def start(self, args: list[str], *, stdin: bool = False) -> Proc:
        proc = Proc(args, stdin=stdin)
        self.procs.append(proc)
        return proc

    @staticmethod
    def lines(proc: Proc) -> list[str]:
        proc.events()
        return proc.seen

    def start_service(self) -> None:
        self.service = self.start(
            [
                *PY,
                "-m",
                "meshbeacon.pages",
                "--data",
                str(self.root / "nomadnet"),
                "--pages",
                str(self.root / "pages" / "public"),
                "--socket",
                str(self.socket),
                "--allow-uid",
                str(os.getuid()),
                "--instance-name",
                self.instance,
                "--rpc-key-file",
                str(self.root / "hub" / "rpc_key"),
                "--fetch-timeout",
                "8",
            ]
        )
        wait_for(self.socket.exists, 60, why=lambda: self.lines(self.service))  # type: ignore[arg-type]

    def stop_service(self) -> None:
        assert self.service is not None
        self.service.p.send_signal(signal.SIGTERM)
        self.service.p.wait(30)

    def ask(self, request: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        return Client(self.socket, expected_uid=os.getuid(), timeout=timeout).request(request)

    def close(self) -> None:
        for proc in reversed(self.procs):
            proc.stop()
        # The daemon is the service's child: it must never outlive it. (/proc, not pgrep: CI's
        # test container has no procps.)
        marker = str(self.root / "nomadnet").encode()
        stray = []
        for pid in filter(str.isdigit, os.listdir("/proc")):
            try:
                if marker in Path(f"/proc/{pid}/cmdline").read_bytes():
                    stray.append(pid)
            except OSError:
                continue
        assert not stray, "a Nomad Network daemon outlived the pages service"


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    w = World(tmp_path)
    try:
        yield w
    finally:
        w.close()


def test_browses_and_discovers_a_real_nomad_network_node(world: World) -> None:
    world.start_service()
    remote = world.start(
        [
            *PY,
            "-m",
            "tests.integration.nomad_nodes",
            "remote",
            str(world.root / "remote"),
            str(world.port),
            "Remote test node",
        ]
    )

    # Discovery: heard through its announce, with its name; not "reachable" before any fetch.
    def heard() -> dict[str, Any] | None:
        nodes = world.ask({"op": "nodes"})["nodes"]
        return next((n for n in nodes if n["name"] == "Remote test node"), None)

    node = wait_for(heard, 90, why=lambda: world.lines(remote)[-5:])
    assert node["heard_recently"] is True and node["reachable"] is False and node["own"] is False
    address = node["address"]

    page = world.ask({"op": "fetch", "address": address, "path": "/page/index.mu"}, 40)
    assert page["ok"] is True and page["content"] == REMOTE_INDEX
    assert world.ask({"op": "fetch", "address": address, "path": "/page/second.mu"}, 40)["content"] == REMOTE_SECOND
    assert next(n for n in world.ask({"op": "nodes"})["nodes"] if n["address"] == address)["reachable"] is True

    # A page the node does not have, an unsafe path, an address nobody answers.
    assert world.ask({"op": "fetch", "address": address, "path": "/page/missing.mu"}, 40)["ok"] is False
    for path in ("/page/../secret.mu", "/file/x", "/page/index.html", "page/index.mu"):
        assert world.ask({"op": "fetch", "address": address, "path": path}) == {"ok": False, "error": "invalid"}
    assert world.ask({"op": "fetch", "address": "zz" * 16, "path": "/page/index.mu"})["error"] == "invalid"
    started = time.monotonic()
    unknown = world.ask({"op": "fetch", "address": secrets.token_hex(16), "path": "/page/index.mu"}, 40)
    assert unknown == {"ok": False, "error": "no_path"} and time.monotonic() - started < 20

    # The heard nodes survive a restart of the service.
    world.stop_service()
    world.start_service()
    assert any(n["address"] == address for n in world.ask({"op": "nodes"})["nodes"])


def test_hosts_pages_with_the_upstream_daemon_for_other_nodes(world: World) -> None:
    assert world.store.handle({"op": "site_save", "node_name": "ito test node", "description": "A test"})["ok"]
    saved = world.store.handle({"op": "page_save", "title": "Notes", "content": "Notes\n`!bold`! text"})
    assert world.store.handle({"op": "page_publish", "id": saved["id"]})["ok"]
    assert world.store.handle({"op": "hosting", "enabled": True})["created_default"] is True
    draft = world.store.handle({"op": "page_save", "title": "Draft", "content": "not yet"})  # never published
    world.start_service()
    fetcher = world.start(
        [*PY, "-m", "tests.integration.nomad_nodes", "fetcher", str(world.root / "fetcher"), str(world.port)],
        stdin=True,
    )
    fetcher.wait_event(lambda e: e.get("event") == "ready", 60)

    status = world.ask({"op": "sync", "hosting": True, "node_name": "ito test node", "log_level": "normal"})
    assert status["ok"] is True
    running = wait_for(
        lambda: (s := world.ask({"op": "status"}))["hosting"]["state"] == "running" and s,
        60,
        why=lambda: world.lines(world.service)[-10:],  # type: ignore[arg-type]
    )
    address = running["hosting"]["address"]
    assert isinstance(address, str) and len(address) == 32
    announce = fetcher.wait_event(lambda e: e.get("event") == "announce" and e.get("address") == address, 60)
    assert announce["name"] == "ito test node"

    def fetch(path: str, tag: str) -> dict[str, Any]:
        fetcher.send({"address": address, "path": path, "tag": tag})
        return fetcher.wait_event(lambda e: e.get("event") == "fetched" and e.get("tag") == tag, 60)

    index = fetch("/page/index.mu", "index")
    assert index["result"] == "ok" and index["content"].startswith(">ito test node")
    assert f":/page/{saved['id']}.mu]" in index["content"]  # the default page links the user's pages
    assert fetch(f"/page/{saved['id']}.mu", "notes")["content"] == "Notes\n`!bold`! text"
    assert fetch(f"/page/{draft['id']}.mu", "draft")["result"] != "ok"  # drafts are never served

    # Unpublished: no longer served, at once.
    assert world.store.handle({"op": "page_unpublish", "id": saved["id"]})["ok"]
    assert fetch(f"/page/{saved['id']}.mu", "gone")["result"] != "ok"

    # Hosting off stops the daemon; on again keeps the same node address (its identity persists).
    world.ask({"op": "sync", "hosting": False, "node_name": "ito test node", "log_level": "normal"})
    assert world.ask({"op": "status"})["hosting"]["state"] == "off"
    world.stop_service()
    world.start_service()
    world.ask({"op": "sync", "hosting": True, "node_name": "ito test node", "log_level": "normal"})
    again = wait_for(lambda: (s := world.ask({"op": "status"}))["hosting"]["state"] == "running" and s, 60)
    assert again["hosting"]["address"] == address


def test_bundled_library_is_discoverable_from_nomad_homepage(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    import RNS

    from meshbeacon.pages import nomadconfig

    from .lxmf_nodes import write_config

    bundle = Path(__file__).resolve().parents[2] / "meshbeacon/frontend/knowledge.json"
    monkeypatch.setattr(store_mod, "KNOWLEDGE_BUNDLE", bundle)
    assert world.store.handle({"op": "site_save", "node_name": "Library test"})["ok"]
    assert world.store.handle({"op": "hosting", "enabled": True})["ok"]
    assert world.store.handle({"op": "share_knowledge", "enabled": True})["ok"]

    folder = world.root / "standalone"
    port = free_port()
    listener = {"type": "TCPServerInterface", "enabled": "yes", "listen_ip": "127.0.0.1", "listen_port": str(port)}
    write_config(folder / "rns", {"share_instance": "No"}, {"Listener": listener})
    config = folder / "nomad"
    config.mkdir()
    files = folder / "files"
    files.mkdir()
    (config / "config").write_text(nomadconfig.render("Library test", world.store.public, files))

    daemon = world.start(
        [
            sys.executable,
            "-I",
            "-u",
            "-m",
            "nomadnet.nomadnet",
            "--daemon",
            "--console",
            "--config",
            str(config),
            "--rnsconfig",
            str(folder / "rns"),
        ]
    )
    identity_file = config / "storage" / "identity"
    wait_for(identity_file.is_file, 15, why=lambda: world.lines(daemon))
    identity = RNS.Identity.from_file(str(identity_file))
    address = RNS.Destination.hash(identity, "nomadnetwork", "node").hex()
    fetcher = world.start(
        [*PY, "-m", "tests.integration.nomad_nodes", "fetcher", str(world.root / "fetcher"), str(port)],
        stdin=True,
    )
    fetcher.wait_event(lambda e: e.get("event") == "ready", 60)

    def fetch(path: str, tag: str) -> dict[str, Any]:
        fetcher.send({"address": address, "path": path, "tag": tag})
        return fetcher.wait_event(lambda e: e.get("event") == "fetched" and e.get("tag") == tag, 60)

    home = fetch("/page/index.mu", "home")
    assert home["result"] == "ok"
    library_path = "/page/ito-guide--index.mu"
    assert f":{library_path}]" in home["content"]
    library = fetch(library_path, "library")
    assert library["result"] == "ok"
    category_path = "/page/ito-guide--water-index.mu"
    assert f":{category_path}]" in library["content"]
    category = fetch(category_path, "water")
    assert category["result"] == "ok"
    guide_path = "/page/ito-guide--water-boiling.mu"
    assert f":{guide_path}]" in category["content"]
    assert fetch(guide_path, "guide")["content"].startswith(">Boiling water")
    quick_path = "/page/ito-guide--water-quick.mu"
    assert f":{quick_path}]" in category["content"]
    quick = fetch(quick_path, "quick")
    assert quick["result"] == "ok"
    assert quick["content"].startswith(">Unsafe water quick card")
    assert len(quick["content"].encode("utf-8")) <= 1024
    assert ":/page/ito-guide--water-safe-water.mu]" in quick["content"]
    assert "Independent review pending." in quick["content"]
    shelter_path = "/page/ito-guide--shelter-index.mu"
    assert f":{shelter_path}]" in library["content"]
    shelter = fetch(shelter_path, "shelter")
    assert shelter["result"] == "ok"
    section_path = "/page/ito-guide--shelter-outdoors-index.mu"
    assert f":{section_path}]" in shelter["content"]
    section = fetch(section_path, "outdoors")
    assert section["result"] == "ok"
    tarp_path = "/page/ito-guide--shelter-tarp.mu"
    assert f":{tarp_path}]" in section["content"]
    assert fetch(tarp_path, "tarp")["content"].startswith(">Pitching an A-frame tarp")
    assert world.store.handle({"op": "share_knowledge", "enabled": False})["ok"]
    assert library_path not in fetch("/page/index.mu", "sharing-off")["content"]
    assert fetch(guide_path, "guide-off")["result"] != "ok"
    assert fetch(quick_path, "quick-off")["result"] != "ok"
    assert daemon.p.poll() is None
