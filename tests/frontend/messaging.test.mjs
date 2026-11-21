// SPDX-License-Identifier: Apache-2.0
// The dashboard's messaging card data (M4): the same summary from either source, nothing invented
// for an app without messaging, and hostile values never shown as an address.

import assert from "node:assert/strict";
import { test } from "node:test";

import { MESSAGING_STEPS, messagingSummary } from "../../custom_components/meshbeacon/frontend/model.js";
import { HassSource } from "../../custom_components/meshbeacon/frontend/sources/hass.js";
import { SnapshotSource } from "../../custom_components/meshbeacon/frontend/sources/snapshot.js";

const ADDRESS = "a1".repeat(16);

function status(messaging) {
  const doc = {
    schema: 1,
    generated_at: 1000,
    app: { version: "0.3.0", state: "running", connectivity: "isolated", problem: "isolated", started_at: 600 },
    node: { running: true, started_at: 610, transport_enabled: false, restarts: 0, memory_restarts: 0 },
    network: { peers_configured: 0, peers_connected: 0 },
    peers: [],
    resources: { memory_bytes: 110 * 2 ** 20 },
  };
  return messaging === undefined ? doc : { ...doc, messaging };
}

test("an app without messaging (v0.2) shows no messaging card", () => {
  const source = new SnapshotSource();
  source.update(status(undefined));
  assert.equal(source.messaging(), null);
  assert.equal(messagingSummary(null), null);
});

test("snapshot source: off, running and problem states", () => {
  const source = new SnapshotSource();
  source.update(status({ enabled: false, state: "disabled", message: null }));
  assert.equal(source.messaging().state, "disabled");
  assert.equal(source.messaging().address, null);
  source.update(
    status({
      enabled: true, state: "running", address: ADDRESS, contacts_configured: 2, contacts_reachable: 1,
      received: 3, replies_sent: 3, last_reply_state: "delivered", last_received_at: 990, last_received_from: "Phone", auto_reply: true,
    }),
  );
  const m = source.messaging();
  assert.deepEqual(
    [m.state, m.label, m.tone, m.address, m.contacts, m.reachable, m.received, m.lastReceived, m.lastFrom, m.lastReplyLabel],
    ["running", "Running", "good", ADDRESS, 2, 1, 3, 990_000, "Phone", "Delivered"],
  );
  source.update(status({ enabled: true, state: "error", message: "Messaging could not start: …" }));
  assert.equal(source.messaging().tone, "bad");
  assert.match(source.messaging().message, /could not start/);
  source.update(null); // the app stops answering
  assert.equal(source.messaging().state, "unavailable");
});

test("hostile values are never shown as an address or an unknown state", () => {
  const m = messagingSummary({ state: "<img>", address: "<script>alert(1)</script>", last_reply_state: "pwned", received: -4 });
  assert.equal(m.state, "unavailable");
  assert.equal(m.address, null);
  assert.equal(m.lastReply, null);
  assert.equal(m.received, null);
});

test("hass source builds the same summary from the messaging entities", async () => {
  const states = {
    "sensor.m": { entity_id: "sensor.m", state: "running", attributes: { address: ADDRESS, contacts: 1, auto_reply: true, last_received_from: "Phone" } },
    "sensor.r": { entity_id: "sensor.r", state: "4", attributes: {} },
    "sensor.c": { entity_id: "sensor.c", state: "1", attributes: {} },
    "sensor.l": { entity_id: "sensor.l", state: "2026-11-20T12:00:00+00:00", attributes: {} },
    "sensor.y": { entity_id: "sensor.y", state: "stored_on_node", attributes: {} },
  };
  const hass = {
    language: "en-GB",
    states,
    entities: {},
    callWS: async () => ({
      nodes: [
        {
          entry_id: "e1", title: "MeshBeacon", app: "local_meshbeacon", peers: [],
          entities: { messaging: "sensor.m", messages_received: "sensor.r", messaging_contacts_reachable: "sensor.c", messaging_last_received: "sensor.l", messaging_last_reply: "sensor.y" },
        },
      ],
    }),
  };
  const source = new HassSource();
  source.update(hass);
  await source.load();
  const m = source.messaging();
  assert.deepEqual(
    [m.state, m.address, m.contacts, m.reachable, m.received, m.lastFrom, m.lastReply, m.lastReceived],
    ["running", ADDRESS, 1, 1, 4, "Phone", "stored_on_node", Date.parse("2026-11-20T12:00:00+00:00")],
  );
  states["sensor.m"] = { entity_id: "sensor.m", state: "unavailable", attributes: {} };
  assert.equal(source.messaging().state, "unavailable");
});

test("the connection steps name only things the user can do without a terminal", () => {
  const text = MESSAGING_STEPS.join(" ");
  assert.match(text, /Messages tab/);
  assert.doesNotMatch(text, /terminal|ssh|json|docker/i);
});
