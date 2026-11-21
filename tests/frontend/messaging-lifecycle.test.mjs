// SPDX-License-Identifier: Apache-2.0
// The Messages view's connection lifecycle (regression: the reconnection storm). Opening a
// conversation once made an endless conversations/history loop, because every read was announced
// as a change and every change was answered with a read. These tests drive the real data source
// with a fake clock, and fake Home Assistants that behave like the integration and the app.

import assert from "node:assert/strict";
import { test } from "node:test";

import { MESSAGING_ERRORS, errorText } from "../../custom_components/meshbeacon/frontend/model.js";
import { HassMessaging } from "../../custom_components/meshbeacon/frontend/sources/messaging.js";

const ADDR = "ab".repeat(16);
const flush = () => new Promise((resolve) => setImmediate(resolve));

/** A deterministic clock and timer queue for the source (nothing real is scheduled). */
function fakeClock() {
  let now = 0;
  let id = 0;
  const timers = new Map();
  return {
    now: () => now,
    random: () => 0.5, // jitter factor exactly 1
    setTimeout: (fn, ms) => {
      id += 1;
      timers.set(id, { at: now + Math.max(0, ms || 0), fn });
      return id;
    },
    clearTimeout: (handle) => timers.delete(handle),
    pending: () => timers.size,
    /** Move time on in 50 ms steps (about one round trip each), firing timers as they fall due. */
    async advance(ms) {
      const end = now + ms;
      for (;;) {
        await flush();
        const due = [...timers.entries()].filter(([, t]) => t.at <= now).sort((a, b) => a[1].at - b[1].at);
        for (const [handle, t] of due) {
          timers.delete(handle);
          t.fn();
          await flush();
        }
        if (now >= end) break;
        now = Math.min(end, now + 50);
      }
      await flush();
    },
  };
}

/**
 * A fake Home Assistant plus app. `announceReads` models the integration before the fix (every
 * command except "conversations" told every panel "changed"). The app allows 240 reads a minute.
 */
function fakeServer(clock, { announceReads = false, fail = null } = {}) {
  const calls = [];
  const panels = [];
  let window = [];
  const server = {
    calls,
    panels,
    fail, // (kind) => code | null
    count: (kind) => calls.filter((c) => c.kind === kind).length,
    refused: () => calls.filter((c) => c.status !== 200).length,
    announce: () => panels.filter((p) => p.active).forEach((p) => p.cb({ type: "changed" })),
    hass() {
      return {
        callWS: async (msg) => {
          await flush(); // a round trip
          const kind = msg.type.split("/").pop();
          const code = server.fail && server.fail(kind);
          if (code) {
            calls.push({ kind, at: clock.now(), status: 503 });
            throw { code };
          }
          window = window.filter((t) => t > clock.now() - 60_000);
          if (kind !== "send" && window.length >= 240) {
            calls.push({ kind, at: clock.now(), status: 429 });
            throw { code: "rate_limited" };
          }
          if (kind !== "send") window.push(clock.now());
          calls.push({ kind, at: clock.now(), status: 200 });
          if (announceReads ? kind !== "conversations" : !["conversations", "history"].includes(kind)) server.announce();
          if (kind === "conversations") return { conversations: [{ id: "ratspeak", name: "RatSpeak", address: ADDR, unread: 0, last: { seq: 2, direction: "in", text: "hello", at: 2 } }] };
          if (kind === "history") return { messages: [{ seq: 1, message_id: "e".repeat(32), direction: "out", text: "hi", at: 1, state: "delivered" }, { seq: 2, message_id: "f".repeat(32), direction: "in", text: "hello", at: 2 }] };
          if (kind === "send") return { message_id: "a".repeat(32), state: "queued" };
          return {};
        },
        connection: {
          subscribeMessage: async (cb) => {
            const panel = { cb, active: true };
            panels.push(panel);
            return () => {
              panel.active = false;
            };
          },
        },
      };
    },
  };
  return server;
}

function source(clock) {
  return new HassMessaging({ setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout, now: clock.now, random: clock.random });
}

async function openRatSpeak(clock, server, m = source(clock)) {
  m.bind(server.hass(), "e1");
  m.start(); // the Messages tab is shown
  await clock.advance(0);
  m.open("ratspeak"); // the conversation is tapped
  await clock.advance(0);
  return m;
}

test("opening a conversation reads it once and then stays quiet", async () => {
  const clock = fakeClock();
  const server = fakeServer(clock);
  const m = await openRatSpeak(clock, server);
  await clock.advance(60_000);
  assert.equal(server.count("conversations"), 1);
  assert.equal(server.count("history"), 1);
  assert.equal(server.refused(), 0);
  assert.equal(m.history("ratspeak").messages.length, 2); // existing history is shown
  assert.equal(m.available, true);
  assert.equal(server.panels.filter((p) => p.active).length, 1);
  m.stop();
});

test("an integration that announces its own reads cannot make a request storm", async () => {
  // Before the fix this made about 240 requests in the first second, then "Reconnecting".
  const clock = fakeClock();
  const server = fakeServer(clock, { announceReads: true });
  const m = await openRatSpeak(clock, server);
  await clock.advance(60_000);
  assert.equal(server.refused(), 0, "the app's allowance is never used up");
  assert.ok(server.calls.length <= 130, `${server.calls.length} requests in a minute`);
  const firstSecond = server.calls.filter((c) => c.at < 1_000).length;
  assert.ok(firstSecond <= 4, `${firstSecond} requests in the first second`);
  assert.notEqual(m.available, false);
  assert.equal(m.history("ratspeak").messages.length, 2);
  m.stop();
});

test("two dashboards on such an integration stay within the app's allowance together", async () => {
  const clock = fakeClock();
  const server = fakeServer(clock, { announceReads: true });
  const ipad = await openRatSpeak(clock, server);
  const laptop = await openRatSpeak(clock, server);
  await clock.advance(120_000);
  assert.equal(server.refused(), 0);
  assert.equal(server.panels.filter((p) => p.active).length, 2); // one subscription each
  ipad.stop();
  laptop.stop();
});

test("a refused read backs off, ignores changes meanwhile, and recovers by itself", async () => {
  const clock = fakeClock();
  const server = fakeServer(clock);
  server.fail = (kind) => (kind === "conversations" ? "rate_limited" : null);
  const m = source(clock);
  m.bind(server.hass(), "e1");
  m.start();
  await clock.advance(0);
  assert.equal(server.count("conversations"), 1);
  assert.equal(m.error, "rate_limited");
  assert.notEqual(m.available, false, "a refused read is not an outage: sending stays possible");
  for (let s = 0; s < 10; s += 1) {
    server.announce(); // new messages arriving meanwhile
    m.start(); // and Home Assistant updating the panel
    await clock.advance(1_000);
  }
  assert.equal(server.count("conversations"), 1, "no retry inside the back-off");
  await clock.advance(10_000); // 15 s after the refusal
  assert.equal(server.count("conversations"), 2);
  await clock.advance(20_000); // the second wait is longer (30 s)
  assert.equal(server.count("conversations"), 2);
  server.fail = null;
  await clock.advance(10_000); // 45 s
  assert.equal(server.count("conversations"), 3);
  assert.equal(m.phase, "ready");
  assert.equal(m.error, null);
  assert.equal(clock.pending(), 0, "nothing left scheduled once it has recovered");
  m.stop();
});

test("back-off is bounded, jittered and capped at a minute", () => {
  const clock = fakeClock();
  const m = source(clock);
  const waits = [1, 2, 3, 4, 5, 6, 10].map((n) => m._backoff("unavailable", n));
  assert.deepEqual(waits, [2_000, 5_000, 15_000, 30_000, 60_000, 60_000, 60_000]);
  assert.deepEqual([1, 2, 3, 9].map((n) => m._backoff("rate_limited", n)), [15_000, 30_000, 60_000, 60_000]);
  const low = new HassMessaging({ random: () => 0 })._backoff("unavailable", 4);
  const high = new HassMessaging({ random: () => 0.999 })._backoff("unavailable", 4);
  assert.ok(low >= 24_000 && high <= 36_000 && low < high);
});

test("an engine outage shows as unavailable, and messaging comes back without any event", async () => {
  const clock = fakeClock();
  const server = fakeServer(clock);
  server.fail = () => "unavailable";
  const m = source(clock);
  m.bind(server.hass(), "e1");
  m.start();
  await clock.advance(0);
  assert.equal(m.available, false);
  assert.equal(m.phase, "error");
  server.fail = null; // the engine is back
  await clock.advance(2_000);
  assert.equal(m.phase, "ready");
  assert.equal(m.available, true);
  m.stop();
});

test("a failed history read is retried with back-off, keeping what was shown", async () => {
  const clock = fakeClock();
  const server = fakeServer(clock);
  const m = await openRatSpeak(clock, server);
  server.fail = (kind) => (kind === "history" ? "busy" : null);
  server.announce(); // something changed: read again
  await clock.advance(2_000);
  const failed = server.count("history");
  assert.equal(m.history("ratspeak").messages.length, 2, "a failed read never empties the conversation");
  assert.equal(m.history("ratspeak").error, "busy");
  await clock.advance(5_000);
  assert.equal(server.count("history"), failed, "no immediate retry");
  server.fail = null;
  await clock.advance(60_000);
  assert.equal(m.history("ratspeak").error, undefined);
  assert.equal(server.refused(), 1, "one refusal, one retry later");
  m.stop();
});

test("repeated start and stop (tab switches, re-renders, Strict-Mode-like double mounting) leak nothing", async () => {
  const clock = fakeClock();
  const server = fakeServer(clock);
  const m = await openRatSpeak(clock, server);
  for (let i = 0; i < 25; i += 1) {
    m.start();
    m.start();
    m.stop();
    m.start();
    await clock.advance(10);
  }
  assert.equal(server.panels.filter((p) => p.active).length, 1, "one live subscription");
  m.stop();
  await clock.advance(0);
  assert.equal(server.panels.filter((p) => p.active).length, 0);
  assert.equal(clock.pending(), 0, "no timers left behind");
  assert.ok(server.calls.length <= 4, `${server.calls.length} requests`);
});

test("stopping during a back-off cancels the retry; showing the view again respects it", async () => {
  const clock = fakeClock();
  const server = fakeServer(clock);
  server.fail = () => "unreachable";
  const m = source(clock);
  m.bind(server.hass(), "e1");
  m.start();
  await clock.advance(0);
  m.stop();
  assert.equal(clock.pending(), 0);
  await clock.advance(120_000);
  assert.equal(server.count("conversations"), 1, "nothing while the view is hidden");
  server.fail = null;
  m.start();
  await clock.advance(0);
  assert.equal(server.count("conversations"), 2);
  assert.equal(m.phase, "ready");
  m.stop();
});

test("sending still works and is followed by one read", async () => {
  const clock = fakeClock();
  const server = fakeServer(clock);
  const m = await openRatSpeak(clock, server);
  const before = server.calls.length;
  const answer = await m.send("ratspeak", "hello", "click-0001");
  await clock.advance(10_000);
  assert.equal(answer.state, "queued");
  assert.equal(server.count("send"), 1);
  assert.ok(server.calls.length - before <= 5, `${server.calls.length - before} requests after a send`);
  m.stop();
});

test("a refused read is described as busy, not as too many messages", () => {
  assert.ok(MESSAGING_ERRORS.busy);
  assert.doesNotMatch(errorText("busy"), /messages/i);
  assert.match(errorText("rate_limited"), /Too many messages/); // sending: unchanged
});
