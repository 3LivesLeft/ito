# SPDX-License-Identifier: Apache-2.0
"""Root start step: hand the core its discovery credential, then become the core (M1.2).

The core's s6 run script runs this as root, just before it drops to the unprivileged
``meshbeacon`` user, in one of two modes:

    python3 -I -m meshbeacon.relay_link --relay /run/meshbeacon/discovery.sock -- s6-setuidgid meshbeacon …
    python3 -I -m meshbeacon.relay_link --token-file /run/s6/container_environment/SUPERVISOR_TOKEN -- …

- ``--relay`` (newer Supervisors, with a per-app socket): connect to the root discovery relay,
  check that root is at the other end, and pass the connected descriptor in ``MESHBEACON_RELAY_FD``.
  The relay accepts root only, so this connection is the only way in.
- ``--token-file`` (the compatibility path for Supervisors without a socket): read the Supervisor
  token as root and pass it through a **one-time pipe** whose read end is ``MESHBEACON_TOKEN_FD``.
  The write end is closed before the core starts, so the core reads the token once and closes
  the pipe. The token never enters any process environment, so it is not in ``/proc/<pid>/environ``.

Either way, the Supervisor token is removed from the environment the core starts with. The core
then marks itself non-dumpable before it starts any child, so a process of the same user (the
Reticulum child) cannot read its memory, environment or descriptors through ``/proc`` or ptrace,
and the descriptors are kept out of every child (threat T72).

This step **always** starts the core, so a relay or token problem never stops the node (ADR 0005).
It waits for the relay for at most ``WAIT`` seconds, which is far below the Supervisor watchdog's
tolerance (two failed checks 120 s apart), and says so in the log if the relay is slow.
"""

from __future__ import annotations

import os
import re
import socket
import sys
import time
from pathlib import Path

from .discovery_relay import peer_uid

RELAY_FD_ENV = "MESHBEACON_RELAY_FD"
TOKEN_FD_ENV = "MESHBEACON_TOKEN_FD"  # noqa: S105 - the variable name, not a secret
SUPERVISOR_TOKEN_ENV = "SUPERVISOR_TOKEN"  # noqa: S105 - the variable name, not a secret
WAIT = 30.0  # slow hardware at boot; never indefinite
SLOW = 5.0  # after this, say that the relay is slow
MAX_TOKEN = 4096
TOKEN = re.compile(r"^[!-~]{16,4096}$")  # printable, no whitespace
MSG_NO_RELAY = (
    "[meshbeacon] The discovery relay did not answer, so Home Assistant cannot be told about "
    "ito until the app restarts. The node works normally."
)
MSG_SLOW_RELAY = "[meshbeacon] Waiting for the discovery relay to start…"
MSG_NO_KEY = "[meshbeacon] The Supervisor's key could not be read, so Home Assistant cannot be told about ito."


def connect(path: str, wait: float | None = None) -> socket.socket | None:
    """A connection to the root relay at ``path``, or None if there is none within ``wait`` s."""
    started = time.monotonic()
    deadline = started + (WAIT if wait is None else wait)
    said = False
    while True:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(1.0)
            sock.connect(path)
        except OSError:
            sock.close()
            now = time.monotonic()
            if now >= deadline:
                return None
            if not said and now - started >= SLOW:
                print(MSG_SLOW_RELAY, flush=True)
                said = True
            time.sleep(0.2)
            continue
        if peer_uid(sock) != 0:  # only ever hand the core a link to root's relay
            sock.close()
            return None
        sock.settimeout(None)
        return sock


def read_token(path: str, environ: dict[str, str]) -> bytes | None:
    """The Supervisor token, from the environment this root step started with or from s6's file."""
    raw = environ.get(SUPERVISOR_TOKEN_ENV, "").encode()
    if not raw:
        try:
            with Path(path).open("rb") as handle:
                raw = handle.read(MAX_TOKEN + 1)
        except OSError:
            return None
    raw = raw.strip()
    return raw if TOKEN.match(raw.decode("ascii", "replace")) else None


def token_pipe(token: bytes) -> int:
    """A pipe holding ``token`` and already closed for writing; returns its read end."""
    read_end, write_end = os.pipe()  # both non-inheritable
    try:
        os.write(write_end, token)  # far below PIPE_BUF, so this never blocks or splits
    finally:
        os.close(write_end)
    return read_end


def _hand_over(fd: int) -> int:
    """Keep ``fd`` clear of stdin, stdout and stderr, and let it cross into the core only."""
    if fd < 3:
        moved = os.dup(fd)
        os.close(fd)
        fd = moved
    os.set_inheritable(fd, True)  # the core reads or adopts it at once and makes it non-inheritable
    return fd


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    relay = token_file = None
    while args and args[0] != "--":
        option = args.pop(0)
        if option in ("--relay", "--token-file") and args and args[0] != "--":
            value = args.pop(0)
            if option == "--relay":
                relay = value
            else:
                token_file = value
        else:
            print("usage: relay_link [--relay SOCKET | --token-file FILE] -- COMMAND…", file=sys.stderr)
            return 2
    if not args or args[0] != "--" or len(args) < 2 or (relay and token_file):
        print("usage: relay_link [--relay SOCKET | --token-file FILE] -- COMMAND…", file=sys.stderr)
        return 2
    command = args[1:]
    environ = dict(os.environ)
    env = {k: v for k, v in environ.items() if k not in (RELAY_FD_ENV, TOKEN_FD_ENV, SUPERVISOR_TOKEN_ENV)}
    try:
        if relay is not None:
            sock = connect(relay)
            if sock is None:
                print(MSG_NO_RELAY, flush=True)
            else:
                env[RELAY_FD_ENV] = str(_hand_over(sock.detach()))
        elif token_file is not None:
            token = read_token(token_file, environ)
            if token is None:
                if Path(token_file).exists() or environ.get(SUPERVISOR_TOKEN_ENV):
                    print(MSG_NO_KEY, flush=True)
            else:
                env[TOKEN_FD_ENV] = str(_hand_over(token_pipe(token)))
    except Exception:  # never stop the core from starting
        env.pop(RELAY_FD_ENV, None)
        env.pop(TOKEN_FD_ENV, None)
    os.execve(command[0], command, env)  # noqa: S606 - fixed argv from the root run script, no shell
    return 1  # pragma: no cover - execve does not return


if __name__ == "__main__":
    sys.exit(main())
