# SPDX-License-Identifier: Apache-2.0
"""HACS compatibility of the integration's packaging (prepared, not published; docs/hacs.md).

These are offline checks of what HACS reads from the repository. They do not replace HACS's own
validation action, which needs GitHub API access and is a maintainer step before any listing.
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

HACS_KEYS = {
    "name",
    "content_in_root",
    "zip_release",
    "filename",
    "hide_default_branch",
    "country",
    "homeassistant",
    "persistent_directory",
    "render_readme",
}


def test_hacs_json_uses_only_known_keys():
    assert HACS["name"] == "MeshBeacon"
    assert set(HACS) <= HACS_KEYS
    assert re.fullmatch(r"\d{4}\.\d{1,2}\.\d+", HACS["homeassistant"])


def test_no_release_install_workflow_is_enabled():
    """Maintainer decision (18 Nov 2026): prepare only. No release ZIPs, no content-in-root."""
    assert "zip_release" not in HACS
    assert "filename" not in HACS
    assert HACS.get("content_in_root", False) is False
    for path in (ROOT / ".github" / "workflows").glob("*.y*ml"):
        workflow = yaml.safe_load(path.read_text())
        triggers = workflow.get("on", workflow.get(True))  # YAML 1.1 reads a bare `on` as True
        assert "release" not in (triggers if isinstance(triggers, (dict, list)) else [triggers]), path
        steps = [step for job in workflow["jobs"].values() for step in job.get("steps", [])]
        for step in steps:
            assert "release" not in str(step.get("uses", "")), (path, step)
            assert not re.search(r"\bgh release\b|upload-release-asset", str(step.get("run", ""))), (path, step)


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


def test_minimum_home_assistant_matches_the_tested_harness():
    pins = (ROOT / "requirements-ha-test.txt").read_text()
    assert "pytest-homeassistant-custom-component==" in pins
    assert HACS["homeassistant"] == "2026.10.4"  # the release the pinned harness runs


def test_frontend_ships_inside_the_integration():
    """HACS copies only custom_components/meshbeacon, so the panel must live there."""
    assert (INTEGRATION / "frontend" / "meshbeacon-panel.js").is_file()
    assert (INTEGRATION / "frontend" / "model.js").is_file()
