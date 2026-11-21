// SPDX-License-Identifier: Apache-2.0
import test from "node:test";
import assert from "node:assert/strict";
import { api, IngressMessaging } from "../../custom_components/meshbeacon/frontend/sources/ingress.js";

test("ingress uses relative authenticated no-store requests with a CSRF header", async (t) => {
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push({ url, options });
    return { ok: true, json: async () => ({ ok: true }) };
  });
  await api("config", { op: "config_save", revision: "test", patch: { network: "custom" } });
  assert.equal(requests[0].options.headers["X-Ito-Request"], "1");
  assert.equal(requests[0].options.cache, "no-store");
  assert.equal(requests[0].options.credentials, "same-origin");
  assert.ok(requests[0].url.pathname.endsWith("/api/config"));
});

test("ingress preserves structured configuration errors", async (t) => {
  t.mock.method(globalThis, "fetch", async () => ({ ok: false, json: async () => ({ error: "conflict" }) }));
  await assert.rejects(api("config", {}), (error) => error.code === "conflict");
});

test("message transport preserves operations, pagination and send idempotency", async (t) => {
  const sent = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    sent.push(JSON.parse(options.body));
    return { ok: true, json: async () => ({ ok: true, conversations: [], messages: [] }) };
  });
  const messaging = new IngressMessaging();
  await messaging._call("history", { contact: "test", before: 40 });
  await messaging.send("test", "Fixture message", "test-idempotency-key");
  assert.deepEqual(sent[0], { op: "history", limit: 50, contact: "test", before: 40 });
  assert.deepEqual(sent.find((r) => r.op === "send"), { op: "send", contact: "test", text: "Fixture message", idempotency_key: "test-idempotency-key" });
});

test("live polling stays bounded and stops when hidden", () => {
  const pending = new Map(); let counter = 0;
  const messaging = new IngressMessaging({ setTimeout: (fn, delay) => { pending.set(++counter, {fn,delay}); return counter; }, clearTimeout: (id) => pending.delete(id) });
  messaging.phase = "ready";
  messaging.start(); messaging.start();
  assert.equal(pending.size, 1);
  assert.equal([...pending.values()][0].delay, 5000);
  messaging.stop();
  assert.equal(pending.size, 0);
});
