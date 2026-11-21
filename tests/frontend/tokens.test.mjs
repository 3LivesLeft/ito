// SPDX-License-Identifier: Apache-2.0
// WCAG 2.2 AA contrast of the design tokens (docs/branding.md), in both themes, on the brand
// surfaces and on Home Assistant's default theme surfaces (which the panel follows).

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";

import { BRAND, THEMES, baseCss, themeCss } from "../../custom_components/meshbeacon/frontend/tokens.js";

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export function contrast(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
}

// Home Assistant's default surfaces (frontend 20260930.5 default theme): light card #ffffff on
// #fafafa; dark card #1c1c1c on #111111.
const HA = { light: ["#FFFFFF", "#FAFAFA"], dark: ["#1C1C1C", "#111111"] };
const TEXT = ["text", "muted", "accentText", "goodText", "warnText", "badText", "infoText", "neutralText"];
const MARKS = ["good", "warn", "bad", "info", "neutral", "series1", "series2"]; // non-text, WCAG 1.4.11

for (const [name, t] of Object.entries(THEMES)) {
  const surfaces = [t.surface, t.bg, ...HA[name]];
  test(`${name}: text tokens reach 4.5:1 on every surface`, () => {
    for (const key of TEXT) {
      for (const surface of surfaces) {
        const ratio = contrast(t[key], surface);
        assert.ok(ratio >= 4.5, `${name}.${key} ${t[key]} on ${surface}: ${ratio.toFixed(2)}`);
      }
    }
  });
  test(`${name}: status and chart colours reach 3:1 on every surface`, () => {
    for (const key of MARKS) {
      for (const surface of surfaces) {
        const ratio = contrast(t[key], surface);
        assert.ok(ratio >= 3, `${name}.${key} ${t[key]} on ${surface}: ${ratio.toFixed(2)}`);
      }
    }
  });
  test(`${name}: text on the accent button reaches 4.5:1`, () => {
    const button = name === "light" ? t.accentText : t.accent; // as .btn in ui/style.js
    assert.ok(contrast(t.onAccent, button) >= 4.5, `${t.onAccent} on ${button}`);
  });
  test(`${name}: CSS falls back to Home Assistant's variables for surfaces only`, () => {
    const css = themeCss(name);
    assert.match(css, /--mb-surface: var\(--card-background-color, #/);
    assert.match(css, /--mb-good-text: #[0-9A-F]{6};/);
  });
}

test("brand colours are exactly those in docs/branding.md", () => {
  const doc = readFileSync(new URL("../../docs/branding.md", import.meta.url), "utf8");
  for (const hex of Object.values(BRAND)) assert.ok(doc.includes(hex), `${hex} missing from docs/branding.md`);
  assert.deepEqual(BRAND, {
    deep: "#284C40",
    sage: "#A6C9B2",
    mist: "#E8F3ED",
    sky: "#0EA5E9",
    emerald: "#10B981",
    amber: "#F59E0B",
    red: "#EF4444",
    navy: "#0B1220",
    offWhite: "#F8FAFC",
    slate: "#0F172A",
  });
});

test("brand text pairs: slate on off-white, off-white on navy and deep green on mist reach 4.5:1", () => {
  assert.ok(contrast(BRAND.slate, BRAND.offWhite) >= 4.5);
  assert.ok(contrast(BRAND.offWhite, BRAND.navy) >= 4.5);
  assert.ok(contrast(BRAND.deep, BRAND.mist) >= 4.5);
  assert.ok(contrast(BRAND.sage, BRAND.navy) >= 4.5);
});

test("every --mb-* variable the interface uses is defined by the tokens", () => {
  const defined = new Set((themeCss("light") + baseCss()).match(/--mb-[a-z0-9-]+/g));
  const root = new URL("../../custom_components/meshbeacon/frontend/", import.meta.url);
  const code = readdirSync(root, { recursive: true })
    .filter((n) => n.endsWith(".js") && n !== "tokens.js")
    .map((n) => readFileSync(new URL(n, root), "utf8"))
    .join("\n");
  const used = new Set(code.match(/var\(--mb-[a-z0-9-]+/g).map((v) => v.slice(4)));
  assert.ok(used.size > 20);
  for (const name of used) assert.ok(defined.has(name), `${name} is used but not defined`);
  assert.deepEqual(new Set(themeCss("dark").match(/--mb-[a-z0-9-]+/g)), new Set(themeCss("light").match(/--mb-[a-z0-9-]+/g)));
});
