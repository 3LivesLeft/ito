# SPDX-License-Identifier: Apache-2.0
"""The M4 Raspberry Pi acceptance tools (docs/testing/m4-pi-acceptance.md): the test-app generator
never produces anything that could replace or update the installed app, changes only what it says
it changes, and the summary computes MS-1 and MS-18 as documented."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "acceptance"))
import pi_summary  # noqa: E402 - after the path is set
import pi_test_apps  # noqa: E402
import stamp_benchmark  # noqa: E402

SOURCE = ROOT / "meshbeacon"


def files(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in folder.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


@pytest.fixture
def made(tmp_path: Path) -> Path:
    out = tmp_path / "apps"
    pi_test_apps.build(SOURCE, out / "meshbeacon_m4p", "meshbeacon_m4p", dev=False)
    pi_test_apps.build(SOURCE, out / "meshbeacon_m4d", "meshbeacon_m4d", dev=True)
    pi_test_apps.build(SOURCE, out / "meshbeacon_v02", "meshbeacon_v02", dev=False)
    return out


def test_every_test_app_has_its_own_slug_and_never_starts_by_itself(made: Path) -> None:
    source = yaml.safe_load((SOURCE / "config.yaml").read_text())
    for name in ("meshbeacon_v02", "meshbeacon_m4p", "meshbeacon_m4d"):
        config = yaml.safe_load((made / name / "config.yaml").read_text())
        assert config["slug"] == name != source["slug"]
        assert config["boot"] == "manual"
        assert "test" in config["name"].lower() and "uninstall" in config["description"]
        for key in set(source) - pi_test_apps.CHANGED_KEYS:
            assert config[key] == source[key], key  # options, schema, permissions: unchanged


def test_only_the_documented_files_change(made: Path) -> None:
    original = files(SOURCE)
    production = files(made / "meshbeacon_m4p")
    dev = files(made / "meshbeacon_m4d")
    assert set(production) == set(dev) == set(original)
    assert {k for k in original if original[k] != production[k]} == {"config.yaml"}
    assert {k for k in original if original[k] != dev[k]} == {"config.yaml", "Dockerfile", "apparmor.txt"}


def test_the_dev_app_builds_the_messaging_dev_stage_with_cis_profile(made: Path) -> None:
    dockerfile = (made / "meshbeacon_m4d" / "Dockerfile").read_text()
    stages = [line for line in dockerfile.splitlines() if line.startswith("FROM ")]
    assert stages[-1] == "FROM app AS messaging-dev"
    assert "AS production" not in dockerfile
    assert (SOURCE / "Dockerfile").read_text().rstrip().endswith("FROM app AS production")
    profile = (made / "meshbeacon_m4d" / "apparmor.txt").read_text().splitlines()
    original = (SOURCE / "apparmor.txt").read_text().splitlines()
    added = [line for line in profile if line not in original]
    assert added == [pi_test_apps.DEV_RULE]  # exactly the one rule CI's dev profile adds
    workflow = (ROOT / ".github" / "workflows" / "ci.yaml").read_text()
    assert "/run/meshbeacon-messaging/{,**} rw," in workflow
    assert pi_test_apps.DEV_RULE not in original  # the production profile stays as it is


def test_the_generator_refuses_unexpected_sources(tmp_path: Path) -> None:
    source = tmp_path / "src"
    shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns("__pycache__"))
    config = source / "config.yaml"
    config.write_text(config.read_text().replace("slug: meshbeacon", "slug: other"))
    with pytest.raises(SystemExit, match="unexpected source slug"):
        pi_test_apps.build(source, tmp_path / "out1", "meshbeacon_m4p", dev=False)
    config.write_text(config.read_text().replace("slug: other", "slug: meshbeacon"))
    dockerfile = source / "Dockerfile"
    dockerfile.write_text(dockerfile.read_text().replace("FROM app AS production", "FROM app AS final"))
    with pytest.raises(SystemExit, match="production alias"):
        pi_test_apps.build(source, tmp_path / "out2", "meshbeacon_m4d", dev=True)
    with pytest.raises(SystemExit, match="exists"):
        (tmp_path / "out3").mkdir()
        pi_test_apps.build(SOURCE, tmp_path / "out3", "meshbeacon_m4p", dev=False)


def write_run(folder: Path, label: str, n: int, mem_mib: float, cpu: float, *, live: str = "started") -> None:
    rows = [f"{1000 + i * 30},{cpu},{int(mem_mib * pi_summary.MIB)},{live},90000000,6000000" for i in range(4)]
    header = f"# label={label} run={n} cpus=4 settle_min=10 sample_min=30 version=0.2.0"
    columns = "epoch,cpu_percent,memory_bytes,live_state,live_memory_bytes,host_mem_available_kib"
    (folder / f"{label}-run{n}.csv").write_text("\n".join([header, columns, *rows]) + "\n")
    core, rns = (30, 40) if label != "m4d" else (31, 41)
    (folder / f"{label}-run{n}.log").write_text(f"[meshbeacon] Status: memory {core} MB core + {rns} MB Reticulum.\n")


def runs(folder: Path) -> list[pi_summary.Run]:
    return [pi_summary.read_run(p) for p in sorted(folder.glob("*.csv"))]


def test_the_summary_computes_ms1_and_ms18(tmp_path: Path) -> None:
    for n in (1, 2):
        write_run(tmp_path, "v02", n, 72.0, 0.03)
        write_run(tmp_path, "m4p", n, 73.0, 0.03)
        write_run(tmp_path, "m4d", n, 110.0, 0.05)
    result = pi_summary.summarise(runs(tmp_path), "core", 0.1)
    assert result["MS-1"] == {"memory_delta_mib": 1.0, "cpu_delta_pct": 0.0, "memory_pass": True, "cpu_pass": True}
    ms18 = result["MS-18"]
    assert isinstance(ms18, dict)
    assert ms18["memory_added_mib"] == 37.0 and ms18["app_total_mib"] == 110.0 and ms18["memory_pass"]
    assert ms18["engine_and_overhead_mib"] == 35.0  # 37 minus the core's and Reticulum's 2 MiB
    assert ms18["cpu_added_pct"] == pytest.approx(0.08)  # 0.02 of the machine is 0.08 of one core
    assert pi_summary.summarise(runs(tmp_path), "machine", 0.1)["MS-18"]["cpu_added_pct"] == pytest.approx(0.02)  # type: ignore[index]
    assert result["live_app"] == {"always_started": True, "other_states": []}


def test_the_summary_fails_what_must_fail(tmp_path: Path) -> None:
    write_run(tmp_path, "v02", 1, 72.0, 0.03)
    write_run(tmp_path, "m4p", 1, 75.0, 0.03)  # +3 MiB: MS-1 fails
    write_run(tmp_path, "m4d", 1, 120.0, 0.2, live="stopped")  # +45 MiB; +0.68 of a core; live app stopped
    result = pi_summary.summarise(runs(tmp_path), "core", 0.1)
    assert result["MS-1"]["memory_pass"] is False  # type: ignore[index]
    assert result["MS-18"]["memory_pass"] is False and result["MS-18"]["cpu_pass"] is False  # type: ignore[index]
    assert result["live_app"] == {"always_started": False, "other_states": ["stopped"]}


def test_the_stamp_summary() -> None:
    rows = [{"seconds": 2.0}, {"seconds": 40.0}, {"seconds": None, "timed_out": True}]
    assert stamp_benchmark.summarise(12, rows) == {
        "cost": 12,
        "trials": 3,
        "finished": 2,
        "timed_out": 1,
        "median_s": 21.0,
        "slowest_s": 40.0,
        "within_30s": 1,
    }


@pytest.mark.parametrize("script", ["pi_preflight.sh", "pi_measure.sh"])
def test_the_pi_scripts_parse_and_only_touch_the_test_apps(script: str) -> None:
    path = ROOT / "tools" / "acceptance" / script
    subprocess.run(["sh", "-n", str(path)], check=True)
    text = path.read_text()
    assert " start local_meshbeacon\n" not in text and "stop local_meshbeacon\n" not in text
    for verb in ("start", "stop", "restart", "update", "rebuild", "uninstall", "install", "options"):
        for line in text.splitlines():
            if f'"$APPS" {verb} ' in line:
                assert '"$TEST"' in line, line  # only ever the test app
