# SPDX-License-Identifier: Apache-2.0
"""Process-isolation probe (ADR 0018, roadmap gate IS-1 to IS-4), run INSIDE the app container.

    docker exec -u mb-rns -i <container> python3 -I - reticulum < isolation_probe.py
    docker exec -u meshbeacon -i <container> python3 -I - core < isolation_probe.py

Each view tries, as that user, every access another service's data, credentials or channels must
refuse, and prints one JSON line of booleans: **every value must be false**. Nothing is changed:
files are opened read-only, FIFOs and s6 control files are opened without blocking and closed
at once, and nothing is written to them.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path


def can(action) -> bool:  # type: ignore[no-untyped-def]
    try:
        action()
    except OSError:
        return False
    return True


def open_close(path: str, flags: int) -> None:
    os.close(os.open(path, flags | os.O_NONBLOCK))


def connect(path: str) -> None:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        sock.connect(path)


def reticulum_view() -> dict[str, bool]:
    """What Reticulum's user (mb-rns) must not reach."""
    return {
        "core_data_listed": can(lambda: os.listdir("/data/meshbeacon")),
        "core_history_read": can(lambda: Path("/data/meshbeacon/starts.json").read_bytes()),
        "data_root_listed": can(lambda: os.listdir("/data")),
        "service_control_opened": any(
            can(lambda s=s: open_close(f"/run/service/{s}/supervise/control", os.O_WRONLY))
            for s in ("reticulum", "rns-prepare", "meshbeacon", "discovery-relay")
        ),
        "service_status_read": can(lambda: Path("/run/service/reticulum/supervise/status").read_bytes()),
        "channel_opened": any(
            can(lambda p=p: open_close(f"/run/meshbeacon-io/{p}", os.O_RDONLY))
            for p in ("reticulum/out", "reticulum/status", "prepare/out", "prepare/result", "prepare/mode")
        ),
        "relay_connected": can(lambda: connect("/run/meshbeacon/discovery.sock")),
        "container_secrets_read": can(lambda: os.listdir("/run/s6/container_environment")),
    }


def core_view() -> dict[str, bool]:
    """What the management core's user must not reach: Reticulum's key material and files."""
    return {
        "reticulum_data_listed": can(lambda: os.listdir("/data/reticulum")),
        "transport_identity_read": can(lambda: Path("/data/reticulum/storage/transport_identity").read_bytes()),
        "identity_backup_read": can(lambda: Path("/data/reticulum/meshbeacon-identity/identity.backup").read_bytes()),
        "reticulum_config_read": can(lambda: Path("/data/reticulum/config").read_bytes()),
        "data_root_listed": can(lambda: os.listdir("/data")),
    }


def main() -> None:
    view = sys.argv[1] if len(sys.argv) > 1 else "reticulum"
    print(json.dumps(core_view() if view == "core" else reticulum_view()))


main()
