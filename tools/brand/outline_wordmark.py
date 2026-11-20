# SPDX-License-Identifier: Apache-2.0
"""Outline the MeshBeacon wordmark and tagline from Inter into SVG paths (branding/src).

A developer tool, run rarely (only if the wordmark changes). It needs fontTools and brotli, which
are not project dependencies, and Inter's WOFF2 files (Inter 5.3.0 from the @fontsource/inter
package, SIL OFL 1.1). The outlines are written to branding/src/wordmark.svg and tagline.svg;
then run tools/brand/build.py.

    python -m venv /tmp/brand && /tmp/brand/bin/pip install fonttools brotli
    /tmp/brand/bin/python tools/brand/outline_wordmark.py \
        --fonts custom_components/meshbeacon/frontend/fonts/inter-5.3.0
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "branding" / "src"
HEADER = "  <!-- SPDX-License-Identifier: Apache-2.0 -->\n"


def outline(woff2: Path, text: str, size: float, tracking: float = 0.0) -> dict[str, float | str]:
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont

    font = TTFont(str(woff2))
    glyphs, cmap, upm = font.getGlyphSet(), font.getBestCmap(), font["head"].unitsPerEm
    scale, x, parts = size / upm, 0.0, []
    ascent = font["hhea"].ascent * scale
    for char in text:
        name = cmap[ord(char)]
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, ascent)))
        parts.append(pen.getCommands())
        x += font["hmtx"][name][0] * scale + tracking * size
    return {"d": _round("".join(parts)), "width": x - tracking * size}


def _round(d: str) -> str:
    return re.sub(r"-?\d+\.\d+", lambda m: f"{float(m.group()):.1f}".rstrip("0").rstrip("."), d)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fonts", type=Path, required=True, help="folder with inter-latin-{500,700}-normal.woff2")
    args = parser.parse_args()
    bold, medium = args.fonts / "inter-latin-700-normal.woff2", args.fonts / "inter-latin-500-normal.woff2"
    mesh, beacon = outline(bold, "Mesh", 100), outline(bold, "Beacon", 100)
    tagline = outline(medium, "DECENTRALISED CONNECTIVITY FOR YOUR HOME", 100, tracking=0.18)
    width = float(mesh["width"]) + float(beacon["width"])
    (SRC / "wordmark.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} 100">\n{HEADER}'
        '  <!-- MeshBeacon wordmark (master): "Mesh" and "Beacon" in Inter Bold (700), outlined to paths\n'
        "       so no font is needed. Regenerate with tools/brand/outline_wordmark.py (Inter 5.3.0,\n"
        "       SIL OFL 1.1; see branding/fonts/OFL.txt). Cap height 72.75, ascent 96.88 units. -->\n"
        "  <title>MeshBeacon</title>\n"
        "  <style>.mesh{fill:#F8FAFC}.beacon{fill:#0EA5E9}</style>\n"
        f'  <path class="mesh" d="{mesh["d"]}"/>\n'
        f'  <path class="beacon" transform="translate({float(mesh["width"]):.1f} 0)" d="{beacon["d"]}"/>\n'
        "</svg>\n"
    )
    (SRC / "tagline.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {float(tagline["width"]):.0f} 100">\n{HEADER}'
        '  <!-- Tagline, "Decentralised connectivity for your home.", set in capitals for the logo lockup:\n'
        "       Inter Medium (500), 0.18 em tracking, outlined to paths (tools/brand/outline_wordmark.py). -->\n"
        "  <title>Decentralised connectivity for your home</title>\n"
        "  <style>.tagline{fill:#CBD5E1}</style>\n"
        f'  <path class="tagline" d="{tagline["d"]}"/>\n'
        "</svg>\n"
    )
    print("wrote branding/src/wordmark.svg and tagline.svg; now run tools/brand/build.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
