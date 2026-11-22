# SPDX-License-Identifier: Apache-2.0
"""Browser check of the Pages tab (v0.6.0, ADR 0027) through the real Ingress handler.

    python tools/pages_browser_check.py            # needs Node.js with Playwright and Chromium

Serves the shared frontend with ito's own IngressServer and PagesSupervisor (a real content store
in a temporary folder) on 127.0.0.1, with a fake pages service that answers page fetches with
hostile content. tools/pages_browser_check.mjs then drives Chromium at phone and desktop sizes.
Nothing leaves the loopback interface. Exit code 0 when every check passes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "meshbeacon" / "core"))

from meshbeacon.ingress import Dashboard, IngressServer  # noqa: E402
from meshbeacon.pages.store import Store  # noqa: E402
from meshbeacon.pages_supervisor import PagesSupervisor  # noqa: E402

REMOTE = "cd" * 16
OWN = "ab" * 16
HOSTILE = "\n".join(
    [
        ">Hostile `Ff00test`f page",
        "x <script>window.__pwned = 1</script>",
        'x <img src=x onerror="window.__pwned = 1">',
        "`[Run me`javascript:window.__pwned=1]",
        "`[Web link`https://example.org/]",
        "`[Next page`:/page/next.mu]",
        "`!Bold`! and `*italic`*",
        "-",
        "`=",
        "<iframe src=//example.org></iframe>",
        "`=",
    ]
)
PAGES = {"/page/index.mu": HOSTILE, "/page/next.mu": ">Next\nYou followed a link."}


class Control:
    def request(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("op") == "config_read":
            return {"ok": True, "options": {"network": "custom", "peers": [], "pages_enabled": True}, "revision": "r"}
        return {"ok": True}


def link(fetched: list[str]) -> Any:
    def answer(payload: dict[str, Any], timeout: float = 0) -> dict[str, Any]:
        if payload["op"] == "nodes":
            now = time.time()
            return {
                "ok": True,
                "nodes": [
                    {
                        "address": REMOTE,
                        "name": "Hill <b>farm</b>",
                        "first_heard": now - 900,
                        "last_heard": now - 120,
                        "heard_recently": True,
                        "path_known": True,
                        "reachable": False,
                        "last_failed": None,
                        "own": False,
                    },
                ],
            }
        if payload["op"] == "fetch":
            fetched.append(payload["path"])
            content = PAGES.get(payload["path"])
            return {"ok": True, "content": content} if content else {"ok": False, "error": "not_found"}
        return {"ok": True}

    return answer


def snapshot() -> dict[str, Any]:
    now = time.time()
    return {
        "schema": 1,
        "generated_at": now,
        "app": {
            "version": "0.6.0",
            "rns_version": "1.6.0",
            "arch": "x86_64",
            "state": "running",
            "connectivity": "isolated",
            "problem": "none",
            "message": None,
            "started_at": now - 60,
        },
        "node": {"running": True, "started_at": now - 60, "transport_enabled": False, "restarts": 0},
        "network": {"peers_configured": 0, "peers_connected": 0},
        "peers": [],
        "resources": {"memory_bytes": 80 * 2**20, "cpu_percent": 1.0},
        "messaging": {"enabled": False, "state": "disabled", "message": None},
    }


def run(device: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        fetched: list[str] = []
        store = Store(Path(tmp) / "pages", group=None)
        pages = PagesSupervisor(lambda: None, print, time.monotonic, store=store, link=link(fetched))  # type: ignore[arg-type,return-value]
        pages.state, pages.healthy = "running", True
        pages.view = {"connected": True, "hosting": {"state": "running", "address": OWN}, "nodes_known": 1}
        assets = ROOT / "custom_components/meshbeacon/frontend"
        dashboard = Dashboard(Control(), lambda _r: (409, {"ok": False}), assets, pages=pages.handle)  # type: ignore[arg-type]
        dashboard.publish(snapshot())
        server = IngressServer(dashboard, "127.0.0.1", 0, allowed_peer="127.0.0.1")
        server.start()
        try:
            script = str(ROOT / "tools" / "pages_browser_check.mjs")
            command = ["node", script, f"http://127.0.0.1:{server.port}/", device]
            result = subprocess.run(command, check=False)
        finally:
            server.stop()
        if result.returncode == 0 and fetched[:3] != ["/page/index.mu", "/page/next.mu", "/page/index.mu"]:
            print(f"FAILED {device}: unexpected fetches {json.dumps(fetched)}")
            return 1
        return result.returncode


def main() -> int:
    return max(run(device) for device in ("iphone", "ipad", "desktop"))


if __name__ == "__main__":
    sys.exit(main())
