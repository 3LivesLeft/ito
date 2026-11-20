// SPDX-License-Identifier: Apache-2.0
// Data source: the core's status snapshot (schema 1, the same document the status API serves) plus
// an optional history provider. It implements the view-data contract so that the same branded
// views can run in a delivery other than the integration panel (the future built-in interface,
// ADR 0013, and the preview). No DOM, no network: the delivery hands it snapshots and history.
//
// Units match what the integration's sensors present in Home Assistant, so both sources look
// identical: data sizes in MB (10^6 bytes), rates in kB/s (10^3 B/s), memory in MiB (2^20).

import { ABSENT, HISTORY_KEYS, LABELS, messagingSummary } from "../model.js";

const SCHEMA = 1;
const MB = 1e6;
const KB = 1e3;
const MIB = 2 ** 20;

const num = (v) => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null);
const bool = (v) => (typeof v === "boolean" ? v : null);

function reading(value, { unit = "", digits = null, scale = 1, label = null, time = null } = {}) {
  if (value === null || value === undefined) return { ...ABSENT, available: true, unit };
  if (typeof value === "boolean") return { ...ABSENT, available: true, known: true, state: value ? "on" : "off" };
  if (typeof value === "string") return { ...ABSENT, available: true, known: true, state: value, label };
  const v = value / scale;
  return { available: true, known: true, state: String(v), value: v, unit, digits, label, time };
}

const NODE = {
  status: (s) => reading(s.app.state, { label: LABELS.status[s.app.state] }),
  connectivity: (s) => reading(s.app.connectivity, { label: LABELS.connectivity[s.app.connectivity] }),
  problem: (s) => reading(s.app.problem, { label: LABELS.problem[s.app.problem] }),
  problem_detected: (s) => reading(typeof s.app.problem === "string" ? s.app.problem !== "none" : null),
  reticulum_running: (s) => reading(bool(s.node.running)),
  transport_mode: (s) => reading(bool(s.node.transport_enabled)),
  app_started: (s) => timeReading(s.app.started_at),
  reticulum_started: (s) => timeReading(s.node.started_at),
  peers_connected: (s) => reading(num(s.network.peers_connected), { digits: 0 }),
  peers_configured: (s) => reading(num(s.network.peers_configured), { digits: 0 }),
  received: (s) => reading(num(s.network.rx_bytes), { unit: "MB", digits: 2, scale: MB }),
  sent: (s) => reading(num(s.network.tx_bytes), { unit: "MB", digits: 2, scale: MB }),
  receive_rate: (s) => reading(num(s.network.rx_rate), { unit: "kB/s", digits: 2, scale: KB }),
  send_rate: (s) => reading(num(s.network.tx_rate), { unit: "kB/s", digits: 2, scale: KB }),
  packets_received: (s) => reading(num(s.network.packets_rx), { digits: 0 }),
  packets_sent: (s) => reading(num(s.network.packets_tx), { digits: 0 }),
  known_paths: (s) => reading(num(s.network.paths), { digits: 0 }),
  relayed_links: (s) => reading(num(s.network.relayed_links), { digits: 0 }),
  announces_received: (s) => reading(num(s.network.announces_rx), { digits: 0 }),
  announces_sent: (s) => reading(num(s.network.announces_tx), { digits: 0 }),
  memory: (s) => reading(num(s.resources.memory_bytes), { unit: "MiB", digits: 0, scale: MIB }),
  core_memory: (s) => reading(num(s.resources.core_memory_bytes), { unit: "MiB", digits: 1, scale: MIB }),
  reticulum_memory: (s) => reading(num(s.resources.reticulum_memory_bytes), { unit: "MiB", digits: 1, scale: MIB }),
  cpu: (s) => reading(num(s.resources.cpu_percent), { unit: "%", digits: 1 }),
  restarts: (s) => reading(num(s.node.restarts), { digits: 0 }),
  memory_restarts: (s) => reading(num(s.node.memory_restarts), { digits: 0 }),
};

const PEER = {
  connected: (p) => reading(bool(p.connected)),
  connected_since: (p) => timeReading(p.connected_since),
  reconnections: (p) => reading(num(p.reconnections), { digits: 0 }),
  received: (p) => reading(num(p.rx_bytes), { unit: "MB", digits: 2, scale: MB }),
  sent: (p) => reading(num(p.tx_bytes), { unit: "MB", digits: 2, scale: MB }),
  receive_rate: (p) => reading(num(p.rx_rate), { unit: "kB/s", digits: 2, scale: KB }),
  send_rate: (p) => reading(num(p.tx_rate), { unit: "kB/s", digits: 2, scale: KB }),
  announces_received: (p) => reading(num(p.announces_rx), { digits: 0 }),
  announces_sent: (p) => reading(num(p.announces_tx), { digits: 0 }),
};

function timeReading(seconds) {
  const t = num(seconds);
  if (t === null) return { ...ABSENT, available: true };
  return { ...ABSENT, available: true, known: true, state: new Date(t * 1000).toISOString(), time: t * 1000 };
}

function valid(snapshot) {
  return (
    snapshot &&
    snapshot.schema === SCHEMA &&
    ["app", "node", "network", "resources"].every((k) => snapshot[k] && typeof snapshot[k] === "object") &&
    Array.isArray(snapshot.peers)
  );
}

export class SnapshotSource {
  /**
   * @param {object} options
   * @param {string} [options.language]
   * @param {(range, start, end) => Promise<object>} [options.history] series {key: [{t, v}]} in
   *   the units above; omitted when the delivery has no history.
   */
  constructor({ language = "en-GB", history = null } = {}) {
    this.language = language;
    this.snapshot = null;
    this.error = null;
    this.reachable = false;
    this._history = history;
  }

  get phase() {
    if (this.error && !this.snapshot) return "error";
    return this.snapshot ? "ready" : "loading";
  }

  /** Give the latest snapshot (or null when the app cannot be reached). Returns true if changed. */
  update(snapshot) {
    if (snapshot === null) {
      const changed = this.reachable;
      this.reachable = false;
      return changed;
    }
    if (!valid(snapshot)) {
      this.error = "unsupported_schema";
      return true;
    }
    const changed = !this.snapshot || snapshot.generated_at !== this.snapshot.generated_at || !this.reachable;
    this.snapshot = snapshot;
    this.reachable = true;
    this.error = null;
    return changed;
  }

  fail(error) {
    this.error = error;
  }

  apps() {
    return [];
  }

  select() {}

  has(key, peer = null) {
    return peer ? key in PEER : key in NODE;
  }

  reading(key, peer = null) {
    if (!this.snapshot) return ABSENT;
    const source = peer ? this._peer(peer.name) : this.snapshot;
    const fn = peer ? PEER[key] : NODE[key];
    if (!fn || !source) return ABSENT;
    const r = fn(source);
    return this.reachable ? r : { ...r, available: false, known: false, state: null, value: null };
  }

  _peer(name) {
    return this.snapshot.peers.find((p) => p && p.name === name) || null;
  }

  /** The optional messaging engine (M4), or null when the app has none. */
  messaging() {
    const m = this.snapshot && this.snapshot.messaging;
    if (!m || typeof m !== "object") return null;
    return messagingSummary(this.reachable ? m : { ...m, state: "unavailable" });
  }

  peers() {
    if (!this.snapshot) return [];
    const names = this.snapshot.peers.filter((p) => p && typeof p.name === "string").map((p) => p.name);
    return [...new Set(names)].slice(0, 10).map((name) => ({ name, reported: true }));
  }

  peerState(peer) {
    if (!this.reachable) return "missing";
    const p = this._peer(peer.name);
    if (!p) return "missing";
    return p.connected === true ? "connected" : p.connected === false ? "disconnected" : "unknown";
  }

  availability() {
    return this.snapshot && this.reachable ? "ok" : "unavailable";
  }

  version() {
    return (this.snapshot && typeof this.snapshot.app.version === "string" && this.snapshot.app.version) || null;
  }

  historyKeys() {
    return this._history ? [...HISTORY_KEYS] : [];
  }

  async history(range, start, end) {
    if (!this._history) throw new Error("no history");
    return this._history(range, start, end);
  }

  historyScope() {
    return "snapshot";
  }
}
