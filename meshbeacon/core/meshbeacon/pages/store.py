# SPDX-License-Identifier: Apache-2.0
"""The hosted pages, owned by the core (ADR 0027 point 3). No RNS and no Nomad Network code.

``/data/pages`` (the core's, group ``mb-page``, 0750)::

    site.json        hosting switch, node name, description, page titles, bookmarks (0600)
    drafts/<id>.mu   what the user is writing (the core only, 0600, in a 0700 folder)
    public/<id>.mu   what is published: the daemon's pages_path (0640, group mb-page; never
                     executable, so Nomad Network never runs it as a script)

Page IDs are ``index`` (the landing page) or 1–40 of ``a-z0-9-``; a page is served as
``/page/<id>.mu``. Content is UTF-8 micron text of at most 32 KiB, without NUL. Nothing here
interprets the content: it is the user's own page, rendered only by Nomad Network clients and by
the dashboard's safe renderer.
"""

from __future__ import annotations

import contextlib
import grp
import os
import re
import stat
import threading
import time
from pathlib import Path
from typing import Any

from .. import fsutil

ROOT = Path("/data/pages")
GROUP = "mb-page"  # the core and the pages service only
PAGE_ID = re.compile(r"^(?:index|[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?)$")
ADDRESS = re.compile(r"^[0-9a-f]{32}$")
PATH = re.compile(r"^/page/[A-Za-z0-9_-][A-Za-z0-9_./-]{0,199}\.mu$")
MAX_PAGES = 50
MAX_CONTENT = 32 * 1024
MAX_TITLE = 64
MAX_DESCRIPTION = 200
MAX_NODE_NAME = 32
MAX_BOOKMARKS = 50
PUBLIC_MODE = 0o640
# Characters a node name never contains: ConfigObj and micron syntax, quotes, controls.
_NAME_FORBIDDEN = set("\"'`#=[]{}<>$%\\|")


class StoreError(ValueError):
    """A request the store refuses, with a plain-language reason for the dashboard."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _printable(value: str, *, newlines: bool = False) -> bool:
    for ch in value:
        if ch in "\n\t" and newlines:
            continue
        code = ord(ch)
        if code < 0x20 or code == 0x7F or 0x80 <= code <= 0x9F or ch in "\u2028\u2029\u202e\ufeff":
            return False
    return True


def valid_node_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= MAX_NODE_NAME
        and value == value.strip()
        and _printable(value)
        and not set(value) & _NAME_FORBIDDEN
    )


def valid_title(value: Any) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= MAX_TITLE and value == value.strip() and _printable(value)


def valid_path(value: Any) -> bool:
    return isinstance(value, str) and bool(PATH.match(value)) and ".." not in value.split("/") and "//" not in value


def micron_text(value: str) -> str:
    """User text as literal micron: formatting characters escaped, one line."""
    text = value.replace("\\", "\\\\").replace("`", "\\`").replace("\n", " ")
    return "\\" + text if text[:1] in (">", "<", "-", "#", "=") else text


def link_label(value: str) -> str:
    return "".join(ch for ch in value if ch not in "`[]\\")


def links_block(pages: list[dict[str, Any]]) -> str:
    """Micron links to every published page except the landing page."""
    lines = [f"`[{link_label(p['title'])}`:/page/{p['id']}.mu]" for p in pages if p["id"] != "index" and p["published"]]
    return "\n".join(lines) if lines else "(No other pages yet.)"


def default_index(node_name: str, description: str, pages: list[dict[str, Any]]) -> str:
    parts = [f">{micron_text(node_name or 'My ito node')}", ""]
    if description:
        parts += [micron_text(description), ""]
    parts += [
        "Welcome! This page is published by ito, a Reticulum node in someone's home.",
        "It reaches you over Reticulum, and works without the internet.",
        "",
        ">>Pages here",
        links_block(pages),
        "",
    ]
    return "\n".join(parts)


def slug(title: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:36].strip("-") or "page"
    if base == "index":
        base = "page"
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


KNOWLEDGE_BUNDLE = Path("/usr/share/meshbeacon/frontend/knowledge.json")
KNOWLEDGE_FILE = re.compile(r"ito-guide--[a-z0-9-]{1,29}\.mu")


class Store:
    def __init__(self, root: Path = ROOT, *, group: str | None = GROUP, clock: Any = time.time) -> None:
        self.root = root
        self.drafts = root / "drafts"
        self.public = root / "public"
        self.site_file = root / "site.json"
        self.clock = clock
        self._library_synced: bool | None = None
        self.lock = threading.Lock()
        self.gid: int | None = None
        if group:
            with contextlib.suppress(KeyError):
                self.gid = grp.getgrnam(group).gr_gid

    # -- persistence ---------------------------------------------------------------------------
    def _prepare(self) -> None:
        fsutil.ensure_dir(self.drafts)
        if not self.public.is_dir():
            # The init step creates it 0750 (group mb-page); outside the app image, make it here.
            self.public.mkdir(mode=0o750, parents=True, exist_ok=True)
        for folder in (self.root, self.drafts, self.public):
            fsutil.remove_stale_temp_files(folder)

    def _load(self) -> dict[str, Any]:
        raw = fsutil.read_json(self.site_file)
        site: dict[str, Any] = {
            "hosting": False,
            "share_knowledge": False,
            "default_created": False,
            "node_name": "",
            "description": "",
            "pages": {},
            "bookmarks": [],
        }
        if not isinstance(raw, dict):
            return site
        site["hosting"] = raw.get("hosting") is True
        site["share_knowledge"] = raw.get("share_knowledge") is True
        site["default_created"] = raw.get("default_created") is True
        if valid_node_name(raw.get("node_name")):
            site["node_name"] = raw["node_name"]
        desc = raw.get("description")
        if isinstance(desc, str) and len(desc) <= MAX_DESCRIPTION and _printable(desc):
            site["description"] = desc
        pages = raw.get("pages")
        if isinstance(pages, dict):
            for pid, meta in list(pages.items())[:MAX_PAGES]:
                valid = isinstance(pid, str) and PAGE_ID.match(pid) and isinstance(meta, dict)
                if valid and valid_title(meta.get("title")):
                    site["pages"][pid] = {
                        "title": meta["title"],
                        "updated": meta.get("updated") if isinstance(meta.get("updated"), (int, float)) else 0,
                        "published": meta.get("published") if isinstance(meta.get("published"), (int, float)) else None,
                    }
        for item in raw.get("bookmarks") or []:
            if isinstance(item, dict) and self._valid_bookmark(item) and len(site["bookmarks"]) < MAX_BOOKMARKS:
                site["bookmarks"].append({k: item[k] for k in ("address", "path", "title")})
        return site

    def _save(self, site: dict[str, Any]) -> None:
        fsutil.atomic_write_json(self.site_file, site)

    @staticmethod
    def _valid_bookmark(item: dict[str, Any]) -> bool:
        return (
            isinstance(item.get("address"), str)
            and bool(ADDRESS.match(item["address"]))
            and valid_path(item.get("path"))
            and valid_title(item.get("title"))
        )

    def _read(self, folder: Path, pid: str) -> str | None:
        path = folder / f"{pid}.mu"
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                return None
            return path.read_bytes()[:MAX_CONTENT].decode("utf-8", "replace")
        except OSError:
            return None

    def _publish_file(self, pid: str, content: str) -> None:
        fsutil.atomic_write(self.public / f"{pid}.mu", content.encode(), mode=PUBLIC_MODE, group=self.gid)

    # -- views -----------------------------------------------------------------------------------
    def _pages(self, site: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for pid, meta in site["pages"].items():
            draft, live = self._read(self.drafts, pid), self._read(self.public, pid)
            out.append(
                {
                    "id": pid,
                    "title": meta["title"],
                    "updated": meta["updated"],
                    "published": live is not None,
                    "changed": live is not None and draft != live,
                }
            )
        out.sort(key=lambda p: (p["id"] != "index", p["title"].casefold()))
        return out

    def view(self) -> dict[str, Any]:
        with self.lock:
            self._prepare()
            site = self._load()
            return {
                "hosting": site["hosting"],
                "share_knowledge": site["share_knowledge"],
                "node_name": site["node_name"],
                "description": site["description"],
                "pages": self._pages(site),
                "bookmarks": site["bookmarks"],
            }

    def hosting(self) -> tuple[bool, str]:
        with self.lock:
            site = self._load()
            return site["hosting"], site["node_name"]

    def sync_knowledge(self) -> None:
        """Reconcile the public copies after startup or an app image update."""
        with self.lock:
            site = self._load()
            self._sync_knowledge(site)

    def _sync_knowledge(self, site: dict[str, Any]) -> None:
        wanted = site["hosting"] and site["share_knowledge"]
        if self._library_synced == wanted:
            return
        desired = {}
        if wanted:
            bundle = fsutil.read_json(KNOWLEDGE_BUNDLE)
            if not isinstance(bundle, dict) or not bundle.get("pages"):
                raise StoreError("unavailable", "The bundled knowledge library is unavailable.")
            desired = bundle["pages"]
            if any(not KNOWLEDGE_FILE.fullmatch(name) or name[:-3] in site["pages"] for name in desired):
                raise StoreError("invalid", "The library contains a conflicting page name.")
        self._library_synced = None
        self._prepare()
        for entry in self.public.glob("ito-guide--*.mu"):
            if KNOWLEDGE_FILE.fullmatch(entry.name) and entry.stem not in site["pages"] and entry.name not in desired:
                entry.unlink()
        for name in sorted(desired, key=lambda name: name == "ito-guide--index.mu"):
            item = desired[name]
            self._publish_file(name[:-3], item["content"])
        self._library_synced = wanted

    # -- operations ----------------------------------------------------------------------------
    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        op = request.get("op")
        try:
            with self.lock:
                self._prepare()
                site = self._load()
                result = self._op(op, request, site)
        except StoreError as exc:
            return {"ok": False, "error": exc.code, "message": exc.message}
        except OSError:
            return {"ok": False, "error": "storage", "message": "ito could not save your pages. Check free space."}
        return {"ok": True, **result}

    def _page_id(self, request: dict[str, Any], site: dict[str, Any]) -> str:
        pid = request.get("id")
        if not isinstance(pid, str) or not PAGE_ID.match(pid) or pid not in site["pages"]:
            raise StoreError("not_found", "That page does not exist (it may have been deleted in another window).")
        return pid

    def _op(self, op: Any, request: dict[str, Any], site: dict[str, Any]) -> dict[str, Any]:
        if op == "page_get":
            pid = self._page_id(request, site)
            return {"id": pid, "title": site["pages"][pid]["title"], "content": self._read(self.drafts, pid) or ""}
        if op == "page_save":
            return self._save_page(request, site)
        if op == "page_delete":
            pid = self._page_id(request, site)
            (self.public / f"{pid}.mu").unlink(missing_ok=True)
            (self.drafts / f"{pid}.mu").unlink(missing_ok=True)
            del site["pages"][pid]
            self._save(site)
            return {}
        if op == "page_publish":
            pid = self._page_id(request, site)
            self._publish_file(pid, self._read(self.drafts, pid) or "")
            site["pages"][pid]["published"] = self.clock()
            self._save(site)
            return {}
        if op == "page_unpublish":
            pid = self._page_id(request, site)
            (self.public / f"{pid}.mu").unlink(missing_ok=True)
            site["pages"][pid]["published"] = None
            self._save(site)
            return {}
        if op == "site_save":
            name, desc = request.get("node_name"), request.get("description", "")
            if not valid_node_name(name):
                raise StoreError(
                    "invalid",
                    "The node name must be 1–32 characters, without quotes, brackets or the characters # = $ % | \\ `.",
                )
            if not isinstance(desc, str) or len(desc) > MAX_DESCRIPTION or not _printable(desc):
                raise StoreError("invalid", f"The description must be at most {MAX_DESCRIPTION} characters, one line.")
            site["node_name"], site["description"] = name, desc.strip()
            self._save(site)
            return {}
        if op == "share_knowledge":
            enabled = request.get("enabled")
            if not isinstance(enabled, bool) or (enabled and not site["hosting"]):
                raise StoreError("invalid", "Start hosting before sharing the library.")
            site["share_knowledge"] = enabled
            self._sync_knowledge(site)
            self._save(site)
            return {}
        if op == "hosting":
            enabled = request.get("enabled")
            if not isinstance(enabled, bool):
                raise StoreError("invalid", "invalid")
            created = False
            if enabled and not site["node_name"]:
                raise StoreError("needs_name", "Give your node a name first: other people see it.")
            if enabled and not site["default_created"] and "index" not in site["pages"]:
                # The first time: a simple landing page linking the published pages, published at
                # once and ready to edit (ADR 0027). Never again, so a deleted one stays deleted.
                content = default_index(site["node_name"], site["description"], self._pages(site))
                fsutil.atomic_write(self.drafts / "index.mu", content.encode())
                self._publish_file("index", content)
                now = self.clock()
                site["pages"]["index"] = {"title": "Welcome", "updated": now, "published": now}
                site["default_created"] = created = True
            site["hosting"] = enabled
            self._save(site)
            self._sync_knowledge(site)
            return {"created_default": created}
        if op == "bookmark_add":
            item = {k: request.get(k) for k in ("address", "path", "title")}
            if not self._valid_bookmark(item):
                raise StoreError("invalid", "That bookmark is not valid.")
            marks = [b for b in site["bookmarks"] if (b["address"], b["path"]) != (item["address"], item["path"])]
            if len(marks) >= MAX_BOOKMARKS:
                raise StoreError("full", f"You can keep at most {MAX_BOOKMARKS} bookmarks.")
            site["bookmarks"] = [item, *marks]
            self._save(site)
            return {}
        if op == "bookmark_remove":
            address, path = request.get("address"), request.get("path")
            site["bookmarks"] = [b for b in site["bookmarks"] if (b["address"], b["path"]) != (address, path)]
            self._save(site)
            return {}
        raise StoreError("invalid", "invalid")

    def _save_page(self, request: dict[str, Any], site: dict[str, Any]) -> dict[str, Any]:
        title, content = request.get("title"), request.get("content")
        if not isinstance(title, str) or not valid_title(title):
            raise StoreError("invalid", f"The title must be 1–{MAX_TITLE} characters on one line.")
        if isinstance(content, str):
            content = content.replace("\r\n", "\n")
        if not isinstance(content, str) or not _printable(content, newlines=True):
            raise StoreError("invalid", "The page contains characters that cannot be published.")
        try:
            data = content.encode("utf-8", "strict")
        except UnicodeEncodeError as exc:
            raise StoreError("invalid", "The page contains characters that cannot be published.") from exc
        if len(data) > MAX_CONTENT:
            raise StoreError("too_large", f"The page is too long: at most {MAX_CONTENT // 1024} KiB.")
        pid = request.get("id")
        if pid is None:
            if len(site["pages"]) >= MAX_PAGES:
                raise StoreError("full", f"You can have at most {MAX_PAGES} pages.")
            wanted = request.get("new_id")
            if wanted == "index" and "index" not in site["pages"]:
                pid = "index"
            else:
                pid = slug(title, set(site["pages"]) | {"index"})
            site["pages"][pid] = {"title": title, "updated": 0, "published": None}
        else:
            pid = self._page_id(request, site)
        fsutil.atomic_write(self.drafts / f"{pid}.mu", data)
        site["pages"][pid]["title"] = title
        site["pages"][pid]["updated"] = self.clock()
        self._save(site)
        return {"id": pid}


def public_files_are_safe(public: Path) -> bool:
    """Every published file is a regular, non-executable ``<id>.mu`` (a test and start-up check)."""
    for entry in public.iterdir():
        st = entry.lstat()
        if entry.name.startswith(fsutil.TMP_PREFIX):
            continue
        if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o111 or not PAGE_ID.match(entry.name.removesuffix(".mu")):
            return False
        if not entry.name.endswith(".mu"):
            return False
    return os.access(public, os.R_OK)
