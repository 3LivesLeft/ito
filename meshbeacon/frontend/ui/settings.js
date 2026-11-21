// SPDX-License-Identifier: Apache-2.0
import { h } from "./dom.js";

export const SETTINGS_STYLE = `
.settings { max-width: 860px; margin: 0 auto; padding: 24px; }
.settings h2 { margin-top: 0; }
.settings fieldset { min-width: 0; margin: 0 0 24px; padding: 20px; border: 1px solid var(--mb-line); border-radius: 12px; background: var(--mb-surface); }
.settings legend { font-weight: 600; padding: 0 8px; }
.settings label { display: flex; flex-direction: column; gap: 6px; margin: 12px 0; }
.settings .check { flex-direction: row; align-items: center; gap: 10px; }
.settings input:not([type=checkbox]), .settings select { width: 100%; min-height: 44px; padding: 10px; border: 1px solid var(--mb-line); border-radius: 6px; background: var(--mb-bg); color: var(--mb-text); font: inherit; }
.settings input[type=checkbox] { width: 20px; height: 20px; accent-color: var(--mb-accent); }
.settings button { min-height: 44px; padding: 10px 18px; font: inherit; cursor: pointer; border: 1px solid var(--mb-line); border-radius: 8px; color: var(--mb-text); background: var(--mb-surface); }
.settings .primary { background: var(--mb-text); color: var(--mb-bg); font-weight: 600; }
.settings :focus-visible { outline: 3px solid var(--mb-accent); outline-offset: 3px; }
.settings .peer { border-top: 1px solid var(--mb-line); padding-top: 12px; margin-top: 16px; }
.settings .actions { display: flex; gap: 12px; flex-wrap: wrap; }
.settings .feedback { white-space: pre-line; }
@media(max-width: 500px) { .settings { padding: 16px; } .settings fieldset { padding: 14px; } }
`;

const ERROR = {
  conflict: "Settings changed in another window. Reload settings before saving again.",
  unavailable: "Could not reach Home Assistant. Your saved settings have not been replaced. Try again shortly.",
  saved_restart_failed: "Settings are saved, but the restart could not be requested. Open the ito app page and select Restart, then return here.",
  busy: "Another change is being applied. Please wait a moment and try again.",
};
export class SettingsView {
  constructor({ request, onSaved }) {
    this.request = request;
    this.onSaved = onSaved;
    this.element = h("section", { class: "settings" });
    this.loaded = false;
    this.busy = false;
    this.renderLoading();
  }
  renderLoading() { this.element.replaceChildren(h("h2", { text: "Settings" }), h("p", { text: "Loading your settings…" })); }
  async load() {
    this.renderLoading();
    try {
      const data = await this.request("config");
      this.original = data.options;
      this.revision = data.revision;
      this.networks = data.networks;
      this.loaded = true;
      this.render();
      return data.options;
    } catch (_) {
      this.element.replaceChildren(h("h2", { text: "Settings are unavailable" }), h("p", { text: "Home Assistant may still be starting. Try again shortly." }), h("button", { text: "Try again", onclick: () => this.load() }));
      return null;
    }
  }
  render() {
    const options = this.original;
    this.fields = {};
    const field = (key, label, type = "text", extra = {}) => {
      const input = h("input", { type, ...extra });
      if (type === "checkbox") input.checked = Boolean(options[key]);
      else input.value = options[key] ?? "";
      this.fields[key] = input;
      return h("label", { class: type === "checkbox" ? "check" : "" }, ...(type === "checkbox" ? [input, label] : [label, input]));
    };
    const network = h("select", { "aria-label": "Public network" }, h("option", { value: "custom", text: "My own connections / stay offline" }), this.networks.map((n) => h("option", { value: n.id, text: n.name })));
    network.value = options.network || "custom";
    this.fields.network = network;
    const rules = h("p");
    const showRules = () => { rules.textContent = this.networks.find((n) => n.id === network.value)?.rules || "ito stays offline until you choose a network or add a connection."; };
    network.addEventListener("change", showRules); showRules();
    const peers = h("div");
    this.peers = [];
    const addPeer = (original = {}) => {
      const row = { original, fields: {} };
      const box = h("div", { class: "peer" });
      for (const [key, label, type] of [["name", "Connection name", "text"], ["host", "Host", "text"], ["port", "Port", "number"], ["network_name", "Network name (optional)", "text"], ["passphrase", original.has_passphrase ? "New passphrase (leave blank to keep current)" : "Passphrase (optional)", "password"]]) {
        const input = h("input", { type, value: original[key] ?? (key === "port" ? 4242 : ""), autocomplete: "off", ...(key === "port" ? { min: 1, max: 65535 } : {}) });
        row.fields[key] = input;
        box.append(h("label", {}, label, input));
      }
      row.clearPassphrase = h("input", { type: "checkbox" });
      if (original.has_passphrase) box.append(h("label", { class: "check" }, row.clearPassphrase, "Clear saved passphrase"));
      box.append(h("button", { type: "button", text: "Remove connection", onclick: () => { this.peers = this.peers.filter((p) => p !== row); box.remove(); } }));
      this.peers.push(row); peers.append(box);
    };
    for (const peer of options.peers || []) addPeer(peer);
    const log = h("select", { "aria-label": "Log detail" }, ["quiet", "normal", "detailed"].map((v) => h("option", { value: v, text: v[0].toUpperCase() + v.slice(1) })));
    log.value = options.log_level || "normal"; this.fields.log_level = log;
    this.feedback = h("p", { class: "feedback", role: "status", "aria-live": "polite" });
    const form = h("form", { onsubmit: (event) => { event.preventDefault(); this.save(); } },
      h("fieldset", {}, h("legend", { text: "Connections" }), h("label", {}, "Public network", network), rules, peers,
        h("button", { type: "button", text: "Add my own connection", onclick: () => { if (this.peers.length < 10) addPeer(); } })),
      h("fieldset", {}, h("legend", { text: "Messaging" }), field("messaging_enabled", "Enable messaging", "checkbox"),
        field("messaging_display_name", "Display name (optional)", "text", { maxLength: 32 }),
        field("messaging_accept_anyone", "Accept messages from people outside my contacts", "checkbox"),
        field("messaging_auto_reply", "Send an automatic reply to incoming messages", "checkbox"),
        field("messaging_propagation_node", "Propagation node address (optional)"),
        h("p", { text: "Add and manage your contacts in Messages. Existing conversations and identities are kept when settings change." })),
      h("fieldset", {}, h("legend", { text: "Advanced" }), field("transport", "Relay traffic for other Reticulum users", "checkbox"),
        field("memory_limit_mb", "Reticulum memory limit (MiB)", "number", { min: 128, max: 1024 }),
        h("label", {}, "Log detail", log), field("home_assistant_integration", "Share status with the optional Home Assistant integration", "checkbox"),
        h("p", { text: "The optional integration adds entities for automations and custom dashboards. Install it through Marketplace only if you need those features." })),
      h("p", { text: "Saving briefly restarts ito to apply your changes. The dashboard reconnects automatically." }), this.feedback,
      h("div", { class: "actions" }, h("button", { class: "primary", type: "submit", text: "Save and apply" }), h("button", { type: "button", text: "Reload settings", onclick: () => this.load() })),
    );
    this.form = form;
    this.element.replaceChildren(h("style", { text: SETTINGS_STYLE }), h("h2", { text: "Make yourself at home" }), h("p", { text: "Choose a connection, switch on messaging, and you’re ready to go." }), form);
  }
  async save() {
    if (this.busy) return;
    const patch = {};
    for (const [key, input] of Object.entries(this.fields)) {
      const value = input.type === "checkbox" ? input.checked : input.type === "number" ? Number(input.value) : input.value;
      if (value !== (this.original[key] ?? "")) patch[key] = value;
    }
    const peers = this.peers.map(({ original, fields, clearPassphrase }) => {
      const peer = Object.fromEntries(Object.entries(fields).map(([key, input]) => [key, key === "port" ? Number(input.value) : input.value]));
      if (!peer.passphrase && original.has_passphrase && !clearPassphrase.checked) { delete peer.passphrase; peer.keep_passphrase = original.name; }
      return peer;
    });
    // Never resubmit untouched peers: preserves Home Assistant !secret references exactly.
    const originalPeers = (this.original.peers || []).map((p) => ({ name: p.name, host: p.host, port: p.port, network_name: p.network_name || "", ...(p.has_passphrase ? { keep_passphrase: p.name } : { passphrase: "" }) }));
    if (JSON.stringify(peers) !== JSON.stringify(originalPeers)) patch.peers = peers;
    this.busy = true;
    for (const el of this.form.elements) el.disabled = true;
    this.feedback.textContent = "Saving settings…";
    try {
      await this.request("config", { op: "config_save", revision: this.revision, patch });
      this.feedback.textContent = "Settings saved. Restarting ito…";
      await this.onSaved();
    } catch (error) {
      this.feedback.textContent = error.problems?.join("\n") || ERROR[error.code] || "Could not apply settings. Reload settings and try again.";
    } finally {
      this.busy = false;
      for (const el of this.form.elements) el.disabled = false;
    }
  }
}
