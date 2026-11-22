// SPDX-License-Identifier: Apache-2.0
// ito views (Overview, Diagnostics). They read data only through the view-data contract
// (source.reading/has/peers/peerState/availability/version: model.js NODE_KEYS, PEER_KEYS) and
// build the page from components. No Home Assistant objects, no network, no storage.
//
// ctx = { source, now, range, history: {state, values}, onRange, copy }

import { CONNECTIVITY_TEXT, MESSAGING_NOTE, MESSAGING_OFF_TEXT, MESSAGING_STEPS, RANGES, TONES, duration, formatNumber, pathsNote, precision } from "../model.js";
import { banner, chartCard, chip, copyButton, segmented, statusMark, tile, value } from "./components.js";
import { h } from "./dom.js";

const DASH = "—";

/** A reading's number, in its own precision or a fallback. */
export function figure(r, language, fallbackDigits) {
  if (!r.known || r.value === null) return DASH;
  return formatNumber(r.value, language, precision({ display_precision: r.digits }, r.value, fallbackDigits));
}

/** A reading as words: enum label, on/off phrasing, number with unit, or a placeholder. */
export function words(r, language, onOff = null) {
  if (!r.available) return "Unavailable";
  if (!r.known) return "Unknown";
  if (onOff && (r.state === "on" || r.state === "off")) return r.state === "on" ? onOff[0] : onOff[1];
  if (r.label) return r.label;
  if (r.value !== null) return `${figure(r, language)}${r.unit ? ` ${r.unit}` : ""}`;
  return r.state;
}

function ago(r, now) {
  return r.time === null ? null : Math.max(0, (now - r.time) / 1000);
}

function problemBanner(ctx) {
  const { source } = ctx;
  const detected = source.reading("problem_detected");
  if (detected.state !== "on") return null;
  const tone = source.reading("status").state === "needs_attention" ? "bad" : "warn";
  return banner(tone, words(source.reading("problem")), ctx.copy.problemHint);
}

function unavailableBanner(ctx) {
  return banner("neutral", "ito is not responding", ctx.copy.unavailable);
}

function hero(ctx) {
  const { source } = ctx;
  const conn = source.reading("connectivity");
  const status = source.reading("status");
  const transport = source.reading("transport_mode");
  const detected = source.reading("problem_detected");
  const key = conn.known ? conn.state : "unknown";
  const tone = conn.known ? TONES.connectivity[key] || "neutral" : "neutral";
  const title = conn.available ? words(conn) : "Unavailable";
  const chips = [];
  if (source.has("status")) chips.push(chip(status.known ? TONES.status[status.state] || "neutral" : "neutral", status.available ? words(status) : "Unavailable"));
  if (transport.known) chips.push(chip(transport.state === "on" ? "info" : "neutral", transport.state === "on" ? "Transport enabled" : "Transport off"));
  if (detected.known && detected.state === "off") chips.push(chip("good", "No problems"));
  return h(
    "section",
    { class: "card hero", "data-tone": tone, "aria-label": "Connectivity" },
    statusMark(conn.known ? key : "unknown", `Connectivity: ${title}`),
    h(
      "div",
      {},
      h("p", { class: "title", text: title }),
      h("div", { class: "muted small", text: conn.known ? CONNECTIVITY_TEXT[key] || "" : "Connectivity is not known while the app is unavailable." }),
      h("div", { class: "chips" }, chips),
    ),
  );
}

function tiles(ctx) {
  const { source } = ctx;
  const lang = source.language;
  const out = [];
  if (source.has("peers_connected")) {
    const configured = source.reading("peers_configured");
    out.push(tile("Peers connected", "mdi:account-network", value(figure(source.reading("peers_connected"), lang, 0), configured.known ? `of ${figure(configured, lang, 0)}` : "")));
  }
  if (source.has("known_paths")) {
    const r = source.reading("known_paths");
    out.push(tile("Known paths", "mdi:map-marker-path", value(figure(r, lang, 0)), pathsNote(r.value)));
  }
  if (source.has("relayed_links")) out.push(tile("Links relayed for others", "mdi:swap-horizontal", value(figure(source.reading("relayed_links"), lang, 0))));
  for (const [key, label, ic] of [
    ["received", "Data received", "mdi:download-network"],
    ["sent", "Data sent", "mdi:upload-network"],
  ]) {
    if (source.has(key)) {
      const r = source.reading(key);
      out.push(tile(label, ic, value(figure(r, lang, 2), r.unit)));
    }
  }
  if (source.has("cpu")) out.push(tile("Processor use", "mdi:cpu-64-bit", value(figure(source.reading("cpu"), lang, 1), "%")));
  if (source.has("memory")) {
    const r = source.reading("memory");
    out.push(tile("Memory use", "mdi:memory", value(figure(r, lang, 0), r.unit)));
  }
  if (source.has("reticulum_started")) out.push(tile("Reticulum running for", "mdi:timer-outline", value(duration(ago(source.reading("reticulum_started"), ctx.now)))));
  return h("section", { class: "tiles", "aria-label": "Key figures" }, out);
}

function charts(ctx) {
  const { source, history } = ctx;
  const range = RANGES.find((r) => r.key === ctx.range);
  const state = history.state === "loading" && !Object.keys(history.values).length ? "loading" : history.state === "unavailable" ? "unavailable" : "ready";
  const make = (title, defs, opts) => {
    const present = defs.filter((d) => source.has(d.key));
    if (!present.length) return null;
    const first = source.reading(present[0].key);
    return chartCard({
      title,
      series: present.map((d) => ({ label: d.label, color: d.color, values: history.values[d.key] || [], current: source.reading(d.key).value })),
      unit: first.unit || opts.unit || "",
      digits: opts.digits,
      floor: opts.floor || 0,
      wide: opts.wide,
      state,
      rangeLabel: range.label,
      language: source.language,
      unavailableText: ctx.copy.historyUnavailable,
      emptyText: ctx.copy.historyEmpty,
    });
  };
  const cards = [
    make(
      "Network traffic",
      [
        { key: "receive_rate", label: "↓ Receive", color: "var(--mb-series-1)" },
        { key: "send_rate", label: "↑ Send", color: "var(--mb-series-2)" },
      ],
      { wide: true, digits: 2 },
    ),
    make("Processor use", [{ key: "cpu", color: "var(--mb-series-1)" }], { unit: "%", digits: 1, floor: 1 }),
    make("Memory use", [{ key: "memory", color: "var(--mb-series-2)" }], { digits: 0 }),
  ].filter(Boolean);
  if (!cards.length) return null;
  const ranges = RANGES.filter((r) => ctx.copy.ranges.includes(r.key));
  return h(
    "section",
    { "aria-label": "History" },
    h("div", { class: "section-head", style: "margin-bottom:12px" }, h("h2", { text: "History" }), segmented("History range", ranges, ctx.range, ctx.onRange)),
    h("div", { class: "charts" }, cards),
  );
}

function peerCard(ctx, peer) {
  const { source } = ctx;
  const lang = source.language;
  const state = source.peerState(peer);
  const tone = { connected: "good", disconnected: "bad", unknown: "neutral", missing: "neutral" }[state];
  const text = { connected: "Connected", disconnected: "Not connected", unknown: "Unknown", missing: peer.reported ? "Unavailable" : "No longer configured" }[state];
  const rows = [];
  const add = (label, v) => rows.push(h("dt", { text: label }), h("dd", { text: v }));
  if (state === "connected" && source.has("connected_since", peer)) add("Connected for", duration(ago(source.reading("connected_since", peer), ctx.now)));
  if (source.has("reconnections", peer)) add("Reconnections", figure(source.reading("reconnections", peer), lang, 0));
  for (const [key, label] of [
    ["receive_rate", "Receiving"],
    ["send_rate", "Sending"],
  ]) {
    if (source.has(key, peer)) {
      const r = source.reading(key, peer);
      add(label, `${figure(r, lang, 2)} ${r.unit}`.trim());
    }
  }
  return h(
    "article",
    { class: "card peer", "data-tone": tone },
    h("div", { class: "section-head" }, h("span", { class: "name", text: peer.name }), chip(tone, text)),
    rows.length ? h("dl", {}, rows) : null,
  );
}


/** The optional LXMF messaging engine (M4): its state, address, counts and how to connect. */
function messagingCard(ctx) {
  const m = ctx.source.messaging ? ctx.source.messaging() : null;
  if (!m) return null; // an app without messaging (v0.2)
  const lang = ctx.source.language;
  const head = h("div", { class: "section-head" }, h("h2", { text: "Messaging" }), chip(m.tone, m.label));
  if (m.state === "disabled") {
    return h("section", { class: "card messaging", "data-tone": m.tone, "aria-label": "Messaging" }, head, h("p", { class: "muted small", text: ctx.copy.messagingOff || MESSAGING_OFF_TEXT }));
  }
  const rows = [];
  const add = (label, text) => rows.push(h("dt", { text: label }), h("dd", { text }));
  const n = (v) => (v === null ? "—" : formatNumber(v, lang, 0));
  const reported = m.received !== null || m.reachable !== null; // counts once the engine has answered
  if (reported && m.contacts !== null) add("Contacts reachable", m.reachable === null ? `— of ${n(m.contacts)}` : `${n(m.reachable)} of ${n(m.contacts)}`);
  if (reported) add("Messages received", n(m.received));
  if (m.lastReceived !== null) add("Last message", `${duration(Math.max(0, (ctx.now - m.lastReceived) / 1000))} ago${m.lastFrom ? `, from ${m.lastFrom}` : ""}`);
  if (reported && m.autoReply !== false) add("Confirmation replies sent", n(m.replies));
  if (m.lastReplyLabel) add("Last confirmation", m.lastReplyLabel);
  const address = m.address
    ? h("div", { class: "address" }, h("code", { text: m.address, "aria-label": "Messaging address" }), copyButton(m.address))
    : h("p", { class: "muted small", text: m.state === "running" ? "The address is not known yet." : "The address appears once messaging is running." });
  return h(
    "section",
    { class: "card messaging", "data-tone": m.tone, "aria-label": "Messaging" },
    head,
    m.message ? h("p", { class: "small", role: m.state === "error" || m.state === "paused" ? "alert" : null, text: m.message }) : null,
    h("div", { class: "label small", text: "ito's messaging address" }),
    address,
    rows.length ? h("dl", { class: "rows" }, rows) : null,
    h(
      "details",
      {},
      h("summary", { text: "How to connect an LXMF app" }),
      h("ol", { class: "small" }, MESSAGING_STEPS.map((step) => h("li", { text: step }))),
      h("p", { class: "muted small", text: MESSAGING_NOTE }),
    ),
  );
}

function peers(ctx) {
  const list = ctx.source.peers();
  return h(
    "section",
    { "aria-label": "Peers" },
    h("div", { class: "section-head", style: "margin-bottom:12px" }, h("h2", { text: "Peers" })),
    list.length
      ? h("div", { class: "peers" }, list.map((p) => peerCard(ctx, p)))
      : h("div", { class: "card muted small", text: "No peers are configured. In the ito app's Configuration tab, choose a public network or add a peer, then restart the app." }),
  );
}

export function overview(ctx) {
  const unavailable = ctx.source.availability() === "unavailable";
  return [unavailable ? unavailableBanner(ctx) : problemBanner(ctx), hero(ctx), tiles(ctx), messagingCard(ctx), charts(ctx), peers(ctx)].filter(Boolean);
}

export function diagnostics(ctx) {
  const { source } = ctx;
  const lang = source.language;
  const rows = [];
  const add = (label, key, format) => {
    if (!source.has(key)) return;
    const r = source.reading(key);
    rows.push(h("dt", { text: label }), h("dd", { text: format ? format(r) : words(r, lang) }));
  };
  const since = (r) => (r.time === null ? words(r, lang) : `${duration(ago(r, ctx.now))} ago`);
  const version = source.version();
  if (version) rows.push(h("dt", { text: "ito version" }), h("dd", { text: version }));
  add("Status", "status");
  add("Problem", "problem");
  add("Reticulum running", "reticulum_running", (r) => words(r, lang, ["Yes", "No"]));
  add("Transport mode", "transport_mode", (r) => words(r, lang, ["Enabled", "Off"]));
  add("App started", "app_started", since);
  add("Reticulum started", "reticulum_started", since);
  add("Reticulum restarts", "restarts");
  add("Restarts to free memory", "memory_restarts");
  add("Peers configured", "peers_configured");
  add("Memory use (total)", "memory");
  add("Memory use (ito core)", "core_memory");
  add("Memory use (Reticulum)", "reticulum_memory");
  add("Memory use (messaging)", "messaging_memory");
  add("Processor use", "cpu");
  add("Packets received (all traffic)", "packets_received");
  add("Packets sent (all traffic)", "packets_sent");
  add("Announces received", "announces_received");
  add("Announces sent", "announces_sent");
  const unavailable = source.availability() === "unavailable";
  return [
    unavailable ? unavailableBanner(ctx) : problemBanner(ctx),
    h("section", { class: "card", "aria-label": "Diagnostics" }, h("dl", { class: "rows" }, rows)),
    ctx.copy.diagnosticsNote ? h("p", { class: "muted small", text: ctx.copy.diagnosticsNote }) : null,
  ].filter(Boolean);
}
