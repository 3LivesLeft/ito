// SPDX-License-Identifier: Apache-2.0
// The MeshBeacon interface stylesheet: design tokens (../tokens.js) and component styles. Shared
// by every delivery (integration panel today; the built-in interface later). docs/branding.md §6.

import { baseCss, themeCss } from "../tokens.js";

export const STYLE = `
:host {
  ${baseCss()}
  ${themeCss("light")}
  display: block;
  min-height: 100vh;
  background: var(--mb-bg);
  color: var(--mb-text);
  font-family: var(--mb-font);
  font-weight: 400;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
:host([data-theme="dark"]) { ${themeCss("dark")} }
@media (prefers-color-scheme: dark) { :host(:not([data-theme])) { ${themeCss("dark")} } }
* { box-sizing: border-box; }
/* Brand header: mark, wordmark, navigation. Surfaces follow the Home Assistant theme. */
header {
  position: sticky; top: 0; z-index: 2;
  display: flex; align-items: center; gap: var(--mb-space-md);
  min-height: var(--header-height, 56px); padding: 0 var(--mb-space-lg);
  background: var(--mb-surface);
  border-bottom: 1px solid var(--mb-line);
}
.brand { display: flex; align-items: center; gap: var(--mb-space-sm); flex: 1; min-width: 0; margin: 0; font-size: 20px; font-weight: 600; letter-spacing: -0.01em; }
.brand svg { width: 32px; height: 32px; flex: none; }
.brand .beacon { color: var(--mb-accent-text); }
header select { font: inherit; font-size: 14px; color: inherit; background: var(--mb-surface); border: 1px solid var(--mb-line); border-radius: var(--mb-radius-sm); padding: 6px 8px; min-height: 32px; }
nav[role="tablist"] {
  display: flex; gap: var(--mb-space-xs); padding: 0 var(--mb-space-lg); overflow-x: auto;
  background: var(--mb-surface); border-bottom: 1px solid var(--mb-line);
}
nav button {
  font: inherit; font-size: 14px; font-weight: 500; color: var(--mb-muted);
  background: none; border: 0; border-bottom: 2px solid transparent;
  padding: 12px var(--mb-space-md) 10px; min-height: 44px; cursor: pointer;
}
nav button:hover { color: var(--mb-text); }
nav button[aria-selected="true"] { color: var(--mb-accent-text); border-bottom-color: var(--mb-accent); }
:focus-visible { outline: 2px solid var(--mb-accent); outline-offset: 2px; border-radius: 4px; }
main { max-width: 1280px; margin: 0 auto; padding: var(--mb-space-lg); display: grid; gap: var(--mb-space-lg); }
@media (min-width: 870px) { main { padding: var(--mb-space-xl); gap: 20px; } }
.card {
  background: var(--mb-surface); border-radius: var(--mb-radius-md);
  border: 1px solid var(--mb-line);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  padding: var(--mb-space-lg);
}
h2 { font-size: 16px; font-weight: 600; margin: 0; letter-spacing: -0.005em; }
.muted { color: var(--mb-muted); }
.small { font-size: 13px; line-height: 1.5; }
[data-tone="good"] { --tone: var(--mb-good); --tone-text: var(--mb-good-text); }
[data-tone="warn"] { --tone: var(--mb-warn); --tone-text: var(--mb-warn-text); }
[data-tone="bad"] { --tone: var(--mb-bad); --tone-text: var(--mb-bad-text); }
[data-tone="info"] { --tone: var(--mb-info); --tone-text: var(--mb-info-text); }
[data-tone="neutral"] { --tone: var(--mb-neutral); --tone-text: var(--mb-neutral-text); }
/* Connectivity hero: colour plus a written state and an icon shape, never colour alone. */
.hero { display: grid; gap: var(--mb-space-lg); grid-template-columns: auto 1fr; align-items: center; border-left: 4px solid var(--tone); }
.status-mark { width: 56px; height: 56px; border-radius: 50%; display: grid; place-items: center;
  background: color-mix(in srgb, var(--tone) 14%, transparent); color: var(--tone-text); }
.status-mark svg { width: 30px; height: 30px; }
.hero .title { font-size: 24px; font-weight: 600; margin: 0 0 2px; letter-spacing: -0.01em; }
.chips { display: flex; flex-wrap: wrap; gap: var(--mb-space-sm); margin-top: 10px; }
.chip { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 500;
  padding: 3px 10px; border-radius: var(--mb-radius-pill); color: var(--tone-text, var(--mb-muted));
  background: color-mix(in srgb, var(--tone, var(--mb-neutral)) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--tone, var(--mb-neutral)) 30%, transparent); }
.chip::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--tone, var(--mb-neutral)); }
.tiles { display: grid; gap: var(--mb-space-md); grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
@media (min-width: 870px) { .tiles { grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--mb-space-lg); } }
.tile { display: flex; flex-direction: column; gap: 6px; min-height: 112px; }
.tile .label { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 500; color: var(--mb-muted); }
.tile .label ha-icon { --mdc-icon-size: 18px; color: var(--mb-accent-text); }
.value { font-size: 34px; line-height: 1.1; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; overflow-wrap: anywhere; }
.value .u { font-size: 16px; font-weight: 500; color: var(--mb-muted); margin-left: 4px; letter-spacing: 0; }
.charts { display: grid; gap: var(--mb-space-lg); grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr)); }
.charts .wide { grid-column: 1 / -1; }
.chart-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--mb-space-sm); flex-wrap: wrap; margin-bottom: var(--mb-space-sm); }
.legend { display: flex; gap: var(--mb-space-md); font-size: 13px; color: var(--mb-muted); font-variant-numeric: tabular-nums; }
.legend span::before { content: ""; display: inline-block; width: 12px; height: 3px; border-radius: 2px; margin-right: 6px; vertical-align: middle; background: var(--c); }
.plot { position: relative; }
.plot svg { display: block; width: 100%; height: 150px; overflow: visible; touch-action: pan-y; }
.plot .grid { stroke: var(--mb-line); stroke-width: 1; vector-effect: non-scaling-stroke; }
.plot .line { fill: none; stroke-width: 2; vector-effect: non-scaling-stroke; stroke-linejoin: round; }
.plot .area { opacity: 0.12; }
.plot .dot { fill: none; stroke-width: 7; stroke-linecap: round; vector-effect: non-scaling-stroke; }
.plot .cursor { visibility: hidden; stroke: var(--mb-muted); stroke-width: 1; vector-effect: non-scaling-stroke; stroke-dasharray: 3 3; }
.axis { display: flex; justify-content: space-between; font-size: 12px; color: var(--mb-muted); margin-top: 6px; }
.ymax { position: absolute; top: -2px; right: 0; font-size: 12px; color: var(--mb-muted); background: var(--mb-surface); padding: 0 0 0 4px; }
.empty { display: grid; place-items: center; height: 150px; text-align: center; color: var(--mb-muted); font-size: 14px; padding: 0 var(--mb-space-lg); }
.seg { display: inline-flex; border: 1px solid var(--mb-line); border-radius: var(--mb-radius-pill); overflow: hidden; background: var(--mb-surface); }
.seg button { font: inherit; font-size: 13px; font-weight: 500; color: var(--mb-muted); background: none; border: 0; padding: 6px 14px; min-height: 32px; cursor: pointer; }
.seg button[aria-pressed="true"] { color: var(--mb-accent-text); background: color-mix(in srgb, var(--mb-accent) 14%, transparent); }
.section-head { display: flex; align-items: center; justify-content: space-between; gap: var(--mb-space-md); flex-wrap: wrap; }
.section-head h2 { font-size: 18px; }
.peers { display: grid; gap: var(--mb-space-md); grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); }
.peer { display: grid; gap: 10px; border-left: 4px solid var(--tone); }
.peer .name { font-size: 17px; font-weight: 600; overflow-wrap: anywhere; }
dl { margin: 0; }
.peer dl { display: grid; grid-template-columns: 1fr auto; gap: 4px var(--mb-space-md); font-size: 14px; }
.peer dt { color: var(--mb-muted); }
.peer dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; font-weight: 500; }
.banner { display: flex; gap: var(--mb-space-md); align-items: flex-start; border-left: 4px solid var(--tone); }
.banner strong { display: block; margin-bottom: 2px; font-weight: 600; }
.rows { display: grid; grid-template-columns: minmax(0, 1fr) auto; }
.messaging { display: grid; gap: 10px; border-left: 4px solid var(--tone); }
.messaging .address { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.messaging code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 14px; overflow-wrap: anywhere; user-select: all; padding: 4px 6px; border: 1px solid var(--mb-line); border-radius: 6px; }
.messaging .copy { font: inherit; font-size: 13px; padding: 4px 10px; border-radius: 6px; border: 1px solid var(--mb-line); background: transparent; color: inherit; cursor: pointer; min-height: 32px; }
.messaging ol { margin: 8px 0; padding-left: 20px; display: grid; gap: 4px; }
.messaging summary { cursor: pointer; font-weight: 500; }
.rows dt, .rows dd { padding: 10px 0; border-bottom: 1px solid var(--mb-line); margin: 0; font-size: 14px; }
.rows dt { color: var(--mb-muted); }
.rows dd { text-align: right; font-variant-numeric: tabular-nums; padding-left: var(--mb-space-md); font-weight: 500; }
.rows dt:last-of-type, .rows dd:last-of-type { border-bottom: 0; }
.btn { font: inherit; font-weight: 600; color: var(--mb-on-accent); background: var(--mb-accent-text); border: 0; border-radius: var(--mb-radius-pill); padding: 10px 20px; min-height: 44px; cursor: pointer; }
:host([data-theme="dark"]) .btn { background: var(--mb-accent); }
.skeleton { background: color-mix(in srgb, var(--mb-line) 70%, transparent); border-radius: var(--mb-radius-md); animation: pulse 1.6s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: 0.55; } }
@media (prefers-reduced-motion: reduce) { .skeleton { animation: none; } * { scroll-behavior: auto !important; transition: none !important; } }
.center { max-width: 560px; margin: 48px auto; text-align: center; display: grid; gap: var(--mb-space-md); justify-items: center; padding: var(--mb-space-xxl) var(--mb-space-xl); }
.center .art { width: 96px; height: 96px; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
/* Brand mark, coloured by tokens so it follows the theme. */
.mk-ring, .mk-wave { fill: none; stroke: var(--mb-accent); stroke-linecap: round; }
.mk-tower { fill: var(--mb-text); }
.mk-lamp { fill: #F59E0B; }
.mk-hillback { fill: color-mix(in srgb, var(--mb-accent) 8%, var(--mb-surface)); stroke: var(--mb-accent); stroke-linejoin: round; }
.mk-hill { fill: color-mix(in srgb, var(--mb-accent) 16%, var(--mb-surface)); stroke: var(--mb-accent); stroke-linejoin: round; }
.mk-link { fill: none; stroke: var(--mb-accent); stroke-linecap: round; stroke-linejoin: round; }
.mk-node { fill: var(--mb-text); stroke: var(--mb-accent); }
`;
