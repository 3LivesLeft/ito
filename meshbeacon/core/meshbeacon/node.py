# SPDX-License-Identifier: Apache-2.0
"""Thin entry point for the Reticulum child process (feasibility Q-12: decided).

Starts the unmodified RNS reference implementation through its public API and, every few
seconds, writes a small JSON status line to a dedicated pipe. Only peer names, interface state and
allow-listed counters are reported — never hashes or keys. RNS's own log output goes to stdout and is
redacted by the supervisor before it reaches the app log.

RNS installs its own SIGTERM/SIGINT handlers, which detach interfaces and exit cleanly.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from typing import Any

REPORTED_TYPES = frozenset({"TCPClientInterface"})

# Allow-lists of the counters read from RNS's ``get_interface_stats()`` (see
# docs/research/v0.2-observability.md §1). Identity, destination and interface hashes, IFAC data
# and addresses are never read. A key that RNS does not provide is reported as ``None``
# ("unavailable"), never as zero.
INTERFACE_COUNTERS = {"rxb": "rxb", "txb": "txb", "arxc": "announces_rx", "atxc": "announces_tx"}
NODE_COUNTERS = {
    "rxb": "rxb",
    "txb": "txb",
    "rxpkts": "packets_rx",
    "txpkts": "packets_tx",
    "tpcount": "paths",
    "tlinks": "relayed_links",
}


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return max(int(value), 0)


def summarise(stats: dict[str, Any] | None, transport: bool | None = None) -> dict[str, Any]:
    stats = stats or {}
    interfaces = []
    for item in stats.get("interfaces", []):
        if not isinstance(item, dict) or item.get("type") not in REPORTED_TYPES:
            continue
        entry: dict[str, Any] = {"name": str(item.get("short_name") or ""), "up": bool(item.get("status"))}
        for key, out in INTERFACE_COUNTERS.items():
            entry[out] = _count(item.get(key))
        interfaces.append(entry)
    summary: dict[str, Any] = {"t": time.time(), "interfaces": interfaces, "transport": transport}
    for key, out in NODE_COUNTERS.items():
        summary[out] = _count(stats.get(key))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meshbeacon-node")
    parser.add_argument("--config", required=True)
    parser.add_argument("--status-fd", type=int, required=True)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--parent", type=int, default=0)
    args = parser.parse_args(argv)
    if args.parent:
        from .procinfo import die_with_parent

        die_with_parent(args.parent)

    status = os.fdopen(args.status_fd, "w", buffering=1, encoding="utf-8")

    import RNS

    reticulum = RNS.Reticulum(configdir=args.config)
    while True:
        try:
            line = json.dumps(
                summarise(reticulum.get_interface_stats(), bool(RNS.Reticulum.transport_enabled())),
                separators=(",", ":"),
            )
            status.write(line + "\n")
        except BrokenPipeError:
            return 0  # supervisor has gone; let RNS's exit handlers run
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
