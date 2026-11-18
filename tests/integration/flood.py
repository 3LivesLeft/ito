# SPDX-License-Identifier: Apache-2.0
"""Announce flood generator for the L2 low-memory test (isolated networks only).

Runs its own RNS instance (no shared instance), connects to a local test peer and announces many
unique destinations as fast as RNS allows. Used only against loopback or an internal Docker
network; never against a real network.

Usage: python -m tests.integration.flood <configdir> <host> <port> <destinations> <seconds>
"""

import os
import sys
import time


def main() -> int:
    configdir, host, port, count, seconds = (
        sys.argv[1],
        sys.argv[2],
        int(sys.argv[3]),
        int(sys.argv[4]),
        float(sys.argv[5]),
    )
    os.makedirs(configdir, exist_ok=True)
    with open(os.path.join(configdir, "config"), "w") as f:
        f.write(
            "[reticulum]\n  enable_transport = No\n  share_instance = No\n[logging]\n  loglevel = 1\n"
            "[interfaces]\n  [[Flood]]\n    type = TCPClientInterface\n    enabled = yes\n"
            f"    target_host = {host}\n    target_port = {port}\n"
            # Hostile sender: no announce cap or ingress control on its own side.
            "    announce_cap = 100\n    ingress_control = No\n"
        )
    import RNS

    RNS.Reticulum(configdir=configdir)
    time.sleep(3)  # let the interface connect
    destinations = [
        RNS.Destination(RNS.Identity(), RNS.Destination.IN, RNS.Destination.SINGLE, "meshbeacontest", "flood", str(i))
        for i in range(count)
    ]
    sent = 0
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for d in destinations:
            d.announce(app_data=os.urandom(64))
            sent += 1
            if time.monotonic() >= end:
                break
    print(f"announces sent: {sent} for {count} destinations", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
