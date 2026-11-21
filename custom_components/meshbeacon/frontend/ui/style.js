// SPDX-License-Identifier: Apache-2.0
// The ito interface stylesheet: design tokens (../tokens.js) and component styles. Shared
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
.slot { display: contents; }
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
.brand .word { color: var(--mb-accent-text); font-weight: 700; letter-spacing: -0.02em; }
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
.mk-globe, .mk-grid { fill: none; stroke: var(--mb-accent-text); stroke-linecap: round; }
.mk-thread { fill: none; stroke: #A6C9B2; stroke-linecap: round; } /* sage in both themes, as in the logo */
.mk-node { fill: var(--mb-accent-text); }
/* Messages (M5): two columns on wide screens; on narrow ones the list, or one conversation. */
.messages-main { max-width: 1280px; }
.msg { display: grid; gap: var(--mb-space-md); }
.msg-status { display: flex; flex-wrap: wrap; align-items: center; gap: var(--mb-space-sm); }
.msg-status > span { display: inline-flex; flex-wrap: wrap; align-items: center; gap: var(--mb-space-sm); }
.msg-panes { display: grid; gap: var(--mb-space-lg); grid-template-columns: minmax(0, 1fr); }
@media (min-width: 870px) { .msg-panes { grid-template-columns: minmax(280px, 360px) minmax(0, 1fr); align-items: start; } }
@media (max-width: 869px) { .msg[data-open="true"] .msg-list { display: none; } .msg:not([data-open="true"]) .msg-chat { display: none; } }
@media (min-width: 870px) { .chat-head .back { display: none; } }
.msg-list, .msg-chat { display: grid; gap: var(--mb-space-md); align-content: start; min-width: 0; }
.msg-chat { min-height: 420px; grid-template-rows: auto auto 1fr auto; }
.msg .address { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.msg code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; overflow-wrap: anywhere; user-select: all; padding: 3px 6px; border: 1px solid var(--mb-line); border-radius: 6px; }
.msg .copy, .btn-quiet { font: inherit; font-size: 13px; font-weight: 500; padding: 6px 12px; border-radius: var(--mb-radius-pill); border: 1px solid var(--mb-line); background: transparent; color: var(--mb-accent-text); cursor: pointer; min-height: 36px; display: inline-flex; align-items: center; gap: 6px; }
.btn-quiet ha-icon { --mdc-icon-size: 18px; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.label { color: var(--mb-muted); font-weight: 500; margin-bottom: 4px; }
.msg-error { color: var(--mb-bad-text); margin: 0; }
.msg-error:empty { display: none; }
.empty-state .title { font-weight: 600; margin: 0 0 4px; }
.empty-state ol { margin: 0; padding-left: 20px; display: grid; gap: 6px; }
.add-form { display: grid; gap: 6px; padding: var(--mb-space-md); border: 1px solid var(--mb-line); border-radius: var(--mb-radius-sm); }
.add-form .row { display: flex; gap: var(--mb-space-sm); flex-wrap: wrap; margin-top: 4px; }
.msg input[type="text"], .msg textarea { font: inherit; font-size: 15px; color: var(--mb-text); background: var(--mb-bg); border: 1px solid var(--mb-line); border-radius: var(--mb-radius-sm); padding: 9px 12px; width: 100%; min-height: 44px; }
.msg input.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 14px; }
.conversations { list-style: none; margin: 0 calc(-1 * var(--mb-space-sm)); padding: 0; display: grid; gap: 2px; }
.conversation { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 12px; align-items: center; width: 100%; text-align: left; font: inherit; color: inherit; background: none; border: 0; border-radius: var(--mb-radius-sm); padding: 10px var(--mb-space-sm); cursor: pointer; min-height: 56px; }
.conversation:hover { background: color-mix(in srgb, var(--mb-accent) 6%, transparent); }
.conversation[aria-current="true"] { background: color-mix(in srgb, var(--mb-accent) 12%, transparent); }
.avatar { width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; flex: none; font-weight: 600; font-size: 15px; color: var(--mb-accent-text); background: color-mix(in srgb, var(--mb-accent) 14%, var(--mb-surface)); }
.who { display: grid; min-width: 0; }
.who .name, .chat-head h2 { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.who .preview { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meta { display: grid; justify-items: end; gap: 4px; }
.badge { min-width: 22px; height: 22px; padding: 0 7px; border-radius: var(--mb-radius-pill); background: var(--mb-accent-text); color: var(--mb-on-accent); font-size: 12px; font-weight: 700; display: grid; place-items: center; }
:host([data-theme="dark"]) .badge { background: var(--mb-accent); }
.chat-head { display: flex; align-items: center; gap: 12px; padding-bottom: var(--mb-space-md); border-bottom: 1px solid var(--mb-line); min-width: 0; }
.chat-head .who { flex: 1; }
.chat-head h2:focus { outline: none; }
.chat-head input { flex: 1; }
.menu { position: relative; }
.menu summary { list-style: none; cursor: pointer; min-width: 40px; min-height: 40px; display: grid; place-items: center; border-radius: 50%; color: var(--mb-muted); }
.menu summary::-webkit-details-marker { display: none; }
.menu summary:not(:has(ha-icon))::before { content: "⋮"; font-size: 20px; }
.menu-items { position: absolute; right: 0; top: 44px; z-index: 3; display: grid; min-width: 210px; padding: 6px; background: var(--mb-surface); border: 1px solid var(--mb-line); border-radius: var(--mb-radius-sm); box-shadow: 0 6px 24px rgba(15, 23, 42, 0.16); }
.menu-items button { font: inherit; font-size: 14px; text-align: left; padding: 10px 12px; min-height: 40px; background: none; border: 0; border-radius: 6px; color: inherit; cursor: pointer; }
.menu-items button:hover { background: color-mix(in srgb, var(--mb-accent) 8%, transparent); }
.menu-items .danger { color: var(--mb-bad-text); }
.log { display: flex; flex-direction: column; gap: 6px; overflow-y: auto; max-height: min(62vh, 640px); min-height: 240px; padding: 4px 2px; overscroll-behavior: contain; }
.log .older { align-self: center; }
.day { align-self: center; padding: 8px 0 2px; font-weight: 500; }
.bubble { max-width: min(78%, 560px); padding: 8px 12px; border-radius: 16px; display: grid; gap: 2px; }
.bubble.in { align-self: flex-start; background: color-mix(in srgb, var(--mb-neutral) 12%, var(--mb-surface)); border: 1px solid var(--mb-line); border-bottom-left-radius: 4px; }
.bubble.out { align-self: flex-end; background: color-mix(in srgb, var(--mb-accent) 16%, var(--mb-surface)); border: 1px solid color-mix(in srgb, var(--mb-accent) 30%, transparent); border-bottom-right-radius: 4px; }
.bubble.auto { opacity: 0.8; font-style: italic; }
.bubble.local { opacity: 0.7; }
.bubble .text { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 15px; }
.auto-label { color: var(--mb-muted); font-style: normal; font-weight: 500; }
.bubble-meta { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 4px 10px; color: var(--mb-muted); font-style: normal; }
.bubble.in .bubble-meta { justify-content: flex-start; }
.bubble-meta .state { display: inline-flex; align-items: center; gap: 3px; color: var(--tone-text); font-weight: 500; }
.bubble-meta .state ha-icon { --mdc-icon-size: 15px; }
.bubble-meta .retry { min-height: 28px; padding: 2px 10px; }
.chat-empty { display: grid; place-items: center; text-align: center; min-height: 200px; }
.composer { display: grid; gap: 6px; padding-top: var(--mb-space-md); border-top: 1px solid var(--mb-line); }
.composer-row { display: flex; gap: var(--mb-space-sm); align-items: flex-end; }
.composer textarea { resize: none; max-height: 200px; line-height: 1.4; }
.composer .send { flex: none; }
.composer p { margin: 0; }
.composer p[hidden], .counter:empty { display: none; }
.composer-note { margin: 0; padding-top: var(--mb-space-md); border-top: 1px solid var(--mb-line); }
@media (max-width: 869px) { .chat-head .avatar { display: none; } .chat-head { gap: 8px; } .chat-head code { font-size: 12px; } .bubble { max-width: 88%; } .log { max-height: calc(100vh - 300px); } }
`;
