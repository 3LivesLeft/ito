# SPDX-License-Identifier: Apache-2.0
"""Release-layout validation: what the Supervisor app store and the Home Assistant Marketplace read.

Checks one source tree, either the working tree or a git ref (a release tag), offline:

- the app repository: ``repository.yaml`` and ``meshbeacon/config.yaml`` (slug, version, no new
  privileges, ``image`` only in its published form);
- the Marketplace: ``hacs.json`` in the root with only keys the Marketplace reads, and exactly one
  integration in ``custom_components/`` with a ``manifest.json`` and brand images;
- one version everywhere (app, integration, core, image label default, changelog, tag);
- the app's build context holds no tests or test-only bindings, so none can reach an image.

    python tools/check_release.py                 # the working tree
    python tools/check_release.py --ref v0.3.0 --tag v0.3.0

Keys and rules are from Home Assistant 2026.11.2 (``components/marketplace``) and Supervisor
2026.11.0, read from source (docs/research/v0.3-install.md). Exit status 0 means no problems.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")
# Skipped when walking the working tree without git (for example in CI's minimal test container).
_SKIP_DIRS = {"__pycache__", "node_modules"}
# Project identifiers live in project.yaml (renaming before the first release changes only that
# file plus what tests/unit/test_project_identifiers.py then points at).
PROJECT: dict[str, str] = {k: str(v) for k, v in yaml.safe_load((ROOT / "project.yaml").read_text()).items()}
NAME = PROJECT["name"]
REPOSITORY_URL = PROJECT["repository"]
PUBLISHED_IMAGE = PROJECT["image"]
DOMAIN = PROJECT["slug"]
# What the Marketplace reads from hacs.json (HA 2026.11.2, marketplace/utils/validate.py). It skips
# other keys silently, so an unknown key is a mistake we want to see, not a harmless extra.
MARKETPLACE_KEYS = frozenset(
    {
        "content_in_root",
        "filename",
        "hacs",
        "hide_default_branch",
        "homeassistant",
        "name",
        "persistent_directory",
        "zip_release",
    }
)
MINIMUM_HOME_ASSISTANT = PROJECT["minimum_home_assistant"]
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
HA_VERSION = re.compile(r"^\d{4}\.\d{1,2}\.\d+$")
# Privileges the approved posture forbids (docs/architecture.md §5); kept in step with test_app_config.
FORBIDDEN_TRUE = (
    "host_network",
    "host_pid",
    "host_ipc",
    "host_uts",
    "host_dbus",
    "hassio_api",
    "homeassistant_api",
    "auth_api",
    "docker_api",
    "full_access",
    "uart",
    "usb",
    "gpio",
    "udev",
    "devicetree",
    "kernel_modules",
    "video",
    "audio",
    "stdin",
    "realtime",
    "journald",
    "privileged",
    "devices",
    "ports",
    "map",
)
# Nothing under the app's build context may look like test code (P-6: test-only bindings stay in tests/).
TEST_ONLY = re.compile(r"(^|/)(tests?|testing|conftest\.py|test_[^/]*\.py|[^/]*_test\.py|fake_[^/]*\.py)(/|$)")


def store_slug(repository_url: str = REPOSITORY_URL, slug: str = DOMAIN) -> str:
    """The app's slug when installed from ``repository_url`` (Supervisor store/utils.py and
    store/data.py: the first 8 hex digits of SHA-1 of the lower-cased URL, then the app's slug)."""
    digest = hashlib.sha1(repository_url.lower().encode(), usedforsecurity=False).hexdigest()
    return f"{digest[:8]}_{slug}"


class Tree:
    """Read files from the working tree or from a git ref, the same way."""

    def __init__(self, root: Path, ref: str | None) -> None:
        self.root, self.ref = root, ref

    def files(self) -> list[str]:
        if self.ref is None and GIT is None:
            return sorted(
                path.relative_to(self.root).as_posix()
                for path in self.root.rglob("*")
                if path.is_file()
                and not any(
                    part.startswith(".") or part in _SKIP_DIRS for part in path.relative_to(self.root).parts[:-1]
                )
            )
        if GIT is None:
            raise RuntimeError("checking a git ref needs git")
        if self.ref is None:
            out = subprocess.run(
                [GIT, "-C", str(self.root), "ls-files", "--cached", "--others", "--exclude-standard"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        else:
            out = subprocess.run(
                [GIT, "-C", str(self.root), "ls-tree", "-r", "--name-only", self.ref],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        return sorted(line for line in out.splitlines() if line)

    def read(self, path: str) -> str | None:
        if self.ref is None:
            file = self.root / path
            return file.read_text() if file.is_file() else None
        if GIT is None:
            raise RuntimeError("checking a git ref needs git")
        result = subprocess.run(
            [GIT, "-C", str(self.root), "show", f"{self.ref}:{path}"], capture_output=True, text=True, check=False
        )
        return result.stdout if result.returncode == 0 else None


def check(tree: Tree, tag: str | None = None) -> list[str]:
    problems: list[str] = []
    add: Callable[[str], None] = problems.append
    files = tree.files()
    present = set(files)

    def load(path: str, parse: Callable[[str], Any]) -> Any:
        text = tree.read(path)
        if text is None:
            add(f"{path} is missing")
            return None
        try:
            return parse(text)
        except (ValueError, yaml.YAMLError) as exc:
            add(f"{path} cannot be parsed: {type(exc).__name__}")
            return None

    # -- App repository (Supervisor) ------------------------------------------------------------
    repo = load("repository.yaml", yaml.safe_load)
    if isinstance(repo, dict):
        if not repo.get("name"):
            add("repository.yaml has no name")
        if repo.get("url") != REPOSITORY_URL:
            add("repository.yaml url is not the canonical repository URL")
    app = load(f"{DOMAIN}/config.yaml", yaml.safe_load)
    app_version = None
    if isinstance(app, dict):
        app_version = app.get("version")
        if app.get("slug") != DOMAIN:
            add(f"config.yaml slug must be {DOMAIN!r} (project.yaml; the slug decides the app's data folder)")
        if app.get("name") != NAME or app.get("url") != REPOSITORY_URL:
            add("config.yaml name or url differs from project.yaml")
        if not isinstance(app_version, str) or not VERSION.match(app_version):
            add("config.yaml version is not MAJOR.MINOR.PATCH")
        for key in FORBIDDEN_TRUE:
            if app.get(key):
                add(f"config.yaml grants {key!r}, which the approved posture forbids")
        for key, value in {"ingress": True, "ingress_port": 8097, "panel_admin": True}.items():
            if app.get(key) != value:
                add(f"config.yaml {key} must be {value!r} (ADR 0026)")
        if app.get("hassio_role", "default") != "default":
            add("config.yaml hassio_role must stay 'default'")
        if app.get("apparmor") is not True or f"{DOMAIN}/apparmor.txt" not in present:
            add("config.yaml must use the custom AppArmor profile")
        if "image" in app and app["image"] != PUBLISHED_IMAGE:
            add(f"config.yaml image must be {PUBLISHED_IMAGE!r} (the multi-arch manifest), if set")
        if set(app.get("arch", [])) != {"aarch64", "amd64"}:
            add("config.yaml arch must be aarch64 and amd64")

    # -- Marketplace -----------------------------------------------------------------------------
    hacs = load("hacs.json", json.loads)
    if isinstance(hacs, dict):
        unknown = set(hacs) - MARKETPLACE_KEYS
        if unknown:
            add(f"hacs.json has keys the Marketplace does not read: {sorted(unknown)}")
        if hacs.get("name") != NAME:
            add(f"hacs.json name must be {NAME!r} (project.yaml)")
        if hacs.get("homeassistant") != MINIMUM_HOME_ASSISTANT:
            add(f"hacs.json homeassistant must be {MINIMUM_HOME_ASSISTANT!r} (decision D2)")
        for key in ("content_in_root", "zip_release", "filename"):
            if key in hacs:
                add(f"hacs.json {key!r} is not used: the Marketplace installs custom_components/{DOMAIN}/")
    integrations = sorted({p.split("/")[1] for p in files if p.startswith("custom_components/") and p.count("/") >= 2})
    if integrations != [DOMAIN]:
        add(f"custom_components/ must hold exactly one integration directory, found {integrations}")
    manifest = load(f"custom_components/{DOMAIN}/manifest.json", json.loads)
    integration_version = None
    if isinstance(manifest, dict):
        integration_version = manifest.get("version")
        if manifest.get("domain") != DOMAIN:
            add(f"manifest.json domain must be {DOMAIN!r} (a changed domain is refused on update)")
        if manifest.get("requirements") != []:
            add("manifest.json must not install anything from PyPI")
        for key in ("name", "documentation", "issue_tracker", "codeowners", "version", "config_flow"):
            if not manifest.get(key):
                add(f"manifest.json has no {key!r}")
    if f"custom_components/{DOMAIN}/brand/icon.png" not in present:
        add("the integration has no brand/icon.png (the catalog's brand check)")

    # -- One version everywhere ------------------------------------------------------------------
    versions: dict[str, Any] = {f"{DOMAIN}/config.yaml": app_version, "manifest.json": integration_version}
    core = tree.read(f"{DOMAIN}/core/meshbeacon/__init__.py") or ""
    match = re.search(r'^__version__ = "([^"]+)"', core, re.M)
    versions["core __version__"] = match.group(1) if match else None
    dockerfile = tree.read(f"{DOMAIN}/Dockerfile") or ""
    match = re.search(r"^ARG BUILD_VERSION=(\S+)", dockerfile, re.M)
    versions["Dockerfile BUILD_VERSION"] = match.group(1) if match else None
    changelog = tree.read(f"{DOMAIN}/CHANGELOG.md") or ""
    match = re.search(r"^## (\d+\.\d+\.\d+)", changelog, re.M)
    versions["CHANGELOG.md (top entry)"] = match.group(1) if match else None
    if tag is not None:
        versions["tag"] = tag[1:] if tag.startswith("v") else tag
    if len(set(versions.values())) != 1:
        add("versions differ: " + ", ".join(f"{k}={v}" for k, v in versions.items()))
    if tag is not None and re.search(r"^## \d+\.\d+\.\d+ — unreleased", changelog, re.M | re.I):
        add("a release tag must not point at a changelog that still says 'unreleased'")

    # -- Public network presets (ADR 0004): a tag ships only presets the maintainer verified ------
    if tag is not None:
        presets = tree.read(f"{DOMAIN}/core/meshbeacon/networks.json")
        try:
            listed = json.loads(presets)["networks"] if presets is not None else []
        except (ValueError, KeyError, TypeError):
            add("networks.json cannot be parsed")
            listed = []
        for item in listed:
            if not isinstance(item, dict) or not item.get("release_checks_passed_on"):
                name = item.get("id") if isinstance(item, dict) else item
                add(f"network preset {name!r} has no recorded release checks (ADR 0004 V1–V7)")

    # -- No tests or test-only bindings in the image's build context -----------------------------
    for path in files:
        if path.startswith(f"{DOMAIN}/") and TEST_ONLY.search(path[len(DOMAIN) + 1 :]):
            add(f"test-only file inside the app's build context: {path}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", help="a git ref to check instead of the working tree (for example a tag)")
    parser.add_argument("--tag", help="the release tag; its version must match")
    args = parser.parse_args(argv)
    problems = check(Tree(ROOT, args.ref), args.tag)
    for problem in problems:
        print(f"✖ {problem}")
    if not problems:
        print("✔ release layout: app repository, Marketplace and versions are consistent")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
