# SPDX-License-Identifier: Apache-2.0
"""Summarise the M4 Raspberry Pi runs (``pi_measure.sh``) into MS-1 and MS-18 verdicts.

    python3 tools/acceptance/pi_summary.py <folder with *-runN.csv and *-runN.log>
        [--cpu-basis core|machine] [--cpu-unchanged 0.1]

Run on a computer after copying ``/share/meshbeacon-m4`` off the Pi. Memory is the Supervisor's
figure (cgroup usage minus inactive file cache, Supervisor 2026.11.0 ``docker/stats.py``), so it
counts every process in the app and its active page cache: it is the conservative reading.
CPU from the Supervisor is a share of the whole machine; ``--cpu-basis core`` (the default, the
stricter one) multiplies it by the number of CPUs so that 0.5 means half of one core.

| Criterion | Pass when |
|---|---|
| MS-1 memory | mean(m4p) − mean(v02) within ±2 MiB |
| MS-1 CPU | abs(mean(m4p) − mean(v02)) ≤ ``--cpu-unchanged`` (percentage points, on the chosen basis) |
| MS-18 memory | mean(m4d) − mean(m4p) ≤ 40 MiB, and mean(m4d) ≤ 160 MiB |
| MS-18 CPU | mean(m4d) − mean(m4p) ≤ 0.5 percentage points (on the chosen basis) |
| Live app | ``started`` in every sample of every run |

The ``Status:`` lines of each run's log give the core's and Reticulum's own RSS + swap, so the
part of the MS-18 difference that is the engine can be told apart from the rest.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

MIB = 1024 * 1024
STATUS = re.compile(r"memory (\d+) MB core(?: \+ (\d+) MB Reticulum)?")
NAME = re.compile(r"^(v02|m4p|m4d)-run(\d+)\.csv$")


@dataclass
class Run:
    label: str
    number: int
    cpus: int
    memory_mib: float
    cpu_machine_pct: float
    samples: int
    live_states: set[str]
    core_mib: float | None = None
    reticulum_mib: float | None = None
    notes: list[str] = field(default_factory=list)

    def cpu(self, basis: str) -> float:
        return self.cpu_machine_pct * (self.cpus if basis == "core" else 1)


def read_run(path: Path) -> Run:
    match = NAME.match(path.name)
    if not match:
        raise ValueError(f"unexpected file name {path.name}")
    lines = path.read_text().splitlines()
    header = dict(part.split("=", 1) for part in lines[0].lstrip("# ").split() if "=" in part)
    rows = list(csv.DictReader(lines[1:]))
    mem = [float(r["memory_bytes"]) / MIB for r in rows if r["memory_bytes"]]
    cpu = [float(r["cpu_percent"]) for r in rows if r["cpu_percent"]]
    if not mem or not cpu:
        raise ValueError(f"{path.name}: no samples")
    run = Run(
        label=match.group(1),
        number=int(match.group(2)),
        cpus=int(header.get("cpus", "1")),
        memory_mib=statistics.mean(mem),
        cpu_machine_pct=statistics.mean(cpu),
        samples=len(rows),
        live_states={r["live_state"] or "unknown" for r in rows},
    )
    log = path.with_suffix(".log")
    if log.exists():
        found = STATUS.findall(log.read_text(errors="replace"))
        if found:
            run.core_mib = statistics.median(float(core) for core, _ in found)
            rns = [float(r) for _, r in found if r]
            run.reticulum_mib = statistics.median(rns) if rns else None
    else:
        run.notes.append("no log")
    return run


def mean_of(runs: list[Run], attr: str, basis: str = "core") -> float | None:
    values = [r.cpu(basis) if attr == "cpu" else getattr(r, attr) for r in runs]
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def summarise(runs: list[Run], basis: str, cpu_unchanged: float) -> dict[str, object]:
    by = {k: [r for r in runs if r.label == k] for k in ("v02", "m4p", "m4d")}
    out: dict[str, object] = {"cpu_basis": basis, "runs": {k: len(v) for k, v in by.items()}}
    means = {
        k: {
            "memory_mib": mean_of(v, "memory_mib"),
            "cpu_pct": mean_of(v, "cpu", basis),
            "core_mib": mean_of(v, "core_mib"),
            "reticulum_mib": mean_of(v, "reticulum_mib"),
        }
        for k, v in by.items()
        if v
    }
    out["means"] = means
    if "v02" in means and "m4p" in means:
        dm = means["m4p"]["memory_mib"] - means["v02"]["memory_mib"]  # type: ignore[operator]
        dc = means["m4p"]["cpu_pct"] - means["v02"]["cpu_pct"]  # type: ignore[operator]
        out["MS-1"] = {
            "memory_delta_mib": round(dm, 1),
            "cpu_delta_pct": round(dc, 3),
            "memory_pass": abs(dm) <= 2,
            "cpu_pass": abs(dc) <= cpu_unchanged,
        }
    if "m4p" in means and "m4d" in means:
        dm = means["m4d"]["memory_mib"] - means["m4p"]["memory_mib"]  # type: ignore[operator]
        dc = means["m4d"]["cpu_pct"] - means["m4p"]["cpu_pct"]  # type: ignore[operator]
        total = means["m4d"]["memory_mib"]
        engine = None
        parts = [means[k][p] for k in ("m4p", "m4d") for p in ("core_mib", "reticulum_mib")]
        if all(v is not None for v in parts):
            p_core, p_rns, d_core, d_rns = (float(v) for v in parts)  # type: ignore[arg-type]
            engine = round(dm - ((d_core + d_rns) - (p_core + p_rns)), 1)
        out["MS-18"] = {
            "memory_added_mib": round(dm, 1),
            "app_total_mib": round(total, 1),  # type: ignore[arg-type]
            "engine_and_overhead_mib": engine,
            "cpu_added_pct": round(dc, 3),
            "memory_pass": dm <= 40 and total <= 160,  # type: ignore[operator]
            "cpu_pass": dc <= 0.5,
        }
    disturbed = sorted({s for r in runs for s in r.live_states} - {"started"})
    out["live_app"] = {"always_started": not disturbed, "other_states": disturbed}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--cpu-basis", choices=("core", "machine"), default="core")
    parser.add_argument("--cpu-unchanged", type=float, default=0.1)
    args = parser.parse_args()
    runs = sorted((read_run(p) for p in args.folder.glob("*-run*.csv")), key=lambda r: (r.label, r.number))
    for run in runs:
        print(
            f"{run.label} run {run.number}: {run.samples} samples, memory {run.memory_mib:.1f} MiB, "
            f"CPU {run.cpu(args.cpu_basis):.3f} % ({args.cpu_basis}), core {run.core_mib} MiB, "
            f"Reticulum {run.reticulum_mib} MiB, live app {sorted(run.live_states)} {' '.join(run.notes)}"
        )
    print(json.dumps(summarise(runs, args.cpu_basis, args.cpu_unchanged), indent=2))


if __name__ == "__main__":
    main()
