// SPDX-License-Identifier: Apache-2.0
// MeshBeacon panel: pure functions (no DOM, no network). Tested with `node --test tests/frontend`.
//
// Everything shown comes from Home Assistant: entity states for live values and the recorder for
// history. Nothing here fetches from the app or stores anything.

export const UNAVAILABLE = new Set(["unavailable", "unknown", "", null, undefined]);

// RNS 1.6.0 culls never-used path-table entries down to this target every five minutes
// (RNS/Transport.py, PATH_POOL_UNUSED_TARGET). A count at or just above it is normal on a busy
// network, not a fault. See docs/research/known-paths.md.
export const PATH_POOL_TARGET = 2048;

export const TONES = {
  status: { running: "good", starting: "info", restarting: "warn", needs_attention: "bad" },
  connectivity: { online: "good", partial: "warn", offline: "bad", isolated: "neutral", unknown: "neutral" },
};

export const LABELS = {
  status: { starting: "Starting", running: "Running", restarting: "Restarting", needs_attention: "Needs attention" },
  connectivity: {
    isolated: "Isolated",
    offline: "Offline",
    partial: "Partly connected",
    online: "Online",
    unknown: "Unknown",
  },
};

LABELS.problem = {
  none: "None",
  isolated: "Not connected to anyone",
  peers_unreachable: "Cannot reach any peer",
  some_peers_unreachable: "Some peers unreachable",
  reticulum_restarting: "Reticulum restarting",
  reticulum_failing: "Reticulum keeps failing",
  restart_loop_paused: "Paused after repeated restarts",
  options: "Options need correcting",
  storage: "Storage low",
  identity: "Identity problem",
  configuration: "Configuration problem",
  data_folder: "Data folder problem",
  preparation_failed: "Preparation failed",
  unexpected: "Unexpected problem",
};

/**
 * The view-data contract (docs/architecture.md, "Interface layers"). Every data source offers
 * readings under these keys, which are the integration's entity keys and map one to one onto the
 * core's status snapshot (schema 1). Views use only these keys, never a source's internals.
 */
export const NODE_KEYS = Object.freeze([
  "status", "connectivity", "problem", "problem_detected", "reticulum_running", "transport_mode",
  "app_started", "reticulum_started", "peers_connected", "peers_configured", "received", "sent",
  "receive_rate", "send_rate", "packets_received", "packets_sent", "known_paths", "relayed_links",
  "announces_received", "announces_sent", "memory", "core_memory", "reticulum_memory", "cpu",
  "restarts", "memory_restarts",
]);
export const PEER_KEYS = Object.freeze([
  "connected", "connected_since", "reconnections", "received", "sent", "receive_rate", "send_rate",
  "announces_received", "announces_sent",
]);
export const HISTORY_KEYS = Object.freeze(["receive_rate", "send_rate", "cpu", "memory"]);

/** A reading that is absent: the source has no such value (for example a disabled sensor). */
export const ABSENT = Object.freeze({ available: false, known: false, state: null, value: null, unit: "", digits: null, label: null, time: null });

export const CONNECTIVITY_TEXT = {
  online: "Connected to every configured peer.",
  partial: "Connected to some peers. The others are being retried automatically.",
  offline: "Cannot reach any peer. MeshBeacon keeps retrying.",
  isolated: "No peers are configured, so this node only reaches devices on its own network.",
  unknown: "Waiting for the first report from the app.",
};

export const RANGES = [
  { key: "6h", label: "6 h", hours: 6, source: "history" },
  { key: "24h", label: "24 h", hours: 24, source: "history" },
  { key: "7d", label: "7 days", hours: 24 * 7, source: "statistics" },
];

export const TABS = [
  { key: "overview", label: "Overview" },
  { key: "messages", label: "Messages" }, // shown only for an app with messaging (M5)
  { key: "diagnostics", label: "Diagnostics" },
];

export function tabFromPath(path) {
  const key = String(path || "")
    .replace(/^\/+/, "")
    .split("/")[0];
  return TABS.some((t) => t.key === key) ? key : "overview";
}

export function numeric(state) {
  if (!state || UNAVAILABLE.has(state.state)) return null;
  const value = Number(state.state);
  return Number.isFinite(value) ? value : null;
}

export function isAvailable(state) {
  return Boolean(state) && state.state !== "unavailable";
}

export function formatNumber(value, language, digits = 0) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(language || "en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

/** Digits to show: the entity's display precision if set, otherwise a sensible default. */
export function precision(entityEntry, value, fallback) {
  const p = entityEntry && Number.isInteger(entityEntry.display_precision) ? entityEntry.display_precision : null;
  if (p !== null) return p;
  if (fallback !== undefined) return fallback;
  if (value === null || Number.isInteger(value)) return 0;
  return Math.abs(value) < 10 ? 2 : 1;
}

export function unit(state) {
  return (state && state.attributes && state.attributes.unit_of_measurement) || "";
}

/** "3 min", "2 h 5 min", "4 days" — for uptime and "connected for". */
export function duration(seconds) {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const s = Math.floor(seconds);
  if (s < 60) return "under a minute";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return m % 60 ? `${h} h ${m % 60} min` : `${h} h`;
  const d = Math.floor(h / 24);
  return `${d} days`;
}

export function secondsSince(state, now) {
  if (!state || UNAVAILABLE.has(state.state)) return null;
  const t = Date.parse(state.state);
  return Number.isFinite(t) ? Math.max(0, (now - t) / 1000) : null;
}

/** Recorder history (minimal response: [{s, lu}] with lu in seconds) to [{t (ms), v}]. */
export function seriesFromHistory(rows) {
  if (!Array.isArray(rows)) return [];
  const out = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const at = Number(row.lu ?? row.lc);
    if (!Number.isFinite(at)) continue;
    const value = Number(row.s);
    out.push({ t: at * 1000, v: UNAVAILABLE.has(row.s) || !Number.isFinite(value) ? null : value });
  }
  return out.sort((a, b) => a.t - b.t);
}

/** Long-term statistics ([{start (ms), mean, max}]) to [{t, v}] using the hourly mean. */
export function seriesFromStatistics(rows) {
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((r) => r && Number.isFinite(Number(r.start)))
    .map((r) => ({ t: Number(r.start), v: Number.isFinite(r.mean) ? r.mean : null }))
    .sort((a, b) => a.t - b.t);
}

/**
 * Downsample a step series into ``count`` equal time buckets between ``start`` and ``end``.
 * A recorder row holds its value until the next row, so each bucket takes the time-weighted mean of
 * the values covering it. Buckets before the first row, or covered only by unavailable values, are
 * null (drawn as a gap, never as zero).
 */
export function bucket(series, start, end, count) {
  const out = new Array(count).fill(null);
  if (!series.length || end <= start || count < 1) return out;
  const width = (end - start) / count;
  const sums = new Array(count).fill(0);
  const covered = new Array(count).fill(0);
  for (let i = 0; i < series.length; i += 1) {
    const { t, v } = series[i];
    if (v === null) continue;
    const from = Math.max(t, start);
    const to = Math.min(i + 1 < series.length ? series[i + 1].t : end, end);
    if (to <= from) continue;
    let b = Math.max(0, Math.floor((from - start) / width));
    while (b < count) {
      const bStart = start + b * width;
      const bEnd = bStart + width;
      const overlap = Math.min(to, bEnd) - Math.max(from, bStart);
      if (overlap > 0) {
        sums[b] += v * overlap;
        covered[b] += overlap;
      }
      if (bEnd >= to) break;
      b += 1;
    }
  }
  for (let b = 0; b < count; b += 1) out[b] = covered[b] > 0 ? sums[b] / covered[b] : null;
  return out;
}

/** A round axis maximum at or above ``value`` (1, 2, 2.5, 5 × 10ⁿ). */
export function niceMax(value) {
  if (!Number.isFinite(value) || value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 2.5, 5, 10]) {
    if (value <= step * power) return step * power;
  }
  return 10 * power;
}

/**
 * Geometry for an SVG chart of one or more bucketed series sharing an axis. Returns, per series, a
 * line path and a closed area path (gaps split the path), plus the axis maximum.
 */
export function chartPaths(seriesList, width, height, floor = 0) {
  const peak = Math.max(floor, ...seriesList.flat().filter((v) => v !== null));
  const max = niceMax(peak);
  const n = Math.max(1, ...seriesList.map((s) => s.length));
  const x = (i) => (n === 1 ? width / 2 : (i / (n - 1)) * width);
  const y = (v) => height - (Math.min(v, max) / max) * height;
  const fmt = (v) => Math.round(v * 10) / 10;
  const paths = seriesList.map((values) => {
    let line = "";
    let area = "";
    let dots = "";
    let run = [];
    const flush = () => {
      if (!run.length) return;
      if (run.length === 1) {
        // An isolated value (for example the first minutes of history): drawn as a round dot.
        dots += `M${fmt(run[0][0])},${fmt(run[0][1])}h0`;
      }
      const pts = run.length === 1 ? [run[0], [run[0][0] + 0.01, run[0][1]]] : run;
      line += `M${pts.map(([px, py]) => `${fmt(px)},${fmt(py)}`).join("L")}`;
      area += `M${fmt(pts[0][0])},${height}L${pts.map(([px, py]) => `${fmt(px)},${fmt(py)}`).join("L")}L${fmt(pts[pts.length - 1][0])},${height}Z`;
      run = [];
    };
    values.forEach((v, i) => (v === null ? flush() : run.push([x(i), y(v)])));
    flush();
    return { line, area, dots };
  });
  return { max, paths };
}

export function lastValue(values) {
  for (let i = values.length - 1; i >= 0; i -= 1) if (values[i] !== null) return values[i];
  return null;
}

export function peakValue(values) {
  const present = values.filter((v) => v !== null);
  return present.length ? Math.max(...present) : null;
}

/**
 * The overall view state for a node, from its entities' current states.
 *   "unavailable": the integration cannot reach the app (every main entity is unavailable);
 *   "ok": values are present (some may still be unknown).
 */
export function nodeState(node, states) {
  const ids = Object.values(node.entities || {});
  if (!ids.length) return "unavailable";
  const main = ["status", "connectivity", "known_paths"].map((k) => node.entities[k]).filter(Boolean);
  const check = main.length ? main : ids;
  return check.every((id) => !isAvailable(states[id])) ? "unavailable" : "ok";
}

export function peerState(peer, states) {
  const connected = states[peer.entities.connected];
  if (!peer.reported || !isAvailable(connected)) return "missing";
  if (connected.state === "on") return "connected";
  if (connected.state === "off") return "disconnected";
  return "unknown";
}

export function pathsNote(paths) {
  if (paths === null || paths < PATH_POOL_TARGET) return null;
  return `Normal on a busy network: Reticulum trims paths it has never used to about ${formatNumber(PATH_POOL_TARGET, "en-GB")}.`;
}

// -- Optional LXMF messaging (M4) ---------------------------------------------------------------
LABELS.messaging = { disabled: "Off", starting: "Starting", running: "Running", error: "Problem", paused: "Paused", unavailable: "Unavailable" };
LABELS.delivery = {
  queued: "Queued",
  sending: "Sending",
  sent_unconfirmed: "Sent, not confirmed",
  delivered: "Delivered",
  stored_on_node: "Stored on a propagation node",
  failed: "Failed",
  rejected: "Refused",
  expired: "Expired",
};
export const MESSAGING_TONES = { disabled: "neutral", starting: "info", running: "good", error: "bad", paused: "bad", unavailable: "neutral" };
export const MESSAGING_OFF_TEXT =
  "LXMF messaging is off. To use it, open Settings → Apps → MeshBeacon → Configuration, tick “Enable LXMF messaging”, save, and restart the app.";
export const MESSAGING_STEPS = Object.freeze([
  "In your LXMF app (for example Sideband), connect to the same Reticulum network as MeshBeacon, for example through the same peer.",
  "Add MeshBeacon as a contact in that app, using the address above.",
  "In MeshBeacon's Messages tab, choose “Add contact” and enter your app's own LXMF address.",
  "Send MeshBeacon a message from your app. It appears in the Messages tab, where you can reply.",
]);
export const MESSAGING_NOTE =
  "Read and answer messages in the Messages tab. Conversations are kept by the MeshBeacon app, never in Home Assistant's history.";

const ADDRESS = /^[0-9a-f]{32}$/;
const count = (v) => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? Math.round(v) : null);

/**
 * The messaging card's data, the same whichever source it comes from. `raw` uses the status API's
 * field names; times are in seconds. Returns null when the app has no messaging at all (v0.2).
 */
export function messagingSummary(raw) {
  if (!raw || typeof raw !== "object") return null;
  const state = typeof raw.state === "string" && LABELS.messaging[raw.state] ? raw.state : "unavailable";
  const reply = typeof raw.last_reply_state === "string" && LABELS.delivery[raw.last_reply_state] ? raw.last_reply_state : null;
  const at = typeof raw.last_received_at === "number" && Number.isFinite(raw.last_received_at) ? raw.last_received_at * 1000 : null;
  return {
    state,
    label: LABELS.messaging[state],
    tone: MESSAGING_TONES[state],
    message: typeof raw.message === "string" && raw.message ? raw.message.slice(0, 500) : null,
    address: typeof raw.address === "string" && ADDRESS.test(raw.address) ? raw.address : null,
    contacts: count(raw.contacts_configured),
    reachable: count(raw.contacts_reachable),
    received: count(raw.received),
    lastReceived: at,
    lastFrom: typeof raw.last_received_from === "string" && raw.last_received_from ? raw.last_received_from.slice(0, 32) : null,
    replies: count(raw.replies_sent),
    lastReply: reply,
    lastReplyLabel: reply ? LABELS.delivery[reply] : null,
    autoReply: typeof raw.auto_reply === "boolean" ? raw.auto_reply : null,
  };
}

// -- Messages (M5, ADR 0024) ----------------------------------------------------------------------
// What each outbound state means to the user. "Delivered" only for LXMF's delivery proof.
export const DELIVERY_TEXT = Object.freeze({
  queued: "Waiting to send",
  sending: "Sending…",
  delivered: "Delivered",
  stored_on_node: "Stored on a propagation node, not yet delivered",
  sent_unconfirmed: "Sent, no delivery confirmation",
  failed: "Not sent",
  rejected: "Refused",
  expired: "Not delivered within 7 days",
});
export const RETRYABLE = Object.freeze(["failed", "rejected", "expired", "sent_unconfirmed"]);
export const DELIVERY_TONE = Object.freeze({
  queued: "neutral",
  sending: "info",
  delivered: "good",
  stored_on_node: "info",
  sent_unconfirmed: "warn",
  failed: "bad",
  rejected: "bad",
  expired: "bad",
});
// Plain-English messages for the codes the integration and the app return.
export const MESSAGING_ERRORS = Object.freeze({
  not_enabled: "Messaging is off in the MeshBeacon app.",
  unavailable: "Messaging is not running right now. It usually comes back by itself within a minute.",
  unreachable: "Home Assistant cannot reach the MeshBeacon app. It may be restarting.",
  unauthorised: "MeshBeacon has a new key and Home Assistant is fetching it. Try again in a moment.",
  rate_limited: "Too many messages in a short time. Wait a minute, then try again.",
  queue_full: "Too many messages are waiting to be sent. Wait until some are delivered.",
  too_long: "This message is too long. Keep it under about 8,000 characters.",
  invalid_address: "That is not an LXMF address. It has 32 characters, using 0–9 and a–f.",
  invalid_name: "Give the contact a name of up to 32 characters.",
  contact_exists: "This address is already one of your contacts.",
  too_many_contacts: "You have reached the limit of 100 contacts.",
  own_address: "That is MeshBeacon's own address. Enter your contact's address instead.",
  unknown_contact: "This contact no longer exists.",
  unknown_message: "This message no longer exists.",
  not_retryable: "This message cannot be sent again.",
  not_found: "MeshBeacon is not set up in Home Assistant.",
});
export const MESSAGE_MAX_BYTES = 8192;
const LXMF_ADDRESS = /^[0-9a-f]{32}$/;

export function errorText(code) {
  return MESSAGING_ERRORS[code] || "Something went wrong. Try again in a moment.";
}

/** An LXMF address as people paste it: spaces, angle brackets and capitals are allowed. */
export function normaliseAddress(text) {
  const value = String(text || "")
    .trim()
    .replace(/^<|>$/g, "")
    .replace(/\s+/g, "")
    .toLowerCase();
  return LXMF_ADDRESS.test(value) ? value : null;
}

export function byteLength(text) {
  return new TextEncoder().encode(String(text)).length;
}

/** A random idempotency key: the same Send, retried or double-clicked, is one message. */
export function newIdempotencyKey() {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return `ui-${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
}

/** A conversation list entry, from the integration's answer, cleaned and bounded. */
export function conversationItem(raw) {
  if (!raw || typeof raw !== "object" || typeof raw.id !== "string") return null;
  const last = raw.last && typeof raw.last === "object" ? messageItem(raw.last) : null;
  return {
    id: raw.id,
    name: typeof raw.name === "string" && raw.name ? raw.name.slice(0, 32) : raw.id === "unknown" ? "Other senders" : raw.id,
    address: typeof raw.address === "string" && LXMF_ADDRESS.test(raw.address) ? raw.address : null,
    fromConfiguration: raw.origin === "configuration",
    strangers: raw.id === "unknown",
    heard: raw.heard === true,
    unread: typeof raw.unread === "number" && raw.unread > 0 ? Math.round(raw.unread) : 0,
    last,
  };
}

/** One message, from the integration's answer. Text is shown as text only, never as markup. */
export function messageItem(raw) {
  if (!raw || typeof raw !== "object") return null;
  const state = typeof raw.state === "string" && DELIVERY_TEXT[raw.state] ? raw.state : null;
  return {
    seq: typeof raw.seq === "number" ? raw.seq : 0,
    id: typeof raw.message_id === "string" ? raw.message_id : "",
    outgoing: raw.direction === "out",
    text: typeof raw.text === "string" ? raw.text : "",
    at: typeof raw.at === "number" && Number.isFinite(raw.at) ? raw.at * 1000 : null,
    state,
    retrying: state === "queued" && raw.reason === "retrying",
    auto: raw.auto === true,
    unread: raw.unread === true,
  };
}

/** The words under an outgoing message. */
export function deliveryWords(m) {
  if (!m.state) return "";
  if (m.retrying) return "Not reached yet, trying again";
  return DELIVERY_TEXT[m.state];
}
