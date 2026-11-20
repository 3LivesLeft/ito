# SPDX-License-Identifier: Apache-2.0
"""``python -m meshbeacon.messaging``: the engine process (s6 service ``messaging``, user mb-lxmf).

Exit codes: 0 stopped; 2 settings invalid; 3 cannot start (node not running, identity damaged).
Messages are plain and never contain addresses, keys or content (rule 5).
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from pathlib import Path

from .. import fsutil, rnsconfig
from . import settings as settings_mod
from .engine import Engine, EngineError
from .server import Server

CORE_UID = 9100


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meshbeacon.messaging")
    parser.add_argument("--data", type=Path, default=Path("/data/messaging"))
    parser.add_argument("--socket", type=Path, default=Path("/run/meshbeacon-messaging/engine.sock"))
    parser.add_argument("--allow-uid", type=int, action="append", default=None)
    # The settings the core wrote from the app's options (D-M4-8); readable, never writable, here.
    parser.add_argument("--settings", type=Path, default=None, help="default: <data>/messaging.json")
    parser.add_argument("--instance-name", default=rnsconfig.INSTANCE_NAME)  # tests only
    # The node's shared RPC key (ADR 0023): readable by this user through the group mb-rpc only.
    parser.add_argument("--rpc-key-file", type=Path, default=rnsconfig.RPC_KEY_FILE)
    args = parser.parse_args(argv)
    os.umask(0o077)
    fsutil.ensure_dir(args.data)
    try:
        settings = settings_mod.load(args.settings or args.data / "messaging.json")
    except settings_mod.SettingsError as exc:
        print(f"meshbeacon-messaging: the settings are invalid: {exc}", file=sys.stderr, flush=True)
        return 2
    rns_config = args.data / "rns"
    fsutil.ensure_dir(rns_config)
    rpc_key = rnsconfig.read_shared_rpc_key(args.rpc_key_file)
    if rpc_key is None:
        # Started all the same: the engine then reports that Reticulum refuses its requests, and
        # the dashboard shows a problem instead of "Running".
        print("meshbeacon-messaging: Reticulum's access key is missing or invalid", file=sys.stderr, flush=True)
    text = rnsconfig.render_client(instance_name=args.instance_name, rpc_key=rpc_key)
    fsutil.atomic_write(rns_config / "config", text.encode())
    engine = Engine(args.data, settings, rns_config=rns_config)
    try:
        engine.start()
    except EngineError as exc:
        print(f"meshbeacon-messaging: cannot start: {exc}", file=sys.stderr, flush=True)
        return 3
    server = Server(args.socket, engine.handle, set(args.allow_uid or [CORE_UID]))
    server.bind()
    threading.Thread(target=server.serve, daemon=True).start()

    def stop(_signum: int, _frame: object) -> None:
        engine.stopping.set()

    # LXMF installs its own SIGINT/SIGTERM handlers (persist and exit); ours replace them so that
    # the socket is removed and the queue closed first, then LXMF's exit handler runs in stop().
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f"meshbeacon-messaging: started (identity {engine.identity_event})", flush=True)
    try:
        engine.run()
    finally:
        server.stop()
        engine.stop()
    print("meshbeacon-messaging: stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
