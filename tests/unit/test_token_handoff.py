# SPDX-License-Identifier: Apache-2.0
"""The Supervisor token on the compatibility path (M1.2 re-review, threat T72).

The root start step (relay_link.py) passes the token through a one-time pipe, never through a
process environment, and the core marks itself non-dumpable before it reads it, so that another
process of the same user (the Reticulum child) cannot recover it through /proc or ptrace. These
tests use real processes; the container tests repeat them with the real users and AppArmor.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from meshbeacon import relay_link as link_mod
from meshbeacon.supervisor import discovery_transport, read_token_fd

TOKEN = "s" * 24 + "0123456789abcdef" * 4
CAP_SYS_PTRACE = 19


def has_cap_sys_ptrace() -> bool:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("CapEff:"):
            return bool(int(line.split()[1], 16) >> CAP_SYS_PTRACE & 1)
    return False


def _capture_exec(monkeypatch):
    calls: list[tuple[str, list[str], dict[str, str]]] = []
    monkeypatch.setattr(link_mod.os, "execve", lambda path, argv, env: calls.append((path, argv, env)))
    return calls


# -- the root start step ----------------------------------------------------------------------------


def test_the_token_goes_through_a_one_time_pipe_not_the_environment(monkeypatch, tmp_path):
    token_file = tmp_path / "SUPERVISOR_TOKEN"
    token_file.write_text(TOKEN)
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    calls = _capture_exec(monkeypatch)
    link_mod.main(["--token-file", str(token_file), "--", "/command/s6-setuidgid", "meshbeacon", "python3"])
    [(_path, argv, env)] = calls
    assert argv == ["/command/s6-setuidgid", "meshbeacon", "python3"]
    assert TOKEN not in "".join(f"{k}={v}" for k, v in env.items())  # in no environment
    assert "SUPERVISOR_TOKEN" not in env
    fd = int(env[link_mod.TOKEN_FD_ENV])
    assert fd >= 3 and os.get_inheritable(fd) and stat.S_ISFIFO(os.fstat(fd).st_mode)
    assert os.read(fd, 4096) == TOKEN.encode()
    assert os.read(fd, 4096) == b""  # the write end is already closed: one-time
    os.close(fd)


def test_a_token_in_the_start_steps_environment_is_moved_into_the_pipe(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPERVISOR_TOKEN", TOKEN)
    calls = _capture_exec(monkeypatch)
    link_mod.main(["--token-file", str(tmp_path / "missing"), "--", "/bin/true"])
    env = calls[0][2]
    assert "SUPERVISOR_TOKEN" not in env
    fd = int(env[link_mod.TOKEN_FD_ENV])
    assert os.read(fd, 4096) == TOKEN.encode()
    os.close(fd)


def test_socket_mode_passes_no_token_at_all(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPERVISOR_TOKEN", TOKEN)
    monkeypatch.setattr(link_mod, "WAIT", 0.1)
    calls = _capture_exec(monkeypatch)
    link_mod.main(["--relay", str(tmp_path / "none.sock"), "--", "/bin/true"])
    env = calls[0][2]
    assert "SUPERVISOR_TOKEN" not in env and link_mod.TOKEN_FD_ENV not in env


@pytest.mark.parametrize("content", ["", "short", "has whitespace inside it ok", "x" * 5000, "ünïcode-token-value-xx"])
def test_a_malformed_token_is_not_passed(monkeypatch, tmp_path, capsys, content):
    token_file = tmp_path / "SUPERVISOR_TOKEN"
    token_file.write_text(content)
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    calls = _capture_exec(monkeypatch)
    link_mod.main(["--token-file", str(token_file), "--", "/bin/true"])
    assert link_mod.TOKEN_FD_ENV not in calls[0][2]
    assert "could not be read" in capsys.readouterr().out


def test_without_a_supervisor_there_is_nothing_to_pass(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    calls = _capture_exec(monkeypatch)
    link_mod.main(["--token-file", str(tmp_path / "missing"), "--", "/bin/true"])
    assert link_mod.TOKEN_FD_ENV not in calls[0][2]
    assert capsys.readouterr().out == ""  # not an error outside the Supervisor


# -- the core ---------------------------------------------------------------------------------------


def test_the_core_reads_the_pipe_once_and_closes_it():
    fd = link_mod.token_pipe(TOKEN.encode())
    env = {link_mod.TOKEN_FD_ENV: str(fd)}
    assert discovery_transport(env) == (TOKEN, None, False)
    with pytest.raises(OSError):
        os.fstat(fd)


def test_the_core_refuses_anything_but_a_pipe_and_closes_it(tmp_path):
    path = tmp_path / "f"
    path.write_text(TOKEN)
    fd = os.open(path, os.O_RDONLY)
    assert read_token_fd(fd) is None  # a regular file
    with pytest.raises(OSError):
        os.fstat(fd)
    bad = link_mod.token_pipe(b"not a token")
    assert read_token_fd(bad) is None
    assert read_token_fd(987654) is None


def test_the_core_never_waits_on_a_pipe_that_is_still_open():
    read_end, write_end = os.pipe()
    started = time.monotonic()
    assert read_token_fd(read_end) is None
    assert time.monotonic() - started < 1
    os.close(write_end)


# -- non-dumpable: what another process of the same user can see -----------------------------------
#
# The threat is the Reticulum child: an ordinary, unprivileged user with no capabilities. Root is
# not the threat (it already controls the container), and root keeps some /proc read access to a
# non-dumpable process even without CAP_SYS_PTRACE, so when these tests run as root (as in CI's test
# container) both processes are run as an unprivileged user instead.

NOBODY = 65534
# Both helper scripts use only the standard library: the real interpreter, which an unprivileged user
# can always run (a virtual environment may sit in a folder only its owner can enter).
PYTHON = os.path.realpath(sys.executable)

PROTECTED = """
import os, sys, time
sys.path.insert(0, sys.argv[1])
from meshbeacon import procinfo
ok = procinfo.set_not_dumpable()
child = os.fork()
if child == 0:
    os.execv('/bin/sleep', ['sleep', '30'])  # a child, as Reticulum is: dumpable again after exec
print(ok, child, flush=True)
time.sleep(30)
"""

READER = """
import json, os, sys
pid, child = sys.argv[1], sys.argv[2]
def can(action):
    try:
        action()
    except OSError:
        return False
    return True
print(json.dumps({
    "environ": can(lambda: open(f"/proc/{pid}/environ", "rb").read(1)),
    "maps": can(lambda: open(f"/proc/{pid}/maps", "rb").read(1)),
    "mem": can(lambda: open(f"/proc/{pid}/mem", "rb").read(1)),
    "fd": can(lambda: os.listdir(f"/proc/{pid}/fd")),
    "child_environ": b"canary-value" in open(f"/proc/{child}/environ", "rb").read(),
    "status": can(lambda: open(f"/proc/{pid}/status").read()),
}))
"""


def _as_user() -> dict[str, int]:
    return {"user": NOBODY, "group": NOBODY, "extra_groups": []} if os.geteuid() == 0 else {}


@pytest.mark.skipif(os.geteuid() != 0 and has_cap_sys_ptrace(), reason="CAP_SYS_PTRACE overrides the protection")
def test_an_unprivileged_same_user_process_cannot_read_the_cores_proc_entries():
    # A copy of procinfo.py that the unprivileged user can read (neither the checkout nor pytest's
    # own temporary folder, which is 0700, need be).
    tmp_path = Path(tempfile.mkdtemp(prefix="mb-dumpable-", dir="/tmp"))
    package = tmp_path / "core" / "meshbeacon"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    source = Path(__file__).resolve().parents[2] / "meshbeacon" / "core" / "meshbeacon" / "procinfo.py"
    (package / "procinfo.py").write_text(source.read_text())
    for path in (tmp_path, tmp_path / "core", package, *package.iterdir()):
        path.chmod(0o755 if path.is_dir() else 0o644)
    proc = subprocess.Popen(
        [PYTHON, "-I", "-c", PROTECTED, str(tmp_path / "core")],
        stdout=subprocess.PIPE,
        text=True,
        env={"SECRET_IN_ENV": "canary-value"},
        **_as_user(),
    )
    assert proc.stdout is not None
    try:
        ok, child = proc.stdout.readline().split()
        assert ok == "True"
        for _ in range(100):  # wait until the child has executed its program (cmdline is world-readable)
            if Path(f"/proc/{child}/cmdline").read_bytes().startswith(b"sleep"):
                break
            time.sleep(0.02)
        out = subprocess.run(
            [PYTHON, "-I", "-c", READER, str(proc.pid), child],
            capture_output=True,
            text=True,
            check=True,
            **_as_user(),
        )
        seen = json.loads(out.stdout)
        # The core's memory, environment, memory map and descriptors: all refused.
        assert seen == {
            "environ": False,
            "maps": False,
            "mem": False,
            "fd": False,
            "child_environ": True,  # its own child (as Reticulum) is readable: monitoring still works
            "status": True,  # /proc/<pid>/status stays readable: memory readings still work
        }, seen
    finally:
        with contextlib.suppress(ProcessLookupError, ValueError, NameError):
            os.kill(int(child), 15)
        proc.kill()
        proc.wait()
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_set_not_dumpable_takes_effect():
    out = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); from meshbeacon import procinfo; "
            "print(procinfo.set_not_dumpable())",
            str(Path(__file__).resolve().parents[2] / "meshbeacon" / "core"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "True"
