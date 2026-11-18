// SPDX-License-Identifier: Apache-2.0
// Delivery shell: the MeshBeacon sidebar panel served by the integration (ADR 0007).
//
// It only connects Home Assistant to the shared interface: the HassSource (entities and the
// recorder), the InterfaceController (tabs, history, rendering) and Home Assistant chrome (menu
// button, theme, routing). Presentation lives in ui/, data access in sources/. A future
// built-in interface uses the same ui/ with sources/snapshot.js (docs/architecture.md).

import { RANGES, tabFromPath } from "./model.js";
import { loadFonts } from "./fonts.js";
import { HassSource } from "./sources/hass.js";
import { InterfaceController } from "./ui/controller.js";
import { h } from "./ui/dom.js";

const COPY = {
  unavailable: "The app may be stopped or restarting. Values reappear automatically when it is back; history below is kept by Home Assistant.",
  problemHint: "Details and suggested steps are in Settings → Repairs and in the MeshBeacon app's log.",
  historyUnavailable: "History is not available. Home Assistant's History integration and recorder must be running.",
  historyEmpty: "No history for this period yet. It builds up as Home Assistant records new values.",
  diagnosticsNote:
    "Some detailed sensors are switched off by default to keep Home Assistant's database small. " +
    "To see them here, enable them under Settings → Devices & services → MeshBeacon.",
  ranges: RANGES.map((r) => r.key),
  notSetUp: {
    title: "MeshBeacon is not connected yet",
    lines: [
      "In the MeshBeacon app's Configuration tab, switch on “Show MeshBeacon's status in Home Assistant” and restart the app. " +
        "Then add MeshBeacon when Home Assistant offers it under Settings → Devices & services.",
    ],
  },
  loadError: (reason) => ({
    title: "MeshBeacon could not be loaded",
    lines: [
      "Home Assistant did not return MeshBeacon's details. Check that the MeshBeacon integration is loaded, then try again.",
      `Reason: ${reason}`,
    ],
  }),
};

class MeshBeaconPanel extends HTMLElement {
  constructor() {
    super();
    this._source = new HassSource();
    this._ui = new InterfaceController({
      root: this.attachShadow({ mode: "open" }),
      source: this._source,
      copy: COPY,
      headerExtras: () => this._headerExtras(),
      onNavigate: (tab) => this._navigate(tab),
      onRetry: () => this._load(),
    });
    this._timer = null;
    this._onVisible = () => !document.hidden && this._refresh();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    // Follow Home Assistant's own light/dark choice; without it, the device preference applies.
    const dark = hass && hass.themes ? hass.themes.darkMode : undefined;
    if (typeof dark === "boolean") this.setAttribute("data-theme", dark ? "dark" : "light");
    else this.removeAttribute("data-theme");
    const changed = this._source.update(hass);
    if (first) this._load();
    else if (changed) this._ui.render();
    this._ui.maybeRefreshHistory();
  }

  set narrow(value) {
    this._narrow = value;
    if (this._hass) this._ui.render();
  }

  set route(route) {
    const tab = tabFromPath(route && route.path);
    if (tab !== this._ui.tab) {
      this._ui.tab = tab;
      if (this._hass) this._ui.render();
    }
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    loadFonts();
    document.addEventListener("visibilitychange", this._onVisible);
    this._timer = setInterval(() => !document.hidden && this._refresh(), 30_000);
    if (this._hass) this._ui.render();
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._onVisible);
    clearInterval(this._timer);
  }

  async _load() {
    this._ui.render();
    await this._source.load();
    this._ui.render();
    this._ui.loadHistory(true);
  }

  async _refresh() {
    // Pick up peers added or removed since the panel opened; cheap (registry lookup only).
    if (!this._hass || this._source.phase === "error") return;
    await this._source.load();
    this._ui.render();
    this._ui.maybeRefreshHistory();
  }

  _headerExtras() {
    const menu =
      this._narrow && customElements.get("ha-menu-button")
        ? Object.assign(document.createElement("ha-menu-button"), { hass: this._hass, narrow: true })
        : null;
    const apps = this._source.apps();
    const picker =
      apps.length > 1
        ? h(
            "select",
            {
              "aria-label": "MeshBeacon app",
              onchange: (ev) => {
                this._source.select(Number(ev.target.value));
                this._source.update(this._hass);
                this._ui.loadHistory(true);
              },
            },
            apps.map((a) => h("option", { value: String(a.index), selected: a.index === this._source.index, text: `${a.title} (${a.app})` })),
          )
        : null;
    return [menu, picker];
  }

  _navigate(tab) {
    const base = (this._panel && this._panel.url_path) || "meshbeacon";
    const path = tab === "overview" ? `/${base}` : `/${base}/${tab}`;
    if (window.location.pathname !== path) {
      window.history.pushState(null, "", path);
      window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
    }
  }
}

if (!customElements.get("meshbeacon-panel")) customElements.define("meshbeacon-panel", MeshBeaconPanel);
