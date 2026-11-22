# SPDX-License-Identifier: Apache-2.0
"""Nomad Network pages in the standard image (v0.6.0, ADR 0027).

    MESHBEACON_IMAGE=<the image> pytest -m container tests/container/test_pages_container.py

Off by default: nothing of pages runs and no data is created. On: the pages service starts after
Reticulum as ``mb-nomad``; the core reaches it over its socket; hosting runs the unmodified
Nomad Network daemon as the same user, serving the core's published pages, which it can read but
not change; users cannot read each other's data; a killed service is restarted without leaving
a second daemon; switching pages off keeps the pages and the page host's identity, and messaging is
unaffected. Only local containers on no network; nothing connects outside.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from .test_container import DEFAULTS
from .test_messaging_container import IMAGE, App, count_engines, engine_up, wait_for
from .test_messaging_container import ON as MESSAGING_ON
from .test_messaging_container import pytestmark as messaging_marks

pytestmark = messaging_marks
PAGES = {**DEFAULTS, "pages_enabled": True}
HEX32 = re.compile(r"(?<![0-9a-f])[0-9a-f]{32,}(?![0-9a-f])", re.I)

STORE = """
import json, sys
from meshbeacon.pages.store import Store
store = Store()
for line in sys.argv[1:]:
    print(json.dumps(store.handle(json.loads(line))))
"""
ASK = """
import json, socket, sys
s = socket.socket(socket.AF_UNIX); s.settimeout(45)
s.connect('/run/meshbeacon-pages/pages.sock')
s.sendall(sys.argv[1].encode() + b'\\n')
print(s.makefile('rb').readline().decode())
"""


@pytest.fixture
def apps() -> Iterator[Callable[..., App]]:
    made: list[App] = []

    def make(image: str, options: dict | None = None, data: Path | None = None) -> App:
        made.append(App(image, options, data))
        return made[-1]

    yield make
    for app in made:
        app.remove()


def pages_up(app: App) -> bool:
    return "meshbeacon-pages: started" in app.logs()


def store(app: App, *requests: dict) -> list[dict]:
    out = app.exec("python3", "-I", "-c", STORE, *(json.dumps(r) for r in requests), user="meshbeacon")
    return [json.loads(line) for line in out.splitlines()]


def ask(app: App, payload: dict) -> dict:
    out = app.exec("python3", "-I", "-c", ASK, json.dumps(payload), user="meshbeacon", check=False).strip()
    return json.loads(out) if out else {}


def owners(app: App, module: str) -> list[str]:
    """The users of every process started as ``python -m <module>``."""
    script = (
        "import os, pwd, sys\n"
        "for p in filter(str.isdigit, os.listdir('/proc')):\n"
        "    try:\n"
        "        a = open(f'/proc/{p}/cmdline','rb').read().split(b'\\0')\n"
        "        if b'-m' in a and a[a.index(b'-m') + 1] == sys.argv[1].encode():\n"
        "            print(pwd.getpwuid(os.stat(f'/proc/{p}').st_uid).pw_name)\n"
        "    except (OSError, IndexError): pass\n"
    )
    return app.exec("python3", "-I", "-c", script, module).split()


def daemons(app: App) -> list[str]:
    return owners(app, "nomadnet.nomadnet")


def test_pages_are_off_by_default(apps):
    app = apps(IMAGE)
    assert wait_for(lambda: "not connected to anyone" in app.logs()), app.logs()
    time.sleep(10)
    assert owners(app, "meshbeacon.pages") == [] and daemons(app) == []
    for path in ("/data/nomadnet", "/data/pages", "/run/meshbeacon-pages", "/run/meshbeacon-io/pages"):
        assert not app.ok("test", "-e", path), path
    assert "share_instance = No" in app.exec("cat", "/data/reticulum/config")
    assert "Nomad Network pages: off" in app.logs()


def test_pages_start_after_reticulum_as_their_own_user_and_are_isolated(apps):
    app = apps(IMAGE, PAGES)
    assert wait_for(lambda: pages_up(app), 90), app.logs()
    logs = app.logs()
    assert logs.index("not connected to anyone") < logs.index("meshbeacon-pages: started"), logs
    assert set(owners(app, "meshbeacon.pages")) == {"mb-nomad"}
    assert count_engines(app) == 0  # messaging stays off
    assert "share_instance = Yes" in app.exec("cat", "/data/reticulum/config")
    assert app.exec("stat", "-c", "%U:%G %a", "/run/meshbeacon-pages").split() == ["mb-nomad:mb-page", "750"]
    assert app.exec("stat", "-c", "%U:%G %a", "/data/pages").split() == ["meshbeacon:mb-page", "750"]
    assert app.exec("stat", "-c", "%U:%G %a", "/data/pages/drafts").split() == ["meshbeacon:meshbeacon", "700"]
    assert app.exec("stat", "-c", "%U %a", "/data/nomadnet").split() == ["mb-nomad", "700"]
    members = app.exec("python3", "-I", "-c", "import grp; print(' '.join(sorted(grp.getgrnam('mb-page').gr_mem)))")
    assert members.split() == ["mb-nomad", "meshbeacon"]
    status = ask(app, {"op": "status"})
    assert status.get("ok") is True and status["connected"] is True and status["rpc_key"] is True, status
    # Only the core is served; Reticulum's user cannot even reach the folder.
    assert not app.ok("python3", "-I", "-c", ASK, '{"op": "status"}', user="mb-rns")
    for user, path in (
        ("mb-nomad", "/data/reticulum/storage/transport_identity"),
        ("mb-nomad", "/data/options.json"),
        ("mb-nomad", "/data/meshbeacon"),
        ("mb-nomad", "/data/pages/drafts"),
        ("mb-rns", "/data/nomadnet"),
        ("mb-rns", "/data/pages/public"),
        ("meshbeacon", "/data/nomadnet/rns/config"),
    ):
        assert not app.ok("cat", path, user=user), (user, path)
        if path.rsplit("/", 1)[-1] not in {"transport_identity", "options.json", "config"}:
            assert not app.ok("ls", path, user=user), (user, path)  # a folder: not even listed


def test_hosting_serves_published_pages_with_the_upstream_daemon(apps):
    app = apps(IMAGE, PAGES)
    assert wait_for(lambda: pages_up(app), 90), app.logs()
    answers = store(
        app,
        {"op": "site_save", "node_name": "Container node", "description": ""},
        {"op": "page_save", "title": "Notes", "content": "Notes\n`!bold`!"},
        {"op": "page_save", "title": "Secret draft", "content": "never served"},
    )
    assert all(a["ok"] for a in answers), answers
    store(app, {"op": "page_publish", "id": "notes"}, {"op": "hosting", "enabled": True})
    # The core sends the switch with its next health check (every 10 s).
    assert wait_for(lambda: ask(app, {"op": "status"}).get("hosting", {}).get("state") == "running", 60), app.logs()
    assert daemons(app) == ["mb-nomad"]
    config = app.exec("cat", "/data/nomadnet/nomadnet/config", user="mb-nomad")
    assert "disable_propagation = yes" in config and "node_name = Container node" in config
    # Published pages: the core's files, readable by the daemon, never writable or executable by it.
    assert app.exec("stat", "-c", "%U:%G %a", "/data/pages/public/notes.mu").split() == ["meshbeacon:mb-page", "640"]
    assert app.ok("cat", "/data/pages/public/notes.mu", user="mb-nomad")
    assert not app.ok("sh", "-c", "echo x >> /data/pages/public/notes.mu", user="mb-nomad")
    assert not app.ok("touch", "/data/pages/public/extra.mu", user="mb-nomad")
    assert not app.ok("cat", "/data/pages/drafts/secret-draft.mu", user="mb-nomad")
    # The page host's own address answers over the shared instance.
    address = ask(app, {"op": "status"})["hosting"]["address"]

    def fetched(path: str) -> dict:
        return ask(app, {"op": "fetch", "address": address, "path": path})

    assert wait_for(lambda: fetched("/page/notes.mu").get("content") == "Notes\n`!bold`!", 90), app.logs()
    assert fetched("/page/index.mu")["content"].startswith(">Container node")
    assert fetched("/page/secret-draft.mu")["ok"] is False
    # Rule 5: the daemon's own log lines go through the core's redaction too.
    assert not HEX32.search(app.logs()), app.logs()

    # A killed service is restarted by the core and never leaves a second daemon behind.
    app.exec("pkill", "-KILL", "-f", "meshbeacon[.]pages --data")
    assert wait_for(lambda: app.logs().count("meshbeacon-pages: started") >= 2, 120), app.logs()
    assert wait_for(lambda: daemons(app) == ["mb-nomad"], 60) and len(daemons(app)) == 1, app.logs()
    assert ask(app, {"op": "status"})["hosting"]["address"] == address  # the same identity
    assert app.health()


def test_switching_pages_off_keeps_pages_and_identity_and_leaves_messaging_running(apps):
    app = apps(IMAGE, {**MESSAGING_ON, "pages_enabled": True})
    assert wait_for(lambda: pages_up(app) and engine_up(app), 120), app.logs()
    store(app, {"op": "site_save", "node_name": "Kept", "description": ""}, {"op": "hosting", "enabled": True})
    assert wait_for(lambda: ask(app, {"op": "status"}).get("hosting", {}).get("state") == "running", 60), app.logs()
    identity = app.exec("sha256sum", "/data/nomadnet/nomadnet/storage/identity").split()[0]
    app.remove()

    off = apps(IMAGE, MESSAGING_ON, data=app.data)
    assert wait_for(lambda: engine_up(off), 90), off.logs()
    time.sleep(10)
    assert owners(off, "meshbeacon.pages") == [] and daemons(off) == []
    assert count_engines(off) == 1  # messaging unaffected
    assert "share_instance = Yes" in off.exec("cat", "/data/reticulum/config")  # still shared for messaging
    assert (app.data / "pages" / "public" / "index.mu").exists()
    assert off.exec("sha256sum", "/data/nomadnet/nomadnet/storage/identity").split()[0] == identity
    off.remove()

    again = apps(IMAGE, PAGES, data=app.data)
    assert wait_for(lambda: pages_up(again), 90), again.logs()
    assert wait_for(lambda: ask(again, {"op": "status"}).get("hosting", {}).get("state") == "running", 60)
    assert again.exec("sha256sum", "/data/nomadnet/nomadnet/storage/identity").split()[0] == identity


def test_options_from_0_5_without_the_pages_key_still_start(apps):
    """An installation updated from 0.5: its options have no ``pages_enabled`` at all."""
    options = {k: v for k, v in DEFAULTS.items() if k != "pages_enabled"}
    app = apps(IMAGE, options)
    assert wait_for(lambda: "not connected to anyone" in app.logs()), app.logs()
    assert "Nomad Network pages: off" in app.logs() and app.health()
