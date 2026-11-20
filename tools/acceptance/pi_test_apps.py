# SPDX-License-Identifier: Apache-2.0
"""Make the M4 Raspberry Pi acceptance apps (MS-1, MS-18) from an app folder.

    python3 tools/acceptance/pi_test_apps.py <output dir> [--v02 <v0.2 app folder>]

Writes up to three Home Assistant local app (formerly add-on) folders, each to be copied into the
device's local apps folder beside, never over, the installed ``meshbeacon`` app:

| Folder             | Built from                     | Image                                  |
|--------------------|--------------------------------|----------------------------------------|
| ``meshbeacon_v02`` | ``--v02`` (``main``'s folder)  | v0.2 production (the MS-1 baseline)    |
| ``meshbeacon_m4p`` | this repository's ``meshbeacon`` | M4 production (the default target)   |
| ``meshbeacon_m4d`` | this repository's ``meshbeacon`` | M4 ``messaging-dev`` (messaging on)  |

Each copy has its **own slug**, so the Supervisor installs it as a separate app with its own
``/data``: the installed app, its identity and its options are never touched, and no copy is
offered as an update of it. The only changes, each checked after it is made:

- ``config.yaml``: ``slug``, ``name``, ``description`` and ``boot: manual`` (never started by a
  reboot of the live installation). Options, schema, permissions and everything else unchanged.
- ``meshbeacon_m4d`` only: the Dockerfile's last line, ``FROM app AS production``, is removed, so
  the Supervisor (which builds the last stage) builds the approved ``messaging-dev`` stage; and
  the AppArmor profile gains the one rule CI adds for that image (``ci.yaml``,
  "Messaging engine confined by AppArmor"): ``/run/meshbeacon-messaging/{,**} rw,``. The production
  profile in the repository is not changed.

Nothing is written outside the output directory, and nothing is sent anywhere.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "meshbeacon"
LIVE_SLUG = "meshbeacon"
PRODUCTION_STAGE = "FROM app AS production"
IO_RULE = "  /run/meshbeacon-io/{,**} rw,"
DEV_RULE = "  /run/meshbeacon-messaging/{,**} rw,"
NOTE = "Acceptance test copy (M4). Not for daily use; uninstall after testing."

APPS = {
    "meshbeacon_v02": ("MeshBeacon test: v0.2 baseline", "v0.2 production image, for MS-1."),
    "meshbeacon_m4p": ("MeshBeacon test: M4 production", "M4 production image, messaging absent (MS-1)."),
    "meshbeacon_m4d": ("MeshBeacon test: M4 messaging", "M4 messaging-dev image, messaging on (MS-18)."),
}
CHANGED_KEYS = {"slug", "name", "description", "boot"}


def replace_line(text: str, old: str, new: str) -> str:
    lines = text.split("\n")
    hits = [i for i, line in enumerate(lines) if line == old]
    if len(hits) != 1:
        raise SystemExit(f"expected exactly one line {old!r}, found {len(hits)}")
    lines[hits[0]] = new
    return "\n".join(lines)


def make_config(text: str, slug: str, name: str, description: str) -> str:
    before = yaml.safe_load(text)
    if before.get("slug") != LIVE_SLUG:
        raise SystemExit(f"unexpected source slug {before.get('slug')!r}")
    text = replace_line(text, f"slug: {LIVE_SLUG}", f"slug: {slug}")
    text = replace_line(text, f"name: {before['name']}", f'name: "{name}"')
    text = replace_line(text, f"description: {before['description']}", f'description: "{description} {NOTE}"')
    text = replace_line(text, f"boot: {before['boot']}", "boot: manual")
    after = yaml.safe_load(text)
    changed = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    if changed != CHANGED_KEYS or after["slug"] != slug or after["boot"] != "manual":
        raise SystemExit(f"config.yaml changed more than intended: {sorted(changed)}")
    return text


def make_dev_dockerfile(text: str) -> str:
    lines = text.rstrip("\n").split("\n")
    if lines[-1] != PRODUCTION_STAGE or "FROM app AS messaging-dev" not in lines:
        raise SystemExit("the Dockerfile does not end with the production alias after messaging-dev")
    lines = lines[:-1]
    while lines and (not lines[-1].strip() or lines[-1].startswith("#")):
        lines.pop()  # the alias's comment and blank lines
    stages = [line for line in lines if line.startswith("FROM ")]
    if not stages[-1].startswith("FROM app AS messaging-dev"):
        raise SystemExit("the last stage is not messaging-dev")
    return "\n".join(lines) + "\n"


def make_dev_apparmor(text: str) -> str:
    if DEV_RULE in text.split("\n"):
        raise SystemExit("the production profile already allows the engine's socket folder")
    return replace_line(text, IO_RULE, IO_RULE + "\n" + DEV_RULE)


def build(source: Path, target: Path, slug: str, dev: bool) -> None:
    if target.exists():
        raise SystemExit(f"{target} exists; choose an empty output directory")
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    name, description = APPS[slug]
    config = target / "config.yaml"
    config.write_text(make_config(config.read_text(), slug, name, description))
    if dev:
        dockerfile = target / "Dockerfile"
        dockerfile.write_text(make_dev_dockerfile(dockerfile.read_text()))
        profile = target / "apparmor.txt"
        profile.write_text(make_dev_apparmor(profile.read_text()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path)
    parser.add_argument("--v02", type=Path, help="the v0.2 app folder (from main), for the MS-1 baseline")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.v02:
        build(args.v02, args.output / "meshbeacon_v02", "meshbeacon_v02", dev=False)
    build(SOURCE, args.output / "meshbeacon_m4p", "meshbeacon_m4p", dev=False)
    build(SOURCE, args.output / "meshbeacon_m4d", "meshbeacon_m4d", dev=True)
    for folder in sorted(args.output.iterdir()):
        print(f"{folder.name}: slug {yaml.safe_load((folder / 'config.yaml').read_text())['slug']}")


if __name__ == "__main__":
    main()
