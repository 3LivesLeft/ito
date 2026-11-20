# SPDX-License-Identifier: Apache-2.0
"""Q-41 / MS-18: how long LXMF takes to make a message stamp on this machine, at costs 8 to 16.

    nice -n 19 python3 -I stamp_benchmark.py [--costs 8 10 12 14 16] [--trials 5] [--timeout 120]

Uses only LXMF's public ``LXMF.LXStamper.generate_stamp`` (the unmodified, pinned LXMF 1.3.0),
on random throwaway message IDs. Each trial runs in its own process and is stopped at the timeout,
so one unlucky stamp cannot run for ever. Stamp work is random (a hash search), so several trials
per cost are needed; the summary gives the median and the slowest. One core is used at a time;
run it under ``nice -n 19`` on a live installation. Nothing is sent, stored or logged elsewhere:
one JSON line per trial on standard output, then one summary line per cost.

MS-18's pass condition is "a stamp at the recipient's cost in at most 30 s, or a clear failure":
read the row for the cost the recipient announces (Q-42, found in MS-14).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import multiprocessing
import os
import platform
import queue
import resource
import signal
import statistics
import time
from typing import Any

import LXMF
import LXMF.LXStamper


def _trial(cost: int, out: Any) -> None:
    # Its own process group: above a threshold cost RNS 1.6.0 spreads the work over a pool of
    # processes (RNS/Stamps.py, job_linux), and a timeout must stop all of them.
    os.setsid()
    started = time.monotonic()
    _stamp, value = LXMF.LXStamper.generate_stamp(os.urandom(32), cost)
    seconds = time.monotonic() - started
    me, kids = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = me.ru_utime + me.ru_stime + kids.ru_utime + kids.ru_stime
    out.put({"seconds": seconds, "value": float(value), "cpu_s": cpu})


def trial(cost: int, timeout: float) -> dict[str, Any]:
    ctx = multiprocessing.get_context("spawn")
    out = ctx.Queue()
    proc = ctx.Process(target=_trial, args=(cost, out))
    started = time.monotonic()
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        pid = proc.pid
        if pid is not None and pid > 1:  # the trial's own group (it called setsid), never ours
            with contextlib.suppress(ProcessLookupError):
                os.killpg(pid, signal.SIGKILL)
        proc.join(5)
        return {"cost": cost, "seconds": None, "timed_out": True, "after": round(time.monotonic() - started, 1)}
    try:
        result = out.get(timeout=5) if proc.exitcode == 0 else None
    except queue.Empty:
        result = None
    if result is None:
        return {"cost": cost, "seconds": None, "error": f"exit code {proc.exitcode}"}
    return {
        "cost": cost,
        "seconds": round(result["seconds"], 2),
        "value": round(result["value"], 2),
        "cores_used": round(result["cpu_s"] / max(result["seconds"], 1e-3), 1),
    }


def summarise(cost: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    done = [r["seconds"] for r in rows if r.get("seconds") is not None]
    return {
        "cost": cost,
        "trials": len(rows),
        "finished": len(done),
        "timed_out": sum(1 for r in rows if r.get("timed_out")),
        "median_s": round(statistics.median(done), 2) if done else None,
        "slowest_s": max(done) if done else None,
        "within_30s": sum(1 for s in done if s <= 30),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--costs", type=int, nargs="+", default=[8, 10, 12, 14, 16])
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    print(json.dumps({"machine": platform.machine(), "cpus": os.cpu_count(), "lxmf": LXMF.__version__}), flush=True)
    summaries = []
    for cost in args.costs:
        rows = []
        for _ in range(args.trials):
            rows.append(trial(cost, args.timeout))
            print(json.dumps(rows[-1]), flush=True)
        summaries.append(summarise(cost, rows))
    for line in summaries:
        print(json.dumps({"summary": line}), flush=True)


if __name__ == "__main__":
    main()
