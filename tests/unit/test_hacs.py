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


def test_no_workflow_publishes_releases():
    """Publishing needs the maintainer's approval (D3, M2). Until then no workflow may release."""
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


def test_minimum_home_assistant_is_the_marketplace_release():
    """D2: Home Assistant 2026.11.0 or newer, the first release with the Marketplace.

    The real-Home Assistant smoke test runs that series. The pytest harness lags: no
    pytest-homeassistant-custom-component release exists for 2026.11 yet, and the 2026.10 one cannot
    load Home Assistant 2026.11, so it stays on 2026.10.4 (docs/testing/strategy.md).
    """
    assert HACS["homeassistant"] == "2026.11.0"
    smoke = (ROOT / "requirements-ha-smoke.txt").read_text()
    smoke_version = re.search(r"^homeassistant==(\S+)$", smoke, re.M)
    assert smoke_version and smoke_version.group(1).startswith("2026.11.")


def test_frontend_ships_inside_the_integration():
    """The Marketplace copies only custom_components/meshbeacon, so the panel must live there."""
    assert (INTEGRATION / "frontend" / "meshbeacon-panel.js").is_file()
    assert (INTEGRATION / "frontend" / "model.js").is_file()
