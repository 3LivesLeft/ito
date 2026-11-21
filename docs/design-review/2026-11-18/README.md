# Design review pack: MeshBeacon branding and interface (18 Nov 2026)

For **independent design review** (roadmap BR-7). The reference is [docs/branding.md](../../branding.md).
Everything was captured in a sandbox. Nothing was taken from, or installed on, the maintainer's
Raspberry Pi.

| File | What | How |
|---|---|---|
| `brand-sheet.png` | Full logo, app icons (dark, light, mono light, mono dark), favicons 64/32/16, horizontal logo, the Home Assistant app `logo.png` and `icon.png`, palette | Composed from `branding/png` |
| `preview-{desktop,tablet,phone}-{light,dark}.png` | Overview at 1280, 820 and 390 px | `tools/panel_preview.html` (sample data matching the first physical readings) |
| `state-*.png` | Problem, app unavailable, error with retry, not connected, loading, the 2,048 known-paths note | Preview scenarios |
| `diagnostics-desktop-light.png` | Diagnostics tab | Preview |
| `ha-2026.11.2-*.png` | Inside a real Home Assistant 2026.11.2 (loopback test instance with a fake status API): the sidebar entry with `mdi:lighthouse-on`, the panel in light and dark themes, and the integration's brand icon under Settings → Devices & services | Playwright, after a real login |

The sample values in the real-HA captures come from the test fixture (for example "365 days").

**Checks run on these states:**
- axe-core 4.14.1, WCAG 2.0/2.1/2.2 A and AA rules: 0 violations in 12 combinations. Checks
  include the panel's shadow root (62 contrast checks inside it).
- Contrast tests for all tokens, in both themes, on the brand and HA default surfaces.
- No horizontal overflow at 320, 390, 820 and 1280 px.
- Inter loaded from local files only.
- Reduced motion honoured.

Questions for the reviewer:
1. Is the mark legible and distinctive at 16 and 32 px?
2. Is the app `logo.png` badge (navy tile) right for both of Home Assistant's themes?
3. Do the second chart colour (violet) and the status colours read as one family with the sky blue?
4. Inside Home Assistant the panel follows the user's theme for surfaces. Is the brand presence
   (mark, wordmark, accent, type) strong enough, or should the header use brand navy and
   off-white surfaces?
