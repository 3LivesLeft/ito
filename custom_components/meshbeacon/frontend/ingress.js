// SPDX-License-Identifier: Apache-2.0
import { loadFonts } from "./fonts.js";
import { SnapshotSource } from "./sources/snapshot.js";
import { api, IngressMessaging } from "./sources/ingress.js";
import { InterfaceController } from "./ui/controller.js";
import { MessagesView } from "./ui/messages.js";
import { SettingsView } from "./ui/settings.js";
import { PagesView } from "./ui/pages.js";
import { h } from "./ui/dom.js";

const COPY = {
  messagingOff: "Open Settings, switch on messaging, then choose Save and apply.",
  unavailable: "ito is restarting or temporarily unavailable. This dashboard reconnects automatically.",
  problemHint: "Check Settings and Diagnostics for details.",
  historyUnavailable: "Recent history is temporarily unavailable.",
  historyEmpty: "Recent history builds up while ito runs and starts afresh after an app restart.",
  diagnosticsNote: "Live readings come directly from ito. Unavailable readings are shown as unknown.",
  ranges: ["24h", "7d"],
  notSetUp: { title: "Welcome to ito", lines: ["Open Settings to choose your connection."] },
  loadError: () => ({ title: "Connecting to ito", lines: ["The app may still be starting. We’ll keep trying automatically."] }),
};

class ItoDashboard extends HTMLElement {
  constructor() {
    super();
    this.source = new SnapshotSource({ history: async (range) => (await api(`history?range=${range.key}`)).values });
    this.messaging = new IngressMessaging();
    this.settings = new SettingsView({ request: api, onSaved: () => this.apply() });
    this.pages = new PagesView({ request: api, bundledLibrary: true, onEnable: () => this.enablePages() });
    this.ui = new InterfaceController({
      root: this.attachShadow({ mode: "open" }), source: this.source, copy: COPY,
      messages: new MessagesView({ messaging: this.messaging, offText: COPY.messagingOff }), settings: this.settings, pages: this.pages,
      onMessages: (shown) => shown && this.messaging.refresh(),
      onRetry: () => this.refresh(),
      onNavigate: (tab) => { history.replaceState(null, "", `#${tab}`); },
      headerExtras: () => [null, h("button", { type: "button", "aria-label": "Switch light or dark theme", text: this.getAttribute("data-theme") === "dark" ? "Light" : "Dark", onclick: () => {
        this.setAttribute("data-theme", this.getAttribute("data-theme") === "dark" ? "light" : "dark"); this.ui.render();
      } }), ...(this.updateReady ? [h("button", { text: "Load update", onclick: () => location.reload() })] : [])],
    });
    this.ui.unread = () => this.messaging.unread;
    this.messaging.onChange(() => this.ui.render());
    this.visible = () => { if (!document.hidden) this.refresh(); else this.messaging.stop(); };
  }
  async connectedCallback() {
    loadFonts();
    this.setAttribute("data-theme", matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    this.ui.render();
    document.addEventListener("visibilitychange", this.visible);
    await this.refresh();
    const options = await this.settings.load();
    const tab = location.hash.slice(1);
    this.ui.setTab(["overview", "messages", "pages", "diagnostics", "settings"].includes(tab) ? tab : options && options.network === "custom" && !options.peers?.length ? "settings" : "overview");
    if (this.isConnected) this.timer = setInterval(() => { if (!document.hidden) this.refresh(); }, 5_000);
  }
  disconnectedCallback() {
    clearInterval(this.timer); this.messaging.stop();
    document.removeEventListener("visibilitychange", this.visible);
  }
  async refresh() {
    if (this.refreshing) return;
    this.refreshing = true;
    try {
      const data = await api("status");
      if (this.build && data.build !== this.build) {
        if (![...this.messaging.drafts.values()].some(Boolean) && !this.messaging.pending.size && this.ui.tab !== "settings" && !this.pages.dirty()) location.reload();
        else this.updateReady = true;
      }
      this.build = data.build;
      this.instance = data.instance;
      this.restartError = data.restart_error;
      this.source.update(data.snapshot);
      if (!document.hidden && this.source.messaging()?.state !== "disabled") this.messaging.start();
      else this.messaging.stop();
    } catch (_) {
      this.source.update(null); this.source.fail("unavailable"); this.messaging.stop();
    } finally { this.refreshing = false; }
    this.ui.render(); this.ui.maybeRefreshHistory();
  }
  /** The Pages tab's "Switch on pages": the same validated, conflict-checked save as Settings. */
  async enablePages() {
    const current = await api("config");
    await api("config", { op: "config_save", revision: current.revision, patch: { pages_enabled: true } });
    await this.apply();
  }
  async apply() {
    const before = this.instance;
    try { await api("config", { op: "app_restart" }); } catch (_) { throw { code: "saved_restart_failed" }; }
    const started = Date.now();
    while (this.isConnected && Date.now() - started < 120_000) {
      await new Promise((resolve) => setTimeout(resolve, 2_000));
      await this.refresh();
      if (this.instance && this.instance !== before) {
        await this.settings.load();
        this.settings.feedback.textContent = "Your settings are applied. ito is reconnecting.";
        return;
      }
      if (this.restartError) break;
    }
    this.settings.feedback.textContent = "Settings are saved, but ito has not finished restarting. Wait a moment, then use Open Web UI from the app page if it does not reconnect.";
  }
}
customElements.define("ito-dashboard", ItoDashboard);
