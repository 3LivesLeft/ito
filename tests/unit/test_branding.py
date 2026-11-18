# SPDX-License-Identifier: Apache-2.0
"""Brand assets (docs/branding.md): present, current, the sizes Home Assistant expects, optimised,
and safe (no scripts, no external references)."""

import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BRANDING = ROOT / "branding"
BRAND = ROOT / "custom_components" / "meshbeacon" / "brand"
APP = ROOT / "meshbeacon"


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    return struct.unpack(">II", data[16:24])


def test_generated_assets_match_the_masters():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "brand" / "build.py"), "--check"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("path", sorted((BRANDING / "src").glob("*.svg")) + sorted((BRANDING / "svg").glob("*.svg")))
def test_svgs_are_safe_and_valid(path):
    text = path.read_text()
    ET.fromstring(text)  # well-formed
    assert "<script" not in text.lower()
    assert not re.search(r"\bon[a-z]+\s*=", text)  # no event handlers
    assert not re.search(r"(?:href|src)\s*=|url\(|@import", text)  # nothing external or embedded
    assert "<title>" in text  # accessible name
    assert "filter" not in text and "Gradient" not in text  # design rule: no glows or gradients


EXPECTED = {
    # Home Assistant app store and app page: icon square (128 recommended); logo about 250 x 100.
    APP / "icon.png": (128, 128),
    APP / "logo.png": (250, 100),
    BRANDING / "png" / "favicon-16.png": (16, 16),
    BRANDING / "png" / "favicon-32.png": (32, 32),
    BRANDING / "png" / "favicon-64.png": (64, 64),
}


@pytest.mark.parametrize(("path", "size"), EXPECTED.items(), ids=lambda v: getattr(v, "name", str(v)))
def test_fixed_sizes(path, size):
    assert png_size(path) == size


def test_integration_brand_images_follow_home_assistant_rules():
    """components/brands: allowed names only; icon 256 (@2x 512); logo shortest side 128 (@2x 256)."""
    allowed = {f"{p}{n}{s}.png" for p in ("", "dark_") for n in ("icon", "logo") for s in ("", "@2x")}
    assert {p.name for p in BRAND.iterdir()} == allowed
    for prefix in ("", "dark_"):
        assert png_size(BRAND / f"{prefix}icon.png") == (256, 256)
        assert png_size(BRAND / f"{prefix}icon@2x.png") == (512, 512)
        assert min(png_size(BRAND / f"{prefix}logo.png")) == 128
        assert min(png_size(BRAND / f"{prefix}logo@2x.png")) == 256


def test_pngs_are_optimised():
    pngs = [*(BRANDING / "png").glob("*.png"), *BRAND.glob("*.png"), APP / "icon.png", APP / "logo.png"]
    assert len(pngs) >= 30
    for path in pngs:
        w, h = png_size(path)
        assert path.stat().st_size <= max(4096, w * h // 8), f"{path.name}: {path.stat().st_size} bytes"
    assert sum(p.stat().st_size for p in pngs) < 400_000


def test_font_licence_is_shipped():
    for path in (
        BRANDING / "fonts" / "OFL.txt",
        ROOT / "custom_components/meshbeacon/frontend/fonts/inter-5.3.0/OFL.txt",
    ):
        assert "SIL Open Font License, Version 1.1" in path.read_text()
    assert "Inter" in (ROOT / "THIRD_PARTY_NOTICES").read_text()
