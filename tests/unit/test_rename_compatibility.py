# SPDX-License-Identifier: Apache-2.0
"""The rename to ito and the repository move to 3LivesLeft/ito keep every installation working
(docs/adr/0026-repository-rename.md).

Home Assistant shows what repository.yaml, the app's config.yaml, hacs.json and the integration's
manifest say, so those say ito and point at the new repository. The identifiers that key an
installation's data stay `meshbeacon`: the app slug (the Supervisor's data folder and backups),
the app folder, the discovery service and the integration's domain (its config entries). Changing
any of them would make an update look like a different app or integration, with a new, empty
identity, so these tests freeze them.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_release  # noqa: E402 - after the path is set

PROJECT = yaml.safe_load((ROOT / "project.yaml").read_text())
OLD_REPOSITORY = "https://github.com/3LivesLeft/meshbeacon"
NEW_REPOSITORY = "https://github.com/3LivesLeft/ito"
FROZEN_SLUG = "meshbeacon"


def text(path: str) -> str:
    return (ROOT / path).read_text()


def test_identifiers_that_key_installed_data_are_unchanged():
    assert PROJECT["slug"] == FROZEN_SLUG, "project.yaml slug keys every installation's data: never rename it"
    app = yaml.safe_load(text(f"{FROZEN_SLUG}/config.yaml"))
    assert app["slug"] == FROZEN_SLUG, "app slug: the Supervisor's data folder and backups are keyed by it"
    assert app["discovery"] == [FROZEN_SLUG], "discovery service: the integration listens for this name"
    manifest = json.loads(text(f"custom_components/{FROZEN_SLUG}/manifest.json"))
    assert manifest["domain"] == FROZEN_SLUG, "integration domain: existing config entries are keyed by it"
    assert "hassio" in manifest["after_dependencies"]
    assert re.search(r'^DOMAIN: Final = "meshbeacon"$', text("custom_components/meshbeacon/const.py"), re.M)
    assert re.search(r'^SERVICE = "meshbeacon"$', text("meshbeacon/core/meshbeacon/discovery_relay.py"), re.M)


def test_home_assistant_metadata_says_ito():
    """What the app store, the app page and Devices & services display."""
    assert PROJECT["name"] == "ito"  # always lower case (docs/branding.md)
    shown = {
        "repository.yaml name": yaml.safe_load(text("repository.yaml"))["name"],
        "repository.yaml maintainer": yaml.safe_load(text("repository.yaml"))["maintainer"],
        "config.yaml name": yaml.safe_load(text("meshbeacon/config.yaml"))["name"],
        "hacs.json name": json.loads(text("hacs.json"))["name"],
        "manifest.json name": json.loads(text("custom_components/meshbeacon/manifest.json"))["name"],
    }
    for where, value in shown.items():
        assert "MeshBeacon" not in value, f"{where} still says MeshBeacon: {value!r}"
        assert value.split()[0] == "ito", f"{where}: {value!r}"


def test_home_assistant_metadata_points_at_the_new_repository():
    assert PROJECT["repository"] == NEW_REPOSITORY
    manifest = json.loads(text("custom_components/meshbeacon/manifest.json"))
    links = {
        "repository.yaml url": yaml.safe_load(text("repository.yaml"))["url"],
        "config.yaml url": yaml.safe_load(text("meshbeacon/config.yaml"))["url"],
        "manifest.json documentation": manifest["documentation"],
        "manifest.json issue_tracker": manifest["issue_tracker"],
    }
    for where, url in links.items():
        assert url == NEW_REPOSITORY or url.startswith(NEW_REPOSITORY + "/"), f"{where}: {url}"
    for path in ("meshbeacon/Dockerfile", "custom_components/meshbeacon/coordinator.py"):
        found = re.findall(r"https://github\.com/3LivesLeft/[\w.-]+", text(path))
        assert found and set(found) == {NEW_REPOSITORY}, f"{path}: {sorted(set(found))}"


def test_the_repository_address_selects_the_installed_app():
    """Supervisor store/utils.py: the app slug is the first 8 hex digits of SHA-1 of the lower-cased
    repository address as the user typed it, `#branch` included, then the app's slug. So an
    installation from the old address keeps its slug and data across the move, and adding the new
    address installs a separate app. docs/getting-started.md must say so."""
    old, new = check_release.store_slug(OLD_REPOSITORY), check_release.store_slug(NEW_REPOSITORY)
    assert old == "ce27fbb5_meshbeacon"  # every installation made before the move
    assert new == "d6f2aa84_meshbeacon"  # new installations, and the one-click links
    assert check_release.store_slug(NEW_REPOSITORY.upper()) == new  # case does not matter
    assert len({old, new, check_release.store_slug(NEW_REPOSITORY + "#develop")}) == 3  # a branch is another app
    guide = text("docs/getting-started.md")
    moved = guide[guide.index("### The repository has moved") :]
    moved = moved[: moved.index("\n## ")]
    assert OLD_REPOSITORY in moved and NEW_REPOSITORY in moved
    assert "change nothing" in moved and "Do **not** remove the old repository" in moved
