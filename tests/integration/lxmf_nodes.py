# SPDX-License-Identifier: Apache-2.0
"""Real Reticulum and LXMF processes for the messaging engine's interoperability tests (M4).

    python -m tests.integration.lxmf_nodes hub  <dir> <port> <instance-name>
    python -m tests.integration.lxmf_nodes peer <dir> <port> [--no-announce]
    python -m tests.integration.lxmf_nodes lxmd <dir> <instance-name> <hub-rpc-key-file>

``hub`` plays MeshBeacon's node: a shared instance (unique instance name per test) listening on
127.0.0.1 only. ``peer`` is a reference LXMF client on the unmodified LXMF package: it connects to
the hub over TCP loopback, writes its address to ``<dir>/address`` (never printed: rule 5), prints
what it receives as JSON lines and takes commands as JSON lines on stdin. ``lxmd`` runs the
unmodified LXMF propagation daemon (its node address goes to ``<dir>/node``). Throwaway
identities in temporary directories only; nothing here connects outside the loopback interface.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import RNS
from RNS.vendor.configobj import ConfigObj


def write_config(configdir: Path, reticulum: dict[str, str], interfaces: dict[str, dict[str, str]]) -> None:
    configdir.mkdir(parents=True, exist_ok=True)
    cfg = ConfigObj()
    cfg["reticulum"] = {"enable_transport": "No", "panic_on_interface_error": "No", **reticulum}
    cfg["logging"] = {"loglevel": "2"}
    cfg["interfaces"] = {}
    for name, section in interfaces.items():
        cfg["interfaces"][name] = section
    (configdir / "config").write_text("\n".join(cfg.write()) + "\n")


def client_interface(port: int) -> dict[str, dict[str, str]]:
    return {
        "Hub": {"type": "TCPClientInterface", "enabled": "yes", "target_host": "127.0.0.1", "target_port": str(port)}
    }


def hub(folder: Path, port: int, instance: str) -> None:
    listener = {
        "type": "TCPServerInterface",
        "enabled": "yes",
        "listen_ip": "127.0.0.1",
        "listen_port": str(port),
        "ingress_control": "No",
    }  # several new peers announcing at once would be held back
    import secrets

    # A key of the hub's own. The engine is never given it, as on MeshBeacon's node (IS-3a); only
    # the lxmd fixture is, because a propagation node must check its clients' link identities.
    folder.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    (folder / "rpc_key").write_text(key)
    write_config(folder, {"share_instance": "Yes", "instance_name": instance, "rpc_key": key}, {"Listener": listener})
    RNS.Reticulum(configdir=str(folder))
    print("hub: ready", flush=True)
    while True:
        time.sleep(60)


def emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def peer(folder: Path, port: int, announce: bool) -> None:
    import LXMF

    write_config(folder / "rns", {"share_instance": "No"}, client_interface(port))
    RNS.Reticulum(configdir=str(folder / "rns"))
    saved = folder / "identity"
    if saved.exists():
        identity = RNS.Identity.from_file(str(saved))
    else:
        identity = RNS.Identity()
        identity.to_file(str(saved))
    router = LXMF.LXMRouter(identity=RNS.Identity(), storagepath=str(folder), autopeer=False)
    me = router.register_delivery_identity(identity, display_name=None)

    def received(message: Any) -> None:
        emit(
            {
                "event": "received",
                "title": message.title.decode("utf-8", "replace"),
                "content": message.content.decode("utf-8", "replace"),
                "verified": bool(message.signature_validated),
                "method": message.method,
            }
        )

    router.register_delivery_callback(received)
    (folder / "address").write_text(me.hash.hex())

    def announcer() -> None:
        while announce:
            router.announce(me.hash)
            time.sleep(5)

    threading.Thread(target=announcer, daemon=True).start()
    emit({"event": "ready"})
    for line in sys.stdin:
        command = json.loads(line)
        if command["cmd"] == "send":
            target = bytes.fromhex(command["to"])
            while RNS.Identity.recall(target) is None:
                RNS.Transport.request_path(target)
                time.sleep(1)
            destination = RNS.Destination(
                RNS.Identity.recall(target), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
            )
            lxm = LXMF.LXMessage(
                destination,
                me,
                "",
                command.get("title", ""),
                fields=command.get("fields") and {int(k): v for k, v in command["fields"].items()},
                desired_method=LXMF.LXMessage.DIRECT,
            )
            if "content_hex" in command:
                lxm.set_content_from_bytes(bytes.fromhex(command["content_hex"]))
            else:
                lxm.set_content_from_string(command["content"])
            tag = command.get("tag", "")
            lxm.register_delivery_callback(lambda m, tag=tag: emit({"event": "delivered", "tag": tag}))
            lxm.register_failed_callback(lambda m, tag=tag: emit({"event": "failed", "tag": tag}))
            router.handle_outbound(lxm)
        elif command["cmd"] == "sync":
            node = bytes.fromhex(command["node"])
            while RNS.Identity.recall(node) is None or not RNS.Transport.has_path(node):
                RNS.Transport.request_path(node)
                time.sleep(1)
            router.set_outbound_propagation_node(node)

            def sync() -> None:
                for _ in range(12):  # until something arrives or a minute has passed
                    router.request_messages_from_propagation_node(identity)
                    time.sleep(5)
                    emit({"event": "sync", "state": router.propagation_transfer_state})

            threading.Thread(target=sync, daemon=True).start()


def lxmd(folder: Path, instance: str, rpc_key_file: Path) -> None:
    """Prepare an ``lxmd`` propagation node (the unmodified daemon) and run it in this process.

    It is a local client of the hub's shared instance, like the engine: a hub without transport
    does not forward between two of its TCP peers. Unlike the engine it holds the hub's RPC key:
    without it RNS 1.6.0 drops the link identifications a propagation node depends on."""
    import os

    folder.mkdir(parents=True, exist_ok=True)
    key = rpc_key_file.read_text().strip()
    write_config(folder / "rns", {"share_instance": "Yes", "instance_name": instance, "rpc_key": key}, {})
    identity = RNS.Identity()
    identity.to_file(str(folder / "identity"))
    node = RNS.Destination.hash_from_name_and_identity("lxmf.propagation", identity)
    cfg = ConfigObj()
    cfg["lxmf"] = {"announce_at_start": "no"}
    cfg["propagation"] = {
        "enable_node": "yes",
        "announce_at_start": "yes",
        "announce_interval": "1",
        "autopeer": "no",
        "propagation_stamp_cost_target": "13",
    }
    cfg["logging"] = {"loglevel": "2"}
    (folder / "config").write_text("\n".join(cfg.write()) + "\n")
    (folder / "node").write_text(node.hex())
    binary = str(Path(sys.executable).parent / "lxmd")
    os.execv(binary, [binary, "--config", str(folder), "--rnsconfig", str(folder / "rns")])  # noqa: S606


def main() -> None:
    kind, folder = sys.argv[1], Path(sys.argv[2])
    if kind == "lxmd":
        lxmd(folder, sys.argv[3], Path(sys.argv[4]))
        return
    port = int(sys.argv[3])
    if kind == "hub":
        hub(folder, port, sys.argv[4])
    elif kind == "peer":
        peer(folder, port, "--no-announce" not in sys.argv)
    else:
        raise SystemExit("unknown kind")


if __name__ == "__main__":
    main()
