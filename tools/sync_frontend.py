# SPDX-License-Identifier: Apache-2.0
"""Bundle the shared frontend in the app's Docker context; --check detects any drift."""

from __future__ import annotations

import argparse
import shutil

from build_knowledge import build
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "custom_components/meshbeacon/frontend"
TARGET = ROOT / "meshbeacon/frontend"


def sync(check: bool = False) -> bool:
    wanted = {p.relative_to(SOURCE): p.read_bytes() for p in SOURCE.rglob("*") if p.is_file()}
    if (ROOT / "content/knowledge/manifest.json").is_file():
        wanted[Path("knowledge.json")] = build(ROOT)
    existing = {p.relative_to(TARGET): p.read_bytes() for p in TARGET.rglob("*") if p.is_file()}
    if check:
        return wanted == existing
    if TARGET.exists():
        shutil.rmtree(TARGET)
    for path, data in wanted.items():
        target = TARGET / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    raise SystemExit(0 if sync(parser.parse_args().check) else "Run python tools/sync_frontend.py")
