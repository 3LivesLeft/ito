# SPDX-License-Identifier: Apache-2.0
"""Every copy of the project's identifiers agrees with project.yaml.

The final name is decided before the first published release. These places cannot read
project.yaml at run time (the app, the integration and Home Assistant read their own files), so a
rename is: edit project.yaml, then make this test pass. Each failure names the file to change.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROJECT = yaml.safe_load((ROOT / "project.yaml").read_text())
NAME, SLUG, REPOSITORY, IMAGE = PROJECT["name"], PROJECT["slug"], PROJECT["repository"], PROJECT["image"]
sys.path.insert(0, str(ROOT / "tools"))
import check_release  # noqa: E402 - after the path is set


def text(path: str) -> str:
    return (ROOT / path).read_text()


def test_app_repository_and_app():
    repository = yaml.safe_load(text("repository.yaml"))
    assert repository["name"] == NAME and repository["url"] == REPOSITORY, "repository.yaml"
    app = yaml.safe_load(text(f"{SLUG}/config.yaml"))
    assert app["name"] == NAME and app["slug"] == SLUG and app["url"] == REPOSITORY, "config.yaml"
    assert app["discovery"] == [SLUG], "config.yaml discovery"
    assert app.get("image", IMAGE) == IMAGE, "config.yaml image"
    assert f'org.opencontainers.image.source="{REPOSITORY}"' in text(f"{SLUG}/Dockerfile"), "Dockerfile label"
    assert f'org.opencontainers.image.title="{NAME}"' in text(f"{SLUG}/Dockerfile"), "Dockerfile label"


def test_integration():
    manifest = json.loads(text(f"custom_components/{SLUG}/manifest.json"))
    assert manifest["domain"] == SLUG and manifest["name"] == NAME, "manifest.json"
    assert manifest["documentation"].startswith(f"{REPOSITORY}/"), "manifest.json documentation"
    assert manifest["issue_tracker"] == f"{REPOSITORY}/issues", "manifest.json issue_tracker"
    assert json.loads(text("hacs.json"))["name"] == NAME, "hacs.json"
    assert re.search(rf'^DOMAIN: Final = "{SLUG}"$', text(f"custom_components/{SLUG}/const.py"), re.M), "const.py"
    assert f'_{SLUG}$"' in text(f"custom_components/{SLUG}/config_flow.py"), "config_flow.py slug pattern"
    for url in re.findall(r'"(https://github\.com/[^"]+)"', text(f"custom_components/{SLUG}/coordinator.py")):
        assert url.startswith(f"{REPOSITORY}/"), "coordinator.py learn-more links"


def test_core_and_relay():
    assert re.search(rf'^DISCOVERY_SERVICE = "{SLUG}"$', text(f"{SLUG}/core/meshbeacon/api.py"), re.M), "api.py"
    relay = text(f"{SLUG}/core/meshbeacon/discovery_relay.py")
    assert re.search(rf'^SERVICE = "{SLUG}"$', relay, re.M), "discovery_relay.py SERVICE"


def test_release_tooling_reads_the_same_values():
    assert check_release.NAME == NAME and check_release.DOMAIN == SLUG
    assert check_release.REPOSITORY_URL == REPOSITORY and check_release.PUBLISHED_IMAGE == IMAGE
    assert json.loads(text("hacs.json"))["homeassistant"] == check_release.MINIMUM_HOME_ASSISTANT


def test_published_slug_follows_the_repository_url():
    """The app store's slug for this repository, used in the one-click links in the documentation."""
    slug = check_release.store_slug()
    assert re.fullmatch(rf"[0-9a-f]{{8}}_{SLUG}", slug)  # both addresses' slugs: test_rename_compatibility.py
    for doc in ("README.md", "docs/getting-started.md", f"{SLUG}/DOCS.md"):
        content = text(doc)
        for found in re.findall(r"supervisor_app/\?app=([0-9a-f]{8}_[a-z0-9_]+)", content):
            assert found == slug, f"{doc}: one-click link uses slug {found}, expected {slug}"
        for found in re.findall(r"repository_url=([^\s)&\"']+)", content):
            assert found == REPOSITORY, f"{doc}: one-click link uses repository {found}"
        for owner, repo in re.findall(r"marketplace_repository/\?owner=([^&]+)&repository=([^&\s)]+)", content):
            assert f"https://github.com/{owner}/{repo}" == REPOSITORY, f"{doc}: Marketplace link"
