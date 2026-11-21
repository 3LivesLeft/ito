# SPDX-License-Identifier: Apache-2.0
"""TEST-ONLY LXMF peer, run *inside* the app container as a second local client of the node's real
RNS 1.6.0 shared instance (the messaging engine is the first). Copied in by
tests/container/test_messaging_container.py; never part of the image.

    python3 -I lxmf_peer.py identity <folder>                        # create a throwaway identity
    python3 -I lxmf_peer.py talk <folder> <engine-address> <key-file> <timeout-s>

``identity`` writes ``<folder>/identity`` and ``<folder>/address`` (the peer's LXMF delivery
address, for the app's contact list). ``talk`` announces, sends the engine one message, waits for
its delivery proof and for the core's automatic reply, then prints one JSON line with what
happened. Addresses are never printed (rule 5). Uses only RNS's and LXMF's public API, and only the
container's own shared instance: the app container has no network.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import RNS


def identity(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    me = RNS.Identity()
    me.to_file(str(folder / "identity"))
    address = RNS.Destination.hash_from_name_and_identity("lxmf.delivery", me)
    (folder / "address").write_text(address.hex())


def talk(folder: Path, engine: bytes, key_file: Path, timeout: float) -> dict[str, object]:
    import LXMF
    from RNS.vendor.configobj import ConfigObj

    configdir = folder / "rns"
    configdir.mkdir(parents=True, exist_ok=True)
    cfg = ConfigObj()
    cfg["reticulum"] = {
        "enable_transport": "No",
        "share_instance": "Yes",
        "instance_name": "meshbeacon",
        # The peer authenticates like the engine, so that its own RPC requests do not put
        # "digest" errors in the node's log, which the test checks for the engine.
        "rpc_key": key_file.read_text().strip(),
        "panic_on_interface_error": "No",
    }
    cfg["logging"] = {"loglevel": "2"}
    cfg["interfaces"] = {}
    (configdir / "config").write_text("\n".join(cfg.write()) + "\n")
    reticulum = RNS.Reticulum(configdir=str(configdir), require_shared_instance=True)
    me = RNS.Identity.from_file(str(folder / "identity"))
    router = LXMF.LXMRouter(identity=RNS.Identity(), storagepath=str(folder), autopeer=False)
    delivery = router.register_delivery_identity(me, display_name=None)
    seen: dict[str, object] = {"delivered": False, "reply": False, "reply_verified": False}
    replied = threading.Event()
    done = threading.Event()

    def received(message: LXMF.LXMessage) -> None:
        if message.source_hash == engine:
            seen["reply"] = True
            seen["reply_verified"] = bool(message.signature_validated)
            replied.set()

    router.register_delivery_callback(received)

    def announcer() -> None:
        while not replied.is_set():
            router.announce(delivery.hash)
            time.sleep(5)

    threading.Thread(target=announcer, daemon=True).start()
    end = time.monotonic() + timeout
    while RNS.Identity.recall(engine) is None and time.monotonic() < end:
        RNS.Transport.request_path(engine)
        time.sleep(1)
    seen["engine_heard"] = RNS.Identity.recall(engine) is not None
    if not seen["engine_heard"]:
        return seen
    out = RNS.Destination.OUT
    target = RNS.Destination(RNS.Identity.recall(engine), out, RNS.Destination.SINGLE, "lxmf", "delivery")
    text = "hello from the container test peer"
    lxm = LXMF.LXMessage(target, delivery, text, "", desired_method=LXMF.LXMessage.DIRECT)
    lxm.register_delivery_callback(lambda _m: (seen.update(delivered=True), done.set()))
    lxm.register_failed_callback(lambda _m: done.set())
    router.handle_outbound(lxm)
    done.wait(max(end - time.monotonic(), 1))
    replied.wait(max(end - time.monotonic(), 1))
    # The peer's own authenticated request, as a control: the same key works for any local client.
    try:
        reticulum.is_blackholed(me.hash)
        seen["peer_rpc"] = True
    except Exception:
        seen["peer_rpc"] = False
    return seen


def main() -> None:
    kind, folder = sys.argv[1], Path(sys.argv[2])
    if kind == "identity":
        identity(folder)
        return
    result = talk(folder, bytes.fromhex(sys.argv[3]), Path(sys.argv[4]), float(sys.argv[5]))
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()
    os._exit(0)  # without RNS's and LXMF's exit handlers: the peer's state is thrown away


if __name__ == "__main__":
    main()
