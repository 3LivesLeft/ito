# SPDX-License-Identifier: Apache-2.0
"""Thin entry point for the Reticulum child process (feasibility Q-12: decided).

Starts the unmodified RNS reference implementation through its public API and, every few
seconds, writes a small JSON status line to a dedicated pipe. Only peer names, interface state and
byte counters are reported — never hashes or keys. RNS's own log output goes to stdout and is
redacted by the supervisor before it reaches the app log.

RNS installs its own SIGTERM/SIGINT handlers, which detach interfaces and exit cleanly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

REPORTED_TYPES = frozenset({"TCPClientInterface"})


def summarise(stats: dict[str, Any] | None) -> dict[str, Any]:
    interfaces = []
    for item in (stats or {}).get("interfaces", []):
        if item.get("type") not in REPORTED_TYPES:
            continue
        interfaces.append(
            {
                "name": str(item.get("short_name") or ""),
                "up": bool(item.get("status")),
                "rxb": int(item.get("rxb") or 0),
                "txb": int(item.get("txb") or 0),
            }
        )
    return {
        "t": time.time(),
        "interfaces": interfaces,
        "rxb": int((stats or {}).get("rxb") or 0),
        "txb": int((stats or {}).get("txb") or 0),
    }


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
            line = json.dumps(summarise(reticulum.get_interface_stats()), separators=(",", ":"))
            status.write(line + "\n")
        except BrokenPipeError:
            return 0  # supervisor has gone; let RNS's exit handlers run
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
