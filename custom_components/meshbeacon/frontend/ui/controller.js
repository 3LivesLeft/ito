// SPDX-License-Identifier: Apache-2.0
// The delivery-independent interface controller: tabs, history range and cadence, rendering.
// A delivery (the integration panel today, the built-in interface later) provides the data
// source, the root to render into, its own header extras and its own wording.

import { RANGES, TABS, bucket } from "../model.js";
import { brandTitle, message, skeletonPage, tabs as tabsBar } from "./components.js";
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
   * @param {object} [o.messages] the Messages view (ui/messages.js), when the delivery offers messaging
   * @param {(shown: boolean) => void} [o.onMessages] told when the Messages view is shown or hidden
   */
  constructor({ root, source, copy, headerExtras = () => [], onNavigate = () => {}, onRetry = () => {}, messages = null, onMessages = () => {}, settings = null }) {
    Object.assign(this, { root, source, copy, headerExtras, onNavigate, onRetry, messages, onMessages, settings });
    this.unread = () => 0;
    this._messagesShown = false;
    // Persistent slots: the Messages view stays mounted across renders, so a message being written,
    // the focus and the scroll position survive live updates.
    this._slots = { header: h("div", { class: "slot" }), nav: h("div", { class: "slot" }), main: h("div", { class: "slot" }) };
    this._mounted = false;
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

  /** The tabs this app offers: Messages only for an app with messaging. */
  tabs() {
    const hasMessaging = Boolean(this.messages && this.source.messaging && this.source.messaging());
    const available = this.settings ? [...TABS, { key: "settings", label: "Settings" }] : TABS;
    return available.filter((t) => t.key !== "messages" || hasMessaging).map((t) => {
      const unread = t.key === "messages" ? this.unread() : 0;
      return unread ? { ...t, label: `${t.label} (${unread > 99 ? "99+" : unread})` } : t;
    });
  }

  render() {
    const phase = this.source.phase;
    let main;
    let showTabs = false;
    const tabs = this.tabs();
    const tab = tabs.some((t) => t.key === this.tab) ? this.tab : "overview";
    const messagesShown = phase === "ready" && tab === "messages";
    if (messagesShown !== this._messagesShown) {
      this._messagesShown = messagesShown;
      this.onMessages(messagesShown);
    }
    if (phase === "error") main = message({ ...this.copy.loadError(this.source.error), alert: true, action: { label: "Try again", onClick: this.onRetry } });
    else if (phase === "loading") main = skeletonPage("Loading ito");
    else if (phase === "empty") main = message(this.copy.notSetUp);
    else {
      showTabs = true;
      if (tab === "settings" && this.settings) {
        const current = this._slots.main.firstElementChild;
        main = current && current.dataset.tab === "settings" ? current : h("main", { id: "content", role: "tabpanel", "data-tab": "settings" }, this.settings.element);
      } else if (messagesShown) {
        this.messages.update({ summary: this.source.messaging(), language: this.source.language, now: Date.now() });
        const current = this._slots.main.firstElementChild;
        main = current && current.dataset.tab === "messages" ? current : h("main", { id: "content", role: "tabpanel", class: "messages-main", "data-tab": "messages" }, this.messages.element);
      } else {
        const ctx = { source: this.source, now: Date.now(), range: this.range, history: this.history, onRange: (r) => this.setRange(r), copy: this.copy };
        main = h("main", { id: "content", role: "tabpanel" }, tab === "diagnostics" ? diagnostics(ctx) : overview(ctx));
      }
    }
    const header = h("header", {}, ...this.headerExtras().slice(0, 1), brandTitle(), ...this.headerExtras().slice(1));
    const nav = showTabs
      ? tabsBar("ito sections", tabs, tab, (t) => {
          this.setTab(t);
          this.onNavigate(t);
        })
      : null;
    if (!this._mounted) {
      this.root.replaceChildren(h("style", { text: STYLE }), this._slots.header, this._slots.nav, this._slots.main);
      this._mounted = true;
    }
    this._slots.header.replaceChildren(header);
    this._slots.nav.replaceChildren(...(nav ? [nav] : []));
    if (this._slots.main.firstElementChild !== main) this._slots.main.replaceChildren(main);
  }
}
