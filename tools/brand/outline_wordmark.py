# SPDX-License-Identifier: Apache-2.0
"""Outline the ito wordmark and tagline from Inter into SVG paths (branding/src).

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
    word = outline(bold, "ito", 100, tracking=-0.02)
    tagline = outline(medium, "THE INTERNET, REIMAGINED", 100, tracking=0.18)
    (SRC / "wordmark.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {float(word["width"]):.0f} 100">\n{HEADER}'
        '  <!-- ito wordmark (master): "ito", always lower case, in Inter Bold (700) with -0.02 em\n'
        "       tracking, outlined to paths so no font is needed. Regenerate with\n"
        "       tools/brand/outline_wordmark.py (Inter 5.3.0, SIL OFL 1.1; see branding/fonts/OFL.txt).\n"
        "       Units as Inter at 100: ascent 96.88, cap height 72.75. -->\n"
        "  <title>ito</title>\n"
        "  <style>.word{fill:#284C40}</style>\n"
        f'  <path class="word" d="{word["d"]}"/>\n'
        "</svg>\n"
    )
    (SRC / "tagline.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {float(tagline["width"]):.0f} 100">\n{HEADER}'
        '  <!-- Tagline, "The internet, reimagined.", set in capitals for the logo lockup:\n'
        "       Inter Medium (500), 0.18 em tracking, outlined to paths (tools/brand/outline_wordmark.py). -->\n"
        "  <title>The internet, reimagined</title>\n"
        "  <style>.tagline{fill:#496A5D}</style>\n"
        f'  <path class="tagline" d="{tagline["d"]}"/>\n'
        "</svg>\n"
    )
    print("wrote branding/src/wordmark.svg and tagline.svg; now run tools/brand/build.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
