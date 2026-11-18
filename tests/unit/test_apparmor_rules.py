# SPDX-License-Identifier: Apache-2.0
"""Static checks of meshbeacon/apparmor.txt (no AppArmor kernel needed)."""

from pathlib import Path

from tests.apparmor.rules import Profile, glob_to_regex, load

PROFILE = load(Path(__file__).resolve().parents[2] / "meshbeacon" / "apparmor.txt")

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


def test_no_write_and_execute_on_app_data():
    for path in ("/data/meshbeacon/x", "/data/reticulum/storage/x", "/tmp/x"):
        assert "x" not in PROFILE.perms(path), path


def test_parser_reads_old_failing_profile_as_failing():
    """Regression: the profile at commit 75060e3 granted '/init ix' without read."""
    old = Profile.parse("profile meshbeacon {\n  /init ix,\n  /package/** ix,\n}\n")
    assert old.can_exec("/init") and not old.can_read("/init")
