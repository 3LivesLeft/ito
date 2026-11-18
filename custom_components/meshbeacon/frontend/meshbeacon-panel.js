// SPDX-License-Identifier: Apache-2.0
// MeshBeacon sidebar panel (ADR 0007). A plain custom element: no framework, no third-party code,
// no build step and no requests of its own beyond Home Assistant's authenticated websocket.
//
// Live values come from `hass.states`; history comes from Home Assistant's recorder
// (`history/history_during_period`, or hourly `recorder/statistics_during_period` for 7 days).
// Every value is written with textContent (never parsed as HTML), so names cannot inject markup.

import {
  CONNECTIVITY_TEXT,
  LABELS,
  RANGES,
  TABS,
  TONES,
  bucket,
  chartPaths,
  duration,
  formatNumber,
  isAvailable,
  lastValue,
  nodeState,
  numeric,
  pathsNote,
  peakValue,
  peerState,
  precision,
  secondsSince,
  seriesFromHistory,
  seriesFromStatistics,
  tabFromPath,
  unit,
} from "./model.js";

const BUCKETS = 120;
const CHART_W = 600;
const CHART_H = 150;
const SVG = "http://www.w3.org/2000/svg"; // XML namespace identifier, not a request

function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key in el && !key.includes("-")) el[key] = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function s(tag, attrs = {}) {
  const el = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}

function icon(name) {
  return customElements.get("ha-icon") ? h("ha-icon", { icon: name, "aria-hidden": "true" }) : null;
}

const STYLE = `
:host {
  --mb-bg: var(--primary-background-color, #f5f6f8);
  --mb-card: var(--ha-card-background, var(--card-background-color, #fff));
  --mb-text: var(--primary-text-color, #1c1d21);
  --mb-muted: var(--secondary-text-color, #5f6368);
  --mb-line: var(--divider-color, rgba(0, 0, 0, 0.12));
  --mb-good: var(--success-color, #2e7d32);
  --mb-warn: var(--warning-color, #ed6c02);
  --mb-bad: var(--error-color, #d32f2f);
  --mb-info: var(--info-color, #0288d1);
  --mb-neutral: var(--disabled-text-color, #8a8d93);
  --mb-rx: var(--primary-color, #03a9f4);
  --mb-tx: var(--accent-color, #ff9800);
  --mb-radius: var(--ha-card-border-radius, 12px);
  display: block;
  min-height: 100vh;
  background: var(--mb-bg);
  color: var(--mb-text);
  font-family: var(--ha-font-family-body, var(--paper-font-body1_-_font-family, system-ui, sans-serif));
  -webkit-font-smoothing: antialiased;
}
@media (prefers-color-scheme: dark) {
  :host(:not([data-theme="light"])) {
    --mb-bg: var(--primary-background-color, #111318);
    --mb-card: var(--ha-card-background, var(--card-background-color, #1c1f26));
    --mb-text: var(--primary-text-color, #e8eaed);
    --mb-muted: var(--secondary-text-color, #a0a4ab);
    --mb-line: var(--divider-color, rgba(255, 255, 255, 0.12));
  }
}
* { box-sizing: border-box; }
header {
  position: sticky; top: 0; z-index: 2;
  display: flex; align-items: center; gap: 8px;
  height: var(--header-height, 56px); padding: 0 16px;
  background: var(--app-header-background-color, var(--mb-card));
  color: var(--app-header-text-color, var(--mb-text));
  border-bottom: var(--app-header-border-bottom, 1px solid var(--mb-line));
}
header h1 { font-size: 20px; font-weight: 400; margin: 0; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
header select { font: inherit; color: inherit; background: transparent; border: 1px solid var(--mb-line); border-radius: 8px; padding: 4px 8px; }
nav[role="tablist"] {
  display: flex; gap: 4px; padding: 0 16px; overflow-x: auto;
  background: var(--app-header-background-color, var(--mb-card));
  border-bottom: 1px solid var(--mb-line);
}
nav button {
  font: inherit; font-size: 14px; font-weight: 500; letter-spacing: 0.02em;
  color: var(--app-header-text-color, var(--mb-muted)); opacity: 0.75;
  background: none; border: 0; border-bottom: 2px solid transparent;
  padding: 12px 12px 10px; cursor: pointer;
}
nav button[aria-selected="true"] { opacity: 1; border-bottom-color: var(--app-header-text-color, var(--mb-rx)); }
nav button:focus-visible, .seg button:focus-visible, .btn:focus-visible { outline: 2px solid var(--mb-rx); outline-offset: 2px; }
main { max-width: 1280px; margin: 0 auto; padding: 16px; display: grid; gap: 16px; }
@media (min-width: 870px) { main { padding: 24px; gap: 20px; } }
.card {
  background: var(--mb-card); border-radius: var(--mb-radius);
  border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--mb-line));
  box-shadow: var(--ha-card-box-shadow, none);
  padding: 16px;
}
.card h2 { font-size: 16px; font-weight: 500; margin: 0; }
.muted { color: var(--mb-muted); }
.small { font-size: 13px; line-height: 1.45; }
.hero { display: grid; gap: 16px; grid-template-columns: auto 1fr; align-items: center; }
.ring { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center;
  background: color-mix(in srgb, var(--tone) 16%, transparent); }
.ring::after { content: ""; width: 26px; height: 26px; border-radius: 50%; background: var(--tone);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--tone) 28%, transparent); }
.hero .title { font-size: 24px; font-weight: 500; margin: 0 0 4px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.chip { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 500;
  padding: 4px 10px; border-radius: 999px; color: var(--tone, var(--mb-muted));
  background: color-mix(in srgb, var(--tone, var(--mb-neutral)) 14%, transparent); }
.chip::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--tone, var(--mb-neutral)); }
[data-tone="good"] { --tone: var(--mb-good); }
[data-tone="warn"] { --tone: var(--mb-warn); }
[data-tone="bad"] { --tone: var(--mb-bad); }
[data-tone="info"] { --tone: var(--mb-info); }
[data-tone="neutral"] { --tone: var(--mb-neutral); }
.tiles { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
@media (min-width: 870px) { .tiles { grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; } }
.tile { display: flex; flex-direction: column; gap: 6px; min-height: 112px; }
.tile .label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--mb-muted); }
.tile .label ha-icon { --mdc-icon-size: 18px; color: var(--state-icon-color, var(--mb-muted)); }
.value { font-size: 34px; line-height: 1.1; font-weight: 500; font-variant-numeric: tabular-nums; letter-spacing: -0.01em; overflow-wrap: anywhere; }
.value .u { font-size: 16px; font-weight: 400; color: var(--mb-muted); margin-left: 4px; }
.charts { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr)); }
.charts .wide { grid-column: 1 / -1; }
.chart-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.legend { display: flex; gap: 12px; font-size: 13px; color: var(--mb-muted); font-variant-numeric: tabular-nums; }
.legend span::before { content: ""; display: inline-block; width: 10px; height: 3px; border-radius: 2px; margin-right: 6px; vertical-align: middle; background: var(--c); }
.plot { position: relative; }
.plot svg { display: block; width: 100%; height: 150px; overflow: visible; touch-action: pan-y; }
.plot .grid { stroke: var(--mb-line); stroke-width: 1; vector-effect: non-scaling-stroke; }
.plot .line { fill: none; stroke-width: 2; vector-effect: non-scaling-stroke; stroke-linejoin: round; }
.plot .area { opacity: 0.14; }
.plot .dot { fill: none; stroke-width: 7; stroke-linecap: round; vector-effect: non-scaling-stroke; }
.plot .cursor { visibility: hidden; stroke: var(--mb-muted); stroke-width: 1; vector-effect: non-scaling-stroke; stroke-dasharray: 3 3; }
.axis { display: flex; justify-content: space-between; font-size: 12px; color: var(--mb-muted); margin-top: 6px; }
.ymax { position: absolute; top: -2px; right: 0; font-size: 12px; color: var(--mb-muted); background: var(--mb-card); padding: 0 0 0 4px; }
.empty { display: grid; place-items: center; height: 150px; text-align: center; color: var(--mb-muted); font-size: 14px; padding: 0 16px; }
.seg { display: inline-flex; border: 1px solid var(--mb-line); border-radius: 999px; overflow: hidden; }
.seg button { font: inherit; font-size: 13px; color: var(--mb-muted); background: none; border: 0; padding: 6px 12px; cursor: pointer; }
.seg button[aria-pressed="true"] { color: var(--mb-text); background: color-mix(in srgb, var(--mb-rx) 16%, transparent); font-weight: 500; }
.section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.section-head h2 { font-size: 18px; font-weight: 500; margin: 0; }
.peers { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); }
.peer { display: grid; gap: 10px; border-left: 4px solid var(--tone); }
.peer .name { font-size: 17px; font-weight: 500; overflow-wrap: anywhere; }
.peer dl { display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; margin: 0; font-size: 14px; }
.peer dt { color: var(--mb-muted); }
.peer dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
.banner { display: flex; gap: 12px; align-items: flex-start; border-left: 4px solid var(--tone); }
.banner strong { display: block; margin-bottom: 2px; }
.rows { display: grid; grid-template-columns: minmax(0, 1fr) auto; margin: 0; }
.rows dt, .rows dd { padding: 10px 0; border-bottom: 1px solid var(--mb-line); margin: 0; font-size: 14px; }
.rows dd { text-align: right; font-variant-numeric: tabular-nums; padding-left: 12px; }
.rows dt:last-of-type, .rows dd:last-of-type { border-bottom: 0; }
.btn { font: inherit; font-weight: 500; color: var(--text-primary-color, #fff); background: var(--mb-rx); border: 0; border-radius: 999px; padding: 8px 18px; cursor: pointer; }
.skeleton { background: linear-gradient(90deg, var(--mb-line) 0%, color-mix(in srgb, var(--mb-line) 40%, transparent) 50%, var(--mb-line) 100%);
  background-size: 200% 100%; animation: shimmer 1.4s infinite linear; border-radius: 8px; }
@keyframes shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
@media (prefers-reduced-motion: reduce) { .skeleton { animation: none; } }
.center { max-width: 560px; margin: 48px auto; text-align: center; display: grid; gap: 12px; justify-items: center; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
`;

class MeshBeaconPanel extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._nodes = null; // null: loading; [] none set up
    this._error = null;
    this._nodeIndex = 0;
    this._range = "24h";
    this._tab = "overview";
    this._history = {}; // entity_id -> bucketed values (for this._historyKey)
    this._historyKey = null;
    this._historyState = "idle"; // idle | loading | ready | unavailable
    this._historyAt = 0;
    this._seen = new Map();
    this._timer = null;
    this._onVisible = () => !document.hidden && this._refresh();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
    else if (this._changed()) this._render();
    this._maybeRefreshHistory();
  }

  set narrow(value) {
    this._narrow = value;
    if (this._hass) this._render();
  }

  set route(route) {
    const tab = tabFromPath(route && route.path);
    if (tab !== this._tab) {
      this._tab = tab;
      if (this._hass) this._render();
    }
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    document.addEventListener("visibilitychange", this._onVisible);
    this._timer = setInterval(() => !document.hidden && this._refresh(), 30_000);
    if (this._hass) this._render();
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._onVisible);
    clearInterval(this._timer);
  }

  // --- data -------------------------------------------------------------------------------------

  get _node() {
    return this._nodes && this._nodes.length ? this._nodes[Math.min(this._nodeIndex, this._nodes.length - 1)] : null;
  }

  _ids() {
    const node = this._node;
    if (!node) return [];
    return [...Object.values(node.entities), ...node.peers.flatMap((p) => Object.values(p.entities))];
  }

  _changed() {
    let changed = false;
    for (const id of this._ids()) {
      const state = this._hass.states[id];
      if (this._seen.get(id) !== state) {
        this._seen.set(id, state);
        changed = true;
      }
    }
    return changed;
  }

  async _load() {
    this._error = null;
    this._render();
    try {
      const result = await this._hass.callWS({ type: "meshbeacon/panel" });
      this._nodes = Array.isArray(result && result.nodes) ? result.nodes : [];
    } catch (err) {
      this._nodes = this._nodes || null;
      this._error = (err && (err.code || err.message)) || "unknown";
    }
    this._changed();
    this._render();
    this._loadHistory(true);
  }

  _refresh() {
    // Pick up peers added or removed since the panel opened; cheap (registry lookup only).
    if (!this._hass || this._error) return;
    this._hass
      .callWS({ type: "meshbeacon/panel" })
      .then((result) => {
        if (Array.isArray(result && result.nodes)) this._nodes = result.nodes;
        this._changed();
        this._render();
      })
      .catch(() => {});
    this._maybeRefreshHistory();
  }

  _maybeRefreshHistory() {
    if (!this._node || document.hidden || this._historyState === "loading") return;
    const range = RANGES.find((r) => r.key === this._range);
    const every = Math.max(60_000, (range.hours * 3_600_000) / BUCKETS);
    if (Date.now() - this._historyAt >= every) this._loadHistory(false);
  }

  _chartIds() {
    const e = (this._node && this._node.entities) || {};
    return ["receive_rate", "send_rate", "cpu", "memory"].map((k) => e[k]).filter(Boolean);
  }

  async _loadHistory(reset) {
    const ids = this._chartIds();
    const range = RANGES.find((r) => r.key === this._range);
    const key = `${this._node ? this._node.entry_id : ""}|${range.key}`;
    if (!ids.length) {
      this._historyState = "ready";
      this._history = {};
      return this._render();
    }
    if (reset || key !== this._historyKey) {
      this._historyState = "loading";
      this._history = {};
      this._render();
    } else {
      this._historyState = "loading";
    }
    const end = Date.now();
    const start = end - range.hours * 3_600_000;
    try {
      let series;
      if (range.source === "statistics") {
        const stats = await this._hass.callWS({
          type: "recorder/statistics_during_period",
          start_time: new Date(start).toISOString(),
          end_time: new Date(end).toISOString(),
          statistic_ids: ids,
          period: "hour",
          types: ["mean"],
        });
        series = Object.fromEntries(ids.map((id) => [id, seriesFromStatistics(stats && stats[id])]));
      } else {
        const hist = await this._hass.callWS({
          type: "history/history_during_period",
          start_time: new Date(start).toISOString(),
          end_time: new Date(end).toISOString(),
          entity_ids: ids,
          minimal_response: true,
          no_attributes: true,
          significant_changes_only: false,
        });
        series = Object.fromEntries(ids.map((id) => [id, seriesFromHistory(hist && hist[id])]));
      }
      this._history = Object.fromEntries(ids.map((id) => [id, bucket(series[id], start, end, BUCKETS)]));
      this._historyState = "ready";
    } catch (_err) {
      this._history = {};
      this._historyState = "unavailable"; // history or recorder not loaded, or entities excluded
    }
    this._historyKey = key;
    this._historyAt = Date.now();
    this._render();
  }

  // --- helpers ----------------------------------------------------------------------------------

  _state(key, peer) {
    const id = peer ? peer.entities[key] : this._node && this._node.entities[key];
    return id ? this._hass.states[id] : undefined;
  }

  _label(group, state) {
    if (!state || state.state === "unavailable") return "Unavailable";
    try {
      if (typeof this._hass.formatEntityState === "function") return this._hass.formatEntityState(state);
    } catch (_err) {
      /* fall through */
    }
    return (LABELS[group] && LABELS[group][state.state]) || state.state;
  }

  _formatted(state) {
    if (!state) return "—";
    if (state.state === "unavailable") return "Unavailable";
    if (state.state === "unknown") return "Unknown";
    try {
      if (typeof this._hass.formatEntityState === "function") return this._hass.formatEntityState(state);
    } catch (_err) {
      /* fall through */
    }
    return `${state.state}${unit(state) ? ` ${unit(state)}` : ""}`;
  }

  _entry(state) {
    return state && this._hass.entities ? this._hass.entities[state.entity_id] : undefined;
  }

  _number(state, fallbackDigits) {
    const v = numeric(state);
    return formatNumber(v, this._hass.language, precision(this._entry(state), v, fallbackDigits));
  }

  _navigate(tab) {
    this._tab = tab;
    const base = (this._panel && this._panel.url_path) || "meshbeacon";
    const path = tab === "overview" ? `/${base}` : `/${base}/${tab}`;
    if (window.location.pathname !== path) {
      window.history.pushState(null, "", path);
      window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
    }
    this._render();
  }

  // --- rendering --------------------------------------------------------------------------------

  _render() {
    if (!this._hass) return;
    const view = this._view();
    const parts = [h("style", { text: STYLE }), this._header(), view.tabs ? this._tabs() : null, view.main];
    this._root.replaceChildren(...parts.filter(Boolean));
  }

  _view() {
    if (this._error && !this._nodes) return { main: this._errorView() };
    if (this._nodes === null) return { main: this._loadingView() };
    if (!this._nodes.length) return { main: this._notSetUpView() };
    const body = this._tab === "diagnostics" ? this._diagnostics() : this._overview();
    return { tabs: true, main: h("main", { id: "content", role: "tabpanel" }, body) };
  }

  _header() {
    const menu =
      this._narrow && customElements.get("ha-menu-button")
        ? Object.assign(document.createElement("ha-menu-button"), { hass: this._hass, narrow: true })
        : null;
    let picker = null;
    if (this._nodes && this._nodes.length > 1) {
      picker = h(
        "select",
        {
          "aria-label": "MeshBeacon app",
          onchange: (ev) => {
            this._nodeIndex = Number(ev.target.value);
            this._seen.clear();
            this._changed();
            this._loadHistory(true);
          },
        },
        this._nodes.map((n, i) => h("option", { value: String(i), selected: i === this._nodeIndex, text: `${n.title} (${n.app})` })),
      );
    }
    return h("header", {}, menu, h("h1", { text: "MeshBeacon" }), picker);
  }

  _tabs() {
    return h(
      "nav",
      { role: "tablist", "aria-label": "MeshBeacon sections" },
      TABS.map((t) =>
        h("button", {
          role: "tab",
          type: "button",
          "aria-selected": String(this._tab === t.key),
          "aria-controls": "content",
          text: t.label,
          onclick: () => this._navigate(t.key),
        }),
      ),
    );
  }

  _loadingView() {
    const block = (height) => h("div", { class: "card skeleton", style: `height:${height}px`, "aria-hidden": "true" });
    return h(
      "main",
      { "aria-busy": "true" },
      h("span", { class: "sr", text: "Loading MeshBeacon" }),
      block(112),
      h("div", { class: "tiles" }, [1, 2, 3, 4].map(() => block(112))),
      block(220),
    );
  }

  _errorView() {
    return h(
      "main",
      {},
      h(
        "div",
        { class: "card center", role: "alert" },
        h("h2", { text: "MeshBeacon could not be loaded" }),
        h("p", {
          class: "muted small",
          text: "Home Assistant did not return MeshBeacon's details. Check that the MeshBeacon integration is loaded, then try again.",
        }),
        h("p", { class: "muted small", text: `Reason: ${this._error}` }),
        h("button", { class: "btn", type: "button", text: "Try again", onclick: () => this._load() }),
      ),
    );
  }

  _notSetUpView() {
    return h(
      "main",
      {},
      h(
        "div",
        { class: "card center" },
        h("h2", { text: "MeshBeacon is not connected yet" }),
        h("p", {
          class: "muted small",
          text:
            "In the MeshBeacon app's Configuration tab, switch on “Show MeshBeacon's status in Home Assistant” and restart the app. " +
            "Then add MeshBeacon when Home Assistant offers it under Settings → Devices & services.",
        }),
      ),
    );
  }

  _unavailableBanner() {
    return h(
      "div",
      { class: "card banner", "data-tone": "neutral", role: "status" },
      h(
        "div",
        {},
        h("strong", { text: "MeshBeacon is not responding" }),
        h("span", {
          class: "muted small",
          text: "The app may be stopped or restarting. Values reappear automatically when it is back; history below is kept by Home Assistant.",
        }),
      ),
    );
  }

  _problemBanner() {
    const detected = this._state("problem_detected");
    if (!detected || detected.state !== "on") return null;
    const status = this._state("status");
    const tone = status && status.state === "needs_attention" ? "bad" : "warn";
    return h(
      "div",
      { class: "card banner", "data-tone": tone, role: "status" },
      h(
        "div",
        {},
        h("strong", { text: this._label("problem", this._state("problem")) }),
        h("span", {
          class: "muted small",
          text: "Details and suggested steps are in Settings → Repairs and in the MeshBeacon app's log.",
        }),
      ),
    );
  }

  _hero() {
    const conn = this._state("connectivity");
    const status = this._state("status");
    const transport = this._state("transport_mode");
    const connKey = isAvailable(conn) ? conn.state : "unknown";
    const tone = isAvailable(conn) ? TONES.connectivity[connKey] || "neutral" : "neutral";
    const chips = [];
    if (status) {
      chips.push(
        h("span", {
          class: "chip",
          "data-tone": isAvailable(status) ? TONES.status[status.state] || "neutral" : "neutral",
          text: this._label("status", status),
        }),
      );
    }
    if (isAvailable(transport) && transport.state !== "unknown") {
      chips.push(
        h("span", {
          class: "chip",
          "data-tone": transport.state === "on" ? "info" : "neutral",
          text: transport.state === "on" ? "Transport enabled" : "Transport off",
        }),
      );
    }
    const detected = this._state("problem_detected");
    if (isAvailable(detected) && detected.state === "off") chips.push(h("span", { class: "chip", "data-tone": "good", text: "No problems" }));
    return h(
      "section",
      { class: "card hero", "data-tone": tone, "aria-label": "Connectivity" },
      h("div", { class: "ring", role: "img", "aria-label": `Connectivity: ${this._label("connectivity", conn)}` }),
      h(
        "div",
        {},
        h("p", { class: "title", text: this._label("connectivity", conn) }),
        h("div", { class: "muted small", text: isAvailable(conn) ? CONNECTIVITY_TEXT[connKey] || "" : "Connectivity is not known while the app is unavailable." }),
        h("div", { class: "chips" }, chips),
      ),
    );
  }

  _tile(label, iconName, valueNode, note) {
    return h(
      "div",
      { class: "card tile" },
      h("div", { class: "label" }, icon(iconName), h("span", { text: label })),
      valueNode,
      note ? h("div", { class: "muted small", text: note }) : null,
    );
  }

  _value(text, unitText) {
    return h("div", { class: "value" }, text, unitText && text !== "—" ? h("span", { class: "u", text: unitText }) : null);
  }

  _tiles() {
    const tiles = [];
    const e = this._node.entities;
    if (e.peers_connected) {
      const connected = this._number(this._state("peers_connected"), 0);
      const configured = numeric(this._state("peers_configured"));
      tiles.push(this._tile("Peers connected", "mdi:account-network", this._value(connected, configured === null ? "" : `of ${formatNumber(configured, this._hass.language)}`)));
    }
    if (e.known_paths) {
      const st = this._state("known_paths");
      tiles.push(this._tile("Known paths", "mdi:map-marker-path", this._value(this._number(st, 0)), pathsNote(numeric(st))));
    }
    if (e.relayed_links) tiles.push(this._tile("Links relayed for others", "mdi:swap-horizontal", this._value(this._number(this._state("relayed_links"), 0))));
    for (const [key, label, ic] of [
      ["received", "Data received", "mdi:download-network"],
      ["sent", "Data sent", "mdi:upload-network"],
    ]) {
      if (e[key]) {
        const st = this._state(key);
        tiles.push(this._tile(label, ic, this._value(this._number(st, 2), unit(st))));
      }
    }
    if (e.cpu) tiles.push(this._tile("Processor use", "mdi:cpu-64-bit", this._value(this._number(this._state("cpu"), 1), "%")));
    if (e.memory) {
      const st = this._state("memory");
      tiles.push(this._tile("Memory use", "mdi:memory", this._value(this._number(st, 0), unit(st))));
    }
    if (e.reticulum_started) {
      const secs = secondsSince(this._state("reticulum_started"), Date.now());
      tiles.push(this._tile("Reticulum running for", "mdi:timer-outline", this._value(duration(secs))));
    }
    return h("section", { class: "tiles", "aria-label": "Key figures" }, tiles);
  }

  _rangePicker() {
    return h(
      "div",
      { class: "seg", role: "group", "aria-label": "History range" },
      RANGES.map((r) =>
        h("button", {
          type: "button",
          "aria-pressed": String(this._range === r.key),
          text: r.label,
          onclick: () => {
            if (this._range === r.key) return;
            this._range = r.key;
            this._loadHistory(true);
          },
        }),
      ),
    );
  }

  _chart(title, series, opts = {}) {
    // series: [{label, id, color}]
    const present = series.filter((x) => x.id);
    if (!present.length) return null;
    const units = unit(this._hass.states[present[0].id]) || opts.unit || "";
    const lang = this._hass.language;
    const digits = opts.digits ?? 1;
    const card = h("section", { class: `card${opts.wide ? " wide" : ""}`, "aria-label": title });
    const legend = h("div", { class: "legend" });
    const setLegend = (index) => {
      legend.replaceChildren(
        ...present.map((x) => {
          const values = this._history[x.id] || [];
          const v = index === null ? numeric(this._hass.states[x.id]) : values[index];
          const shown = v === null || v === undefined ? "\u2014" : `${formatNumber(v, lang, digits)} ${units}`.trim();
          return h("span", { style: `--c:${x.color}`, text: `${x.label ? `${x.label} ` : ""}${shown}` });
        }),
      );
    };
    setLegend(null);
    card.append(h("div", { class: "chart-head" }, h("h2", { text: title }), legend));
    if (this._historyState === "loading" && !Object.keys(this._history).length) {
      card.append(h("div", { class: "skeleton", style: "height:150px", "aria-hidden": "true" }));
      return card;
    }
    if (this._historyState === "unavailable") {
      card.append(h("div", { class: "empty", text: "History is not available. Home Assistant's History integration and recorder must be running." }));
      return card;
    }
    const lists = present.map((x) => this._history[x.id] || []);
    if (!lists.some((l) => l.some((v) => v !== null))) {
      card.append(h("div", { class: "empty", text: "No history for this period yet. It builds up as Home Assistant records new values." }));
      return card;
    }
    const { max, paths } = chartPaths(lists, CHART_W, CHART_H, opts.floor ?? 0);
    const svg = s("svg", { viewBox: `0 0 ${CHART_W} ${CHART_H}`, preserveAspectRatio: "none", role: "img" });
    const peaks = present.map((x, i) => `${x.label || title} peak ${formatNumber(peakValue(lists[i]), lang, digits)} ${units}, latest ${formatNumber(lastValue(lists[i]), lang, digits)} ${units}`);
    svg.setAttribute("aria-label", `${title}, ${RANGES.find((r) => r.key === this._range).label}: ${peaks.join("; ")}`);
    for (const f of [0.25, 0.5, 0.75, 1]) svg.append(s("line", { class: "grid", x1: 0, x2: CHART_W, y1: CHART_H * (1 - f), y2: CHART_H * (1 - f) }));
    paths.forEach((p, i) => {
      svg.append(s("path", { class: "area", d: p.area, fill: present[i].color }));
      svg.append(s("path", { class: "line", d: p.line, stroke: present[i].color }));
      if (p.dots) svg.append(s("path", { class: "dot", d: p.dots, stroke: present[i].color }));
    });
    const cursor = s("line", { class: "cursor", y1: 0, y2: CHART_H, x1: 0, x2: 0 });
    svg.append(cursor);
    const n = Math.max(...lists.map((l) => l.length));
    const move = (ev) => {
      const rect = svg.getBoundingClientRect();
      if (!rect.width) return;
      const index = Math.round(Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width)) * (n - 1));
      const x = n === 1 ? CHART_W / 2 : (index / (n - 1)) * CHART_W;
      cursor.setAttribute("x1", x);
      cursor.setAttribute("x2", x);
      cursor.style.visibility = "visible";
      setLegend(index);
    };
    const leave = () => {
      cursor.style.visibility = "hidden";
      setLegend(null);
    };
    svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerdown", move);
    svg.addEventListener("pointerleave", leave);
    const range = RANGES.find((r) => r.key === this._range);
    card.append(
      h("div", { class: "plot" }, svg, h("span", { class: "ymax", text: `${formatNumber(max, lang, max < 10 ? 1 : 0)} ${units}` })),
      h("div", { class: "axis" }, h("span", { text: `${range.label} ago` }), h("span", { text: "Now" })),
    );
    return card;
  }

  _charts() {
    const e = this._node.entities;
    const charts = [
      this._chart(
        "Network traffic",
        [
          { label: "↓ Receive", id: e.receive_rate, color: "var(--mb-rx)" },
          { label: "↑ Send", id: e.send_rate, color: "var(--mb-tx)" },
        ],
        { wide: true, digits: 2 },
      ),
      this._chart("Processor use", [{ id: e.cpu, color: "var(--mb-info)" }], { unit: "%", digits: 1, floor: 1 }),
      this._chart("Memory use", [{ id: e.memory, color: "var(--mb-good)" }], { digits: 0 }),
    ].filter(Boolean);
    if (!charts.length) return null;
    return h(
      "section",
      { "aria-label": "History" },
      h("div", { class: "section-head", style: "margin-bottom:12px" }, h("h2", { text: "History" }), this._rangePicker()),
      h("div", { class: "charts" }, charts),
    );
  }

  _peerCard(peer) {
    const state = peerState(peer, this._hass.states);
    const tone = { connected: "good", disconnected: "bad", unknown: "neutral", missing: "neutral" }[state];
    const text = {
      connected: "Connected",
      disconnected: "Not connected",
      unknown: "Unknown",
      missing: peer.reported ? "Unavailable" : "No longer configured",
    }[state];
    const rows = [];
    const add = (label, value) => rows.push(h("dt", { text: label }), h("dd", { text: value }));
    if (state === "connected" && peer.entities.connected_since) add("Connected for", duration(secondsSince(this._state("connected_since", peer), Date.now())));
    if (peer.entities.reconnections) add("Reconnections", this._number(this._state("reconnections", peer), 0));
    for (const [key, label] of [
      ["receive_rate", "Receiving"],
      ["send_rate", "Sending"],
    ]) {
      if (peer.entities[key]) {
        const st = this._state(key, peer);
        add(label, `${this._number(st, 2)} ${unit(st)}`.trim());
      }
    }
    return h(
      "article",
      { class: "card peer", "data-tone": tone },
      h("div", { class: "section-head" }, h("span", { class: "name", text: peer.name }), h("span", { class: "chip", "data-tone": tone, text })),
      rows.length ? h("dl", {}, rows) : null,
    );
  }

  _peers() {
    const peers = this._node.peers;
    return h(
      "section",
      { "aria-label": "Peers" },
      h("div", { class: "section-head", style: "margin-bottom:12px" }, h("h2", { text: "Peers" })),
      peers.length
        ? h("div", { class: "peers" }, peers.map((p) => this._peerCard(p)))
        : h("div", { class: "card muted small", text: "No peers are configured. Add a peer in the MeshBeacon app's Configuration tab to connect to a wider network." }),
    );
  }

  _overview() {
    const node = this._node;
    const unavailable = nodeState(node, this._hass.states) === "unavailable";
    return [unavailable ? this._unavailableBanner() : this._problemBanner(), this._hero(), this._tiles(), this._charts(), this._peers()].filter(Boolean);
  }

  _diagnostics() {
    const e = this._node.entities;
    const rows = [];
    const add = (label, key, format) => {
      if (!e[key]) return;
      const st = this._state(key);
      rows.push(h("dt", { text: label }), h("dd", { text: format ? format(st) : this._formatted(st) }));
    };
    const ago = (st) => {
      const secs = secondsSince(st, Date.now());
      return secs === null ? this._formatted(st) : `${duration(secs)} ago`;
    };
    add("Status", "status");
    add("Problem", "problem");
    add("Reticulum running", "reticulum_running", (st) => (isAvailable(st) && st.state !== "unknown" ? (st.state === "on" ? "Yes" : "No") : this._formatted(st)));
    add("Transport mode", "transport_mode", (st) => (isAvailable(st) && st.state !== "unknown" ? (st.state === "on" ? "Enabled" : "Off") : this._formatted(st)));
    add("App started", "app_started", ago);
    add("Reticulum started", "reticulum_started", ago);
    add("Reticulum restarts", "restarts");
    add("Restarts to free memory", "memory_restarts");
    add("Peers configured", "peers_configured");
    add("Memory use (total)", "memory");
    add("Memory use (MeshBeacon core)", "core_memory");
    add("Memory use (Reticulum)", "reticulum_memory");
    add("Processor use", "cpu");
    add("Packets received (all traffic)", "packets_received");
    add("Packets sent (all traffic)", "packets_sent");
    add("Announces received", "announces_received");
    add("Announces sent", "announces_sent");
    const device = (() => {
      const id = e.status;
      const entry = id && this._hass.entities ? this._hass.entities[id] : null;
      return entry && entry.device_id && this._hass.devices ? this._hass.devices[entry.device_id] : null;
    })();
    if (device && device.sw_version) rows.unshift(h("dt", { text: "MeshBeacon version" }), h("dd", { text: device.sw_version }));
    const unavailable = nodeState(this._node, this._hass.states) === "unavailable";
    return [
      unavailable ? this._unavailableBanner() : this._problemBanner(),
      h("section", { class: "card", "aria-label": "Diagnostics" }, h("dl", { class: "rows" }, rows)),
      h("p", {
        class: "muted small",
        text:
          "Some detailed sensors are switched off by default to keep Home Assistant's database small. " +
          "To see them here, enable them under Settings → Devices & services → MeshBeacon.",
      }),
    ].filter(Boolean);
  }
}

if (!customElements.get("meshbeacon-panel")) customElements.define("meshbeacon-panel", MeshBeaconPanel);
