# SPDX-License-Identifier: Apache-2.0
"""Endpoints for the forwarding test: two isolated Reticulum instances that each listen on
127.0.0.1 and can reach each other only through MeshBeacon in transport mode (v0.2).

    python -m tests.integration.relay_nodes server <configdir> <port> <hashfile>
    python -m tests.integration.relay_nodes client <configdir> <port> <hashfile>
    python -m tests.integration.relay_nodes contract <configdir> <port>

Nothing here connects outside the loopback interface.
"""

import json
import sys
import time
from pathlib import Path

import RNS

APP = ("meshbeacon_test", "relay")


def write_config(configdir: Path, port: int | None) -> None:
    configdir.mkdir(parents=True, exist_ok=True)
    text = "[reticulum]\n  enable_transport = No\n  share_instance = No\n[logging]\n  loglevel = 2\n[interfaces]\n"
    if port is not None:
        text += (
            "  [[Listener]]\n    type = TCPServerInterface\n    enabled = yes\n"
            f"    listen_ip = 127.0.0.1\n    listen_port = {port}\n"
        )
    (configdir / "config").write_text(text)


def server(configdir: Path, port: int, hashfile: Path) -> None:
    write_config(configdir, port)
    RNS.Reticulum(configdir=str(configdir))
    dest = RNS.Destination(RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, *APP)
    hashfile.write_text(dest.hash.hex())
    while True:
        dest.announce()
        time.sleep(3)


def client(configdir: Path, port: int, hashfile: Path) -> None:
    write_config(configdir, port)
    RNS.Reticulum(configdir=str(configdir))
    while not hashfile.exists():
        time.sleep(0.2)
    target = bytes.fromhex(hashfile.read_text())
    while not RNS.Transport.has_path(target):
        RNS.Transport.request_path(target)
        time.sleep(1)
    print("relay-client: path known", flush=True)
    link = RNS.Link(RNS.Destination(RNS.Identity.recall(target), RNS.Destination.OUT, RNS.Destination.SINGLE, *APP))
    while link.status != RNS.Link.ACTIVE:
        time.sleep(0.2)
    print("relay-client: link active", flush=True)
    while True:
        RNS.Packet(link, b"x" * 64).send()
        time.sleep(0.5)


def contract(configdir: Path, port: int) -> None:
    """Print which of the keys MeshBeacon reads are present in the pinned RNS (no values)."""
    write_config(configdir, port)
    config = (configdir / "config").read_text().replace("enable_transport = No", "enable_transport = Yes")
    (configdir / "config").write_text(config)
    reticulum = RNS.Reticulum(configdir=str(configdir))
    stats = reticulum.get_interface_stats()
    print(
        json.dumps(
            {
                "node_keys": sorted(stats),
                "interface_keys": sorted(stats["interfaces"][0]) if stats.get("interfaces") else [],
                "transport_enabled": RNS.Reticulum.transport_enabled(),
                "tpcount": stats.get("tpcount"),
                "path_table_len": len(reticulum.get_path_table()),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    mode, rest = sys.argv[1], sys.argv[2:]
    if mode == "contract":
        contract(Path(rest[0]), int(rest[1]))
    else:
        {"server": server, "client": client}[mode](Path(rest[0]), int(rest[1]), Path(rest[2]))
