// SPDX-License-Identifier: Apache-2.0
// ito design tokens (docs/branding.md). The single source for the interface's colours,
// type, spacing and shape; future views (messaging, I2P, LoRa) use these, never raw values.
// tests/frontend/tokens.test.mjs checks that text and status colours meet WCAG 2.2 AA.

export const BRAND = Object.freeze({
  forest: "#0B1A14", // dark background and brand ink
  deep: "#1F4D3A", // deep moss: accessible brand accent on light surfaces
  leaf: "#3E8F6E", // secondary brand accent
  sage: "#A6C9B2", // accent on dark surfaces; the thread in the mark
  mist: "#E8F3ED", // pale brand background
  sky: "#0EA5E9", // information and charts
  emerald: "#10B981", // success / online
  amber: "#F59E0B", // warning
  red: "#EF4444", // error / offline
  navy: "#0B1A14", // forest background from the approved creative direction
  offWhite: "#E8F3ED", // mist background, light text
  slate: "#0B1A14", // forest ink
});

// Per theme. "*Text" variants are for text and small marks on the surface (contrast >= 4.5:1);
// the plain colours are for fills, bars and indicators next to a text label (>= 3:1).
export const THEMES = Object.freeze({
  light: Object.freeze({
    bg: BRAND.offWhite,
    surface: "#FFFFFF",
    text: BRAND.slate,
    muted: "#475569",
    line: "#E2E8F0",
    accent: BRAND.deep,
    accentText: BRAND.deep,
    good: "#059669",
    goodText: "#047857",
    warn: "#D97706",
    warnText: "#B45309",
    bad: "#DC2626",
    badText: "#B91C1C",
    info: "#0284C7",
    infoText: "#0369A1",
    neutral: "#64748B",
    neutralText: "#475569",
    series1: "#0284C7",
    series2: "#7C3AED",
    onAccent: "#FFFFFF",
  }),
  dark: Object.freeze({
    bg: BRAND.navy,
    surface: "#1F4D3A",
    text: BRAND.offWhite,
    muted: "#94A3B8",
    line: "#1E293B",
    accent: BRAND.sage,
    accentText: BRAND.sage,
    good: BRAND.emerald,
    goodText: "#34D399",
    warn: BRAND.amber,
    warnText: "#FBBF24",
    bad: BRAND.red,
    badText: "#F87171",
    info: BRAND.sky,
    infoText: "#38BDF8",
    neutral: "#64748B",
    neutralText: "#94A3B8",
    series1: BRAND.sky,
    series2: "#A78BFA",
    onAccent: BRAND.navy,
  }),
});

export const TYPE = Object.freeze({
  family: '"ito Inter", Inter, var(--ha-font-family-body, system-ui), system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  regular: 400, // body
  medium: 500, // labels, navigation
  semibold: 600, // headings
  bold: 700, // prominent figures
});

export const SPACE = Object.freeze({ xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 });
export const RADIUS = Object.freeze({ sm: 8, md: 12, lg: 16, pill: 999 });

const kebab = (key) => key.replace(/[A-Z0-9]+/g, (m) => `-${m.toLowerCase()}`);

/**
 * CSS custom properties for one theme. Home Assistant's own surface and text variables win when
 * they exist (inside Home Assistant), so the user's theme is respected; brand colours are the
 * fallbacks (preview, future built-in interface) and always provide accent and status colours.
 */
export function themeCss(name) {
  const t = THEMES[name];
  const ha = {
    bg: "--primary-background-color",
    surface: "--card-background-color",
    text: "--primary-text-color",
    muted: "--secondary-text-color",
    line: "--divider-color",
  };
  return Object.entries(t)
    .map(([key, value]) => `--mb-${kebab(key)}: ${ha[key] ? `var(${ha[key]}, ${value})` : value};`)
    .join(" ");
}

export function baseCss() {
  return [
    `--mb-font: ${TYPE.family};`,
    ...Object.entries(SPACE).map(([k, v]) => `--mb-space-${k}: ${v}px;`),
    ...Object.entries(RADIUS).map(([k, v]) => `--mb-radius-${k}: ${v}px;`),
  ].join(" ");
}
