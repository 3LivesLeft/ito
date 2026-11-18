// SPDX-License-Identifier: Apache-2.0
// The view-data contract and the layer boundaries (docs/architecture.md, "Interface layers").
// Both data sources must offer the same keys with the same meaning, and presentation code must
// never reach into Home Assistant or the network directly.

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";

import { HISTORY_KEYS, NODE_KEYS, PEER_KEYS } from "../../custom_components/meshbeacon/frontend/model.js";
import { HassSource } from "../../custom_components/meshbeacon/frontend/sources/hass.js";
import { SnapshotSource } from "../../custom_components/meshbeacon/frontend/sources/snapshot.js";

const FRONTEND = new URL("../../custom_components/meshbeacon/frontend/", import.meta.url);
const READING_FIELDS = ["available", "digits", "known", "label", "state", "time", "unit", "value"];

function snapshot(changes = {}) {
  const base = {
    schema: 1,
    generated_at: 1000,
    app: { version: "0.2.0", state: "running", connectivity: "online", problem: "none", started_at: 600 },
    node: { running: true, started_at: 610, transport_enabled: true, restarts: 0, memory_restarts: 0 },
    network: {
      peers_configured: 1, peers_connected: 1, rx_bytes: 2_000_000, tx_bytes: 1_000_000, rx_rate: 120.5, tx_rate: 60,
      packets_rx: 900, packets_tx: 800, paths: 2048, relayed_links: 2, announces_rx: 300, announces_tx: 20,
    },
    peers: [{ name: "Emerald", connected: true, connected_since: 620, rx_bytes: 5, tx_bytes: 6, rx_rate: 1500, tx_rate: 0, announces_rx: 1, announces_tx: 2, reconnections: 1 }],
    resources: { memory_bytes: 78 * 2 ** 20, core_memory_bytes: 2 ** 20, reticulum_memory_bytes: 2 ** 21, cpu_percent: 1.8 },
  };
  return { ...base, ...changes };
}

function fakeHass(states, entities = {}) {
  return {
    language: "en-GB",
    states,
    entities,
    callWS: async (msg) => {
      if (msg.type === "meshbeacon/panel") {
        return {
          nodes: [
            {
              entry_id: "e1", title: "MeshBeacon", app: "local_meshbeacon",
              entities: { known_paths: "sensor.p", connectivity: "sensor.c", status: "sensor.s", receive_rate: "sensor.r" },
              peers: [{ name: "Emerald", reported: true, entities: { connected: "binary_sensor.e" } }],
            },
          ],
        };
      }
      if (msg.type === "history/history_during_period") return { "sensor.r": [{ s: "1.5", lu: 10 }, { s: "unavailable", lu: 20 }] };
      throw new Error("unexpected");
    },
  };
}

test("both sources return complete readings for every contract key", async () => {
  const snap = new SnapshotSource();
  snap.update(snapshot());
  const hass = new HassSource();
  hass.update(fakeHass({}));
  for (const key of NODE_KEYS) {
    assert.deepEqual(Object.keys(snap.reading(key)).sort(), READING_FIELDS, `snapshot ${key}`);
    assert.deepEqual(Object.keys(hass.reading(key)).sort(), READING_FIELDS, `hass ${key}`);
  }
  for (const key of PEER_KEYS) assert.deepEqual(Object.keys(snap.reading(key, { name: "Emerald" })).sort(), READING_FIELDS);
});

test("snapshot source converts to the units the integration presents", () => {
  const src = new SnapshotSource();
  src.update(snapshot());
  assert.equal(src.reading("received").value, 2);
  assert.equal(src.reading("received").unit, "MB");
  assert.equal(src.reading("receive_rate").value, 0.1205);
  assert.equal(src.reading("receive_rate").unit, "kB/s");
  assert.equal(src.reading("memory").value, 78);
  assert.equal(src.reading("memory").unit, "MiB");
  assert.equal(src.reading("known_paths").value, 2048);
  assert.equal(src.reading("status").label, "Running");
  assert.equal(src.reading("problem_detected").state, "off");
  assert.equal(src.reading("transport_mode").state, "on");
  assert.equal(src.reading("reticulum_started").time, 610_000);
  assert.equal(src.reading("receive_rate", { name: "Emerald" }).value, 1.5);
  assert.equal(src.peerState({ name: "Emerald" }), "connected");
  assert.equal(src.version(), "0.2.0");
});

test("snapshot source: unknown values stay unknown, never zero", () => {
  const src = new SnapshotSource();
  src.update(snapshot({ network: { ...snapshot().network, paths: null, rx_rate: -1 }, resources: { ...snapshot().resources, cpu_percent: Number.NaN } }));
  for (const key of ["known_paths", "receive_rate", "cpu"]) {
    const r = src.reading(key);
    assert.equal(r.available, true, key);
    assert.equal(r.known, false, key);
    assert.equal(r.value, null, key);
  }
});

test("snapshot source: an unreachable app makes every reading unavailable but keeps the layout", () => {
  const src = new SnapshotSource();
  src.update(snapshot());
  assert.equal(src.update(null), true);
  assert.equal(src.availability(), "unavailable");
  assert.equal(src.reading("known_paths").available, false);
  assert.equal(src.peerState({ name: "Emerald" }), "missing");
  assert.equal(src.phase, "ready");
});

test("snapshot source refuses other schemas and hostile shapes", () => {
  const src = new SnapshotSource();
  src.update({ schema: 2 });
  assert.equal(src.phase, "error");
  const ok = new SnapshotSource();
  ok.update(snapshot({ peers: [null, 5, { name: 7 }, { name: "A" }, { name: "A" }, ...Array.from({ length: 20 }, (_, i) => ({ name: `P${i}` }))] }));
  const names = ok.peers().map((p) => p.name);
  assert.equal(names[0], "A");
  assert.equal(new Set(names).size, names.length);
  assert.ok(names.length <= 10);
});

test("hass source maps entities, readings and history through Home Assistant", async () => {
  const states = {
    "sensor.p": { entity_id: "sensor.p", state: "2048", attributes: {} },
    "sensor.c": { entity_id: "sensor.c", state: "online", attributes: {} },
    "sensor.s": { entity_id: "sensor.s", state: "unavailable", attributes: {} },
    "sensor.r": { entity_id: "sensor.r", state: "1.5", attributes: { unit_of_measurement: "kB/s" } },
    "binary_sensor.e": { entity_id: "binary_sensor.e", state: "on", attributes: {} },
  };
  const src = new HassSource();
  src.update(fakeHass(states, { "sensor.r": { display_precision: 3 } }));
  await src.load();
  assert.equal(src.phase, "ready");
  assert.equal(src.reading("known_paths").value, 2048);
  assert.equal(src.reading("connectivity").label, "Online"); // no formatEntityState: built-in label
  assert.equal(src.reading("status").available, false);
  assert.equal(src.reading("receive_rate").digits, 3);
  assert.equal(src.reading("receive_rate").unit, "kB/s");
  assert.equal(src.has("cpu"), false); // disabled or absent entities are simply not shown
  assert.equal(src.peerState(src.peers()[0]), "connected");
  assert.deepEqual(src.historyKeys(), ["receive_rate"]);
  const history = await src.history({ source: "history", hours: 6 }, 0, 30_000);
  assert.deepEqual(history.receive_rate, [{ t: 10_000, v: 1.5 }, { t: 20_000, v: null }]);
});

test("hass source reports a loading error instead of throwing", async () => {
  const src = new HassSource();
  src.update({ ...fakeHass({}), callWS: async () => Promise.reject({ code: "unknown_command" }) });
  await src.load();
  assert.equal(src.phase, "error");
  assert.equal(src.error, "unknown_command");
});

test("history keys are the contract's", () => {
  const src = new SnapshotSource({ history: async () => ({}) });
  assert.deepEqual(src.historyKeys(), [...HISTORY_KEYS]);
  assert.deepEqual(new SnapshotSource().historyKeys(), []);
});

// --- layer boundaries --------------------------------------------------------------------------

const read = (path) => readFileSync(new URL(path, FRONTEND), "utf8");
const strip = (source) => source.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");

test("presentation (ui/) never touches Home Assistant, the network or storage", () => {
  for (const name of readdirSync(new URL("ui/", FRONTEND))) {
    const code = strip(read(`ui/${name}`));
    assert.doesNotMatch(code, /\bhass\b|callWS|formatEntityState|\.states\[/, `ui/${name} reaches into Home Assistant`);
    assert.doesNotMatch(code, /\bfetch\(|XMLHttpRequest|WebSocket|localStorage|sessionStorage|indexedDB/, `ui/${name}`);
    assert.doesNotMatch(code, /from "\.\.\/sources\//, `ui/${name} imports a data source`);
  }
});

test("data sources never touch the DOM", () => {
  for (const name of readdirSync(new URL("sources/", FRONTEND))) {
    const code = strip(read(`sources/${name}`));
    assert.doesNotMatch(code, /\bdocument\b|\bwindow\b|customElements|innerHTML/, `sources/${name}`);
    assert.doesNotMatch(code, /from "\.\.\/ui\//, `sources/${name} imports presentation`);
  }
});

test("only the snapshot source is free of Home Assistant; the delivery shell is the only HA-specific UI file", () => {
  assert.doesNotMatch(strip(read("sources/snapshot.js")), /\bhass\b|callWS/);
  const shell = read("meshbeacon-panel.js");
  assert.match(shell, /HassSource/);
  assert.match(shell, /InterfaceController/);
});
