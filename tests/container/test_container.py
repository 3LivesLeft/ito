# SPDX-License-Identifier: Apache-2.0
"""Container security and behaviour tests (roadmap LP-3, LP-4, LP-10, LP-12, LP-16, LP-17).

Run against a built image: MESHBEACON_IMAGE=meshbeacon:dev pytest -m container tests/container
These tests start only local containers on an internal Docker network; nothing connects outside.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

IMAGE = os.environ.get("MESHBEACON_IMAGE", "")
# Under QEMU (emulated aarch64) everything is slower and memory readings include the emulator's own
# overhead, so timings are stretched and the memory figure is recorded but not asserted. Emulated
# results are never physical Raspberry Pi validation (roadmap RG-1, RG-2).
EMULATED = os.environ.get("MESHBEACON_EMULATED") == "1"
# Name of an AppArmor profile, built from meshbeacon/apparmor.txt and loaded into the host kernel,
# to run MeshBeacon containers under (CI on an AppArmor-enabled runner). Empty: unconfined.
APPARMOR = os.environ.get("MESHBEACON_APPARMOR", "")
SCALE = 4 if EMULATED else 1
pytestmark = [
    pytest.mark.container,
    pytest.mark.skipif(not IMAGE or shutil.which("docker") is None, reason="needs Docker and MESHBEACON_IMAGE"),
]


def sh(*args: str, check: bool = True, timeout: float = 120) -> str:
    return subprocess.run(args, check=check, capture_output=True, text=True, timeout=timeout).stdout


def wait_for(pred, timeout=60.0):
    end = time.monotonic() + timeout * SCALE
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.5)
    return False


@pytest.fixture(scope="module")
def network():
    name = f"mbtest-{uuid.uuid4().hex[:8]}"
    sh("docker", "network", "create", "--internal", name)  # no route to the outside world
    yield name
    sh("docker", "network", "rm", name, check=False)


class Container:
    def __init__(self, name: str, data: Path) -> None:
        self.name, self.data = name, data

    def logs(self) -> str:
        return subprocess.run(["docker", "logs", self.name], capture_output=True, text=True).stdout

    def exec(self, *cmd: str) -> str:
        return sh("docker", "exec", self.name, *cmd)

    def running(self) -> bool:
        return sh("docker", "inspect", "-f", "{{.State.Running}}", self.name, check=False).strip() == "true"


@pytest.fixture
def run(tmp_path, network):
    started: list[str] = []

    def start(options: dict, *extra: str, name: str | None = None) -> Container:
        data = tmp_path / (name or "data")
        data.mkdir()
        (data / "options.json").write_text(json.dumps(options))
        cname = name or f"mb-{uuid.uuid4().hex[:8]}"
        confine = ["--security-opt", f"apparmor={APPARMOR}"] if APPARMOR else []
        sh("docker", "run", "-d", "--name", cname, "--network", network, "-v", f"{data}:/data", *confine, *extra, IMAGE)
        started.append(cname)
        c = Container(cname, data)
        assert wait_for(lambda: "[meshbeacon]" in c.logs()), c.logs()
        return c

    yield start
    for name in started:
        sh("docker", "rm", "-f", name, check=False)


DEFAULTS = {"peers": [], "transport": False, "log_level": "normal", "memory_limit_mb": 256, "replace_identity": False}


def test_defaults_non_root_permissions_health_and_no_connections(run):
    c = run(DEFAULTS)
    assert wait_for(lambda: "not connected to anyone" in c.logs())
    users = c.exec("ps", "-o", "user,args")
    py = [line for line in users.splitlines() if "meshbeacon." in line]
    assert len(py) >= 2 and all(line.split()[0].startswith("meshbeac") for line in py), users
    assert c.exec("wget", "-qO-", "http://127.0.0.1:8099/health").strip() == "ok"
    modes = c.exec("find", "/data/meshbeacon", "/data/reticulum", "-exec", "stat", "-c", "%a|%F|%n", "{}", "+")
    for line in modes.splitlines():
        mode, kind, _path = line.split("|", 2)
        assert mode == ("700" if kind == "directory" else "600"), line
    time.sleep(15)
    # Only the health listener; no outbound or established sockets.
    docker_dns = "0B00007F:"  # 127.0.0.11: Docker's embedded resolver on user-defined networks, not ours
    tcp = [
        line for line in c.exec("cat", "/proc/net/tcp").splitlines()[1:] if not line.split()[1].startswith(docker_dns)
    ]
    states = {line.split()[3] for line in tcp}
    assert states <= {"0A", "06"}, tcp  # LISTEN, TIME_WAIT (from our own health request)
    assert [line for line in tcp if line.split()[3] == "0A"] and all(
        line.split()[1].endswith(":1FA3") for line in tcp if line.split()[3] == "0A"
    )


def test_idle_memory_under_128_mb(run):
    c = run(DEFAULTS)
    assert wait_for(lambda: "not connected to anyone" in c.logs())
    time.sleep(20)
    out = c.exec("sh", "-c", "for p in $(pgrep -u meshbeacon); do grep -E '^(VmRSS|VmSwap)' /proc/$p/status; done")
    total_kb = sum(int(line.split()[1]) for line in out.splitlines())
    label = "EMULATED (indicative only)" if EMULATED else "native"
    print(f"idle RSS+swap of app processes ({label}): {total_kb / 1024:.1f} MiB")
    if not EMULATED:
        assert total_kb < 128 * 1024


def test_low_memory_profile(run):
    c = run(DEFAULTS, "--memory=256m", "--memory-swap=256m")
    assert wait_for(lambda: "not connected to anyone" in c.logs())
    time.sleep(10)
    assert c.running()
    assert "Killed" not in c.logs()


def test_connects_to_peer_on_internal_network(run, network, tmp_path):
    peer_dir = tmp_path / "peer"
    peer_dir.mkdir()
    (peer_dir / "config").write_text(
        "[reticulum]\n  enable_transport = Yes\n  share_instance = No\n[logging]\n  loglevel = 2\n"
        "[interfaces]\n  [[srv]]\n    type = TCPServerInterface\n    enabled = yes\n"
        "    listen_ip = 0.0.0.0\n    listen_port = 4242\n"
    )
    peer = f"mbpeer-{uuid.uuid4().hex[:6]}"
    sh(
        "docker",
        "run",
        "-d",
        "--name",
        peer,
        "--network",
        network,
        "-v",
        f"{peer_dir}:/cfg",
        "--entrypoint",
        "python3",
        IMAGE,
        "-I",
        "-m",
        "RNS.Utilities.rnsd",
        "--config",
        "/cfg",
    )
    try:
        c = run({**DEFAULTS, "log_level": "detailed", "peers": [{"name": "Test peer", "host": peer, "port": 4242}]})
        assert wait_for(lambda: "Connected to Test peer" in c.logs(), timeout=90), c.logs()
        # Reticulum's own output reaches the app log promptly (unbuffered) and is redacted.
        assert wait_for(lambda: "[reticulum]" in c.logs(), timeout=30), c.logs()
        import re

        assert not re.search(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", c.logs())
    finally:
        sh("docker", "rm", "-f", peer, check=False)


def test_sigterm_stops_cleanly(run):
    c = run(DEFAULTS)
    assert wait_for(lambda: "not connected to anyone" in c.logs())
    start = time.monotonic()
    sh("docker", "stop", "-t", "20", c.name, timeout=60)
    assert time.monotonic() - start < 20 * SCALE
    assert "Stopping MeshBeacon." in c.logs()
    assert sh("docker", "inspect", "-f", "{{.State.ExitCode}}", c.name).strip() == "0"


def test_core_crash_stops_container_instead_of_looping(run):
    c = run(DEFAULTS)
    assert wait_for(lambda: "not connected to anyone" in c.logs())
    pid = c.exec("pgrep", "-f", "meshbeacon.supervisor").split()[0]
    c.exec("kill", "-9", pid)
    assert wait_for(lambda: not c.running(), timeout=30), c.logs()
    assert sh("docker", "inspect", "-f", "{{.State.ExitCode}}", c.name).strip() != "0"


def test_runs_with_minimal_capabilities(run):
    caps = ["--cap-drop=ALL"] + [
        f"--cap-add={c}" for c in ("CHOWN", "FOWNER", "DAC_OVERRIDE", "SETUID", "SETGID", "KILL")
    ]
    c = run(DEFAULTS, *caps, "--security-opt=no-new-privileges")
    assert wait_for(lambda: "not connected to anyone" in c.logs()), c.logs()
    assert c.exec("wget", "-qO-", "http://127.0.0.1:8099/health").strip() == "ok"


def test_invalid_options_need_attention_and_stay_healthy(run):
    c = run({**DEFAULTS, "peers": [{"name": "Bad", "host": "evil\n[[x]]", "port": 4242}]})
    assert wait_for(lambda: "need correcting" in c.logs()), c.logs()
    time.sleep(3)
    assert c.running()
    assert c.exec("wget", "-qO-", "http://127.0.0.1:8099/health").strip() == "ok"
    assert "meshbeacon.node" not in c.exec("ps", "-o", "args")


@pytest.mark.skipif(EMULATED, reason="flood under QEMU emulation is too slow to be meaningful")
def test_low_memory_announce_flood(run, network, tmp_path):
    """L2: transport on, 256 MB hard limit with no swap, flood forwarded by a peer that applies no
    announce cap or ingress control. MeshBeacon must not be killed for lack of memory."""
    repo = Path(__file__).resolve().parents[2]
    peer_dir = tmp_path / "peer"
    peer_dir.mkdir()
    (peer_dir / "config").write_text(
        "[reticulum]\n  enable_transport = Yes\n  share_instance = Yes\n  instance_name = floodpeer\n"
        "[logging]\n  loglevel = 2\n[interfaces]\n  [[srv]]\n    type = TCPServerInterface\n    enabled = yes\n"
        "    listen_ip = 0.0.0.0\n    listen_port = 4242\n    announce_cap = 100\n    ingress_control = No\n"
    )
    peer = f"mbpeer-{uuid.uuid4().hex[:6]}"
    flooder = f"mbflood-{uuid.uuid4().hex[:6]}"
    sh(
        "docker",
        "run",
        "-d",
        "--name",
        peer,
        "--network",
        network,
        "-v",
        f"{peer_dir}:/cfg",
        "--entrypoint",
        "python3",
        IMAGE,
        "-I",
        "-m",
        "RNS.Utilities.rnsd",
        "--config",
        "/cfg",
    )
    try:
        c = run(
            {
                **DEFAULTS,
                "transport": True,
                "log_level": "detailed",
                "memory_limit_mb": 160,
                "peers": [{"name": "Flood peer", "host": peer, "port": 4242}],
            },
            "--memory=256m",
            "--memory-swap=256m",
        )
        assert wait_for(lambda: "Connected to Flood peer" in c.logs(), timeout=90), c.logs()
        sh(
            "docker",
            "run",
            "-d",
            "--name",
            flooder,
            "--network",
            network,
            "-v",
            f"{repo / 'tests' / 'integration' / 'flood.py'}:/flood.py:ro",
            "--entrypoint",
            "python3",
            IMAGE,
            "-I",
            "/flood.py",
            "/tmp/flooder",
            peer,
            "4242",
            "3000",
            "40",
        )
        peak_kb = 0
        end = time.monotonic() + 55
        while time.monotonic() < end:
            out = c.exec(
                "sh", "-c", "for p in $(pgrep -u meshbeacon); do grep -E '^(VmRSS|VmSwap)' /proc/$p/status; done"
            )
            peak_kb = max(peak_kb, sum(int(line.split()[1]) for line in out.splitlines()))
            time.sleep(2)
        stats = json.loads(
            sh("docker", "exec", peer, "python3", "-I", "-m", "RNS.Utilities.rnstatus", "--config", "/cfg", "-j")
        )
        print(f"flood container test: peer sent {stats['txb']} bytes; peak app memory {peak_kb / 1024:.1f} MiB")
        assert stats["txb"] > 1_000_000, "the flood did not reach MeshBeacon"
        assert c.running()
        assert sh("docker", "inspect", "-f", "{{.State.OOMKilled}}", c.name).strip() == "false"
        assert "stopped unexpectedly" not in c.logs()
        assert c.exec("wget", "-qO-", "http://127.0.0.1:8099/health").strip() == "ok"
        assert peak_kb < 256 * 1024
    finally:
        sh("docker", "rm", "-f", flooder, check=False)
        sh("docker", "rm", "-f", peer, check=False)


INVENTORY = r"""
import json, os, stat
out = {}
for top in ("/init", "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/usr/local/bin", "/package", "/command", "/etc"):
    paths = [top] if os.path.isfile(top) else [os.path.join(d, f) for d, _, fs in os.walk(top) for f in fs]
    for p in paths:
        try:
            st = os.stat(p)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode) or not st.st_mode & 0o111:
            continue
        real = os.path.realpath(p)
        with open(real, "rb") as f:
            head = f.read(128)
        interp = head[2:].split(b"\n")[0].split()[0].decode() if head.startswith(b"#!") else None
        out[real] = interp
print(json.dumps(out))
"""


def test_apparmor_profile_covers_every_program_in_the_image():
    """Static check against the real image (no AppArmor kernel needed): every program the profile
    allows to run can actually be run — scripts must also be readable, and their interpreters
    executable. This is the check that would have caught the v0.1.0 '/init' startup failure."""
    from tests.apparmor.rules import load

    profile = load(Path(__file__).resolve().parents[2] / "meshbeacon" / "apparmor.txt")
    inventory = json.loads(sh("docker", "run", "--rm", "--entrypoint", "python3", IMAGE, "-I", "-c", INVENTORY))
    must_run = [
        "/init",
        "/etc/cont-init.d/10-meshbeacon",
        "/etc/services.d/meshbeacon/run",
        "/etc/services.d/meshbeacon/finish",
    ]
    must_run += [p for p in inventory if "/s6-overlay" in p and "/libexec/" in p]
    for path in must_run:
        assert path in inventory, f"{path} missing from the image"
        assert profile.can_exec(path), f"{path} cannot be executed under the profile"
    problems = []
    for path, interpreter in inventory.items():
        if not profile.can_exec(path) or interpreter is None:
            continue
        if not profile.can_read(path):
            problems.append(f"{path}: script without read permission")
        target = os.path.realpath(interpreter) if not interpreter.startswith("/") else interpreter
        if not profile.can_exec(target) and not profile.can_exec(interpreter):
            problems.append(f"{path}: interpreter {interpreter} not executable")
    assert not problems, "\n".join(problems[:40])


@pytest.mark.skipif(not APPARMOR, reason="needs MESHBEACON_APPARMOR (an AppArmor-enabled host)")
def test_apparmor_confinement_is_active_and_restrictive(run):
    c = run(DEFAULTS)
    assert wait_for(lambda: "not connected to anyone" in c.logs()), c.logs()
    assert c.exec("cat", "/proc/1/attr/current").strip() == f"{APPARMOR} (enforce)"
    # Writes outside the permitted locations are refused, even for root inside the container.
    blocked = subprocess.run(
        ["docker", "exec", c.name, "sh", "-c", "echo x > /usr/local/lib/mb-test"], capture_output=True
    )
    assert blocked.returncode != 0
    assert subprocess.run(["docker", "exec", c.name, "sh", "-c", "echo x > /tmp/mb-test"]).returncode == 0
    # Nothing may be executed from app data.
    c.exec("cp", "/bin/busybox", "/data/mb-busybox")
    denied = subprocess.run(["docker", "exec", c.name, "/data/mb-busybox", "true"], capture_output=True, text=True)
    assert denied.returncode != 0
    assert "permission denied" in (denied.stdout + denied.stderr).lower(), denied
    c.exec("rm", "-f", "/data/mb-busybox")
