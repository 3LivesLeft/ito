# SPDX-License-Identifier: Apache-2.0
"""M4 messaging in the standard image (WP4, D-M4-8; MS-1, MS-2, MS-15, IS-3, IS-3a).

    MESHBEACON_IMAGE=<the image> [MESHBEACON_PREVIOUS_IMAGE=<v0.2 image>] \\
        pytest -m container tests/container/test_messaging_container.py

One image for everyone: it carries the messaging engine, which runs only when the option
``messaging_enabled`` is on (off by default). Off: nothing of messaging runs and no messaging
data is created. On: the engine's s6 lifecycle, start order, clean stop, restarts, socket and
settings permissions and user isolation, and that its failures never touch Reticulum or the core.
``MESHBEACON_PREVIOUS_IMAGE`` (v0.2, built from ``main``) enables the upgrade test. Only local
containers on no network; nothing connects outside.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from .test_container import DEFAULTS, SCALE, app_memory_kib, processes, sh

IMAGE = os.environ.get("MESHBEACON_IMAGE", "")
PREVIOUS = os.environ.get("MESHBEACON_PREVIOUS_IMAGE", "")
# An AppArmor profile loaded on the host (CI: the app's own profile). Empty: unconfined.
APPARMOR = os.environ.get("MESHBEACON_APPARMOR", "")
REPO = Path(__file__).resolve().parents[2]
pytestmark = [
    pytest.mark.container,
    pytest.mark.skipif(not IMAGE or shutil.which("docker") is None, reason="needs Docker and MESHBEACON_IMAGE"),
]
needs_previous = pytest.mark.skipif(not PREVIOUS, reason="needs MESHBEACON_PREVIOUS_IMAGE (v0.2)")
# The 0.3.0 app as first installed on the Pi (messaging, but no shared RPC key: before ADR 0023).
PREVIOUS_MESSAGING = os.environ.get("MESHBEACON_PREVIOUS_MESSAGING_IMAGE", "")
needs_previous_messaging = pytest.mark.skipif(
    not PREVIOUS_MESSAGING, reason="needs MESHBEACON_PREVIOUS_MESSAGING_IMAGE (0.3.0 before ADR 0023)"
)
ADDRESS = "a1" * 16  # a made-up contact address (no such node exists)
ON = {**DEFAULTS, "messaging_enabled": True, "messaging_contacts": [{"name": "Phone", "address": ADDRESS}]}


def wait_for(pred: Callable[[], object], timeout: float = 60.0) -> bool:
    end = time.monotonic() + timeout * SCALE
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.5)
    return False


class App:
    def __init__(
        self, image: str, options: dict | None = None, data: Path | None = None, extra: tuple[str, ...] = ()
    ) -> None:
        self.image = image
        self.data = data or Path(tempfile.mkdtemp(prefix="mb-m4-", dir="/tmp"))
        (self.data / "options.json").write_text(json.dumps(options or DEFAULTS))
        self.name = f"mb-m4-{uuid.uuid4().hex[:8]}"
        confine = ["--security-opt", f"apparmor={APPARMOR}"] if APPARMOR else []
        sh(
            "docker", "run", "-d", "--name", self.name, "--network", "none", "-v", f"{self.data}:/data",
            *confine, *extra, image,
        )  # fmt: skip

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

    def make(image: str, options: dict | None = None, data: Path | None = None, extra: tuple[str, ...] = ()) -> App:
        app = App(image, options, data, extra)
        made.append(app)
        return app

    yield make
    for app in made:
        app.remove()


# -- The standard image: messaging included, off by default (D-M4-8) -----------------------------


def test_the_standard_image_carries_the_messaging_engine():
    script = (
        "import importlib.util as u, os, pwd, grp, json\n"
        "print(json.dumps({\n"
        "  'engine': u.find_spec('meshbeacon.messaging') is not None,\n"
        "  'lxmf': u.find_spec('LXMF') is not None,\n"
        "  'service': os.path.isfile('/etc/services.d/messaging/run'),\n"
        "  'starts_down': os.path.isfile('/etc/services.d/messaging/down'),\n"
        "  'init': os.path.isfile('/etc/cont-init.d/20-messaging'),\n"
        "  'marker': os.path.exists('/etc/meshbeacon/messaging'),\n"
        "  'engine_uid': pwd.getpwnam('mb-lxmf').pw_uid,\n"
        "  'msg_group': sorted(grp.getgrnam('mb-msg').gr_mem),\n"
        "  'rpc_group': sorted(grp.getgrnam('mb-rpc').gr_mem)}))\n"
    )
    seen = json.loads(
        sh("docker", "run", "--rm", "--network", "none", "--entrypoint", "python3", IMAGE, "-I", "-c", script)
    )
    assert seen == {
        "engine": True, "lxmf": True, "service": True, "starts_down": True, "init": True, "marker": False,
        "engine_uid": 9102, "msg_group": ["mb-lxmf", "meshbeacon"],
        "rpc_group": ["mb-lxmf", "mb-nomad", "mb-rns"],  # ADR 0023, ADR 0027 (pages): never the core
    }  # fmt: skip


def test_messaging_is_off_by_default(apps):
    """MS-1 in the standard image: no engine process, no messaging data or folders, no shared
    instance, and the gateway works as before."""
    app = apps(IMAGE)
    assert wait_for(lambda: "not connected to anyone" in app.logs()), app.logs()
    time.sleep(15)
    owners = processes(app)  # type: ignore[arg-type]
    assert "meshbeacon.messaging" not in owners and set(owners.get("meshbeacon.node", ())) == {"mb-rns"}, owners
    assert not (app.data / "messaging").exists()
    assert not app.ok("test", "-e", "/run/meshbeacon-messaging")
    assert not app.ok("test", "-e", "/run/meshbeacon-rpc")  # no shared instance, so no shared key
    assert "enable_interface_management" not in app.exec("cat", "/data/reticulum/config")
    assert "share_instance = No" in app.exec("cat", "/data/reticulum/config")
    unix = app.exec("cat", "/proc/net/unix")
    assert "@rns" not in unix and "meshbeacon-messaging" not in unix
    assert "LXMF messaging: off" in app.logs() and "meshbeacon-messaging" not in app.logs()
    assert app.health()
    print(f"MS-1 messaging off, idle RSS+swap: {app_memory_kib(app) / 1024:.1f} MiB")  # type: ignore[arg-type]


def test_switching_messaging_on_off_and_on_again_keeps_both_identities(apps):
    """The checkbox: on starts exactly one engine; off stops only messaging and keeps its data;
    on again uses the same messaging identity. The node's identity never changes."""
    app = apps(IMAGE, ON)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    time.sleep(5)
    assert processes(app).get("meshbeacon.messaging") == {"mb-lxmf"}  # type: ignore[arg-type]
    assert count_engines(app) == 1
    node_id = app.exec("sha256sum", "/data/reticulum/storage/transport_identity").split()[0]
    messaging_id = app.exec("sha256sum", "/data/messaging/identity").split()[0]
    app.remove()

    off = apps(IMAGE, DEFAULTS, data=app.data)
    assert wait_for(lambda: "not connected to anyone" in off.logs()), off.logs()
    time.sleep(10)
    assert count_engines(off) == 0 and "LXMF messaging: off" in off.logs()
    assert off.exec("sha256sum", "/data/messaging/identity").split()[0] == messaging_id  # kept
    assert "share_instance = No" in off.exec("cat", "/data/reticulum/config")
    off.remove()

    again = apps(IMAGE, ON, data=app.data)
    assert wait_for(lambda: engine_up(again), 90), again.logs()
    assert "meshbeacon-messaging: started (identity unchanged)" in again.logs()
    assert again.exec("sha256sum", "/data/messaging/identity").split()[0] == messaging_id
    assert again.exec("sha256sum", "/data/reticulum/storage/transport_identity").split()[0] == node_id
    assert count_engines(again) == 1


def test_the_engine_gets_its_settings_from_the_options_and_can_change_nothing(apps):
    """The core writes the engine's settings from the validated options into a folder the engine
    can read but not write; Reticulum's user cannot even reach it. The engine never sees the
    options file itself (IS-2: it holds peer passphrases)."""
    app = apps(IMAGE, ON)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    folder = app.exec("stat", "-c", "%U:%G %a", "/run/meshbeacon-messaging/config").split()
    assert folder == ["meshbeacon:mb-msg", "750"]
    assert app.exec("stat", "-c", "%U:%G %a", "/run/meshbeacon-messaging/config/settings.json").split() == [
        "meshbeacon:mb-msg",
        "640",
    ]
    settings = json.loads(app.exec("cat", "/run/meshbeacon-messaging/config/settings.json", user="mb-lxmf"))
    assert settings["contacts"] == [{"id": "phone", "name": "Phone", "destination": ADDRESS}]
    assert settings["inbound"] == "contacts" and settings["display_name"] == ""
    assert not app.ok("sh", "-c", "echo x >> /run/meshbeacon-messaging/config/settings.json", user="mb-lxmf")
    assert not app.ok("touch", "/run/meshbeacon-messaging/config/other", user="mb-lxmf")
    assert not app.ok("cat", "/run/meshbeacon-messaging/config/settings.json", user="mb-rns")
    assert not app.ok("cat", "/data/options.json", user="mb-lxmf")
    contacts = request(app, {"op": "contacts"})
    assert contacts == {"ok": True, "contacts": [{"id": "phone", "name": "Phone", "heard": False}]}, contacts
    answer = request(app, {"op": "status"})
    assert answer is not None and re.fullmatch(r"[0-9a-f]{32}", answer["address"]) and answer["address"] != ADDRESS


def test_invalid_messaging_options_need_attention_and_keep_reticulum_safe(apps):
    """A bad contact address: the core explains it in plain language and starts nothing."""
    bad = {**ON, "messaging_contacts": [{"name": "Phone", "address": "not-an-address"}]}
    app = apps(IMAGE, bad)
    assert wait_for(lambda: "32 hexadecimal" in app.logs(), 60), app.logs()
    assert "Traceback" not in app.logs()
    time.sleep(5)
    assert count_engines(app) == 0 and app.health()  # needs_attention is healthy (ADR 0005)


@needs_previous
def test_upgrade_from_v02_keeps_the_identity_and_leaves_messaging_off(apps):
    """Upgrade: v0.2 creates the node; the standard image takes its data and options as they are
    (no messaging keys: the Supervisor adds the defaults), keeps the identity, and starts no
    messaging until the user switches it on."""
    v02 = apps(PREVIOUS)
    assert wait_for(lambda: "not connected to anyone" in v02.logs()), v02.logs()
    node_id = v02.exec("sha256sum", "/data/reticulum/storage/transport_identity").split()[0]
    v02.remove()
    assert "messaging_enabled" not in (v02.data / "options.json").read_text()

    app = apps(IMAGE, json.loads((v02.data / "options.json").read_text()), data=v02.data)
    assert wait_for(lambda: "not connected to anyone" in app.logs()), app.logs()
    assert "unchanged since last start" in app.logs() and "LXMF messaging: off" in app.logs()
    assert app.exec("sha256sum", "/data/reticulum/storage/transport_identity").split()[0] == node_id
    time.sleep(5)
    assert count_engines(app) == 0 and not (app.data / "messaging").exists()
    app.remove()

    on = apps(IMAGE, ON, data=v02.data)
    assert wait_for(lambda: engine_up(on), 90), on.logs()
    assert "meshbeacon-messaging: started (identity created)" in on.logs()
    assert on.exec("sha256sum", "/data/reticulum/storage/transport_identity").split()[0] == node_id


# -- WP4: the engine, switched on -------------------------------------------------------


def engine_up(app: App) -> bool:
    return "meshbeacon-messaging: started" in app.logs()


def count_engines(app: App) -> int:
    script = (
        "import os\n"
        "n = 0\n"
        "for p in filter(str.isdigit, os.listdir('/proc')):\n"
        "    try: a = open(f'/proc/{p}/cmdline','rb').read().split(b'\\0')\n"
        "    except OSError: continue\n"
        "    n += b'-m' in a and a[a.index(b'-m')+1] == b'meshbeacon.messaging'\n"
        "print(n)\n"
    )
    return int(app.exec("python3", "-I", "-c", script).strip())


def request(app: App, payload: dict) -> dict | None:
    """One contract request as the core's user (the only peer the engine serves)."""
    script = (
        "import json, socket, sys\n"
        "s = socket.socket(socket.AF_UNIX); s.settimeout(10)\n"
        "s.connect('/run/meshbeacon-messaging/engine.sock')\n"
        "s.sendall(sys.argv[1].encode() + b'\\n')\n"
        "print(s.makefile('rb').readline().decode())\n"
    )
    out = app.exec("python3", "-I", "-c", script, json.dumps(payload), user="meshbeacon", check=False).strip()
    return json.loads(out) if out else None


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


def test_the_engine_starts_after_reticulum_as_its_own_user(apps):
    app = apps(IMAGE, ON)
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
    # ADR 0023 (amends IS-3a): the node shares its instance with interface management off; the
    # engine holds the node's RPC key (the same one, compared without printing it) and no interfaces.
    node_config = app.exec("cat", "/data/reticulum/config")
    assert "share_instance = Yes" in node_config and "enable_interface_management = No" in node_config
    engine_config = app.exec("cat", "/data/messaging/rns/config")
    assert "share_instance = Yes" in engine_config and "[[" not in engine_config
    assert same_rpc_key(app)
    # MS-2: a separate identity from the transport identity.
    transport = app.exec("sha256sum", "/data/reticulum/storage/transport_identity").split()[0]
    messaging = app.exec("sha256sum", "/data/messaging/identity").split()[0]
    assert transport != messaging
    # Rule 5: no hash (identity, destination, message) reaches the log; the engine's output goes
    # through the core's redaction like Reticulum's.
    assert not re.search(r"(?<![0-9a-f])[0-9a-f]{32,}(?![0-9a-f])", app.logs(), re.I), app.logs()


def test_only_the_core_can_use_the_engine_socket(apps):
    """Peer checks both ways: the core reaches the engine's user only; nobody else is served."""
    app = apps(IMAGE, ON)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    core = status(app, "meshbeacon")
    assert core is not None and core["server_uid"] == 9102 and core["answer"]["ok"] is True, core
    assert core["answer"]["connected"] is True
    assert status(app, "mb-rns") == {"error": "PermissionError"}  # cannot even reach the folder
    refused = status(app, "root")  # root can connect, but the engine serves the core only
    assert refused is not None and refused.get("answer") is None, refused


def test_users_cannot_read_each_others_data(apps):
    app = apps(IMAGE, ON)
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


def test_killing_the_engine_restarts_only_the_engine(apps):
    """MS-15: Reticulum keeps running (same process) and the health endpoint never fails."""
    app = apps(IMAGE, ON)
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


def test_a_hung_engine_is_detected_and_restarted(apps):
    """MS-15: a stopped (hung) engine misses three health checks, is killed and started again."""
    app = apps(IMAGE, ON)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    node, engine = app.pid("meshbeacon.node"), app.pid("meshbeacon.messaging")
    app.exec("kill", "-STOP", str(engine))
    assert wait_for(lambda: "Messaging stopped responding" in app.logs(), 180), app.logs()
    assert wait_for(lambda: app.pid("meshbeacon.messaging") not in (None, engine), 60)
    assert app.pid("meshbeacon.node") == node and app.health()


def test_an_engine_that_cannot_start_never_affects_the_node(apps):
    """Both copies of the messaging identity damaged: the engine refuses to start (rule 13) and
    replaces nothing; the core backs off; Reticulum and the health endpoint carry on."""
    data = Path(tempfile.mkdtemp(prefix="mb-m4-", dir="/tmp"))
    (data / "messaging").mkdir()
    (data / "messaging" / "identity").write_bytes(b"damaged")
    (data / "messaging" / "identity.backup").write_bytes(b"damaged too")
    app = apps(IMAGE, ON, data=data)
    reason = "Messaging could not start: Reticulum was not reachable"  # the dashboard's plain words
    assert wait_for(lambda: app.logs().count(reason) >= 2, 120), app.logs()
    assert "Traceback" not in app.logs()
    assert "identity is damaged" in app.logs()
    node = app.pid("meshbeacon.node")
    time.sleep(5)
    assert app.pid("meshbeacon.node") == node and app.health()
    assert app.exec("cat", "/data/messaging/identity") == "damaged"  # kept for manual recovery


def test_the_engine_survives_a_reticulum_restart(apps):
    app = apps(IMAGE, ON)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    engine = app.pid("meshbeacon.messaging")
    app.exec("kill", "-9", str(app.pid("meshbeacon.node")))
    assert wait_for(lambda: "Restarting the Reticulum service" in app.logs(), 60), app.logs()
    assert wait_for(lambda: (s := status(app)) and s.get("answer", {}).get("connected") is True, 120)
    assert app.pid("meshbeacon.messaging") == engine  # the engine reconnected by itself


def test_stopping_the_app_leaves_messaging_data_intact(apps):
    """A container stop (s6 stops every service at once) exits cleanly, and the engine's data
    comes back as it was: the queue is not quarantined and the identity is unchanged."""
    app = apps(IMAGE, ON)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    identity = app.exec("sha256sum", "/data/messaging/identity").split()[0]
    assert app.exec("ls", "/data/messaging").split().count("queue.db") == 1
    sh("docker", "stop", "-t", "30", app.name, timeout=60)
    assert sh("docker", "inspect", "-f", "{{.State.ExitCode}}", app.name).strip() == "0"
    again = apps(IMAGE, ON, data=app.data)
    assert wait_for(lambda: engine_up(again), 90), again.logs()
    assert "meshbeacon-messaging: started (identity unchanged)" in again.logs()
    assert again.exec("sha256sum", "/data/messaging/identity").split()[0] == identity
    assert not [n for n in again.exec("ls", "/data/messaging").split() if ".corrupt-" in n]


def test_the_messaging_identity_is_independent_of_the_transport_identity(apps):
    """MS-2: replacing the transport identity leaves the messaging identity as it was."""
    app = apps(IMAGE, ON)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    transport = app.exec("sha256sum", "/data/reticulum/storage/transport_identity").split()[0]
    messaging = app.exec("sha256sum", "/data/messaging/identity").split()[0]
    app.remove()
    again = apps(IMAGE, {**ON, "replace_identity": True}, data=app.data)
    assert wait_for(lambda: engine_up(again), 90), again.logs()
    assert again.exec("sha256sum", "/data/reticulum/storage/transport_identity").split()[0] != transport
    assert again.exec("sha256sum", "/data/messaging/identity").split()[0] == messaging
    assert "meshbeacon-messaging: started (identity unchanged)" in again.logs()


def test_idle_memory_with_messaging_on(apps):
    """Q-40 / MS-18 (indicative only: MS-18 is decided on the Pi, D-M4-7)."""
    app = apps(IMAGE, ON)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    time.sleep(20)
    print(f"messaging on, idle RSS+swap (core + Reticulum + engine): {app_memory_kib(app) / 1024:.1f} MiB")  # type: ignore[arg-type]


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


def test_the_shared_instance_is_reachable_only_inside_the_app_container(apps):
    """IS-3a: the RNS 1.6.0 shared instance is an abstract Unix socket (``\\0rns/meshbeacon``,
    RNS/Reticulum.py lines 369 and 825-826), which lives in the container's own network namespace
    (the app has no host network). Another container cannot reach it; inside, it is there."""
    app = apps(IMAGE, ON)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    assert "@rns/meshbeacon" in app.exec("cat", "/proc/net/unix")
    inside = json.loads(app.exec("python3", "-I", "-c", ABSTRACT, "rns/meshbeacon", user="mb-lxmf"))
    assert inside == "connected"
    for network in ("none", "bridge"):
        outside = sh(
            "docker", "run", "--rm", "--network", network, "--entrypoint", "python3", IMAGE,
            "-I", "-c", ABSTRACT, "rns/meshbeacon",
        )  # fmt: skip
        assert json.loads(outside) in ("ConnectionRefusedError", "FileNotFoundError"), (network, outside)


# -- ADR 0023: the engine's authenticated RPC with the node's shared instance -------------------
#
# The 0.3.0 failure on the Raspberry Pi: the engine connected to the shared instance, but RNS 1.6.0
# authenticates every local RPC client with the node's ``rpc_key``, and the engine had none, so it
# derived a key of its own and every request was refused ("digest received was wrong" in the node,
# "digest sent was rejected" in the engine) while the dashboard showed "Running".

KEY_FILE = "/run/meshbeacon-rpc/rpc_key"
RPC_WITH_KEY = (
    "import json, multiprocessing.connection as mc, sys\n"
    "try:\n"
    "    key = bytes.fromhex(open(sys.argv[1]).read().strip()) if sys.argv[1] else b'0' * 32\n"
    "except OSError as e:\n"
    "    print(json.dumps(type(e).__name__)); sys.exit()\n"
    "try:\n"
    "    mc.Client('\\0rns/meshbeacon/rpc', family='AF_UNIX', authkey=key).close()\n"
    "    print(json.dumps('authenticated'))\n"
    "except Exception as e:\n"
    "    print(json.dumps(type(e).__name__))\n"
)
RPC_FAILURES = ("digest received was wrong", "digest sent was rejected", "Shared instance RPC failed")
SAME_KEY = (
    "import sys\n"
    "def key(path):\n"
    "    for line in open(path):\n"
    "        k, _, v = line.partition('=')\n"
    "        if k.strip() == 'rpc_key': return v.strip()\n"
    "shared = open(sys.argv[1]).read().strip()\n"
    "print(key('/data/reticulum/config') == key('/data/messaging/rns/config') == shared)\n"
)


def same_rpc_key(app: App) -> bool:
    """The node, the engine and the shared key file hold the same key (compared, never printed)."""
    return app.exec("python3", "-I", "-c", SAME_KEY, KEY_FILE).strip() == "True"


def engine_status(app: App) -> dict:
    answer = request(app, {"op": "status"})
    return answer if isinstance(answer, dict) else {}


def rpc_failures(logs: str) -> list[str]:
    return [line for line in logs.splitlines() if any(f in line for f in RPC_FAILURES)]


def with_api(apps: Callable[..., App], options: dict, tmp: Path, extra: tuple[str, ...] = ()) -> tuple[App, str]:
    """The app with its Home Assistant status API on, announced to a fake Supervisor through a
    local socket (as on newer Supervisors; no network). Returns the app and the API token."""
    out = tmp / "supervisor"
    out.mkdir()
    out.chmod(0o777)
    api = Path(f"/tmp/mbsock-{uuid.uuid4().hex[:6]}")
    api.mkdir(mode=0o755)
    bind = "/run/os/supervisor/apps/ce27fbb5_meshbeacon"
    sup = f"mbsup-{uuid.uuid4().hex[:6]}"
    sh(
        "docker", "run", "-d", "--name", sup, "--network", "none",
        "-v", f"{REPO / 'tests' / 'container' / 'fake_supervisor.py'}:/fake.py:ro", "-v", f"{out}:/out",
        "-v", f"{api}:{bind}", "--entrypoint", "python3", IMAGE, "-I", "/fake.py", "--unix", f"{bind}/supervisor.sock",
    )  # fmt: skip
    fake_supervisors.append(sup)
    assert wait_for((api / "supervisor.sock").exists, 30)
    app = apps(
        IMAGE,
        {**options, "home_assistant_integration": True},
        extra=(
            "-e", "SUPERVISOR_SOCKET=/run/supervisor/api/supervisor.sock", "-v", f"{api}:/run/supervisor/api:ro",
            "--hostname", "ce27fbb5-meshbeacon", *extra,
        ),
    )  # fmt: skip
    record = out / "discovery.json"
    assert wait_for(lambda: record.exists() and record.read_text().endswith("}"), 90), app.logs()
    return app, json.loads(record.read_text())["body"]["config"]["token"]


fake_supervisors: list[str] = []  # fake Supervisor containers, removed after each test


@pytest.fixture(autouse=True)
def _remove_fake_supervisors() -> Iterator[None]:
    yield
    while fake_supervisors:
        sh("docker", "rm", "-f", fake_supervisors.pop(), check=False)


API = (
    "import http.client, json, ssl, sys\n"
    "c = ssl.create_default_context(); c.check_hostname = False; c.verify_mode = ssl.CERT_NONE\n"
    "h = http.client.HTTPSConnection('127.0.0.1', 8100, timeout=10, context=c)\n"
    "h.request('GET', '/api/v1/status', headers={'Authorization': 'Bearer ' + sys.argv[1]})\n"
    "print(json.dumps(json.loads(h.getresponse().read()).get('messaging')))\n"
)


MESSAGES = (
    "import http.client, json, ssl, sys\n"
    "c = ssl.create_default_context(); c.check_hostname = False; c.verify_mode = ssl.CERT_NONE\n"
    "h = http.client.HTTPSConnection('127.0.0.1', 8100, timeout=15, context=c)\n"
    "h.request('POST', '/api/v1/messaging', body=sys.argv[2], headers={'Authorization': 'Bearer ' + sys.argv[1]})\n"
    "r = h.getresponse(); print(json.dumps({'status': r.status, 'body': json.loads(r.read() or b'null')}))\n"
)


def messages(app: App, key: str, request: dict) -> dict:
    """One request to the messaging endpoint (M5, ADR 0024), as Home Assistant makes it."""
    out = app.exec("python3", "-I", "-c", MESSAGES, key, json.dumps(request), check=False).strip()
    try:
        return json.loads(out.splitlines()[-1])
    except (ValueError, IndexError):
        return {}


def dashboard(app: App, token: str) -> dict:
    """The ``messaging`` section of the status API: what the integration and its panel show."""
    out = app.exec("python3", "-I", "-c", API, token, check=False).strip()
    try:
        value = json.loads(out.splitlines()[-1])
    except (ValueError, IndexError):
        return {}
    return value if isinstance(value, dict) else {}


def test_only_reticulum_and_the_engine_hold_the_shared_rpc_key(apps):
    """ADR 0023: the key is root's file, readable by the group mb-rpc (Reticulum's and the engine's
    users) only. With it the node's RPC listener authenticates; without it, it refuses."""
    app = apps(IMAGE, ON)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    assert "@rns/meshbeacon/rpc" in app.exec("cat", "/proc/net/unix")
    assert app.exec("stat", "-c", "%U:%G %a", "/run/meshbeacon-rpc").split() == ["root:mb-rpc", "750"]
    assert app.exec("stat", "-c", "%U:%G %a", KEY_FILE).split() == ["root:mb-rpc", "640"]
    for user in ("mb-lxmf", "mb-rns"):
        assert json.loads(app.exec("python3", "-I", "-c", RPC_WITH_KEY, KEY_FILE, user=user)) == "authenticated", user
        assert not app.ok("sh", "-c", f"echo x >> {KEY_FILE}", user=user), user  # read only
    # The core may not use it: it cannot read it, and a guessed key is refused.
    assert json.loads(app.exec("python3", "-I", "-c", RPC_WITH_KEY, KEY_FILE, user="meshbeacon")) == "PermissionError"
    for user in ("mb-lxmf", "meshbeacon"):
        assert json.loads(app.exec("python3", "-I", "-c", RPC_WITH_KEY, "", user=user)) == "AuthenticationError", user
    # Reticulum's private files stay its own (the key gives the engine no access to them).
    for path in ("/data/reticulum/config", "/data/reticulum/storage/transport_identity", "/data/reticulum/storage"):
        assert not app.ok("cat", path, user="mb-lxmf") and not app.ok("ls", path, user="mb-lxmf"), path
    assert same_rpc_key(app)
    # The key survives a restart of Reticulum (the prepare step reuses it), so a running engine is
    # never locked out by the node's restart policy.
    app.exec("kill", "-9", str(app.pid("meshbeacon.node")))
    assert wait_for(lambda: "Restarting the Reticulum service" in app.logs(), 60), app.logs()
    assert wait_for(lambda: app.pid("meshbeacon.node") is not None, 120)
    assert same_rpc_key(app)
    assert wait_for(lambda: engine_status(app).get("rpc") is True, 120), app.logs()


def test_messaging_talks_lxmf_over_the_shared_instance_with_authenticated_rpc(apps, tmp_path):
    """The real users, the real RNS 1.6.0 shared instance and the LXMF engine: the engine creates
    its LXMF delivery destination and announces it; a second local client of the same shared
    instance (a reference LXMF peer, inside the container) sends it a message and gets the core's
    automatic reply, signed by the engine. Throughout, the node accepts every RPC request of the
    engine, and the dashboard shows Running."""
    peer_dir = tmp_path / "peer"
    peer_dir.mkdir()
    script = REPO / "tests" / "container" / "lxmf_peer.py"
    sh(
        "docker", "run", "--rm", "--network", "none", "-v", f"{peer_dir}:/peer", "-v", f"{script}:/lxmf_peer.py:ro",
        "--entrypoint", "python3", IMAGE, "-I", "/lxmf_peer.py", "identity", "/peer",
    )  # fmt: skip
    peer_address = (peer_dir / "address").read_text().strip()
    options = {**ON, "messaging_contacts": [{"name": "Peer", "address": peer_address}], "messaging_auto_reply": True}
    app, token = with_api(apps, options, tmp_path)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    assert wait_for(lambda: "Reticulum accepts the engine's requests" in app.logs(), 60), app.logs()
    status = engine_status(app)
    assert status.get("connected") is True and status.get("rpc") is True, status
    engine_address = status["address"]
    assert re.fullmatch(r"[0-9a-f]{32}", engine_address) and engine_address != peer_address  # LXMF destination
    assert wait_for(lambda: dashboard(app, token).get("state") == "running", 60), dashboard(app, token)

    app.exec("mkdir", "-p", "/tmp/peer")
    sh("docker", "cp", str(script), f"{app.name}:/tmp/lxmf_peer.py")
    sh("docker", "cp", str(peer_dir / "identity"), f"{app.name}:/tmp/peer/identity")
    talk = 90 * SCALE
    out = app.exec(
        "python3", "-I", "/tmp/lxmf_peer.py", "talk", "/tmp/peer", engine_address, KEY_FILE, str(talk), check=False
    )
    lines = [line for line in out.splitlines() if line.startswith("{")]
    assert lines, out
    seen = json.loads(lines[-1])
    assert seen["engine_heard"] is True, seen  # the engine's announce reached the other client
    assert seen["delivered"] is True, seen  # a delivery proof from the engine's LXMF
    assert seen["reply"] is True and seen["reply_verified"] is True, seen  # the engine sent, signed
    assert seen["peer_rpc"] is True, seen
    # The engine knows its contact (Identity.recall reports each use to the node over RPC: the
    # request that failed every 10 s in 0.3.0), counted the message and saw the reply delivered.
    assert wait_for(lambda: dashboard(app, token).get("contacts_reachable") == 1, 60), dashboard(app, token)
    assert wait_for(lambda: dashboard(app, token).get("received") == 1, 60), dashboard(app, token)
    assert wait_for(lambda: dashboard(app, token).get("last_reply_state") == "delivered", 60), dashboard(app, token)
    time.sleep(25 * SCALE)  # several of the core's 10 s polls, each of which recalls the contact
    final = dashboard(app, token)
    assert final.get("state") == "running" and final.get("message") is None, final
    assert engine_status(app).get("rpc") is True
    logs = app.logs()
    assert rpc_failures(logs) == [], rpc_failures(logs)
    assert "Traceback" not in logs
    assert not re.search(r"(?<![0-9a-f])[0-9a-f]{32,}(?![0-9a-f])", logs, re.I)  # rule 5
    # Only the known RNS 1.6.0 limitation is left (ADR 0023): a client reads the shared instance's
    # destination table from its *own* configuration folder, which the engine's user cannot share
    # with Reticulum's without reaching into Reticulum's private storage. Once per engine start.
    assert logs.count("Could not load known destinations from shared instance database") == 1
    # M5 (ADR 0024): the same conversation through the Home Assistant endpoint, with the separate
    # messaging key from the discovery message; the status key is refused there.
    config = json.loads((tmp_path / "supervisor" / "discovery.json").read_text())["body"]["config"]
    key = config["messaging_key"]
    assert key != token
    assert messages(app, token, {"op": "conversations"})["status"] == 401
    listed = messages(app, key, {"op": "conversations"})
    assert listed["status"] == 200, listed
    [peer] = [c for c in listed["body"]["conversations"] if c["name"] == "Peer"]
    assert peer["address"] == peer_address and peer["origin"] == "configuration"
    history = messages(app, key, {"op": "history", "contact": peer["id"]})["body"]["messages"]
    assert [m["direction"] for m in history] == ["in", "out"] and history[1]["auto"] is True
    assert history[1]["state"] == "delivered"
    assert messages(app, key, {"op": "inbound", "cursor": 0})["status"] == 400  # the core's own operation
    assert not re.search(r"(?<![0-9a-f])[0-9a-f]{32,}(?![0-9a-f])", app.logs(), re.I)  # rule 5


def test_an_engine_that_reticulum_refuses_shows_a_problem_not_running(apps, tmp_path):
    """Reproduces 0.3.0: the engine runs and is connected, but holds no valid key. The node refuses
    its RPC requests with RNS's own errors, the engine says so in plain words, the dashboard shows
    a problem instead of Running, and the gateway carries on unaffected."""
    app, token = with_api(apps, ON, tmp_path)
    assert wait_for(lambda: engine_up(app), 90), app.logs()
    assert wait_for(lambda: dashboard(app, token).get("state") == "running", 60), dashboard(app, token)
    node = app.pid("meshbeacon.node")
    # As in 0.3.0: the engine starts without the node's key.
    app.exec("rm", "-f", KEY_FILE)
    engine = app.pid("meshbeacon.messaging")
    app.exec("kill", "-9", str(engine))
    assert wait_for(lambda: app.pid("meshbeacon.messaging") not in (None, engine), 90), app.logs()
    assert wait_for(lambda: engine_status(app).get("rpc") is False, 90), app.logs()
    logs = app.logs()
    assert "access key is missing or invalid" in logs
    assert "Reticulum refused the engine's requests (its shared-instance authentication was refused)" in logs
    assert "digest received was wrong" in logs  # the node's side of the 0.3.0 error
    status = engine_status(app)
    assert status.get("connected") is True and status.get("rpc") is False, status  # connected, yet refused
    # (The kill itself is reported first, as "stopped unexpectedly"; then the relaunched engine.)
    refused = lambda: (d := dashboard(app, token)).get("state") == "error" and "refuses its requests" in d["message"]  # noqa: E731
    assert wait_for(refused, 60), dashboard(app, token)
    # The gateway is not affected: same Reticulum process, healthy app.
    assert app.pid("meshbeacon.node") == node and app.health()


# -- 0.3.1: an existing 0.3.0 installation, upgraded ---------------------------------------------


def identities(app: App) -> tuple[str, str]:
    """Digests of both identity files (compared, never printed in full)."""
    out = app.exec("sha256sum", "/data/reticulum/storage/transport_identity", "/data/messaging/identity")
    node, messaging = (line.split()[0] for line in out.splitlines())
    return node, messaging


@needs_previous_messaging
def test_an_upgraded_0_3_0_installation_authenticates_and_keeps_both_identities(apps):
    """The Pi's path: 0.3.0 with messaging on (identity created, the node's old random key in
    /data/reticulum/config, the engine's keyless client configuration in /data/messaging/rns),
    then this version on the same data. Both configurations are rewritten with the shared key, the
    node accepts the engine, and neither identity is touched."""
    old_options = {k: v for k, v in ON.items() if k != "network"}  # 0.3.0 predates the option
    old = apps(PREVIOUS_MESSAGING, old_options)
    assert wait_for(lambda: engine_up(old), 90), old.logs()
    before = identities(old)
    assert "rpc_key" not in old.exec("cat", "/data/messaging/rns/config")  # 0.3.0: no key
    sh("docker", "stop", "-t", "30", old.name, timeout=60)
    old.remove()

    new = apps(IMAGE, ON, data=old.data)  # the Supervisor adds new options' defaults on update
    assert wait_for(lambda: "Reticulum accepts the engine's requests" in new.logs(), 120), new.logs()
    assert "meshbeacon-messaging: started (identity unchanged)" in new.logs()
    assert identities(new) == before
    assert same_rpc_key(new)
    assert engine_status(new).get("rpc") is True and engine_status(new).get("rpc_key") is True
    time.sleep(25 * SCALE)  # several of the core's 10 s polls
    assert rpc_failures(new.logs()) == [], rpc_failures(new.logs())


def test_a_key_the_init_step_cannot_create_is_reported_with_what_to_do(apps, tmp_path):
    """0.3.1: on Home Assistant OS a Rebuild keeps the previous AppArmor profile, which does not let
    root's init step write /run/meshbeacon-rpc. Simulated here with a read-only folder (the same
    effect: the write fails). The gateway runs; the dashboard says to update, not to restart."""
    empty = tmp_path / "no-write"
    empty.mkdir()
    app, token = with_api(apps, ON, tmp_path, extra=("-v", f"{empty}:/run/meshbeacon-rpc:ro"))
    assert wait_for(lambda: engine_status(app).get("rpc") is False, 120), app.logs()
    logs = app.logs()
    assert "the app's security profile may be out of date" in logs and "Rebuild is not enough" in logs
    assert "digest received was wrong" in logs  # what the Pi showed
    status = engine_status(app)
    assert status.get("rpc_key") is False and status.get("connected") is True, status
    missing = lambda: "update the app" in (dashboard(app, token).get("message") or "")  # noqa: E731
    assert wait_for(missing, 60), dashboard(app, token)
    assert dashboard(app, token)["state"] == "error" and app.health()
