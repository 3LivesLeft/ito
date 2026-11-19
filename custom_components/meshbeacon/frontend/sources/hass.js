// SPDX-License-Identifier: Apache-2.0
// Data source: Home Assistant (the integration's entities, and HA's recorder for history).
// Implements the view-data contract (model.js NODE_KEYS / PEER_KEYS); no DOM, no rendering.

import {
  ABSENT,
  HISTORY_KEYS,
  LABELS,
  UNAVAILABLE,
  nodeState,
  peerState,
  seriesFromHistory,
  seriesFromStatistics,
} from "../model.js";

const ENUM_GROUPS = { status: "status", connectivity: "connectivity", problem: "problem" };
const TIMESTAMPS = new Set(["app_started", "reticulum_started", "connected_since"]);

export class HassSource {
  constructor() {
    this.hass = null;
    this.nodes = null; // null: not loaded; [] none set up
    this.error = null;
    this.index = 0;
    this._seen = new Map();
  }

  get language() {
    return (this.hass && this.hass.language) || "en-GB";
  }

  /** "loading" | "error" | "empty" | "ready" */
  get phase() {
    if (this.error && !this.nodes) return "error";
    if (this.nodes === null) return "loading";
    return this.nodes.length ? "ready" : "empty";
  }

  get node() {
    return this.nodes && this.nodes.length ? this.nodes[Math.min(this.index, this.nodes.length - 1)] : null;
  }

  apps() {
    return (this.nodes || []).map((n, i) => ({ index: i, title: n.title, app: n.app }));
  }

  select(index) {
    this.index = index;
    this._seen.clear();
  }

  /** Give the latest `hass`; returns true when one of this node's entities changed. */
  update(hass) {
    this.hass = hass;
    let changed = false;
    for (const id of this._ids()) {
      const state = hass.states[id];
      if (this._seen.get(id) !== state) {
        this._seen.set(id, state);
        changed = true;
      }
    }
    return changed;
  }

  async load() {
    try {
      const result = await this.hass.callWS({ type: "meshbeacon/panel" });
      this.nodes = Array.isArray(result && result.nodes) ? result.nodes : [];
      this.error = null;
    } catch (err) {
      this.error = (err && (err.code || err.message)) || "unknown";
    }
    if (this.hass) this.update(this.hass);
  }

  _ids() {
    const node = this.node;
    if (!node) return [];
    return [...Object.values(node.entities), ...node.peers.flatMap((p) => Object.values(p.entities))];
  }

  _id(key, peer) {
    if (peer) return peer.entities[key];
    return this.node ? this.node.entities[key] : undefined;
  }

  has(key, peer = null) {
    return Boolean(this._id(key, peer));
  }

  reading(key, peer = null) {
    const id = this._id(key, peer);
    const st = id && this.hass ? this.hass.states[id] : undefined;
    if (!st) return ABSENT;
    const available = st.state !== "unavailable";
    const known = available && !UNAVAILABLE.has(st.state);
    const number = Number(st.state);
    const entry = this.hass.entities ? this.hass.entities[id] : undefined;
    let label = null;
    if (known) {
      // Home Assistant's own formatting: translated states, display precision, units.
      try {
        label = typeof this.hass.formatEntityState === "function" ? this.hass.formatEntityState(st) : null;
      } catch (_err) {
        label = null;
      }
      if (!label && ENUM_GROUPS[key]) label = LABELS[ENUM_GROUPS[key]][st.state] || st.state;
    }
    const time = TIMESTAMPS.has(key) && known ? Date.parse(st.state) : NaN;
    return {
      available,
      known,
      state: known ? st.state : null,
      value: known && Number.isFinite(number) ? number : null,
      unit: (st.attributes && st.attributes.unit_of_measurement) || "",
      digits: entry && Number.isInteger(entry.display_precision) ? entry.display_precision : null,
      label,
      time: Number.isFinite(time) ? time : null,
    };
  }

  peers() {
    return this.node ? this.node.peers : [];
  }

  peerState(peer) {
    return peerState(peer, this.hass ? this.hass.states : {});
  }

  availability() {
    return this.node && this.hass ? nodeState(this.node, this.hass.states) : "unavailable";
  }

  version() {
    const id = this._id("status");
    const entry = id && this.hass && this.hass.entities ? this.hass.entities[id] : null;
    const device = entry && entry.device_id && this.hass.devices ? this.hass.devices[entry.device_id] : null;
    return (device && device.sw_version) || null;
  }

  historyKeys() {
    return HISTORY_KEYS.filter((k) => this.has(k));
  }

  /** History from Home Assistant's recorder: {key: [{t, v}]}. Throws if unavailable. */
  async history(range, start, end) {
    const keys = this.historyKeys();
    const ids = keys.map((k) => this._id(k));
    if (!ids.length) return {};
    let raw;
    if (range.source === "statistics") {
      const stats = await this.hass.callWS({
        type: "recorder/statistics_during_period",
        start_time: new Date(start).toISOString(),
        end_time: new Date(end).toISOString(),
        statistic_ids: ids,
        period: "hour",
        types: ["mean"],
      });
      raw = ids.map((id) => seriesFromStatistics(stats && stats[id]));
    } else {
      const hist = await this.hass.callWS({
        type: "history/history_during_period",
        start_time: new Date(start).toISOString(),
        end_time: new Date(end).toISOString(),
        entity_ids: ids,
        minimal_response: true,
        no_attributes: true,
        significant_changes_only: false,
      });
      raw = ids.map((id) => seriesFromHistory(hist && hist[id]));
    }
    return Object.fromEntries(keys.map((k, i) => [k, raw[i]]));
  }

  /** A cache key for history: changes when the app or the set of series changes. */
  historyScope() {
    return `${this.node ? this.node.entry_id : ""}|${this.historyKeys().join(",")}`;
  }
}
