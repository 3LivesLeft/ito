# SPDX-License-Identifier: Apache-2.0
"""Marketplace compatibility of the integration's packaging (docs/marketplace.md).

Home Assistant 2026.11 replaced HACS with the built-in Marketplace, which still reads ``hacs.json``.
These are offline checks of what the Marketplace reads, verified against its source in Home
Assistant 2026.11.2 (``components/marketplace``). They do not replace the catalog's own checks
(the HACS action and Hassfest), which need GitHub API access.
"""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HACS = json.loads((ROOT / "hacs.json").read_text())
INTEGRATION = ROOT / "custom_components" / "meshbeacon"
MANIFEST = json.loads((INTEGRATION / "manifest.json").read_text())
APP = yaml.safe_load((ROOT / "meshbeacon" / "config.yaml").read_text())

# What the Marketplace reads from hacs.json (HA 2026.11.2, marketplace/utils/validate.py).
MARKETPLACE_KEYS = {
    "content_in_root",
    "filename",
    "hacs",
    "hide_default_branch",
    "homeassistant",
    "name",
    "persistent_directory",
    "zip_release",
}


def test_hacs_json_uses_only_keys_the_marketplace_reads():
    assert HACS["name"] == "MeshBeacon"
    assert set(HACS) <= MARKETPLACE_KEYS  # others are skipped silently, so they would be mistakes
    assert re.fullmatch(r"\d{4}\.\d{1,2}\.\d+", HACS["homeassistant"])


def test_marketplace_installs_the_integration_directory():
    """No release ZIPs and no content-in-root: the Marketplace copies custom_components/meshbeacon."""
    assert "zip_release" not in HACS
    assert "filename" not in HACS
    assert HACS.get("content_in_root", False) is False


def test_exactly_one_integration_in_custom_components():
    found = [p.name for p in (ROOT / "custom_components").iterdir() if p.is_dir() and not p.name.startswith("__")]
    assert found == ["meshbeacon"]


def test_manifest_has_what_hacs_and_home_assistant_need():
    for key in ("domain", "name", "documentation", "issue_tracker", "codeowners", "version"):
        assert MANIFEST[key], key
    assert MANIFEST["domain"] == INTEGRATION.name
    assert re.fullmatch(r"\d+\.\d+\.\d+", MANIFEST["version"])
    assert MANIFEST["requirements"] == []  # nothing for HACS or Home Assistant to install
    assert MANIFEST["documentation"].startswith("https://github.com/3LivesLeft/meshbeacon/")


def test_integration_and_app_versions_match():
    assert MANIFEST["version"] == APP["version"]


def test_minimum_home_assistant_is_the_marketplace_release():
    """D2: Home Assistant 2026.11.0 or newer, the first release with the Marketplace.

    The real-Home Assistant smoke test runs that series. The pytest harness lags: no
    pytest-homeassistant-custom-component release exists for 2026.11 yet, and the 2026.10 one cannot
    load Home Assistant 2026.11, so it stays on 2026.10.4 (docs/testing/strategy.md).
    """
    assert HACS["homeassistant"] == "2026.11.0"
    smoke = (ROOT / "requirements-ha-smoke.in").read_text()
    smoke_version = re.search(r"^homeassistant==(\S+)$", smoke, re.M)
    assert smoke_version and smoke_version.group(1).startswith("2026.11.")


def test_frontend_ships_inside_the_integration():
    """The Marketplace copies only custom_components/meshbeacon, so the panel must live there."""
    assert (INTEGRATION / "frontend" / "meshbeacon-panel.js").is_file()
    assert (INTEGRATION / "frontend" / "model.js").is_file()


def test_release_dry_run_checks_reproducibility_and_attestations():
    workflow = (ROOT / ".github" / "workflows" / "release-dry-run.yaml").read_text()
    assert "SOURCE_DATE_EPOCH" in workflow and "rewrite-timestamp=true" in workflow
    assert "--sbom=generator=" in workflow and "--provenance=mode=max" in workflow
    assert "tools/verify_image.py candidate-1.tar candidate-2.tar" in workflow
    assert "tools/check_release.py" in workflow
    for line in workflow.splitlines():
        if "uses:" in line and not line.strip().startswith("#"):
            assert re.search(r"@[0-9a-f]{40} # v", line), f"action not pinned to a commit SHA: {line.strip()}"


DIGEST = r"@sha256:[0-9a-f]{64}"


def test_every_image_the_build_runs_is_pinned_by_digest():
    """M1.2 (M-2): QEMU's binfmt, BuildKit, the SBOM scanner, the Dockerfile frontend and the base
    image are pinned by digest, and no release build restores anything from the action cache."""
    dockerfile = (ROOT / "meshbeacon" / "Dockerfile").read_text()
    assert re.match(rf"# syntax=docker/dockerfile:[0-9.]+{DIGEST}\n", dockerfile)
    assert re.search(rf"^FROM \S+{DIGEST}( AS \S+)?$", dockerfile, re.M)
    external = [line for line in re.findall(r"^FROM (\S+)", dockerfile, re.M) if "/" in line or ":" in line]
    assert all(re.search(DIGEST, image) for image in external), external
    for name in ("release-dry-run.yaml", "ci.yaml"):
        workflow = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                uses, with_ = str(step.get("uses", "")), step.get("with") or {}
                if "setup-qemu-action" in uses:
                    assert re.search(DIGEST, str(with_.get("image", ""))), (name, step)
                    assert with_.get("cache-image") is False, (name, step)
                if "setup-buildx-action" in uses:
                    assert re.search(rf"image=\S+{DIGEST}", str(with_.get("driver-opts", ""))), (name, step)
                    assert with_.get("cache-binary") is False, (name, step)
                assert "actions/cache" not in uses, (name, step)
                for image in re.findall(
                    r"\b(?:python|ghcr\.io/\S+|docker\.io/\S+):[\w.-]+(?:@\S+)?", str(step.get("run", ""))
                ):
                    assert re.search(DIGEST, image), (name, image)
    release = (ROOT / ".github" / "workflows" / "release-dry-run.yaml").read_text()
    assert re.search(rf"--sbom=generator=\S+{DIGEST}", release)


def test_every_python_install_in_ci_is_hash_checked():
    """M1.2 (M-2): CI and release tooling installs only hash-locked requirement files."""
    for path in (ROOT / ".github" / "workflows").glob("*.y*ml"):
        for line in path.read_text().splitlines():
            if re.search(r"\bpip\b.*\binstall\b", line):
                assert "--require-hashes" in line and re.search(r"-r requirements-[\w-]+\.txt", line), (path, line)
    for lock in ROOT.glob("requirements-*.txt"):
        text = lock.read_text()
        pins = re.findall(r"^[A-Za-z0-9_.-]+==\S+", text, re.M)
        assert pins and text.count("--hash=sha256:") >= len(pins), lock
        assert (ROOT / lock.name.replace(".txt", ".in")).exists(), f"{lock.name} has no .in source"


def test_both_vulnerability_policies_gate_ci_and_the_release_dry_run():
    """M1.2 (L-4): any critical finding fails; a high finding with an available fix fails."""
    for name in ("release-dry-run.yaml", "ci.yaml"):
        workflow = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())
        scans = [
            step.get("with") or {}
            for job in workflow["jobs"].values()
            for step in job.get("steps", [])
            if "anchore/scan-action" in str(step.get("uses", ""))
        ]
        assert any(
            s.get("fail-build") and s.get("severity-cutoff") == "critical" and not s.get("only-fixed") for s in scans
        ), name
        assert any(s.get("fail-build") and s.get("severity-cutoff") == "high" and s.get("only-fixed") for s in scans), (
            name
        )


def test_the_release_candidate_is_scanned_for_each_platform():
    """M1.2 re-review: both policies for amd64 and for arm64 (what a Raspberry Pi pulls), chosen
    explicitly; a multi-platform archive is otherwise read for one platform only."""
    release = yaml.safe_load((ROOT / ".github" / "workflows" / "release-dry-run.yaml").read_text())
    scans = set()
    for job in release["jobs"].values():
        for step in job.get("steps", []):
            with_ = step.get("with") or {}
            if "anchore/scan-action" in str(step.get("uses", "")) and with_.get("fail-build"):
                platform = (step.get("env") or {}).get("GRYPE_PLATFORM")
                scans.add((platform, with_.get("severity-cutoff"), bool(with_.get("only-fixed"))))
    for platform in ("linux/amd64", "linux/arm64"):
        assert (platform, "critical", False) in scans, platform
        assert (platform, "high", True) in scans, platform
