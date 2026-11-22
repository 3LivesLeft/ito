# SPDX-License-Identifier: Apache-2.0
"""Real Nomad Network and Reticulum processes for the pages tests (v0.6.0, ADR 0027).

    python -m tests.integration.nomad_nodes remote <dir> <port> <name>
    python -m tests.integration.nomad_nodes fetcher <dir> <port>

``remote`` is somebody else's node: the unmodified ``nomadnet`` daemon on its own Reticulum
instance, connected to the test hub over TCP loopback, serving two pages. ``fetcher`` is a plain
Reticulum client of the hub over TCP that fetches pages with link requests, as any Nomad Network
browser does (JSON commands on stdin, JSON results on stdout). Throwaway identities in temporary
directories only; nothing connects outside the loopback interface.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from .lxmf_nodes import client_interface, write_config

REMOTE_INDEX = ">Remote test node\n\nHello from `!far away`!.\n`[Second page`:/page/second.mu]\n"
REMOTE_SECOND = "Second page\n`[Back`:/page/index.mu]\n"


def remote(folder: Path, port: int, name: str) -> None:
    from RNS.vendor.configobj import ConfigObj

    write_config(folder / "rns", {"share_instance": "No"}, client_interface(port))
    pages = folder / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    (pages / "index.mu").write_text(REMOTE_INDEX)
    (pages / "second.mu").write_text(REMOTE_SECOND)
    (folder / "files").mkdir(exist_ok=True)
    (folder / "nn").mkdir(exist_ok=True)
    cfg = ConfigObj()
    cfg.filename = str(folder / "nn" / "config")
    cfg["logging"] = {"loglevel": "3", "destination": "console"}
    cfg["client"] = {"enable_client": "no", "announce_at_start": "no", "periodic_lxmf_sync": "no"}
    cfg["textui"] = {}
    cfg["node"] = {
        "enable_node": "yes",
        "node_name": name,
        "announce_at_start": "yes",
        "pages_path": str(pages),
        "files_path": str(folder / "files"),
        "disable_propagation": "yes",
    }
    cfg.write()
    args = [sys.executable, "-I", "-u", "-m", "nomadnet.nomadnet", "--daemon", "--console"]
    os.execv(sys.executable, [*args, "--config", str(folder / "nn"), "--rnsconfig", str(folder / "rns")])  # noqa: S606


def emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def fetcher(folder: Path, port: int) -> None:
    import RNS

    write_config(folder / "rns", {"share_instance": "No"}, client_interface(port))
    RNS.Reticulum(configdir=str(folder / "rns"))

    class Heard:
        aspect_filter = "nomadnetwork.node"

        def received_announce(self, destination_hash: bytes, announced_identity: Any, app_data: Any) -> None:
            name = app_data.decode("utf-8", "replace") if isinstance(app_data, bytes) else None
            emit({"event": "announce", "address": destination_hash.hex(), "name": name})

    RNS.Transport.register_announce_handler(Heard())
    emit({"event": "ready"})
    for line in sys.stdin:
        command = json.loads(line)
        target = bytes.fromhex(command["address"])
        deadline = time.monotonic() + 30
        while not RNS.Transport.has_path(target) and time.monotonic() < deadline:
            RNS.Transport.request_path(target)
            time.sleep(1)
        identity = RNS.Identity.recall(target)
        if identity is None:
            emit({"event": "fetched", "tag": command["tag"], "result": "no_path"})
            continue
        destination = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "nomadnetwork", "node")
        done = threading.Event()
        out: dict[str, Any] = {"result": "failed"}

        def established(
            link: Any, path: str = command["path"], out: dict[str, Any] = out, done: threading.Event = done
        ) -> None:
            def response(receipt: Any, done: threading.Event = done) -> None:
                data = receipt.response
                out["result"] = "ok" if isinstance(data, bytes) else "empty"
                out["content"] = data.decode("utf-8", "replace") if isinstance(data, bytes) else None
                done.set()

            link.request(path, None, response_callback=response, failed_callback=lambda _r, d=done: d.set(), timeout=20)

        link = RNS.Link(destination, established_callback=established, closed_callback=lambda _l, d=done: d.set())
        done.wait(40)
        link.teardown()
        emit({"event": "fetched", "tag": command["tag"], **out})


def main() -> None:
    mode, folder, port = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
    if mode == "remote":
        remote(folder, port, sys.argv[4])
    else:
        fetcher(folder, port)


if __name__ == "__main__":
    main()
