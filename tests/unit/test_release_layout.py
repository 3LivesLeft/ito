# SPDX-License-Identifier: Apache-2.0
"""tools/check_release.py: the release layout the app store and the Marketplace read (M1)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_release  # noqa: E402 - after the path is set


class DictTree(check_release.Tree):
    """A source tree held in memory, so each test can break one thing."""

    def __init__(self, files: dict[str, str]) -> None:
        super().__init__(ROOT, None)
        self._files = files

    def files(self) -> list[str]:
        return sorted(self._files)

    def read(self, path: str) -> str | None:
        return self._files.get(path)


def good_tree(version: str = "0.3.0") -> dict[str, str]:
    app = yaml.safe_load((ROOT / "meshbeacon" / "config.yaml").read_text())
    app["version"] = version
    manifest = json.loads((ROOT / "custom_components" / "meshbeacon" / "manifest.json").read_text())
    manifest["version"] = version
    return {
        "repository.yaml": (ROOT / "repository.yaml").read_text(),
        "meshbeacon/config.yaml": yaml.safe_dump(app),
        "meshbeacon/apparmor.txt": "profile",
        "meshbeacon/Dockerfile": f"FROM x\nARG BUILD_VERSION={version}\n",
        "meshbeacon/CHANGELOG.md": f"# Changelog\n\n## {version}\n",
        "meshbeacon/core/meshbeacon/__init__.py": f'__version__ = "{version}"\n',
        "hacs.json": json.dumps({"name": "MeshBeacon", "homeassistant": "2026.11.0"}),
        "custom_components/meshbeacon/manifest.json": json.dumps(manifest),
        "custom_components/meshbeacon/brand/icon.png": "png",
        "custom_components/__init__.py": "",
    }


def problems(files: dict[str, str], tag: str | None = None) -> list[str]:
    return check_release.check(DictTree(files), tag)


def test_the_working_tree_passes():
    assert check_release.check(check_release.Tree(ROOT, None)) == []


def test_a_consistent_release_tree_passes_with_its_tag():
    assert problems(good_tree(), tag="v0.3.0") == []


@pytest.mark.parametrize(
    ("path", "change", "expected"),
    [
        ("hacs.json", lambda d: {**d, "render_readme": True}, "keys the Marketplace does not read"),
        ("hacs.json", lambda d: {**d, "homeassistant": "2026.10.4"}, "decision D2"),
        ("hacs.json", lambda d: {**d, "zip_release": True}, "is not used"),
        ("custom_components/meshbeacon/manifest.json", lambda d: {**d, "domain": "other"}, "domain"),
        ("custom_components/meshbeacon/manifest.json", lambda d: {**d, "requirements": ["x"]}, "PyPI"),
    ],
)
def test_marketplace_mistakes_are_refused(path, change, expected):
    files = good_tree()
    files[path] = json.dumps(change(json.loads(files[path])))
    assert any(expected in p for p in problems(files)), problems(files)


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("hassio_api", True, "hassio_api"),
        ("homeassistant_api", True, "homeassistant_api"),
        ("ingress", True, "ingress"),
        ("map", ["share:rw"], "map"),
        ("ports", {"8100/tcp": 8100}, "ports"),
        ("hassio_role", "manager", "hassio_role"),
        ("image", "ghcr.io/someone/meshbeacon", "image"),
        ("slug", "meshbeacon2", "slug"),
    ],
)
def test_app_privileges_and_identity_are_guarded(key, value, expected):
    files = good_tree()
    app = yaml.safe_load(files["meshbeacon/config.yaml"])
    app[key] = value
    files["meshbeacon/config.yaml"] = yaml.safe_dump(app)
    assert any(expected in p for p in problems(files)), problems(files)


def test_the_published_image_name_is_accepted():
    files = good_tree()
    app = yaml.safe_load(files["meshbeacon/config.yaml"])
    app["image"] = check_release.PUBLISHED_IMAGE
    files["meshbeacon/config.yaml"] = yaml.safe_dump(app)
    assert problems(files) == []


def test_versions_must_agree_with_each_other_and_the_tag():
    files = good_tree()
    files["meshbeacon/core/meshbeacon/__init__.py"] = '__version__ = "0.2.9"\n'
    assert any("versions differ" in p for p in problems(files))
    assert any("versions differ" in p for p in problems(good_tree(), tag="v0.3.1"))


def test_a_tag_cannot_ship_an_unreleased_changelog():
    files = good_tree()
    files["meshbeacon/CHANGELOG.md"] = "# Changelog\n\n## 0.3.0 — unreleased (in development)\n"
    assert any("unreleased" in p for p in problems(files, tag="v0.3.0"))
    assert problems(files) == []  # fine between releases


def test_exactly_one_integration_with_brand_images():
    files = good_tree()
    files["custom_components/other/manifest.json"] = "{}"
    assert any("exactly one integration" in p for p in problems(files))
    files = good_tree()
    del files["custom_components/meshbeacon/brand/icon.png"]
    assert any("brand" in p for p in problems(files))


@pytest.mark.parametrize(
    "path",
    [
        "meshbeacon/core/meshbeacon/tests/binding.py",
        "meshbeacon/core/meshbeacon/test_move.py",
        "meshbeacon/core/meshbeacon/fake_supervisor.py",
        "meshbeacon/rootfs/conftest.py",
    ],
)
def test_test_only_code_cannot_enter_the_build_context(path):
    """P-6: test-only bindings live in tests/ and never in the app's build context."""
    files = good_tree()
    files[path] = ""
    assert any("test-only" in p for p in problems(files))


def test_the_working_tree_passes_without_git(monkeypatch):
    """CI's network-less test container has no git: the checker walks the files instead."""
    monkeypatch.setattr(check_release, "GIT", None)
    tree = check_release.Tree(ROOT, None)
    assert "hacs.json" in tree.files() and not any("__pycache__" in f or f.startswith(".git/") for f in tree.files())
    assert check_release.check(tree) == []


@pytest.mark.skipif(check_release.GIT is None, reason="needs git")
def test_a_git_ref_is_read_like_the_working_tree():
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    tree = check_release.Tree(ROOT, head.stdout.strip())
    assert "hacs.json" in tree.files()
    assert tree.read("repository.yaml") is not None
    assert tree.read("does/not/exist") is None


def test_a_tag_cannot_ship_an_unverified_network_preset():
    """ADR 0004: presets ship only after the maintainer's manual checks V1–V7 are recorded."""
    tree = good_tree()
    entry = {"id": "example", "release_checks_passed_on": None}
    tree["meshbeacon/core/meshbeacon/networks.json"] = json.dumps({"version": 1, "networks": [entry]})
    assert problems(tree) == []  # branches and the working tree are not releases
    assert any("'example' has no recorded release checks" in p for p in problems(tree, tag="v0.3.0"))
    entry["release_checks_passed_on"] = "2026-11-20"
    tree["meshbeacon/core/meshbeacon/networks.json"] = json.dumps({"version": 1, "networks": [entry]})
    assert problems(tree, tag="v0.3.0") == []
