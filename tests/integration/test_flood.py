# SPDX-License-Identifier: Apache-2.0
"""L2 low-memory announce-flood test with isolated Reticulum instances (PR #2 review, item 3).

Topology, all on loopback:  flooder (thousands of unique destinations, no announce cap)
→ test peer (transport, announce cap and ingress control disabled: forwards everything)
→ MeshBeacon (transport on, RNS defaults, memory limit 160 MB, detailed logs).

MeshBeacon must stay healthy, keep Reticulum within its memory limit (or restart it under its own
guard and recover), and keep its log output within the rate limit.
"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from meshbeacon import procinfo
from meshbeacon.logfilter import RateLimiter

from .conftest import TestPeer, free_port, wait_for, write_options

pytestmark = pytest.mark.slow

FLOOD_SECONDS = 40
DESTINATIONS = 3000
MEMORY_LIMIT_MB = 160


def test_announce_flood_is_bounded(data, tmp_path, runner_factory):
    peer = TestPeer(tmp_path, free_port(), forward_everything=True)
    peer.start()
    try:
        write_options(
            data,
            transport=True,
            log_level="detailed",
            memory_limit_mb=MEMORY_LIMIT_MB,
            peers=[{"name": "Peer", "host": "127.0.0.1", "port": peer.port}],
        )
        r = runner_factory(data)
        assert wait_for(lambda: r.out.has("Connected to Peer"), timeout=60), r.out.text()
        lines_before = len(r.out.lines)
        flood = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.integration.flood",
                str(tmp_path / "flooder"),
                "127.0.0.1",
                str(peer.port),
                str(DESTINATIONS),
                str(FLOOD_SECONDS),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        started = time.monotonic()
        peak = 0
        health = set()
        while flood.poll() is None or time.monotonic() - started < FLOOD_SECONDS + 10:
            if r.sup.child is not None:
                peak = max(peak, procinfo.memory_bytes(r.sup.child.proc.pid) or 0)
            health.add(r.health())
            time.sleep(1)
        elapsed = time.monotonic() - started
        assert flood.stdout is not None
        sent = flood.stdout.read()
        text = r.out.text()

        received = r.sup.snapshot.rxb if r.sup.snapshot else 0
        print(f"flood: {sent.strip()}; MeshBeacon received {received} bytes; peak RNS memory {peak / 1048576:.1f} MiB")
        assert received > 1_000_000, "the flood did not reach MeshBeacon, so the test proves nothing"
        assert health == {200}
        assert "stopped unexpectedly" not in text
        if "more memory than its limit" in text:  # the guard acted: it must have recovered
            assert wait_for(lambda: r.sup.child is not None and r.sup.child.proc.poll() is None, timeout=60)
        else:
            assert peak < MEMORY_LIMIT_MB * 1024 * 1024
        # Log output stays within the token bucket (burst + rate x time), plus MeshBeacon's own lines.
        limiter = RateLimiter()
        allowed = limiter.burst + limiter.rate * elapsed + 50
        assert len(r.out.lines) - lines_before <= allowed
        assert r.sup.child is not None and r.sup.child.proc.poll() is None
    finally:
        peer.stop()
