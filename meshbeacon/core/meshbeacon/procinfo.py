# SPDX-License-Identifier: Apache-2.0
"""Resource readings from /proc (Linux only)."""

from __future__ import annotations

import os
from pathlib import Path

CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def memory_bytes(pid: int) -> int | None:
    """RSS + swap of a process, in bytes (so that swapping cannot hide growth)."""
    try:
        text = Path(f"/proc/{pid}/status").read_text()
    except OSError:
        return None
    total = 0
    for line in text.splitlines():
        if line.startswith(("VmRSS:", "VmSwap:")):
            total += int(line.split()[1]) * 1024
    return total


def cpu_seconds(pid: int) -> float | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except (OSError, IndexError):
        return None
    # fields[11], fields[12] are utime and stime (fields 14 and 15 of the full line)
    return (int(fields[11]) + int(fields[12])) / CLK_TCK


def die_with_parent(expected_parent: int) -> None:
    """Ask the kernel to send SIGTERM to this process when its parent dies (Linux PR_SET_PDEATHSIG).

    This prevents an orphaned Reticulum process from surviving a crash of the supervisor and then
    running alongside a newly started one on the same storage.
    """
    import ctypes
    import ctypes.util
    import signal

    pr_set_pdeathsig = 1
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c") or None, use_errno=True)
        libc.prctl(pr_set_pdeathsig, int(signal.SIGTERM), 0, 0, 0)
    except (OSError, AttributeError):
        return
    if os.getppid() != expected_parent:  # parent already gone before prctl took effect
        os.kill(os.getpid(), signal.SIGTERM)
