# SPDX-License-Identifier: Apache-2.0
"""The hosted pages (ADR 0027 point 3): create, edit, publish, delete, validation, persistence."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from meshbeacon.pages import store as store_mod
from meshbeacon.pages.store import Store, default_index, micron_text, public_files_are_safe, valid_node_name


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "pages", group=None, clock=lambda: 1000.0)


def ok(answer: dict) -> dict:
    assert answer["ok"] is True, answer
    return answer


def test_create_edit_publish_unpublish_delete(store: Store) -> None:
    pid = ok(store.handle({"op": "page_save", "title": "Garden notes", "content": "> Garden\nTomatoes"}))["id"]
    assert pid == "garden-notes"
    assert ok(store.handle({"op": "page_get", "id": pid}))["content"] == "> Garden\nTomatoes"
    page = store.view()["pages"][0]
    assert page == {"id": pid, "title": "Garden notes", "updated": 1000.0, "published": False, "changed": False}
    assert not (store.public / f"{pid}.mu").exists()  # a draft is never served

    ok(store.handle({"op": "page_publish", "id": pid}))
    assert (store.public / f"{pid}.mu").read_text() == "> Garden\nTomatoes"
    ok(store.handle({"op": "page_save", "id": pid, "title": "Garden", "content": "changed"}))
    page = store.view()["pages"][0]
    assert page["published"] and page["changed"] and page["title"] == "Garden"
    assert (store.public / f"{pid}.mu").read_text() == "> Garden\nTomatoes"  # live copy unchanged until published

    ok(store.handle({"op": "page_unpublish", "id": pid}))
    assert not (store.public / f"{pid}.mu").exists()
    ok(store.handle({"op": "page_delete", "id": pid}))
    assert store.view()["pages"] == [] and not (store.drafts / f"{pid}.mu").exists()
    assert store.handle({"op": "page_get", "id": pid})["error"] == "not_found"


def test_published_files_are_readable_by_the_group_and_never_executable(store: Store) -> None:
    pid = ok(store.handle({"op": "page_save", "title": "A", "content": "x"}))["id"]
    ok(store.handle({"op": "page_publish", "id": pid}))
    mode = stat.S_IMODE((store.public / f"{pid}.mu").stat().st_mode)
    assert mode == 0o640 and not mode & 0o111
    assert stat.S_IMODE((store.drafts / f"{pid}.mu").stat().st_mode) == 0o600
    assert stat.S_IMODE(store.drafts.stat().st_mode) == 0o700
    assert public_files_are_safe(store.public)
    os.chmod(store.public / f"{pid}.mu", 0o750)  # noqa: S103 - the unsafe case under test
    assert not public_files_are_safe(store.public)


def test_unique_ids_and_index(store: Store) -> None:
    ids = [
        ok(store.handle({"op": "page_save", "title": t, "content": ""}))["id"] for t in ("News", "News", "index", "!!!")
    ]
    assert ids == ["news", "news-2", "page", "page-2"]  # "index" is only ever the landing page
    assert ok(store.handle({"op": "page_save", "title": "Home", "content": "", "new_id": "index"}))["id"] == "index"


@pytest.mark.parametrize(
    "request_",
    [
        {"op": "page_save", "title": "", "content": "x"},
        {"op": "page_save", "title": "a\nb", "content": "x"},
        {"op": "page_save", "title": "x" * 65, "content": "x"},
        {"op": "page_save", "title": "ok", "content": "nul\x00"},
        {"op": "page_save", "title": "ok", "content": "esc\x1b[31m"},
        {"op": "page_save", "title": "ok", "content": "x" * (32 * 1024 + 1)},
        {"op": "page_save", "title": "ok", "content": 5},
        {"op": "page_save", "id": "../../etc/passwd", "title": "ok", "content": "x"},
        {"op": "page_get", "id": "../site"},
        {"op": "page_publish", "id": "nope"},
        {"op": "page_delete", "id": "index.mu"},
        {"op": "hosting", "enabled": "yes"},
        {"op": "site_save", "node_name": "", "description": ""},
        {"op": "site_save", "node_name": 'a"b', "description": ""},
        {"op": "site_save", "node_name": "x" * 33, "description": ""},
        {"op": "site_save", "node_name": "ok", "description": "two\nlines"},
        {"op": "bookmark_add", "address": "zz" * 16, "path": "/page/index.mu", "title": "x"},
        {"op": "bookmark_add", "address": "ab" * 16, "path": "/page/../x.mu", "title": "x"},
        {"op": "rm_rf"},
    ],
)
def test_invalid_requests_are_refused_without_writing(store: Store, request_: dict) -> None:
    answer = store.handle(request_)
    assert answer["ok"] is False and isinstance(answer.get("message"), str)
    assert list(store.drafts.iterdir()) == [] and list(store.public.iterdir()) == []


def test_crlf_and_unicode_content_are_kept(store: Store) -> None:
    pid = ok(store.handle({"op": "page_save", "title": "Ünïcode ✓", "content": "line\r\nzweite Zeile — ok\t✓"}))["id"]
    assert store.handle({"op": "page_get", "id": pid})["content"] == "line\nzweite Zeile — ok\t✓"


def test_page_limit(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store_mod, "MAX_PAGES", 2)
    for title in ("a", "b"):
        ok(store.handle({"op": "page_save", "title": title, "content": ""}))
    assert store.handle({"op": "page_save", "title": "c", "content": ""})["error"] == "full"


def test_first_hosting_creates_an_editable_default_page_once(store: Store) -> None:
    assert store.handle({"op": "hosting", "enabled": True})["error"] == "needs_name"
    ok(store.handle({"op": "site_save", "node_name": "Hill farm", "description": "Weather and `notes`"}))
    notes = ok(store.handle({"op": "page_save", "title": "Notes", "content": "n"}))["id"]
    ok(store.handle({"op": "page_publish", "id": notes}))
    assert ok(store.handle({"op": "hosting", "enabled": True}))["created_default"] is True
    index = (store.public / "index.mu").read_text()
    assert index.startswith(">Hill farm\n") and "Weather and \\`notes\\`" in index
    assert "`[Notes`:/page/notes.mu]" in index
    assert store.view()["hosting"] is True
    ok(store.handle({"op": "page_delete", "id": "index"}))
    ok(store.handle({"op": "hosting", "enabled": False}))
    assert (
        ok(store.handle({"op": "hosting", "enabled": True}))["created_default"] is False
    )  # a deleted one stays deleted


def test_content_and_settings_survive_a_restart(store: Store, tmp_path: Path) -> None:
    ok(store.handle({"op": "site_save", "node_name": "Home", "description": ""}))
    ok(store.handle({"op": "hosting", "enabled": True}))
    ok(store.handle({"op": "bookmark_add", "address": "ab" * 16, "path": "/page/index.mu", "title": "Friend"}))
    again = Store(tmp_path / "pages", group=None)
    view = again.view()
    assert view["hosting"] is True and view["node_name"] == "Home" and view["pages"][0]["id"] == "index"
    assert view["bookmarks"] == [{"address": "ab" * 16, "path": "/page/index.mu", "title": "Friend"}]
    assert again.hosting() == (True, "Home")


def test_a_damaged_site_file_never_breaks_the_store(store: Store) -> None:
    store.view()
    store.site_file.write_text("{not json")
    assert store.view()["pages"] == []
    store.site_file.write_text(
        json.dumps({"pages": {"../x": {"title": "bad"}, "ok": {"title": 5}}, "node_name": "a\nb"})
    )
    assert store.view() == {"hosting": False, "node_name": "", "description": "", "pages": [], "bookmarks": []}


def test_node_names_and_micron_escaping() -> None:
    assert valid_node_name("Rowan's? no") is False  # quotes are refused (ConfigObj and micron)
    assert valid_node_name("Hill farm (north)") and valid_node_name("Café 7")
    assert not valid_node_name(" padded") and not valid_node_name("a#b") and not valid_node_name("a`b")
    assert micron_text(">not a heading") == "\\>not a heading"
    assert micron_text("a `!b`!") == "a \\`!b\\`!"
    assert default_index("", "", []).startswith(">My ito node")
