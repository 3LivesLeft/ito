// SPDX-License-Identifier: Apache-2.0
// The Messages view's data (M5, ADR 0024): the source talks only through Home Assistant's
// websocket, makes one message of a double click, keeps nothing in browser storage, and the
// helpers never invent a delivery state.

import assert from "node:assert/strict";
import { test } from "node:test";

import { DELIVERY_TEXT, conversationItem, deliveryWords, errorText, messageItem, newIdempotencyKey, normaliseAddress } from "../../custom_components/meshbeacon/frontend/model.js";
import { HassMessaging } from "../../custom_components/meshbeacon/frontend/sources/messaging.js";

const ADDR = "ab".repeat(16);

function fakeHass(handlers = {}) {
  const calls = [];
  const subscriptions = [];
  const hass = {
    calls,
    subscriptions,
    callWS: async (msg) => {
      calls.push(msg);
      const kind = msg.type.split("/").pop();
      if (handlers[kind]) return handlers[kind](msg);
      if (kind === "conversations") return { conversations: [{ id: "alice", name: "Alice", address: ADDR, unread: 2, last: { seq: 2, direction: "in", text: "hi", at: 1 } }] };
      if (kind === "history") return { messages: [{ seq: 1, message_id: "e".repeat(32), direction: "in", text: "<b>hi</b>", at: 1 }] };
      return {};
    },
    connection: {
      subscribeMessage: async (cb, msg) => {
        subscriptions.push({ cb, msg, active: true });
        const s = subscriptions[subscriptions.length - 1];
        return () => {
          s.active = false;
        };
      },
    },
  };
  return hass;
}

test("addresses are accepted as people paste them, and nothing else", () => {
  assert.equal(normaliseAddress(` <${ADDR.toUpperCase()}> `), ADDR);
  assert.equal(normaliseAddress("ab ab ab ab ab ab ab ab ab ab ab ab ab ab ab ab"), ADDR);
  assert.equal(normaliseAddress("ab".repeat(15)), null);
  assert.equal(normaliseAddress("zz".repeat(16)), null);
});

test("a message is delivered only when the app says so", () => {
  assert.equal(messageItem({ direction: "out", state: "nonsense" }).state, null);
  assert.equal(deliveryWords(messageItem({ direction: "out", state: "stored_on_node" })), DELIVERY_TEXT.stored_on_node);
  assert.doesNotMatch(DELIVERY_TEXT.stored_on_node, /^Delivered/);
  assert.equal(deliveryWords(messageItem({ direction: "out", state: "queued", reason: "retrying" })), "Not reached yet, trying again");
  assert.equal(messageItem({ text: "<script>x</script>" }).text, "<script>x</script>"); // kept as text; dom.js writes text only
});

test("conversations are cleaned and bounded", () => {
  const item = conversationItem({ id: "x", name: "N".repeat(80), address: "not an address", unread: -3 });
  assert.equal(item.name.length, 32);
  assert.equal(item.address, null);
  assert.equal(item.unread, 0);
  assert.equal(conversationItem({ id: "unknown", name: "" }).name, "Other senders");
  assert.equal(conversationItem(null), null);
});

test("every error code has plain words, and unknown ones a safe default", () => {
  assert.match(errorText("invalid_address"), /32 characters/);
  assert.match(errorText("whatever"), /Try again/);
});

test("idempotency keys are random and the app accepts their shape", () => {
  const keys = new Set(Array.from({ length: 50 }, newIdempotencyKey));
  assert.equal(keys.size, 50);
  for (const key of keys) assert.match(key, /^[A-Za-z0-9_-]{8,64}$/);
});

test("the source reads conversations and history for the selected app only", async () => {
  const hass = fakeHass();
  const m = new HassMessaging();
  m.bind(hass, "entry1");
  await m.refresh();
  assert.equal(m.phase, "ready");
  assert.equal(m.unread, 2);
  await m.open("alice");
  assert.deepEqual(m.history("alice").messages.map((x) => x.text), ["<b>hi</b>"]);
  assert.equal(m.unread, 0); // opening marks it read
  assert.ok(hass.calls.every((c) => c.entry_id === "entry1"));
  assert.ok(hass.calls.some((c) => c.type === "meshbeacon/messaging/read" && c.contact === "alice"));
});

test("a double click on Send is one request, and the key is passed on", async () => {
  let release;
  const gate = new Promise((r) => (release = r));
  const hass = fakeHass({ send: async () => (await gate, { message_id: "f".repeat(32), state: "queued" }) });
  const m = new HassMessaging();
  m.bind(hass, "entry1");
  const first = m.send("alice", "hello", "ui-key-0001");
  const second = await m.send("alice", "hello", "ui-key-0001");
  assert.equal(second, null);
  assert.equal(m.pendingFor("alice").length, 1);
  release();
  await first;
  const sends = hass.calls.filter((c) => c.type.endsWith("/send"));
  assert.deepEqual(sends, [{ type: "meshbeacon/messaging/send", entry_id: "entry1", contact: "alice", text: "hello", idempotency_key: "ui-key-0001" }]);
  assert.equal(m.pendingFor("alice").length, 0);
});

test("live updates refresh on change, report unavailability and stop cleanly", async () => {
  const hass = fakeHass();
  let now = 0;
  const m = new HassMessaging({ now: () => now });
  m.bind(hass, "entry1");
  m.start();
  await new Promise((r) => setTimeout(r, 0));
  now += 2_000; // reads after a change are at most one every 2 s (no request storm)
  assert.equal(hass.subscriptions.length, 1);
  assert.deepEqual(hass.subscriptions[0].msg, { type: "meshbeacon/messaging/subscribe", entry_id: "entry1" });
  hass.subscriptions[0].cb({ type: "unavailable", error: "unreachable" });
  assert.equal(m.available, false);
  const before = hass.calls.length;
  hass.subscriptions[0].cb({ type: "changed" });
  await new Promise((r) => setTimeout(r, 0));
  assert.ok(hass.calls.length > before && m.available === true);
  m.stop();
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(hass.subscriptions[0].active, false);
});

test("choosing another app forgets the first one's conversations and drafts", async () => {
  const m = new HassMessaging();
  m.bind(fakeHass(), "entry1");
  await m.refresh();
  m.drafts.set("alice", "unsent");
  m.bind(fakeHass(), "entry2");
  assert.deepEqual(m.conversations, []);
  assert.equal(m.drafts.size, 0);
});

test("a failing app is an error with a code, never an exception in the view", async () => {
  const m = new HassMessaging();
  m.bind(fakeHass({ conversations: async () => Promise.reject({ code: "not_enabled" }) }), "entry1");
  await m.refresh();
  assert.equal(m.phase, "error");
  assert.equal(m.error, "not_enabled");
});
