# SPDX-License-Identifier: Apache-2.0
"""MS-1 baseline (M4): with messaging off, compare two production images on the same host.

    python3 tools/acceptance/ms1_baseline.py <baseline image> <candidate image> [--runs 2]

For example the v0.2 production image built from ``main`` and the M4 production image. Each run
starts the image with default options on Docker's ``none`` network (nothing can connect out),
waits 60 s, then measures for 120 s: CPU from the container's cgroup (v1 ``cpuacct`` or v2
``cpu.stat``), RSS + swap of every process in the container, the listening TCP and UDP ports and
Unix sockets, and whether ``/data/messaging`` was created. One line per run; then the difference
of the means. It prints no addresses, identities or keys (rule 5) and changes no image.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from statistics import mean

OPTIONS = {"peers": [], "transport": False, "log_level": "normal", "memory_limit_mb": 256, "replace_identity": False}
SETTLE_S, SAMPLE_S = 60, 120
DOCKER = shutil.which("docker") or "/usr/bin/docker"

INSIDE = r"""
import json, os
mem = 0
for p in filter(str.isdigit, os.listdir("/proc")):
    try:
        status = open(f"/proc/{p}/status").read().splitlines()
    except OSError:
        continue
    mem += sum(int(x.split()[1]) for x in status if x.startswith(("VmRSS:", "VmSwap:")))
listen = set()
for kind in ("tcp", "tcp6", "udp", "udp6"):
    try:
        rows = open(f"/proc/net/{kind}").read().splitlines()[1:]
    except OSError:
        continue  # no IPv6 on the none network
    for row in rows:
        c = row.split()
        if kind.startswith("udp") or c[3] == "0A":
            listen.add(f"{kind}:{int(c[1].split(':')[1], 16)}")
for row in open("/proc/net/unix").read().splitlines()[1:]:
    c = row.split()
    if len(c) > 7 and int(c[3], 16) & 0x10000:  # __SO_ACCEPTCON: a listening socket
        listen.add("unix:" + c[7])
print(json.dumps({"mem_kib": mem, "listen": sorted(listen)}))
"""


def docker(*args: str) -> str:
    return subprocess.run([DOCKER, *args], check=True, capture_output=True, text=True).stdout.strip()


def cpu_seconds(container_id: str) -> float:
    for path, scale in (
        (f"/sys/fs/cgroup/cpuacct/docker/{container_id}/cpuacct.usage", 1e9),
        (f"/sys/fs/cgroup/system.slice/docker-{container_id}.scope/cpu.stat", 1e6),
    ):
        p = Path(path)
        if p.exists():
            text = p.read_text()
            if p.name == "cpu.stat":
                text = next(line.split()[1] for line in text.splitlines() if line.startswith("usage_usec"))
            return int(text) / scale
    raise SystemExit("cannot find the container's CPU cgroup (run on the Docker host)")


def run(image: str) -> dict[str, object]:
    data = Path(tempfile.mkdtemp(prefix="mb-ms1-"))
    (data / "options.json").write_text(json.dumps(OPTIONS))
    cid = docker("run", "-d", "--network", "none", "-v", f"{data}:/data", image)
    try:
        time.sleep(SETTLE_S)
        before = cpu_seconds(cid)
        time.sleep(SAMPLE_S)
        cpu = (cpu_seconds(cid) - before) / SAMPLE_S * 100
        inside = json.loads(docker("exec", cid, "python3", "-I", "-c", INSIDE))
        return {
            "image": image,
            "cpu_pct": round(cpu, 3),
            "mem_mib": round(inside["mem_kib"] / 1024, 1),
            "listen": inside["listen"],
            "data_messaging": (data / "messaging").exists(),
        }
    finally:
        subprocess.run([DOCKER, "rm", "-f", cid], check=False, capture_output=True)
        shutil.rmtree(data, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args()
    results: dict[str, list[dict[str, object]]] = {args.baseline: [], args.candidate: []}
    for image in (args.baseline, args.candidate):
        for _ in range(args.runs):
            result = run(image)
            results[image].append(result)
            print(json.dumps(result), flush=True)
    base, cand = results[args.baseline], results[args.candidate]

    def avg(rows: list[dict[str, object]], key: str) -> float:
        return mean(float(r[key]) for r in rows)  # type: ignore[arg-type]

    print(
        json.dumps(
            {
                "mem_mib_delta": round(avg(cand, "mem_mib") - avg(base, "mem_mib"), 1),
                "cpu_pct_delta": round(avg(cand, "cpu_pct") - avg(base, "cpu_pct"), 3),
                "same_endpoints": all(r["listen"] == base[0]["listen"] for r in base + cand),
                "messaging_data_created": any(r["data_messaging"] for r in base + cand),
            }
        )
    )


if __name__ == "__main__":
    main()
