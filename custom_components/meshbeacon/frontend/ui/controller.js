// SPDX-License-Identifier: Apache-2.0
// The delivery-independent interface controller: tabs, history range and cadence, rendering.
// A delivery (the integration panel today, the built-in interface later) provides the data
// source, the root to render into, its own header extras and its own wording.

import { RANGES, TABS, bucket } from "../model.js";
import { brandTitle, message, skeletonPage, tabs } from "./components.js";
import { h } from "./dom.js";
import { STYLE } from "./style.js";
import { diagnostics, overview } from "./views.js";

export const BUCKETS = 120;

export class InterfaceController {
  /**
   * @param {object} o
   * @param {ShadowRoot} o.root
   * @param {object} o.source a data source implementing the view-data contract
   * @param {object} o.copy delivery wording: unavailable, problemHint, historyUnavailable,
   *   historyEmpty, diagnosticsNote, notSetUp {title, lines}, loadError {title, lines}, ranges
   * @param {() => Node[]} [o.headerExtras] e.g. Home Assistant's menu button, an app picker
   * @param {(tab: string) => void} [o.onNavigate]
   * @param {() => void} [o.onRetry]
   */
  constructor({ root, source, copy, headerExtras = () => [], onNavigate = () => {}, onRetry = () => {} }) {
    Object.assign(this, { root, source, copy, headerExtras, onNavigate, onRetry });
    this.tab = "overview";
    this.range = copy.ranges.includes("24h") ? "24h" : copy.ranges[0];
    this.history = { state: "idle", values: {} };
    this._historyAt = 0;
    this._historyScope = null;
  }

  setTab(tab) {
    if (tab === this.tab) return;
    this.tab = tab;
    this.render();
  }

  setRange(range) {
    this.range = range;
    this.loadHistory(true);
  }

  /** Fetch history when due: at most once per chart bucket (>= 60 s), only while visible. */
  maybeRefreshHistory() {
    if (this.source.phase !== "ready" || document.hidden || this.history.state === "loading") return;
    const range = RANGES.find((r) => r.key === this.range);
    const every = Math.max(60_000, (range.hours * 3_600_000) / BUCKETS);
    const scope = `${this.source.historyScope()}|${this.range}`;
    if (scope !== this._historyScope || Date.now() - this._historyAt >= every) this.loadHistory(scope !== this._historyScope);
  }

  async loadHistory(reset) {
    const range = RANGES.find((r) => r.key === this.range);
    const scope = `${this.source.historyScope()}|${this.range}`;
    if (!this.source.historyKeys().length) {
      this.history = { state: "ready", values: {} };
      this._historyScope = scope;
      return this.render();
    }
    this.history = { state: "loading", values: reset ? {} : this.history.values };
    if (reset) this.render();
    const end = Date.now();
    const start = end - range.hours * 3_600_000;
    try {
      const series = await this.source.history(range, start, end);
      const values = Object.fromEntries(Object.entries(series).map(([k, v]) => [k, bucket(v, start, end, BUCKETS)]));
      this.history = { state: "ready", values };
    } catch (_err) {
      this.history = { state: "unavailable", values: {} };
    }
    this._historyScope = scope;
    this._historyAt = Date.now();
    this.render();
  }

  render() {
    const phase = this.source.phase;
    let main;
    let showTabs = false;
    if (phase === "error") main = message({ ...this.copy.loadError(this.source.error), alert: true, action: { label: "Try again", onClick: this.onRetry } });
    else if (phase === "loading") main = skeletonPage("Loading MeshBeacon");
    else if (phase === "empty") main = message(this.copy.notSetUp);
    else {
      showTabs = true;
      const ctx = { source: this.source, now: Date.now(), range: this.range, history: this.history, onRange: (r) => this.setRange(r), copy: this.copy };
      main = h("main", { id: "content", role: "tabpanel" }, this.tab === "diagnostics" ? diagnostics(ctx) : overview(ctx));
    }
    const header = h("header", {}, ...this.headerExtras().slice(0, 1), brandTitle(), ...this.headerExtras().slice(1));
    const nav = showTabs
      ? tabs("MeshBeacon sections", TABS, this.tab, (t) => {
          this.setTab(t);
          this.onNavigate(t);
        })
      : null;
    this.root.replaceChildren(...[h("style", { text: STYLE }), header, nav, main].filter(Boolean));
  }
}
