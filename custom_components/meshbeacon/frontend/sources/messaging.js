// SPDX-License-Identifier: Apache-2.0
// Data source for the Messages view (M5, ADR 0024): Home Assistant's websocket commands
// meshbeacon/messaging/*, which only administrators may use. The browser never holds a key;
// conversations stay in memory while the panel is open and are never written to browser storage.
// No DOM, no rendering.

import { conversationItem, messageItem, newIdempotencyKey } from "../model.js";

const PAGE = 50;
const RESUBSCRIBE = [5_000, 15_000, 30_000, 60_000];
// Reads that follow a "changed" event: at most one every REFRESH_GAP, however many events arrive,
// so the view can never read in a tight loop (two dashboards stay well inside the app's 240 reads
// a minute). After a failed read, the next automatic one waits (bounded, jittered back-off).
const REFRESH_GAP = 2_000;
const BACKOFF = [2_000, 5_000, 15_000, 30_000, 60_000];
const JITTER = 0.2; // ±20 %
// Refused because of how often we asked (the app's limit is per minute): start at 15 s, not 2 s.
const THROTTLED = new Set(["rate_limited", "busy"]);
// Codes that mean the messaging path itself is down (shown as "Reconnecting"). Any other failure,
// such as a refused read, is not an outage: the engine is working and sending stays possible.
const OUTAGE = new Set(["unavailable", "unreachable", "not_enabled", "not_found", "unauthorised"]);

export class HassMessaging {
  /** `timers` replaces setTimeout/clearTimeout/Date.now/Math.random (tests use a fake clock). */
  constructor(timers = {}) {
    this._setTimeout = timers.setTimeout || ((fn, ms) => setTimeout(fn, ms));
    this._clearTimeout = timers.clearTimeout || ((handle) => clearTimeout(handle));
    this._now = timers.now || (() => Date.now());
    this._random = timers.random || Math.random;
    this.hass = null;
    this.entryId = null;
    this.phase = "idle"; // idle | loading | ready | error
    this.error = null; // the last code from Home Assistant or the app
    this.available = null; // the app's engine answers (live-update channel)
    this.conversations = [];
    this.histories = new Map(); // contact -> { messages, complete, loading }
    this.pending = new Map(); // idempotency key -> { contact, text } while a Send is on its way
    this.drafts = new Map(); // contact -> text not yet sent (memory only)
    this._listeners = new Set();
    this._unsubscribe = null;
    this._subscribing = false;
    this._timer = null;
    this._failures = 0;
    this._active = false;
    this._refreshing = null;
    this._again = false;
    this._retry = null; // the one scheduled automatic read, if any
    this._holdUntil = 0; // no automatic read before this time
    this._readFailures = 0;
  }

  onChange(listener) {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  _emit() {
    for (const listener of this._listeners) listener();
  }

  /** Give the latest `hass` and the selected app's entry. A different app starts afresh. */
  bind(hass, entryId) {
    this.hass = hass;
    if (entryId === this.entryId) return;
    this.stop();
    this.entryId = entryId;
    this.phase = "idle";
    this.conversations = [];
    this.histories.clear();
    this.pending.clear();
    this.drafts.clear();
    this.error = null;
    this.available = null;
  }

  /** Live updates while the Messages view is shown; nothing at all otherwise. */
  start() {
    // Home Assistant calls this on every update of the panel: it must be idempotent.
    this._active = true;
    if (this.phase === "idle") this.refresh();
    else if (this.phase === "error") this._scheduleRefresh(); // respects a back-off under way
    this._subscribe();
  }

  stop() {
    this._active = false;
    this._clearTimeout(this._timer);
    this._timer = null;
    this._clearTimeout(this._retry);
    this._retry = null;
    const unsubscribe = this._unsubscribe;
    this._unsubscribe = null;
    if (unsubscribe) Promise.resolve(unsubscribe()).catch(() => {});
  }

  get unread() {
    return this.conversations.reduce((sum, c) => sum + c.unread, 0);
  }

  async _call(kind, fields = {}) {
    if (!this.hass || !this.entryId) throw { code: "not_found" };
    return this.hass.callWS({ type: `meshbeacon/messaging/${kind}`, entry_id: this.entryId, ...fields });
  }

  async _subscribe() {
    if (!this._active || this._unsubscribe || this._subscribing || !this.hass || !this.hass.connection) return;
    this._subscribing = true;
    try {
      const unsubscribe = await this.hass.connection.subscribeMessage((event) => this._event(event), {
        type: "meshbeacon/messaging/subscribe",
        entry_id: this.entryId,
      });
      if (this._active) this._unsubscribe = unsubscribe;
      else Promise.resolve(unsubscribe()).catch(() => {});
      this._failures = 0;
    } catch (_err) {
      // Back off, then try again (the integration may still be starting).
      const delay = this._jitter(RESUBSCRIBE[Math.min(this._failures, RESUBSCRIBE.length - 1)]);
      this._failures += 1;
      this._clearTimeout(this._timer);
      this._timer = this._active ? this._setTimeout(() => this._subscribe(), delay) : null;
    } finally {
      this._subscribing = false;
    }
  }

  _event(event) {
    if (!event || typeof event !== "object") return;
    if (event.type === "unavailable") {
      this.available = false;
      this._emit();
    } else if (event.type === "changed") {
      this.available = true;
      this._scheduleRefresh();
    }
  }

  _jitter(ms) {
    return Math.round(ms * (1 - JITTER + 2 * JITTER * this._random()));
  }

  /** How long to wait after the n-th failed read in a row. */
  _backoff(code, n) {
    const step = Math.max(n, 1) - 1 + (THROTTLED.has(code) ? 2 : 0);
    return this._jitter(BACKOFF[Math.min(step, BACKOFF.length - 1)]);
  }

  /** Read again when allowed: at once, or once the gap or back-off is over. Never two waiting. */
  _scheduleRefresh() {
    if (!this._active || this._retry) return;
    const wait = this._holdUntil - this._now();
    if (wait <= 0 && !this._refreshing) {
      this.refresh();
      return;
    }
    this._retry = this._setTimeout(() => {
      this._retry = null;
      this._scheduleRefresh();
    }, Math.max(wait, 0) || REFRESH_GAP);
  }

  _readFailed(code) {
    this._readFailures += 1;
    this._holdUntil = this._now() + this._backoff(code, this._readFailures);
  }

  /** Read the conversation list and every open conversation again (coalesced). */
  async refresh() {
    if (this._refreshing) {
      this._again = true;
      return this._refreshing;
    }
    if (this.phase === "idle") {
      this.phase = "loading";
      this._emit();
    }
    this._holdUntil = Math.max(this._holdUntil, this._now() + REFRESH_GAP);
    let failed = null;
    this._refreshing = (async () => {
      try {
        const answer = await this._call("conversations");
        this.conversations = (Array.isArray(answer && answer.conversations) ? answer.conversations : []).map(conversationItem).filter(Boolean);
        this.phase = "ready";
        this.error = null;
        this.available = true;
        const codes = await Promise.all([...this.histories.keys()].map((contact) => this._loadLatest(contact)));
        failed = codes.find(Boolean) || null;
      } catch (err) {
        failed = (err && err.code) || "unavailable";
        this.error = failed;
        this.phase = this.phase === "ready" ? "ready" : "error";
        // Only an outage of the messaging path is "Reconnecting"; a refused read is not.
        if (OUTAGE.has(failed)) this.available = false;
      }
    })();
    try {
      await this._refreshing;
    } finally {
      this._refreshing = null;
      if (failed) this._readFailed(failed);
      else this._readFailures = 0;
      this._emit();
    }
    if (failed) {
      this._again = false;
      this._scheduleRefresh(); // one retry, after the back-off; changes meanwhile are covered by it
    } else if (this._again) {
      this._again = false;
      return this.refresh();
    }
    return undefined;
  }

  history(contact) {
    return this.histories.get(contact) || { messages: [], complete: false, loading: false };
  }

  /** Open a conversation: load its newest messages and mark it read. */
  async open(contact) {
    if (!this.histories.has(contact)) {
      this.histories.set(contact, { messages: [], complete: false, loading: true });
      this._emit();
    }
    await this._loadLatest(contact);
    this._emit();
    await this.markRead(contact);
  }

  close(contact) {
    this.histories.delete(contact);
  }

  async _loadLatest(contact) {
    try {
      const answer = await this._call("history", { contact });
      const latest = (answer.messages || []).map(messageItem).filter(Boolean);
      const old = this.history(contact);
      // Keep older pages already loaded, then the newest page in place of what overlapped it.
      const first = latest.length ? latest[0].seq : Infinity;
      const kept = latest.length < PAGE ? [] : old.messages.filter((m) => m.seq < first); // a short page is everything
      this.histories.set(contact, { messages: [...kept, ...latest], complete: old.complete || latest.length < PAGE, loading: false });
      return null;
    } catch (err) {
      // Keep what is shown: a failed read never empties a conversation.
      const old = this.history(contact);
      const code = (err && err.code) || "unavailable";
      this.histories.set(contact, { ...old, loading: false, error: code });
      return code;
    }
  }

  async loadOlder(contact) {
    const old = this.history(contact);
    if (old.complete || old.loading || !old.messages.length) return;
    this.histories.set(contact, { ...old, loading: true });
    this._emit();
    try {
      const answer = await this._call("history", { contact, before: old.messages[0].seq });
      const older = (answer.messages || []).map(messageItem).filter(Boolean);
      this.histories.set(contact, { messages: [...older, ...old.messages], complete: older.length < PAGE, loading: false });
    } catch (err) {
      this.histories.set(contact, { ...old, loading: false, error: (err && err.code) || "unavailable" });
    }
    this._emit();
  }

  async markRead(contact) {
    const item = this.conversations.find((c) => c.id === contact);
    if (!item || !item.unread) return;
    item.unread = 0;
    this._emit();
    try {
      await this._call("read", { contact });
    } catch (_err) {
      // Shown as unread again at the next refresh; nothing else to do.
    }
  }

  /**
   * Send a message. The key is made once per Send press and reused if the same press is retried,
   * so a double click or a retried request is one message. Throws {code} on failure.
   */
  async send(contact, text, key = newIdempotencyKey()) {
    if (this.pending.has(key)) return null;
    this.pending.set(key, { contact, text });
    this._emit();
    try {
      return await this._call("send", { contact, text, idempotency_key: key });
    } finally {
      this.pending.delete(key);
      await this.refresh();
    }
  }

  pendingFor(contact) {
    return [...this.pending.values()].filter((p) => p.contact === contact);
  }

  async retry(messageId) {
    await this._call("retry", { message_id: messageId });
    await this.refresh();
  }

  async addContact(name, address) {
    const answer = await this._call("contact_add", { name, address });
    await this.refresh();
    return answer && answer.contact;
  }

  async renameContact(contact, name) {
    await this._call("contact_rename", { contact, name });
    await this.refresh();
  }

  async removeContact(contact) {
    await this._call("contact_remove", { contact });
    this.histories.delete(contact);
    this.drafts.delete(contact);
    await this.refresh();
  }

  async clearConversation(contact) {
    await this._call("clear", { contact });
    this.histories.set(contact, { messages: [], complete: true, loading: false });
    await this.refresh();
  }
}
