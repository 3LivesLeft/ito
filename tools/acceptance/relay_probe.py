# SPDX-License-Identifier: Apache-2.0
"""Relay-link probe, run INSIDE the MeshBeacon app container as the service user (M1.2).

    docker exec -u meshbeacon -i <container> python3 -I - < tools/acceptance/relay_probe.py

Used by the container tests and by VM acceptance test SO-1 (docs/testing/v0.3-vm-acceptance.md).
It prints one JSON line and changes nothing. It reads only /proc entries of MeshBeacon's own
processes and prints no secret: a descriptor number and booleans.

- ``core_fd`` / ``core_is_socket``: the core holds the relay link (socket mode only);
- ``node_shares_it``: the Reticulum child holds the same socket (must be false);
- ``core_env_token`` / ``node_env_token``: the Supervisor token is in a process's environment
  (must be false in socket mode);
- ``same_user_can_take_link``: a process of the service user could copy the core's descriptor with
  pidfd_getfd (must be false under AppArmor).
"""

from __future__ import annotations

import ctypes
import json
import os
import stat
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


def environ(pid: str) -> dict[bytes, bytes]:
    entries = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    return dict(e.split(b"=", 1) for e in entries if b"=" in e)  # type: ignore[misc]


def inode(pid: str, fd: str) -> int | None:
    try:
        info = os.stat(f"/proc/{pid}/fd/{fd}")
    except OSError:
        return None
    return info.st_ino if stat.S_ISSOCK(info.st_mode) else None


def take(pid: str, fd: str) -> bool:
    """Try to copy the core's descriptor, as a compromised same-user process might."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        pidfd = os.pidfd_open(int(pid))
    except OSError:
        return False
    try:
        got = libc.syscall(PIDFD_GETFD, pidfd, int(fd), 0)
        if got >= 0:
            os.close(got)
        return bool(got >= 0)
    finally:
        os.close(pidfd)


def main() -> None:
    core, node = pid_of(b"meshbeacon.supervisor"), pid_of(b"meshbeacon.node")
    if core is None or node is None:
        print(json.dumps({"error": "the core or the Reticulum child is not running"}))
        return
    raw = environ(core).get(b"MESHBEACON_RELAY_FD")
    fd = raw.decode() if raw else None
    core_inode = inode(core, fd) if fd else None
    node_inodes = {inode(node, n) for n in os.listdir(f"/proc/{node}/fd")}
    result = {
        "same_user_can_take_link": take(core, fd) if fd else False,
        "core_fd": fd,
        "core_is_socket": core_inode is not None,
        "node_shares_it": core_inode is not None and core_inode in node_inodes,
        "core_env_token": b"SUPERVISOR_TOKEN" in environ(core),
        "node_env_token": b"SUPERVISOR_TOKEN" in environ(node),
    }
    print(json.dumps(result))


main()
