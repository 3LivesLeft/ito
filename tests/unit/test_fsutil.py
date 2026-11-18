# SPDX-License-Identifier: Apache-2.0
"""Crash consistency of atomic writes (testing strategy §4.3, roadmap LP-7)."""

import os
import random
import signal
import stat
import subprocess
import sys
import textwrap

import pytest

from meshbeacon import fsutil

CORE = os.path.join(os.path.dirname(__file__), "..", "..", "meshbeacon", "core")


def test_atomic_write_mode_and_content(tmp_path):
    target = tmp_path / "f"
    fsutil.atomic_write(target, b"x" * 64)
    assert target.read_bytes() == b"x" * 64
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(fsutil.TMP_PREFIX)]


def test_atomic_write_ignores_umask(tmp_path):
    old = os.umask(0)
    try:
        fsutil.atomic_write(tmp_path / "f", b"data")
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / "f").stat().st_mode) == 0o600


def test_repair_permissions(tmp_path):
    (tmp_path / "d").mkdir(mode=0o755)
    f = tmp_path / "d" / "f"
    f.write_bytes(b"1")
    f.chmod(0o644)
    fsutil.repair_permissions(tmp_path)
    assert stat.S_IMODE((tmp_path / "d").stat().st_mode) == 0o700
    assert stat.S_IMODE(f.stat().st_mode) == 0o600


def test_read_json_corrupt_returns_none(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json")
    assert fsutil.read_json(p) is None
    assert fsutil.read_json(tmp_path / "missing") is None


def test_clear_directory_and_size(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "f").write_bytes(b"x" * 100)
    assert fsutil.tree_size(tmp_path) == 100
    fsutil.clear_directory(tmp_path)
    assert list(tmp_path.iterdir()) == []


WRITER = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, sys.argv[1])
    from pathlib import Path
    from meshbeacon import fsutil
    target = Path(sys.argv[2])
    print("ready", flush=True)
    i = 0
    while True:
        i += 1
        fsutil.atomic_write(target, bytes([i % 256]) * 64)
    """
)


@pytest.mark.slow
def test_randomised_kills_never_leave_partial_file(tmp_path):
    """Kill a writer at random moments 1,000 times; the target is always complete or absent."""
    script = tmp_path / "writer.py"
    script.write_text(WRITER)
    target = tmp_path / "out" / "transport_identity"
    target.parent.mkdir()
    rng = random.Random(1234)
    for _ in range(1000):
        proc = subprocess.Popen([sys.executable, str(script), CORE, str(target)], stdout=subprocess.PIPE)
        assert proc.stdout is not None
        proc.stdout.readline()
        os.kill(proc.pid, signal.SIGSTOP) if rng.random() < 0.01 else None
        delay = rng.random() * 0.004
        if delay:
            import time

            time.sleep(delay)
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait()
        proc.stdout.close()
        if target.exists():
            data = target.read_bytes()
            assert len(data) == 64 and len(set(data)) == 1, "partial or mixed write observed"
        fsutil.remove_stale_temp_files(target.parent)
