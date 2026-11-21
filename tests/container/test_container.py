# SPDX-License-Identifier: Apache-2.0
"""Container security and behaviour tests (roadmap LP-3, LP-4, LP-10, LP-12, LP-16, LP-17).

Run against a built image: MESHBEACON_IMAGE=meshbeacon:dev pytest -m container tests/container
These tests start only local containers on an internal Docker network; nothing connects outside.
"""

from __future__ import annotations

import json
import os
import re
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
    # The module-scoped network is an empty internal network that keeps no state between tests,
    # so CI may run these tests in different shards (tests/conftest.py).
    pytest.mark.shard_per_test,
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
    # ADR 0018: the core and Reticulum run as separate, unprivileged users.
    owners = processes(c)
    assert owners.get("meshbeacon.supervisor") == {"meshbeacon"}, owners
    assert owners.get("meshbeacon.node") == {"mb-rns"}, owners
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
    total_kb = app_memory_kib(c)
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
    assert "Stopping ito." in c.logs()
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
            peak_kb = max(peak_kb, app_memory_kib(c))
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
        "/etc/services.d/discovery-relay/run",
        "/etc/services.d/discovery-relay/finish",
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
    # Nothing may be executed from app data. The program must be started from a confined shell:
    # `docker exec` starts its own first program from the unconfined runtime and attaches the
    # profile as that program starts, so the profile's execute rules never apply to it (an earlier
    # version of this test passed only because busybox, renamed, found no applet to run).
    c.exec("cp", "/bin/busybox", "/data/mb-busybox")
    denied = subprocess.run(
        ["docker", "exec", c.name, "sh", "-c", "/data/mb-busybox true"], capture_output=True, text=True
    )
    assert denied.returncode == 126, denied
    assert "permission denied" in (denied.stdout + denied.stderr).lower(), denied
    c.exec("rm", "-f", "/data/mb-busybox")


SUPERVISOR_TOKEN = "container-test-supervisor-token"


def test_home_assistant_integration_end_to_end(run, network, tmp_path):
    """v0.2 (ADR 0006): discovery to a fake Supervisor, token-protected API on port 8100 only,
    the Supervisor token never reaches Reticulum, and idle memory stays under 128 MB."""
    repo = Path(__file__).resolve().parents[2]
    out = tmp_path / "supervisor"
    out.mkdir()
    out.chmod(0o777)
    sup = f"mbsup-{uuid.uuid4().hex[:6]}"
    sh(
        "docker", "run", "-d", "--name", sup, "--network", network, "--network-alias", "supervisor",
        "-v", f"{repo / 'tests' / 'container' / 'fake_supervisor.py'}:/fake.py:ro", "-v", f"{out}:/out",
        "--entrypoint", "python3", IMAGE, "-I", "/fake.py",
    )  # fmt: skip
    try:
        c = run(
            {**DEFAULTS, "home_assistant_integration": True},
            "-e",
            f"SUPERVISOR_TOKEN={SUPERVISOR_TOKEN}",
            "--hostname",
            "local-meshbeacon",
            "--network-alias",
            "local-meshbeacon",
        )
        assert wait_for(lambda: complete_json(out / "discovery.json"), timeout=60), c.logs()
        record = json.loads((out / "discovery.json").read_text())
        assert record["path"] == "/discovery" and record["auth"] == f"Bearer {SUPERVISOR_TOKEN}"
        config = record["body"]["config"]
        assert record["body"]["service"] == "meshbeacon"
        assert config["host"] == "local-meshbeacon" and config["port"] == 8100
        assert len(config["cert_sha256"]) == 64
        token = config["token"]

        fingerprint = config["cert_sha256"]
        fetch = (
            "import hashlib, http.client, ssl, sys\n"
            "c = ssl.create_default_context(); c.check_hostname = False; c.verify_mode = ssl.CERT_NONE\n"
            "h = http.client.HTTPSConnection('local-meshbeacon', 8100, timeout=10, context=c); h.connect()\n"
            "fp = hashlib.sha256(h.sock.getpeercert(binary_form=True)).hexdigest()\n"
            "if fp != sys.argv[2]: print('PIN-MISMATCH'); sys.exit(0)\n"
            "auth = {'Authorization': 'Bearer ' + sys.argv[1]} if sys.argv[1] else {}\n"
            "h.request('GET', '/api/v1/status', headers=auth)\n"
            "r = h.getresponse(); print(r.status); print(r.read().decode())\n"
        )

        def get(auth: str | None) -> str:
            cmd = ["docker", "exec", sup, "python3", "-I", "-c", fetch, auth or "", fingerprint]
            r = subprocess.run(cmd, capture_output=True, text=True)
            return r.stdout + r.stderr

        assert "401" in get(None) and "401" in get("wrong")

        def snapshot() -> dict:
            reply = get(token)
            return json.loads(reply[reply.index("{") : reply.rindex("}") + 1]) if "{" in reply else {}

        assert wait_for(lambda: snapshot().get("node", {}).get("running") is True, timeout=60), get(token)
        snap = snapshot()
        assert snap["app"]["state"] == "running" and snap["app"]["problem"] == "isolated"
        version = re.search(r'^version: "([^"]+)"', (repo / "meshbeacon" / "config.yaml").read_text(), re.M)
        assert version and snap["app"]["version"] == version.group(1)
        # D-M4-8: the status API reports messaging, off by default, with nothing else about it.
        assert snap["messaging"] == {"enabled": False, "state": "disabled", "message": None}
        # Listeners: health (8099) and the API (8100); nothing published, nothing outbound to peers.
        listening = {
            line.split()[1].split(":")[1]
            for line in c.exec("cat", "/proc/net/tcp").splitlines()[1:]
            if line.split()[3] == "0A" and not line.split()[1].startswith("0B00007F:")
        }
        assert listening == {"1FA3", "1FA4"}, listening
        # The Supervisor token is never passed to the prepare step or Reticulum.
        rns = c.exec("pgrep", "-f", "meshbeacon.node").split()[0]
        # Read as Reticulum's own user (ADR 0018): root in the container lacks CAP_SYS_PTRACE.
        environ = sh("docker", "exec", "-u", "mb-rns", c.name, "cat", f"/proc/{rns}/environ")
        assert "PATH=" in environ  # the read worked
        assert SUPERVISOR_TOKEN not in environ
        assert SUPERVISOR_TOKEN not in c.logs() and token not in c.logs()
        # M1.2 re-review: on this compatibility path the token reaches the core through a one-time
        # pipe; Reticulum can find it neither in an environment nor in the core's memory or files.
        assert_isolated(c, SUPERVISOR_TOKEN, socket_mode=False)
        time.sleep(20)
        total_kb = app_memory_kib(c)
        label = "EMULATED (indicative only)" if EMULATED else "native"
        print(f"idle RSS+swap with the Home Assistant integration on ({label}): {total_kb / 1024:.1f} MiB")
        if not EMULATED:
            assert total_kb < 128 * 1024
    finally:
        sh("docker", "rm", "-f", sup, check=False)


# Where the Supervisor binds an app's socket inside its own container (e610ca8: config.py, apps/app.py).
SUPERVISOR_BIND = "/run/os/supervisor/apps/ce27fbb5_meshbeacon"


def test_discovery_over_the_supervisor_socket(run, tmp_path):
    """M1: where the Supervisor gives the app its own socket (root-owned, 0600), the unprivileged
    core announces through the root relay. No token is sent and nothing crosses the network."""
    repo = Path(__file__).resolve().parents[2]
    out = tmp_path / "supervisor"
    out.mkdir()
    out.chmod(0o777)
    api = Path(f"/tmp/mbsock-{uuid.uuid4().hex[:6]}")
    api.mkdir(mode=0o755)
    sup = f"mbsup-{uuid.uuid4().hex[:6]}"
    sh(
        "docker", "run", "-d", "--name", sup, "--network", "none",
        "-v", f"{repo / 'tests' / 'container' / 'fake_supervisor.py'}:/fake.py:ro", "-v", f"{out}:/out",
        # Bound where the real Supervisor binds it, so that AppArmor checks the real name.
        "-v", f"{api}:{SUPERVISOR_BIND}", "--entrypoint", "python3", IMAGE, "-I", "/fake.py",
        "--unix", f"{SUPERVISOR_BIND}/supervisor.sock",
    )  # fmt: skip
    try:
        assert wait_for((api / "supervisor.sock").exists, timeout=30)
        c = run(
            {**DEFAULTS, "home_assistant_integration": True},
            "-e",
            f"SUPERVISOR_TOKEN={SUPERVISOR_TOKEN}",  # present, as on today's Supervisors; must not be used
            "-e",
            "SUPERVISOR_SOCKET=/run/supervisor/api/supervisor.sock",
            "-v",
            f"{api}:/run/supervisor/api:ro",
            "--hostname",
            "ce27fbb5-meshbeacon",
        )
        assert wait_for(lambda: complete_json(out / "discovery.json"), timeout=60), c.logs()
        record = json.loads((out / "discovery.json").read_text())
        assert record["path"] == "/discovery" and record["auth"] is None  # the socket identifies the app
        config = record["body"]["config"]
        assert record["body"]["service"] == "meshbeacon"
        assert set(config) == {"host", "port", "token", "cert_sha256"}
        assert config["host"] == "ce27fbb5-meshbeacon" and config["port"] == 8100
        assert "local socket" in c.logs()
        # The relay runs as root; the core and Reticulum do not.
        assert wait_for(lambda: "meshbeacon.node" in processes(c), timeout=60), c.logs()
        owners = processes(c)
        assert owners.get("meshbeacon.discovery_relay") == {"root"}
        assert owners.get("meshbeacon.supervisor") == {"meshbeacon"}
        assert owners.get("meshbeacon.node") == {"mb-rns"}
        # The core cannot open the Supervisor socket itself (root-only); only the relay can.
        probe = subprocess.run(
            ["docker", "exec", "-u", "meshbeacon", c.name, "python3", "-I", "-c",
             "import socket; s = socket.socket(socket.AF_UNIX); s.connect('/run/supervisor/api/supervisor.sock')"],
            capture_output=True, text=True,
        )  # fmt: skip
        assert probe.returncode != 0 and "Permission" in probe.stderr
        assert SUPERVISOR_TOKEN not in c.logs() and config["token"] not in c.logs()
        assert "meshbeacon.relay_link" not in owners  # the root start step became the core

        # M-1: the relay's own socket is root's alone, so the service user (which Reticulum runs as)
        # cannot connect to it, and so can neither announce nor withdraw.
        modes = c.exec("stat", "-c", "%a %U %G %n", "/run/meshbeacon", "/run/meshbeacon/discovery.sock")
        assert modes.split("\n")[:2] == [
            "700 root root /run/meshbeacon",
            "600 root root /run/meshbeacon/discovery.sock",
        ], modes
        for request in ('{"op": "withdraw", "uuid": "0123abcd"}', json.dumps({"op": "announce", "config": config})):
            probe = subprocess.run(
                ["docker", "exec", "-u", "meshbeacon", c.name, "python3", "-I", "-c",
                 "import socket, sys; s = socket.socket(socket.AF_UNIX); s.connect('/run/meshbeacon/discovery.sock');"
                 " s.sendall(sys.argv[1].encode() + b'\\n'); print(s.recv(100))", request],
                capture_output=True, text=True,
            )  # fmt: skip
            assert probe.returncode != 0 and "Permission" in probe.stderr, probe
        # The core holds the link; Reticulum has no part of it and cannot reach the core's /proc,
        # memory or descriptors; the Supervisor token is in no process at all (L-1).
        assert_isolated(c, SUPERVISOR_TOKEN, socket_mode=True)
    finally:
        sh("docker", "rm", "-f", sup, check=False)
        for path in api.iterdir():
            path.unlink()
        api.rmdir()


LINK_PROBE = (Path(__file__).resolve().parents[2] / "tools" / "acceptance" / "relay_probe.py").read_text()


def complete_json(path: Path) -> bool:
    """The fake Supervisor's record exists and is fully written (it can be read mid-write)."""
    try:
        json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    return True


def app_memory_kib(c: Container) -> int:
    """RSS + swap of the app's own users' processes (the core and Reticulum, ADR 0018), by their
    real UID (/proc/<pid>/status stays readable for the non-dumpable core, whose /proc entries
    otherwise look root-owned)."""
    script = (
        "import os\n"
        "total = 0\n"
        "for pid in filter(str.isdigit, os.listdir('/proc')):\n"
        "    try:\n"
        "        status = open(f'/proc/{pid}/status').read().splitlines()\n"
        "    except OSError:\n"
        "        continue\n"
        "    if int(next(x for x in status if x.startswith('Uid:')).split()[1]) in (9100, 9101, 9102):\n"
        "        total += sum(int(x.split()[1]) for x in status if x.startswith(('VmRSS:', 'VmSwap:')))\n"
        "print(total)\n"
    )
    return int(c.exec("python3", "-I", "-c", script).strip())


def probe(c: Container, mode: str, canary: str = "") -> dict[str, bool]:
    """tools/acceptance/relay_probe.py. The attacker view runs inside the app container as the
    service user (Reticulum's user), under the app's AppArmor profile when CI loads it. The
    observer view only looks: an unconfined, privileged sidecar sharing the app container's
    process namespace (inside the container, the profile refuses even a privileged process
    ptrace access, which CI showed)."""
    if mode == "attacker":
        cmd = ["docker", "exec", "-u", "mb-rns", c.name, "python3"]  # Reticulum's user (ADR 0018)
    else:
        cmd = [
            "docker", "run", "--rm", "--privileged", f"--pid=container:{c.name}", "--network", "none",
            "--security-opt", "apparmor=unconfined", "--entrypoint", "python3", IMAGE,
        ]  # fmt: skip
    result = json.loads(sh(*cmd, "-I", "-c", LINK_PROBE, mode, canary))
    print(f"{mode} probe: {result}")
    return result


def assert_isolated(c: Container, canary: str, *, socket_mode: bool) -> None:
    """M1.2 (threat T72): what a compromised Reticulum child could reach, in either transport."""
    seen = probe(c, "observer", canary)
    assert seen["core_non_dumpable"], seen
    assert not seen["core_env_token"] and not seen["node_env_token"], seen  # in no environment
    assert not seen["token_fd_open"], seen  # the one-time pipe was read and closed
    assert not seen["node_shares_link"] and not seen["node_holds_core_pipe_or_link"], seen
    assert seen["core_holds_link"] is socket_mode, seen
    attack = probe(c, "attacker", canary)
    assert attack == {
        "core_environ": False,
        "core_fds": False,
        "core_maps": False,
        "core_memory": False,
        "took_fd": False,
        "container_env_read": False,
        "canary_found": False,
    }, attack


ISOLATION_PROBE = (Path(__file__).resolve().parents[2] / "tools" / "acceptance" / "isolation_probe.py").read_text()


def isolation(c: Container, view: str) -> dict[str, bool]:
    user = "meshbeacon" if view == "core" else "mb-rns"
    result = json.loads(sh("docker", "exec", "-u", user, c.name, "python3", "-I", "-c", ISOLATION_PROBE, view))
    print(f"isolation probe ({view}): {result}")
    return result


def test_services_are_isolated_by_user(run):
    """ADR 0018, gate IS-1 to IS-4: the core and Reticulum are separate users, and neither can
    reach the other's data, credentials or channels. The same probe must notice when the isolation
    is weakened, or it would prove nothing (IS-4)."""
    c = run(DEFAULTS)
    assert wait_for(lambda: "meshbeacon.node" in processes(c), timeout=60), c.logs()
    owners = processes(c)
    assert owners.get("meshbeacon.supervisor") == {"meshbeacon"} and owners.get("meshbeacon.node") == {"mb-rns"}
    # The prepare step ran as Reticulum's user too: it created the identity in mb-rns's folder.
    owner = c.exec("stat", "-c", "%U %a", "/data/reticulum/storage/transport_identity").split()
    assert owner == ["mb-rns", "600"], owner
    for view in ("reticulum", "core"):
        assert not any(isolation(c, view).values()), view
    # A deliberately weakened installation: the probe must report every breach it is shown.
    c.exec("chmod", "-R", "a+rwX", "/data/meshbeacon", "/data/reticulum", "/run/meshbeacon-io")
    c.exec("chmod", "0755", "/data")
    c.exec("chmod", "0755", "/run/service/reticulum/supervise")
    c.exec("chmod", "0666", "/run/service/reticulum/supervise/control")
    weak_rns, weak_core = isolation(c, "reticulum"), isolation(c, "core")
    for key in (
        "core_data_listed",
        "core_history_read",
        "data_root_listed",
        "service_control_opened",
        "channel_opened",
    ):
        assert weak_rns[key], (key, weak_rns)
    for key in ("reticulum_data_listed", "transport_identity_read", "identity_backup_read", "reticulum_config_read"):
        assert weak_core[key], (key, weak_core)


def test_identity_survives_isolation_upgrade_and_downgrade(run, tmp_path):
    """ADR 0018: moving to separate users keeps the node's identity, and so does going back. An
    installation from before ADR 0018 is simulated: the identity's companion files in the core's
    folder and everything owned by the core's user, as the previous image left them."""
    c = run(DEFAULTS, name="upgrade")
    assert wait_for(lambda: "meshbeacon.node" in processes(c), timeout=60), c.logs()
    identity = c.exec("sha256sum", "/data/reticulum/storage/transport_identity").split()[0]
    sh("docker", "rm", "-f", c.name)
    # Back to the previous layout and ownership (what an older image leaves behind).
    data = tmp_path / "upgrade"
    sh(
        "docker", "run", "--rm", "-v", f"{data}:/data", "--entrypoint", "sh", IMAGE, "-c",
        "mv /data/reticulum/meshbeacon-identity/* /data/meshbeacon/ && "
        "rmdir /data/reticulum/meshbeacon-identity && chown -R 9100:9100 /data/meshbeacon /data/reticulum",
    )  # fmt: skip
    c2 = Container(f"mb-again-{uuid.uuid4().hex[:6]}", data)
    confine = ["--security-opt", f"apparmor={APPARMOR}"] if APPARMOR else []
    sh("docker", "run", "-d", "--name", c2.name, "-v", f"{data}:/data", *confine, IMAGE)
    try:
        assert wait_for(lambda: "meshbeacon.node" in processes(c2), timeout=60), c2.logs()
        assert "unchanged since last start" in c2.logs(), c2.logs()
        after = c2.exec("sha256sum", "/data/reticulum/storage/transport_identity").split()[0]
        assert after == identity  # the very same key, now owned by Reticulum's user
        files = c2.exec("ls", "/data/reticulum/meshbeacon-identity", "/data/meshbeacon").split()
        assert "identity.backup" in files and "identity.json" in files
        assert not any(f.startswith("identity.") for f in c2.exec("ls", "/data/meshbeacon").split())
    finally:
        sh("docker", "rm", "-f", c2.name, check=False)


def processes(c: Container) -> dict[str, set[str]]:
    """Owner (real UID) of each MeshBeacon Python module running in the container."""
    script = (
        "import os, pwd\n"
        "for pid in filter(str.isdigit, os.listdir('/proc')):\n"
        "    try:\n"
        "        args = open(f'/proc/{pid}/cmdline', 'rb').read().split(b'\\0')\n"
        "        status = open(f'/proc/{pid}/status').read().splitlines()\n"
        "        uid = int(next(x for x in status if x.startswith('Uid:')).split()[1])\n"
        "    except OSError:\n"
        "        continue\n"
        "    if b'-m' in args:\n"
        "        print(args[args.index(b'-m') + 1].decode(), pwd.getpwuid(uid).pw_name)\n"
    )
    found: dict[str, set[str]] = {}
    for line in c.exec("python3", "-I", "-c", script).splitlines():
        module, owner = line.split()
        found.setdefault(module, set()).add(owner)
    return found


def test_without_a_socket_the_relay_is_idle(run):
    """Today's Supervisors: no socket, so the relay never starts; the compatibility path is used."""
    c = run({**DEFAULTS})
    assert wait_for(lambda: "meshbeacon.node" in processes(c), timeout=60), c.logs()
    assert "meshbeacon.discovery_relay" not in processes(c)
    assert "s6-pause" in c.exec("sh", "-c", "cat /proc/[0-9]*/comm")
