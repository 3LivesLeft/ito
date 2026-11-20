# SPDX-License-Identifier: Apache-2.0
"""Static checks of meshbeacon/apparmor.txt (no AppArmor kernel needed)."""

from pathlib import Path

from tests.apparmor.rules import Profile, glob_to_regex, load

ROOT = Path(__file__).resolve().parents[2]
PROFILE = load(ROOT / "meshbeacon" / "apparmor.txt")

# Programs started during initialisation and at run time. Scripts need read AND execute.
SCRIPTS = [
    "/init",  # s6-overlay 3.x: '#!/bin/sh -e' (verified in 3.2.3.2)
    "/package/admin/s6-overlay-3.2.3.2/libexec/preinit",
    "/package/admin/s6-overlay-3.2.3.2/libexec/stage0",
    "/package/admin/s6-overlay-3.2.3.2/libexec/logutil-service-main",
    "/etc/cont-init.d/10-meshbeacon",
    "/etc/services.d/meshbeacon/run",
    "/etc/services.d/meshbeacon/finish",
]
BINARIES = ["/bin/sh", "/bin/busybox", "/command/s6-setuidgid", "/usr/local/bin/python3", "/usr/local/bin/python3.13"]


def test_glob_translation():
    assert glob_to_regex("/a/**").match("/a/b/c")
    assert not glob_to_regex("/a/*").match("/a/b/c")
    assert glob_to_regex("/run/{s6,service}/**").match("/run/service/x/run")
    assert glob_to_regex("@{PROC}/@{pid}/status").match("/proc/123/status")


def test_profile_name_is_the_slug():
    assert PROFILE.name == "meshbeacon"


def test_scripts_are_readable_and_executable():
    for path in SCRIPTS:
        assert PROFILE.can_exec(path), f"{path} is not executable under the profile"
        assert PROFILE.can_read(path), f"{path} is a script but cannot be read by its interpreter"


def test_binaries_are_executable():
    for path in BINARIES:
        assert PROFILE.can_exec(path), path


def test_writes_are_limited():
    for path in ("/data/meshbeacon/x", "/data/reticulum/storage/x", "/run/s6/x", "/tmp/x"):
        assert "w" in PROFILE.perms(path), path
    for path in ("/usr/local/lib/python3.13/site-packages/meshbeacon/node.py", "/etc/passwd", "/init", "/bin/sh"):
        assert "w" not in PROFILE.perms(path), path


# s6-overlay 3.2.3.2's run-time paths (libexec/preinit, s6-linux-init's container skeleton, s6-rc).
S6_RUN_PATHS = [
    "/run/test of writability",
    "/run/s6/container_environment/SUPERVISOR_TOKEN",
    "/run/s6/basedir/bin/halt",
    "/run/s6/db/servicedirs/x",
    "/run/",  # s6-linux-init's chmod and chown of /run itself (CI enforcement, M1.2)
    "/run/s6-rc",
    "/run/s6-rc:s6-rc-init:BJBmMn/",  # s6-rc-init's live folder, created with a trailing slash
    "/run/s6-rc:s6-rc-init:AbCd/servicedirs/meshbeacon/supervise/status",
    "/run/service/meshbeacon/supervise/control",
    "/run/service/.s6-svscan/control",
    "/run/uncaught-logs/current",
    "/run/s6-linux-init-container-results/exitcode",
]


def test_run_is_writable_only_where_s6_overlay_keeps_its_state():
    """M1.2 (M-3): /run is no longer writable as a whole."""
    for path in S6_RUN_PATHS:
        assert "w" in PROFILE.perms(path), path
    for path in ("/run/x", "/run/evil/discovery.sock", "/run/meshbeacon-other/x", "/run/supervisor/api/x"):
        assert "w" not in PROFILE.perms(path), path
    assert "r" in PROFILE.perms("/run/")
    assert "x" not in PROFILE.perms("/run/x") and "k" not in PROFILE.perms("/run/x")


def test_the_relay_folder_is_for_its_owner_only():
    """M1.2 (M-1, M-3): an owner rule, so a process of another user (Reticulum) is refused even if
    the folder's mode were wrong; the relay (root, the owner) keeps full use of it."""
    for path in ("/run/meshbeacon/", "/run/meshbeacon/discovery.sock"):
        assert "w" in PROFILE.perms(path, owner=True), path
        assert not PROFILE.perms(path, owner=False) & {"w", "k"}, path
    sock = "/run/os/supervisor/apps/ce27fbb5_meshbeacon/supervisor.sock"
    assert "w" in PROFILE.perms(sock, owner=True) and "w" not in PROFILE.perms(sock, owner=False)


def test_no_write_and_execute_on_app_data():
    for path in ("/data/meshbeacon/x", "/data/reticulum/storage/x", "/tmp/x"):
        assert "x" not in PROFILE.perms(path), path


def test_parser_reads_old_failing_profile_as_failing():
    """Regression: the profile at commit 75060e3 granted '/init ix' without read."""
    old = Profile.parse("profile meshbeacon {\n  /init ix,\n  /package/** ix,\n}\n")
    assert old.can_exec("/init") and not old.can_read("/init")


def test_capabilities_are_exactly_the_reviewed_set():
    """Any new capability needs review (CLAUDE.md rule 4); fsetid is denied explicitly so that the
    init step's chmod does not log a denial on every start (seen under enforcement in CI)."""
    import re

    text = (Path(__file__).resolve().parents[2] / "meshbeacon" / "apparmor.txt").read_text()
    rules = [line.split("#", 1)[0].strip() for line in text.splitlines()]
    granted = {m.group(1) for r in rules if (m := re.fullmatch(r"capability (\w+),", r))}
    denied = {m.group(1) for r in rules if (m := re.fullmatch(r"deny capability (\w+),", r))}
    assert granted == {"chown", "fowner", "dac_override", "setuid", "setgid", "kill"}
    assert denied == {"fsetid"}
    assert not any(re.fullmatch(r"capability,", r) for r in rules), "blanket capability rule"


def test_supervisor_socket_and_relay_rules():
    """M1: the relay listens in /run/meshbeacon and connects to the Supervisor's per-app socket
    (mounted at /run/supervisor/api). The relay's script must be runnable like the core's."""
    for path in ("/run/meshbeacon/discovery.sock", "/run/supervisor/api/supervisor.sock"):
        assert "w" in PROFILE.perms(path), path  # as their owner (root), see the test above
        assert "x" not in PROFILE.perms(path), path
    assert "network unix," in (ROOT / "meshbeacon" / "apparmor.txt").read_text()
    # AppArmor checks the name the Supervisor bound the socket to, inside its own container.
    assert "w" in PROFILE.perms("/run/os/supervisor/apps/ce27fbb5_meshbeacon/supervisor.sock")
    for script in ("/etc/services.d/discovery-relay/run", "/etc/services.d/discovery-relay/finish"):
        assert PROFILE.can_exec(script) and PROFILE.can_read(script), script
