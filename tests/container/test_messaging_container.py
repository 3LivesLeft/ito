# SPDX-License-Identifier: Apache-2.0
"""M4 messaging in real images (WP4, WP5; MS-1, MS-2, MS-15, IS-3a).

    MESHBEACON_IMAGE=<production image> MESHBEACON_MESSAGING_IMAGE=<messaging-dev image> \\
        pytest -m container tests/container/test_messaging_container.py

Production (``MESHBEACON_IMAGE``, the Dockerfile's default target): nothing of the messaging engine
is present, not in the final file system and not in any layer, and nothing of it runs. This does
not rely on a switch: the files are absent and the tests look for them.

Development (``MESHBEACON_MESSAGING_IMAGE``, target ``messaging-dev``): the engine's s6 lifecycle,
start order, clean stop, restarts, socket permissions and user isolation, and that its failures
never touch Reticulum or the core. Only local containers on no network; nothing connects outside.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from .test_container import DEFAULTS, SCALE, app_memory_kib, processes, sh

PRODUCTION = os.environ.get("MESHBEACON_IMAGE", "")
DEV = os.environ.get("MESHBEACON_MESSAGING_IMAGE", "")
# An AppArmor profile loaded on the host (CI: the production profile plus the engine's socket
# folder, for the development image only). Empty: unconfined.
APPARMOR = os.environ.get("MESHBEACON_APPARMOR", "")
REPO = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.container, pytest.mark.skipif(shutil.which("docker") is None, reason="needs Docker")]
needs_production = pytest.mark.skipif(not PRODUCTION, reason="needs MESHBEACON_IMAGE")
needs_dev = pytest.mark.skipif(not DEV, reason="needs MESHBEACON_MESSAGING_IMAGE")

# Anything of the engine, its dependency or its service, by path inside an image or a layer.
FORBIDDEN_PATHS = re.compile(
    r"(^|/)(site-packages/meshbeacon/messaging(/|$)|site-packages/LXMF(/|$)|site-packages/lxmf-[^/]*\.dist-info"
    r"|bin/lxmd$|etc/services\.d/messaging(/|$)|etc/cont-init\.d/20-messaging$|etc/meshbeacon/messaging$"
    r"|run/meshbeacon-messaging)",
    re.IGNORECASE,
)


def wait_for(pred: Callable[[], object], timeout: float = 60.0) -> bool:
    end = time.monotonic() + timeout * SCALE
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.5)
    return False


class App:
    def __init__(self, image: str, options: dict | None = None, data: Path | None = None) -> None:
        self.image = image
        self.data = data or Path(tempfile.mkdtemp(prefix="mb-m4-", dir="/tmp"))
        (self.data / "options.json").write_text(json.dumps(options or DEFAULTS))
        self.name = f"mb-m4-{uuid.uuid4().hex[:8]}"
        confine = ["--security-opt", f"apparmor={APPARMOR}"] if APPARMOR else []
        sh("docker", "run", "-d", "--name", self.name, "--network", "none", "-v", f"{self.data}:/data", *confine, image)

    def logs(self) -> str:
        return subprocess.run(["docker", "logs", self.name], capture_output=True, text=True).stdout

    def exec(self, *cmd: str, user: str = "root", check: bool = True) -> str:
        return sh("docker", "exec", "-u", user, self.name, *cmd, check=check)

    def ok(self, *cmd: str, user: str = "root") -> bool:
        return subprocess.run(["docker", "exec", "-u", user, self.name, *cmd], capture_output=True).returncode == 0

    def pid(self, module: str) -> int | None:
        script = (
            "import os, sys\n"
            "for p in filter(str.isdigit, os.listdir('/proc')):\n"
            "    try: a = open(f'/proc/{p}/cmdline','rb').read().split(b'\\0')\n"
            "    except OSError: continue\n"
            "    if b'-m' in a and a[a.index(b'-m')+1] == sys.argv[1].encode(): print(p)\n"
        )
        out = self.exec("python3", "-I", "-c", script, module).split()
        return int(out[0]) if out else None

    def health(self) -> bool:
        return self.ok("wget", "-qO-", "http://127.0.0.1:8099/health")

    def remove(self) -> None:
        sh("docker", "rm", "-f", self.name, check=False)


@pytest.fixture
def apps() -> Iterator[Callable[..., App]]:
    made: list[App] = []

    def make(image: str, options: dict | None = None, data: Path | None = None) -> App:
        app = App(image, options, data)
        made.append(app)
        return app

    yield make
    for app in made:
        app.remove()


# -- WP5: the production image ------------------------------------------------------------------


@needs_production
def test_the_production_image_has_no_messaging_files_users_or_packages():
    script = (
        "import importlib.metadata as m, importlib.util as u, os, pwd, grp, json\n"
        "found = []\n"
        "for root in ('/usr', '/etc', '/opt', '/run', '/package', '/command'):\n"
        "    for d, dirs, files in os.walk(root):\n"
        "        found += [os.path.join(d, n) for n in dirs + files]\n"
        "print(json.dumps({\n"
        "  'paths': found,\n"
        "  'dists': sorted(d.metadata['Name'].lower() for d in m.distributions()),\n"
        "  'engine_importable': u.find_spec('meshbeacon.messaging') is not None,\n"
        "  'lxmf_importable': u.find_spec('LXMF') is not None,\n"
        "  'users': [p.pw_name for p in pwd.getpwall()], 'groups': [g.gr_name for g in grp.getgrall()]}))\n"
    )
    seen = json.loads(
        sh("docker", "run", "--rm", "--network", "none", "--entrypoint", "python3", PRODUCTION, "-I", "-c", script)
    )
    assert [p for p in seen["paths"] if FORBIDDEN_PATHS.search(p)] == []
    assert "lxmf" not in seen["dists"] and not seen["engine_importable"] and not seen["lxmf_importable"]
    assert "mb-lxmf" not in seen["users"] and not {"mb-lxmf", "mb-msg"} & set(seen["groups"])
    assert [p for p in seen["paths"] if "lxmf" in p.lower() or "/messaging" in p.lower()] == []


# The engine's user and group, in any passwd or group file a layer writes.
MESSAGING_ACCOUNTS = re.compile(r"(^|[:,])mb-(lxmf|msg)(:|,|$)", re.MULTILINE)


class Layer:
    def __init__(self, name: str, raw: bytes, names: list[str], accounts: str) -> None:
        self.name, self.raw, self.names, self.accounts = name, raw, names, accounts


def image_layers(image: str, folder: Path) -> list[Layer]:
    """Every layer of ``image`` (its history, not only the final file system), from ``docker save``."""
    archive = folder / "image.tar"
    sh("docker", "save", "-o", str(archive), image, timeout=300)
    found: list[Layer] = []
    with tarfile.open(archive) as outer:
        for member in outer.getmembers():
            blob = outer.extractfile(member) if member.isfile() else None
            if blob is None:
                continue
            raw = blob.read()
            try:
                with tarfile.open(fileobj=io.BytesIO(raw)) as layer:
                    names = layer.getnames()
                    accounts = ""
                    for entry in ("etc/passwd", "etc/group"):
                        if entry in names:
                            data = layer.extractfile(entry)
                            accounts += data.read().decode(errors="replace") if data else ""
            except tarfile.ReadError:
                continue  # a config or manifest, not a layer
            found.append(Layer(member.name, raw, names, accounts))
    return found


def messaging_in(layer: Layer) -> list[str]:
    hits = [n for n in layer.names if FORBIDDEN_PATHS.search(n) or "lxmf" in n.lower()]
    return hits + [f"account {m.group(2)}" for m in MESSAGING_ACCOUNTS.finditer(layer.accounts)]


@needs_production
def test_no_layer_of_the_production_image_ever_contained_messaging(tmp_path):
    """Not merely deleted in a later layer: no layer of the image (its history) holds any of it,
    neither a file nor the engine's user or group in a passwd or group file."""
    layers = image_layers(PRODUCTION, tmp_path)
    hits = [f"{layer.name}: {hit}" for layer in layers for hit in messaging_in(layer)]
    assert len(layers) >= 3 and hits == []
    assert any("meshbeacon" in layer.accounts for layer in layers)  # the scan does read accounts


@needs_dev
def test_the_exclusion_checks_find_the_engine_where_it_is(tmp_path):
    """WP5 control: the same scans, and release verification's own detector, on the development
    image, which does hold the engine. They find each part of it, so their silence on the
    production image means absence, not a scan that sees nothing."""
    import sys

    sys.path.insert(0, str(REPO / "tools"))
    import verify_image

    layers = image_layers(DEV, tmp_path)
    hits = [hit for layer in layers for hit in messaging_in(layer)]
    release = [hit for layer in layers for hit in verify_image.messaging_paths(layer.raw)]
    site = "site-packages/"
    expected = [
        f"{site}meshbeacon/messaging/engine.py",
        f"{site}LXMF/LXMRouter.py",
        "bin/lxmd",
        "etc/services.d/messaging/run",
        "etc/cont-init.d/20-messaging",
        "etc/meshbeacon/messaging",
    ]
    for part in expected:
        assert any(h.endswith(part) for h in hits), f"the scan missed {part}"
        assert any(h.endswith(part) for h in release), f"release verification missed {part}"
    assert "account lxmf" in hits and "account msg" in hits


@needs_production
def test_the_app_options_have_no_messaging_option():
    import yaml

    config = yaml.safe_load((REPO / "meshbeacon" / "config.yaml").read_text())
    keys = json.dumps({"options": config.get("options"), "schema": config.get("schema")}).lower()
    assert "messag" not in keys and "lxmf" not in keys


@needs_production
def test_production_runs_no_messaging_and_never_shares_its_instance(apps):
    """MS-1: no engine process, no /data/messaging, no shared instance (IS-3a applies only to the
    development image), and memory as before."""
    app = apps(PRODUCTION)
    assert wait_for(lambda: "not connected to anyone" in app.logs()), app.logs()
    time.sleep(15)
    owners = processes(app)  # type: ignore[arg-type]
    assert "meshbeacon.messaging" not in owners and set(owners.get("meshbeacon.node", ())) == {"mb-rns"}, owners
    assert not (app.data / "messaging").exists()
    assert "share_instance = No" in app.exec("cat", "/data/reticulum/config")
    unix = app.exec("cat", "/proc/net/unix")
    assert "@rns" not in unix and "meshbeacon-messaging" not in unix
    assert "messaging" not in app.logs().lower()
    print(f"MS-1 production idle RSS+swap: {app_memory_kib(app) / 1024:.1f} MiB")  # type: ignore[arg-type]


# -- WP4: the messaging development image -------------------------------------------------------


def engine_up(app: App) -> bool:
    return "meshbeacon-messaging: started" in app.logs()


def status(app: App, user: str = "meshbeacon") -> dict | None:
    """A contract ``status`` request as ``user``, checking that the engine's user serves it."""
    script = (
        "import json, socket, struct, sys\n"
        "s = socket.socket(socket.AF_UNIX); s.settimeout(5)\n"
        "try:\n"
        "    s.connect('/run/meshbeacon-messaging/engine.sock')\n"
        "except OSError as e:\n"
        "    print(json.dumps({'error': type(e).__name__})); sys.exit()\n"
        "uid = struct.unpack('3i', s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]\n"
        "try:\n"
        '    s.sendall(b\'{"op": "status"}\\n\')\n'
        "    line = s.makefile('rb').readline()\n"
        "except OSError:\n"
        "    line = b''  # disconnected without an answer\n"
        "print(json.dumps({'server_uid': uid, 'answer': json.loads(line) if line else None}))\n"
    )
    out = app.exec("python3", "-I", "-c", script, user=user, check=False).strip()
    return json.loads(out) if out else None


@needs_dev
def test_the_engine_starts_after_reticulum_as_its_own_user(apps):
    app = apps(DEV)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    logs = app.logs()
    # Reticulum's first status (the "not connected" report) comes before the engine starts.
    assert logs.index("not connected to anyone") < logs.index("meshbeacon-messaging: started"), logs
    owners = processes(app)  # type: ignore[arg-type]
    assert owners.get("meshbeacon.messaging") == {"mb-lxmf"} and owners.get("meshbeacon.node") == {"mb-rns"}
    assert owners.get("meshbeacon.supervisor") == {"meshbeacon"}
    # Socket and folders.
    assert app.exec("stat", "-c", "%U:%G %a", "/run/meshbeacon-messaging").split() == ["mb-lxmf:mb-msg", "750"]
    assert app.exec("stat", "-c", "%U:%G %a %F", "/run/meshbeacon-messaging/engine.sock").split()[:3] == [
        "mb-lxmf:mb-msg",
        "660",
        "socket",
    ]
    for line in app.exec("find", "/data/messaging", "-exec", "stat", "-c", "%U|%a|%F|%n", "{}", "+").splitlines():
        owner, mode, kind, _name = line.split("|", 3)
        assert owner == "mb-lxmf" and mode == ("700" if kind == "directory" else "600"), line
    # IS-3a: the node shares its instance; the engine holds no RPC key and no interfaces.
    assert "share_instance = Yes" in app.exec("cat", "/data/reticulum/config")
    engine_config = app.exec("cat", "/data/messaging/rns/config")
    assert "rpc_key" not in engine_config and "share_instance = Yes" in engine_config
    # MS-2: a separate identity from the transport identity.
    transport = app.exec("sha256sum", "/data/reticulum/storage/transport_identity").split()[0]
    messaging = app.exec("sha256sum", "/data/messaging/identity").split()[0]
    assert transport != messaging
    # Rule 5: no hash (identity, destination, message) reaches the log; the engine's output goes
    # through the core's redaction like Reticulum's.
    assert not re.search(r"(?<![0-9a-f])[0-9a-f]{32,}(?![0-9a-f])", app.logs(), re.I), app.logs()


@needs_dev
def test_only_the_core_can_use_the_engine_socket(apps):
    """Peer checks both ways: the core reaches the engine's user only; nobody else is served."""
    app = apps(DEV)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    core = status(app, "meshbeacon")
    assert core is not None and core["server_uid"] == 9102 and core["answer"]["ok"] is True, core
    assert core["answer"]["connected"] is True
    assert status(app, "mb-rns") == {"error": "PermissionError"}  # cannot even reach the folder
    refused = status(app, "root")  # root can connect, but the engine serves the core only
    assert refused is not None and refused.get("answer") is None, refused


@needs_dev
def test_users_cannot_read_each_others_data(apps):
    app = apps(DEV)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    # The socket's group holds exactly the core and the engine.
    members = app.exec("python3", "-I", "-c", "import grp; print(' '.join(sorted(grp.getgrnam('mb-msg').gr_mem)))")
    assert members.split() == ["mb-lxmf", "meshbeacon"], members
    for user, path in (
        ("mb-lxmf", "/data/reticulum/storage/transport_identity"),
        ("mb-lxmf", "/data/reticulum/config"),
        ("mb-lxmf", "/data/meshbeacon"),
        ("mb-lxmf", "/data/options.json"),
        ("mb-rns", "/data/messaging/identity"),
        ("mb-rns", "/data/messaging"),
        ("meshbeacon", "/data/messaging/identity"),
        ("meshbeacon", "/data/messaging/queue.db"),
    ):
        assert not app.ok("cat", path, user=user), (user, path)
        if not path.endswith(("identity", ".db", ".json", "config")):
            assert not app.ok("ls", path, user=user), (user, path)  # a folder: not even listed
    assert not app.ok("/command/s6-svc", "-d", "/run/service/reticulum", user="mb-lxmf")
    assert not app.ok("/command/s6-svc", "-d", "/run/service/messaging", user="mb-rns")
    # IS-4: against a deliberately weakened installation the same checks must report the breach,
    # or they would prove nothing. Weaken the engine's folders and socket.
    app.exec("chmod", "-R", "a+rwX", "/data/messaging", "/run/meshbeacon-messaging")
    assert app.ok("cat", "/data/messaging/identity", user="mb-rns")  # now readable: detected
    assert app.ok("ls", "/run/meshbeacon-messaging", user="mb-rns")
    # The socket is reachable now, but the engine's peer check still serves the core only.
    weakened = status(app, "mb-rns")
    assert weakened is not None and "error" not in weakened and weakened.get("answer") is None, weakened


@needs_dev
def test_killing_the_engine_restarts_only_the_engine(apps):
    """MS-15: Reticulum keeps running (same process) and the health endpoint never fails."""
    app = apps(DEV)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    node, core = app.pid("meshbeacon.node"), app.pid("meshbeacon.supervisor")
    engine = app.pid("meshbeacon.messaging")
    assert node and core and engine
    app.exec("kill", "-9", str(engine))
    assert wait_for(lambda: "Messaging stopped unexpectedly" in app.logs(), 30), app.logs()
    healthy = []
    assert wait_for(lambda: healthy.append(app.health()) or app.pid("meshbeacon.messaging") not in (None, engine), 60)
    assert all(healthy), "the health endpoint failed while the engine restarted"
    assert app.pid("meshbeacon.node") == node and app.pid("meshbeacon.supervisor") == core
    assert wait_for(lambda: (s := status(app)) and s.get("answer", {}).get("ok"), 60)


@needs_dev
def test_a_hung_engine_is_detected_and_restarted(apps):
    """MS-15: a stopped (hung) engine misses three health checks, is killed and started again."""
    app = apps(DEV)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    node, engine = app.pid("meshbeacon.node"), app.pid("meshbeacon.messaging")
    app.exec("kill", "-STOP", str(engine))
    assert wait_for(lambda: "Messaging stopped responding" in app.logs(), 180), app.logs()
    assert wait_for(lambda: app.pid("meshbeacon.messaging") not in (None, engine), 60)
    assert app.pid("meshbeacon.node") == node and app.health()


@needs_dev
def test_an_engine_that_cannot_start_never_affects_the_node(apps):
    """Both copies of the messaging identity damaged: the engine refuses to start (rule 13) and
    replaces nothing; the core backs off; Reticulum and the health endpoint carry on."""
    data = Path(tempfile.mkdtemp(prefix="mb-m4-", dir="/tmp"))
    (data / "messaging").mkdir()
    (data / "messaging" / "identity").write_bytes(b"damaged")
    (data / "messaging" / "identity.backup").write_bytes(b"damaged too")
    app = apps(DEV, data=data)
    assert wait_for(lambda: app.logs().count("Messaging stopped unexpectedly (exit code 3)") >= 2, 120), app.logs()
    assert "identity is damaged" in app.logs()
    node = app.pid("meshbeacon.node")
    time.sleep(5)
    assert app.pid("meshbeacon.node") == node and app.health()
    assert app.exec("cat", "/data/messaging/identity") == "damaged"  # kept for manual recovery


@needs_dev
def test_the_engine_survives_a_reticulum_restart(apps):
    app = apps(DEV)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    engine = app.pid("meshbeacon.messaging")
    app.exec("kill", "-9", str(app.pid("meshbeacon.node")))
    assert wait_for(lambda: "Restarting the Reticulum service" in app.logs(), 60), app.logs()
    assert wait_for(lambda: (s := status(app)) and s.get("answer", {}).get("connected") is True, 120)
    assert app.pid("meshbeacon.messaging") == engine  # the engine reconnected by itself


@needs_dev
def test_stopping_the_app_leaves_messaging_data_intact(apps):
    """A container stop (s6 stops every service at once) exits cleanly, and the engine's data
    comes back as it was: the queue is not quarantined and the identity is unchanged."""
    app = apps(DEV)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    identity = app.exec("sha256sum", "/data/messaging/identity").split()[0]
    assert app.exec("ls", "/data/messaging").split().count("queue.db") == 1
    sh("docker", "stop", "-t", "30", app.name, timeout=60)
    assert sh("docker", "inspect", "-f", "{{.State.ExitCode}}", app.name).strip() == "0"
    again = apps(DEV, data=app.data)
    assert wait_for(lambda: engine_up(again), 90), again.logs()
    assert "meshbeacon-messaging: started (identity unchanged)" in again.logs()
    assert again.exec("sha256sum", "/data/messaging/identity").split()[0] == identity
    assert not [n for n in again.exec("ls", "/data/messaging").split() if ".corrupt-" in n]


@needs_dev
def test_the_messaging_identity_is_independent_of_the_transport_identity(apps):
    """MS-2: replacing the transport identity leaves the messaging identity as it was."""
    app = apps(DEV)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    transport = app.exec("sha256sum", "/data/reticulum/storage/transport_identity").split()[0]
    messaging = app.exec("sha256sum", "/data/messaging/identity").split()[0]
    app.remove()
    again = apps(DEV, {**DEFAULTS, "replace_identity": True}, data=app.data)
    assert wait_for(lambda: engine_up(again), 90), again.logs()
    assert again.exec("sha256sum", "/data/reticulum/storage/transport_identity").split()[0] != transport
    assert again.exec("sha256sum", "/data/messaging/identity").split()[0] == messaging
    assert "meshbeacon-messaging: started (identity unchanged)" in again.logs()


@needs_dev
def test_development_image_idle_memory(apps):
    """Q-40 / MS-18 (indicative only: MS-18 is decided on the spare Pi, D-M4-7)."""
    app = apps(DEV)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    time.sleep(20)
    print(f"messaging-dev idle RSS+swap (core + Reticulum + engine): {app_memory_kib(app) / 1024:.1f} MiB")  # type: ignore[arg-type]


ABSTRACT = (
    "import json, socket, sys\n"
    "name = sys.argv[1].encode()\n"
    "s = socket.socket(socket.AF_UNIX)\n"
    "try:\n"
    "    s.connect(b'\\0' + name); print(json.dumps('connected'))\n"
    "except OSError as e:\n"
    "    print(json.dumps(type(e).__name__))\n"
)
RPC = (
    "import json, os, multiprocessing.connection as mc\n"
    "try:\n"
    "    mc.Client('\\0rns/meshbeacon/rpc', family='AF_UNIX', authkey=os.urandom(32)).close()\n"
    "    print(json.dumps('authenticated'))\n"
    "except Exception as e:\n"
    "    print(json.dumps(type(e).__name__))\n"
)


@needs_dev
def test_the_shared_instance_is_reachable_only_inside_the_app_container(apps):
    """IS-3a: the RNS 1.6.0 shared instance is an abstract Unix socket (``\\0rns/meshbeacon``,
    RNS/Reticulum.py lines 369 and 825-826), which lives in the container's own network namespace
    (the app has no host network). Another container cannot reach it; inside, it is there."""
    app = apps(DEV)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    assert "@rns/meshbeacon" in app.exec("cat", "/proc/net/unix")
    inside = json.loads(app.exec("python3", "-I", "-c", ABSTRACT, "rns/meshbeacon", user="mb-lxmf"))
    assert inside == "connected"
    for network in ("none", "bridge"):
        outside = sh(
            "docker", "run", "--rm", "--network", network, "--entrypoint", "python3", DEV,
            "-I", "-c", ABSTRACT, "rns/meshbeacon",
        )  # fmt: skip
        assert json.loads(outside) in ("ConnectionRefusedError", "FileNotFoundError"), (network, outside)


@needs_dev
def test_the_node_rpc_refuses_anyone_without_its_key(apps):
    """IS-3a: the RPC listener is reachable inside the container, but only Reticulum's user holds
    its key (in /data/reticulum/config, 0600). The engine has no key; a wrong key is refused."""
    app = apps(DEV)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    assert "@rns/meshbeacon/rpc" in app.exec("cat", "/proc/net/unix")
    for user in ("mb-lxmf", "meshbeacon"):
        assert json.loads(app.exec("python3", "-I", "-c", RPC, user=user)) == "AuthenticationError", user
        assert not app.ok("cat", "/data/reticulum/config", user=user), user
    assert "rpc_key" not in app.exec("cat", "/data/messaging/rns/config")
