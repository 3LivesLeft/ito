# SPDX-License-Identifier: Apache-2.0
"""``python -m meshbeacon.pages``: the pages service (s6 service ``pages``, user mb-nomad).

Exit codes: 0 stopped; 3 cannot start (Reticulum's shared instance is not running).
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
from ..messaging.server import Server  # the generic, peer-checked JSON-lines socket (ADR 0014)
from .helper import Helper

CORE_UID = 9100


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meshbeacon.pages")
    parser.add_argument("--data", type=Path, default=Path("/data/nomadnet"))
    parser.add_argument("--pages", type=Path, default=Path("/data/pages/public"))
    parser.add_argument("--socket", type=Path, default=Path("/run/meshbeacon-pages/pages.sock"))
    parser.add_argument("--allow-uid", type=int, action="append", default=None)
    parser.add_argument("--instance-name", default=rnsconfig.INSTANCE_NAME)  # tests only
    parser.add_argument("--rpc-key-file", type=Path, default=rnsconfig.RPC_KEY_FILE)
    parser.add_argument("--fetch-timeout", type=float, default=30.0, help=argparse.SUPPRESS)  # tests only
    args = parser.parse_args(argv)
    os.umask(0o077)
    fsutil.ensure_dir(args.data)
    rns_config = args.data / "rns"
    fsutil.ensure_dir(rns_config)
    rpc_key = rnsconfig.read_shared_rpc_key(args.rpc_key_file)
    if rpc_key is None:
        print("meshbeacon-pages: Reticulum's access key is missing or invalid", file=sys.stderr, flush=True)
    text = rnsconfig.render_client(instance_name=args.instance_name, rpc_key=rpc_key)
    fsutil.atomic_write(rns_config / "config", text.encode())
    helper = Helper(args.data, args.pages, rns_config, fetch_timeout=min(max(args.fetch_timeout, 1.0), 30.0))
    helper.has_rpc_key = rpc_key is not None
    try:
        helper.start()
    except SystemError:
        print("meshbeacon-pages: cannot start: the Reticulum node is not running", file=sys.stderr, flush=True)
        return 3
    server = Server(args.socket, helper.handle, set(args.allow_uid or [CORE_UID]))
    server.bind()
    threading.Thread(target=server.serve, daemon=True).start()

    def stop(_signum: int, _frame: object) -> None:
        helper.stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print("meshbeacon-pages: started", flush=True)
    try:
        helper.run()
    finally:
        server.stop()
        helper.stop()
    print("meshbeacon-pages: stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
