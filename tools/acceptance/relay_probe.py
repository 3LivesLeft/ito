# SPDX-License-Identifier: Apache-2.0
"""Credential-isolation probe, run INSIDE the MeshBeacon app container (M1.2, threat T72).

Two views, each printing one JSON line and changing nothing:

    # what Reticulum's user (mb-rns, ADR 0018) can do, like a compromised Reticulum child:
    docker exec -u mb-rns -i <container> python3 -I - attacker [CANARY] < relay_probe.py
    # what is really there, only to observe: an unconfined privileged sidecar in the app's PID
    # namespace (inside the app, its AppArmor profile refuses even a privileged process ptrace):
    docker run --rm -i --privileged --pid=container:<container> --security-opt apparmor=unconfined \
        --entrypoint python3 <image> -I - observer [CANARY|@auto] < relay_probe.py

``CANARY`` is the Supervisor token *of a test installation* (never one anybody relies on): the
probe reports only whether it was found, never the value. ``@FILE`` reads it from FILE and deletes
the file, so that the value is not on a command line (on a VM); ``@auto`` (observer only, beside
the app) reads the app's own token through ``/proc/<core>/root``. Used by the container tests and by VM acceptance test
SO-1 (docs/testing/v0.3-vm-acceptance.md). Every key must come out ``false`` except where noted.

attacker:
- ``core_environ`` / ``core_fds`` / ``core_maps`` / ``core_memory``: the core's /proc entries could be
  read (the core is non-dumpable, so the kernel refuses them);
- ``took_fd``: a descriptor of the core could be copied with pidfd_getfd;
- ``container_env_read``: s6-overlay's copy of the container environment could be read;
- ``canary_found``: the token was found anywhere this user could read.

observer:
- ``core_non_dumpable``: the core's /proc entries belong to root although it runs as the service
  user (must be **true**);
- ``core_env_token`` / ``node_env_token``: the token is in a process environment;
- ``token_fd_open``: the one-time pipe is still open in the core: an anonymous pipe the core holds
  and no other process shares (descriptor numbers are reused, so the number alone proves nothing), or any
  such pipe from which the token can still be read;
- ``core_holds_link`` (socket mode, must be **true**) / ``node_shares_link``: who holds the relay link;
- ``node_holds_core_pipe_or_link``: Reticulum holds a descriptor that is also open in the core,
  other than its own stdout and status pipes.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import stat
import sys
from pathlib import Path

PIDFD_GETFD = 438  # the same number on x86-64 and arm64


def pid_of(module: bytes) -> str | None:
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if b"-m" in args and args[args.index(b"-m") + 1] == module:
            return pid
    return None


def readable(action) -> bool:  # type: ignore[no-untyped-def]
    try:
        action()
    except OSError:
        return False
    return True


def environ(pid: str) -> bytes:
    return Path(f"/proc/{pid}/environ").read_bytes()


def env_value(pid: str, name: bytes) -> str | None:
    for entry in environ(pid).split(b"\0"):
        if entry.startswith(name + b"="):
            return entry.split(b"=", 1)[1].decode()
    return None


def fd_inodes(pid: str) -> dict[str, int]:
    found = {}
    for name in os.listdir(f"/proc/{pid}/fd"):
        with contextlib.suppress(OSError):
            found[name] = os.stat(f"/proc/{pid}/fd/{name}").st_ino
    return found


def read_memory(pid: str, canary: bytes) -> tuple[bool, bool]:
    """(could read any memory, canary found in readable memory)."""
    try:
        maps = Path(f"/proc/{pid}/maps").read_text().splitlines()
        mem = Path(f"/proc/{pid}/mem").open("rb")  # noqa: SIM115 - closed by the with block below
    except OSError:
        return False, False
    read_any = found = False
    with mem:
        for line in maps:
            addresses, perms = line.split()[:2]
            if not perms.startswith("rw"):
                continue
            start, end = (int(x, 16) for x in addresses.split("-"))
            try:
                mem.seek(start)
                data = mem.read(min(end - start, 64 << 20))
            except OSError:
                continue
            read_any = True
            if canary and canary in data:
                found = True
                break
    return read_any, found


def take_any_fd(pid: str) -> bool:
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        pidfd = os.pidfd_open(int(pid))
    except OSError:
        return False
    try:
        for fd in range(3, 64):
            got = libc.syscall(PIDFD_GETFD, pidfd, fd, 0)
            if got >= 0:
                os.close(got)
                return True
        return False
    finally:
        os.close(pidfd)


def attacker(core: str, node: str, canary: bytes) -> dict[str, bool]:
    memory, in_memory = read_memory(core, canary)
    core_env = readable(lambda: environ(core))
    container_env = Path("/run/s6/container_environment/SUPERVISOR_TOKEN")
    env_file = readable(container_env.read_bytes)
    found = in_memory or (
        bool(canary)
        and (
            canary in environ(node)
            or (core_env and canary in environ(core))
            or (env_file and canary in container_env.read_bytes())
        )
    )
    return {
        "core_environ": core_env,
        "core_fds": readable(lambda: os.listdir(f"/proc/{core}/fd")),
        "core_maps": readable(lambda: Path(f"/proc/{core}/maps").read_bytes()),
        "core_memory": memory,
        "took_fd": take_any_fd(core),
        "container_env_read": env_file,
        "canary_found": bool(found),
    }


def unshared_pipe_with(core: str, core_fds: dict[str, int], node_fds: dict[str, int], canary: bytes) -> bool:
    """True if the core holds a pipe shared with no other process, or one that still yields the
    token. Reading is non-blocking and only from pipes nobody else uses, so nothing is disturbed."""
    others = set(node_fds.values())
    for name, inode in core_fds.items():
        if name in ("0", "1", "2"):
            continue  # the core's own stdio: its log pipe to s6, never read here
        path = f"/proc/{core}/fd/{name}"
        try:
            if not os.readlink(path).startswith("pipe:"):
                continue  # named FIFOs (the services' channels, ADR 0018) are not the token pipe
            if not stat.S_ISFIFO(os.stat(path).st_mode) or inode in others:
                continue
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            with contextlib.suppress(BlockingIOError):
                if canary and canary in os.read(fd, 65536):
                    return True
        finally:
            os.close(fd)
        return True  # an unshared pipe is still open in the core
    return False


def observer(core: str, node: str, canary: bytes) -> dict[str, bool]:
    relay_fd = env_value(core, b"MESHBEACON_RELAY_FD")
    token_fd = env_value(core, b"MESHBEACON_TOKEN_FD")
    core_fds, node_fds = fd_inodes(core), fd_inodes(node)
    link = core_fds.get(relay_fd) if relay_fd else None
    node_own = {node_fds.get(n) for n in ("0", "1", "2")}  # its stdio, shared with the core by design
    args = Path(f"/proc/{node}/cmdline").read_bytes().split(b"\0")
    if b"--status-fd" in args:  # its own status pipe, also shared with the core by design
        node_own.add(node_fds.get(args[args.index(b"--status-fd") + 1].decode()))
    shared = (set(node_fds.values()) & set(core_fds.values())) - node_own
    status = Path(f"/proc/{core}/status").read_text().splitlines()
    uid = next(int(line.split()[1]) for line in status if line.startswith("Uid:"))
    return {
        "core_non_dumpable": os.stat(f"/proc/{core}/environ").st_uid == 0 and uid != 0,
        "core_env_token": bool(canary) and canary in environ(core),
        "node_env_token": bool(canary) and canary in environ(node),
        "token_fd_open": bool(token_fd) and unshared_pipe_with(core, core_fds, node_fds, canary),
        "core_holds_link": link is not None and stat.S_ISSOCK(os.stat(f"/proc/{core}/fd/{relay_fd}").st_mode),
        "node_shares_link": link is not None and link in set(node_fds.values()),
        "node_holds_core_pipe_or_link": bool({i for i in shared if i is not None}),
    }


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "attacker"
    canary = sys.argv[2].encode() if len(sys.argv) > 2 else b""
    if canary.startswith(b"@") and canary != b"@auto":  # @FILE: read, then delete (no command line)
        path = Path(canary[1:].decode())
        canary = path.read_bytes().strip()
        path.unlink()
    core, node = pid_of(b"meshbeacon.supervisor"), pid_of(b"meshbeacon.node")
    if canary == b"@auto" and core is not None:  # observer beside the app: the app's own token
        canary = Path(f"/proc/{core}/root/run/s6/container_environment/SUPERVISOR_TOKEN").read_bytes().strip()
    if core is None or node is None:
        print(json.dumps({"error": "the core or the Reticulum child is not running"}))
        return
    print(json.dumps((observer if mode == "observer" else attacker)(core, node, canary)))


main()
