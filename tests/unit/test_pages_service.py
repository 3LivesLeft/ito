# SPDX-License-Identifier: Apache-2.0
"""The pages service and its supervision (ADR 0027), without Reticulum: the daemon's configuration,
the core's start/stop rules, the dashboard's allow-list and limits, discovery and the
architecture boundaries."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from meshbeacon.pages import nomadconfig
from meshbeacon.pages.helper import Directory, Host, clean_name, clean_text
from meshbeacon.pages.store import Store
from meshbeacon.pages_supervisor import PagesSupervisor
from meshbeacon.settings import ValidationError, parse_options

CORE = Path(__file__).resolve().parents[2] / "meshbeacon" / "core" / "meshbeacon"


# -- the daemon's configuration ------------------------------------------------------------------
def test_daemon_configuration_round_trips_and_closes_unwanted_behaviour(tmp_path: Path) -> None:
    text = nomadconfig.render("Hill farm (north)", tmp_path / "public", tmp_path / "files", "quiet")
    from RNS.vendor.configobj import ConfigObj

    cfg = ConfigObj(text.splitlines())
    assert cfg["node"]["enable_node"] == "yes" and cfg["node"]["node_name"] == "Hill farm (north)"
    assert cfg["node"]["disable_propagation"] == "yes"  # never an LXMF propagation node
    assert cfg["client"]["announce_at_start"] == "no"  # its own LXMF address is never announced
    assert cfg["client"]["periodic_lxmf_sync"] == "no"  # no sync with an auto-selected node
    assert cfg["client"]["required_stamp_cost"] == "16" and cfg["client"]["max_accepted_size"] == "1"
    assert cfg["logging"] == {"loglevel": "2", "destination": "console"}
    assert cfg["printing"]["print_messages"] == "no"


@pytest.mark.parametrize("name", ["", 'x"y', "a\nb", "x" * 33, "[node]", "a=b", "a#b"])
def test_daemon_configuration_refuses_unsafe_names(tmp_path: Path, name: str) -> None:
    with pytest.raises(nomadconfig.ConfigError):
        nomadconfig.render(name, tmp_path, tmp_path)


def test_daemon_configuration_refuses_unsafe_paths(tmp_path: Path) -> None:
    for path in (Path("relative"), tmp_path / "a#b", tmp_path / "x\ny"):
        with pytest.raises(nomadconfig.ConfigError):
            nomadconfig.render("ok", path, tmp_path)


# -- discovery -----------------------------------------------------------------------------------
def test_directory_is_bounded_keeps_names_and_never_claims_reachability(tmp_path: Path, monkeypatch) -> None:
    from meshbeacon.pages import helper

    monkeypatch.setattr(helper, "MAX_NODES", 3)
    now = [1000.0]
    d = Directory(tmp_path / "nodes.json", clock=lambda: now[0])
    for i in range(4):
        now[0] += 1
        d.received_announce(bytes([i]) * 16, None, f"Node {i}".encode())
    assert len(d.nodes) == 3 and (bytes([0]) * 16).hex() not in d.nodes  # the oldest went
    d.received_announce(bytes([3]) * 16, None, None)  # no name in this announce: keep the old one
    assert d.nodes[(bytes([3]) * 16).hex()]["name"] == "Node 3"
    view = d.view(lambda _h: True, None)
    assert all(not n["reachable"] for n in view)  # heard is not reachable
    d.result((bytes([3]) * 16).hex(), True)
    assert next(n for n in d.view(lambda _h: False, None) if n["name"] == "Node 3")["reachable"] is True
    now[0] += 3600
    stale = d.view(lambda _h: False, None)
    assert not any(n["heard_recently"] or n["reachable"] for n in stale)
    d.save()
    again = Directory(tmp_path / "nodes.json")
    assert {n["name"] for n in again.nodes.values()} == {"Node 1", "Node 2", "Node 3"}


def test_untrusted_names_and_pages_are_cleaned() -> None:
    assert clean_name(b"\x1b[31mEvil\x00 node\n") == "[31mEvil node"
    assert clean_name(b"") is None and clean_name("str") is None and clean_name(b"x" * 300) is None
    assert clean_text(b"a\r\nb\x07c\xff") == "a\nbc�"


# -- the daemon as a child --------------------------------------------------------------------------
class FakeProc:
    def __init__(self) -> None:
        self.code: int | None = None
        self.pid = 0
        self.signals: list[int] = []

    def poll(self) -> int | None:
        return self.code

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)
        self.code = 0

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        self.code = -9


def test_host_never_runs_without_the_shared_instance_and_backs_off(tmp_path: Path, monkeypatch) -> None:
    now = [0.0]
    host = Host(tmp_path, tmp_path / "public", tmp_path / "rns", clock=lambda: now[0])
    procs: list[FakeProc] = []

    def popen(*_args: Any, **_kwargs: Any) -> FakeProc:
        procs.append(FakeProc())
        return procs[-1]

    monkeypatch.setattr("meshbeacon.pages.helper.subprocess.Popen", popen)
    host.sync(True, "Home", "normal")
    host.step(connected=False)
    assert procs == []  # never without ito's shared instance (F5)
    host.step(connected=True)
    assert len(procs) == 1 and host.address and len(host.address) == 32
    identity = (tmp_path / "nomadnet" / "storage" / "identity").read_bytes()
    host.step(connected=False)  # the instance went away: the daemon is stopped
    assert procs[0].signals and host.proc is None
    for _ in range(5):  # crashes: back-off, then a pause
        host.step(connected=True)
        if host.proc is not None:
            host.proc.code = 1  # type: ignore[attr-defined]
            host.step(connected=True)
        now[0] += 400
    assert host.state == "paused" and host.view()["message"]
    host.sync(False, "Home", "normal")
    host.sync(True, "Home", "normal")  # switching hosting off and on again clears the pause
    host.step(connected=True)
    assert host.state == "starting"
    assert (tmp_path / "nomadnet" / "storage" / "identity").read_bytes() == identity  # never replaced


def test_a_damaged_daemon_identity_stops_hosting_and_is_kept(tmp_path: Path, monkeypatch) -> None:
    storage = tmp_path / "nomadnet" / "storage"
    storage.mkdir(parents=True)
    (storage / "identity").write_bytes(b"damaged")
    monkeypatch.setattr("meshbeacon.pages.helper.subprocess.Popen", lambda *a, **k: pytest.fail("started"))
    host = Host(tmp_path, tmp_path / "public", tmp_path / "rns")
    host.sync(True, "Home", "normal")
    host.step(connected=True)
    assert host.state == "error" and "never replaces" in (host.message or "")
    assert (storage / "identity").read_bytes() == b"damaged"


# -- the core's supervision ----------------------------------------------------------------------
class FakeS6:
    def __init__(self) -> None:
        self.code: int | None = None
        self.pid = 0
        self.terminated = False

    def poll(self) -> int | None:
        return self.code

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def terminate(self) -> None:
        self.terminated, self.code = True, 0

    def kill(self) -> None:
        self.code = -9


def make(tmp_path: Path, answers: dict[str, Any] | None = None) -> tuple[PagesSupervisor, list[FakeS6], list[dict]]:
    started: list[FakeS6] = []
    sent: list[dict] = []
    now = [0.0]

    def link(payload: dict[str, Any], timeout: float = 0) -> dict[str, Any] | None:
        sent.append(payload)
        if payload["op"] == "sync":
            return {"ok": True, "connected": True, "hosting": {"state": "running", "address": "ab" * 16}}
        return (answers or {}).get(payload["op"], {"ok": True})

    def start() -> FakeS6:
        started.append(FakeS6())
        return started[-1]

    sup = PagesSupervisor(
        start, lambda _m: None, lambda: now[0], store=Store(tmp_path / "pages", group=None), link=link
    )
    sup.now = now  # type: ignore[attr-defined]
    return sup, started, sent


def run_probe(sup: PagesSupervisor) -> None:
    sup.next_health = 0
    sup._check_health(sup.clock())
    for _ in range(100):
        if not sup.probing:
            break
        import time

        time.sleep(0.01)
    sup._check_health(sup.clock())


def test_starts_only_with_reticulum_and_stops_without_it(tmp_path: Path) -> None:
    sup, started, _sent = make(tmp_path)
    sup.step(node_ready=False)
    assert started == []
    sup.step(node_ready=True)
    assert len(started) == 1
    sup.step(node_ready=False)
    assert started[0].terminated and sup.proc is None and sup.state == "waiting"


def test_crashes_back_off_then_pause_without_touching_anything_else(tmp_path: Path) -> None:
    sup, started, _sent = make(tmp_path)
    for _ in range(5):
        sup.step(node_ready=True)
        if sup.proc is not None:
            started[-1].code = 3
            sup.step(node_ready=True)
        sup.now[0] += 400  # type: ignore[attr-defined]
    assert sup.state == "paused" and sup.public()["state"] == "paused"


def test_health_sync_carries_the_hosting_switch_and_status_has_no_address(tmp_path: Path) -> None:
    sup, _started, sent = make(tmp_path)
    sup.store.handle({"op": "site_save", "node_name": "Home", "description": ""})
    sup.store.handle({"op": "hosting", "enabled": True})
    sup.step(node_ready=True)
    run_probe(sup)
    sync = next(p for p in sent if p["op"] == "sync")
    assert sync == {"op": "sync", "hosting": True, "node_name": "Home", "log_level": "normal"}
    public = sup.public()
    assert public["state"] == "running" and public["hosting_state"] == "running"
    assert "ab" * 16 not in repr(public)  # the snapshot (and so Home Assistant) never gets the address
    assert sup.overview()["address"] == "ab" * 16  # the dashboard does


def test_dashboard_requests_are_allow_listed_and_limited(tmp_path: Path) -> None:
    sup, _started, sent = make(tmp_path, {"fetch": {"ok": True, "content": "x"}})
    assert sup.handle({"op": "sync", "hosting": True})[0] == 400  # never the service's own controls
    assert sup.handle({"op": "status"})[0] == 400
    assert sup.handle("x")[0] == 400
    assert sup.handle({"op": "fetch", "address": "ab" * 16, "path": "/page/index.mu"})[0] == 503  # not running yet
    sup.step(node_ready=True)
    run_probe(sup)
    status, answer = sup.handle({"op": "fetch", "address": "ab" * 16, "path": "/page/index.mu", "extra": "dropped"})
    assert status == 200 and answer["content"] == "x"
    assert sent[-1] == {"op": "fetch", "address": "ab" * 16, "path": "/page/index.mu"}
    codes = [sup.handle({"op": "fetch", "address": "ab" * 16, "path": "/page/index.mu"})[0] for _ in range(40)]
    assert 429 in codes
    codes = [sup.handle({"op": "page_save", "title": "t", "content": ""})[0] for _ in range(70)]
    assert codes.count(429) >= 10


def test_the_option_is_off_by_default_and_shares_the_instance_when_on() -> None:
    assert parse_options({}).pages_enabled is False
    assert parse_options({}).share_instance is False
    on = parse_options({"pages_enabled": True})
    assert on.pages_enabled and on.share_instance
    with pytest.raises(ValidationError):
        parse_options({"pages_enabled": "yes"})


# -- boundaries ----------------------------------------------------------------------------------
def imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add("." * node.level + (node.module or ""))
    return found


def test_nothing_imports_nomadnet_and_the_core_never_imports_the_service() -> None:
    for path in CORE.rglob("*.py"):
        names = imports(path)
        assert not any(n.split(".")[0] == "nomadnet" for n in names), path  # a separate program only (GPL)
        if "pages" not in path.parts:
            assert not any(n.endswith("helper") for n in names), path  # the core never runs the service
    for path in (CORE / "pages" / "store.py", CORE / "pages" / "__init__.py", CORE / "pages_supervisor.py"):
        assert not any(n.startswith("RNS") for n in imports(path)), path


def test_a_stop_for_a_damaged_identity_or_full_storage_stays_until_switched_off_and_on(
    tmp_path: Path, monkeypatch
) -> None:
    """The core repeats the hosting switch every 10 s; that must not undo a deliberate stop."""
    from meshbeacon.pages import helper

    storage = tmp_path / "nomadnet" / "storage"
    storage.mkdir(parents=True)
    (storage / "identity").write_bytes(b"damaged")
    procs: list[FakeProc] = []
    monkeypatch.setattr(helper.subprocess, "Popen", lambda *a, **k: procs.append(FakeProc()) or procs[-1])
    host = Host(tmp_path, tmp_path / "public", tmp_path / "rns")
    for _ in range(3):
        host.sync(True, "Home", "normal")
        host.step(connected=True)
    assert host.state == "error" and procs == []
    (storage / "identity").unlink()  # the user restored a backup (here: none, so a new one is made)
    host.sync(False, "Home", "normal")
    host.sync(True, "Home", "normal")
    host.step(connected=True)
    assert len(procs) == 1
    monkeypatch.setattr(helper, "STORAGE_LIMIT", 0)  # now the daemon's storage is "full"
    host.last_storage = -1e9
    host.step(connected=True)
    assert host.state == "error" and "64 MiB" in (host.message or "")
    host.sync(True, "Home", "normal")
    host.step(connected=True)
    assert host.state == "error" and len(procs) == 1  # not restarted by the periodic sync


def test_a_damaged_daemon_identity_is_restored_from_its_verified_backup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("meshbeacon.pages.helper.subprocess.Popen", lambda *a, **k: FakeProc())
    host = Host(tmp_path, tmp_path / "public", tmp_path / "rns")
    host.identity()
    storage = tmp_path / "nomadnet" / "storage"
    good, address = (storage / "identity").read_bytes(), host.address
    (storage / "identity").write_bytes(b"damaged")
    assert host.identity() is not None and host.address == address
    assert (storage / "identity").read_bytes() == good
