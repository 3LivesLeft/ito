# SPDX-License-Identifier: Apache-2.0
"""Root start step: open the core's link to the discovery relay, then become the core (M1.2).

Used only where the Supervisor gives the app its own socket. The core's s6 run script runs this as
root, just before it drops to the unprivileged ``meshbeacon`` user::

    python3 -I -m meshbeacon.relay_link /run/meshbeacon/discovery.sock -- s6-setuidgid meshbeacon …

It waits briefly for the relay's socket (the two services start together), connects, checks that
the other end really is root, and passes the connected descriptor to the core in
``MESHBEACON_RELAY_FD``. Then it executes the command that follows ``--``. It **always** does so:
if the relay cannot be reached, the core starts without the link and says that Home Assistant
cannot be told about it, so a relay problem never stops the node (ADR 0005).

The relay accepts only root, so this connection is the only way in. The core keeps it out of every
child process, so the Reticulum child can neither announce nor withdraw (threat T72).
"""

from __future__ import annotations

import os
import socket
import sys
import time

from .discovery_relay import peer_uid

RELAY_FD_ENV = "MESHBEACON_RELAY_FD"
WAIT = 5.0
MSG_NO_RELAY = (
    "[meshbeacon] The discovery relay did not answer, so Home Assistant cannot be told about "
    "MeshBeacon until the app restarts. The node works normally."
)


def connect(path: str, wait: float | None = None) -> socket.socket | None:
    """A connection to the root relay at ``path``, or None if there is none within ``wait`` s."""
    deadline = time.monotonic() + (WAIT if wait is None else wait)
    while True:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(1.0)
            sock.connect(path)
        except OSError:
            sock.close()
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.1)
            continue
        if peer_uid(sock) != 0:  # only ever hand the core a link to root's relay
            sock.close()
            return None
        sock.settimeout(None)
        return sock


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3 or args[1] != "--":
        print("usage: relay_link SOCKET -- COMMAND…", file=sys.stderr)
        return 2
    path, command = args[0], args[2:]
    env = {k: v for k, v in os.environ.items() if k != RELAY_FD_ENV}
    try:
        sock = connect(path)
    except Exception:  # never stop the core from starting
        sock = None
    if sock is None:
        print(MSG_NO_RELAY, flush=True)
    else:
        fd = sock.detach()
        if fd < 3:  # keep it clear of stdin, stdout and stderr
            moved = os.dup(fd)
            os.close(fd)
            fd = moved
        os.set_inheritable(fd, True)  # into the core only; the core makes it non-inheritable at once
        env[RELAY_FD_ENV] = str(fd)
    os.execve(command[0], command, env)  # noqa: S606 - fixed argv from the root run script, no shell
    return 1  # pragma: no cover - execve does not return


if __name__ == "__main__":
    sys.exit(main())
