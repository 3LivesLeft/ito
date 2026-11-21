// SPDX-License-Identifier: Apache-2.0
// The Messages view (M5, ADR 0024): conversations, a conversation, a composer and contacts.
//
// It reads a messaging source through its documented methods only (sources/messaging.js shape) and
// the messaging summary of the view-data contract; it knows nothing of Home Assistant. It is one
// persistent component: updates change it in place, so a half-written message, the focus and the
// scroll position survive live updates. Every value is written as text (dom.js), never as markup.

import { DELIVERY_TONE, MESSAGE_MAX_BYTES, MESSAGING_OFF_TEXT, RETRYABLE, byteLength, deliveryWords, errorText, newIdempotencyKey, normaliseAddress } from "../model.js";
import { chip, copyButton } from "./components.js";
import { h, icon } from "./dom.js";

const KEPT_WHILE_OFF = "Your contacts and conversations are kept, and appear here again when messaging is switched on.";
const STRANGERS_NOTE = "These senders are not your contacts, so ito cannot reply to them here.";
const EMPTY_STEPS = [
  "Copy ito's address above and add it as a contact in your LXMF app (for example Sideband or Ratspeak).",
  "Choose “Add contact” and paste your app's own LXMF address.",
  "Send a message from either side. Replies appear here as they arrive.",
];

function initials(name) {
  const words = String(name || "").split(/[^\p{L}\p{N}]+/u).filter(Boolean);
  const letters = words.slice(0, 2).map((w) => [...w][0]);
  return letters.join("").toUpperCase() || "?";
}

function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export class MessagesView {
  /** @param {{messaging: object}} o the messaging source (sources/messaging.js shape) */
  constructor({ messaging }) {
    this.messaging = messaging;
    this.selected = null;
    this.adding = false;
    this.renaming = false;
    this.formError = null;
    this.sendError = null;
    this.actionError = null;
    this.sending = false;
    this._key = null;
    this._ctx = null;
    this.element = h("div", { class: "msg" });
    this.listPane = h("section", { class: "msg-list card", "aria-label": "Conversations" });
    this.chatPane = h("section", { class: "msg-chat card", "aria-label": "Conversation" });
    this.status = h("div", { class: "msg-status", role: "status" });
    this.element.append(this.status, h("div", { class: "msg-panes" }, this.listPane, this.chatPane));
    this._buildComposer();
    this._buildAddForm();
  }

  // -- persistent parts ---------------------------------------------------------------------------
  _buildComposer() {
    this.input = h("textarea", { rows: 1, "aria-label": "Message", placeholder: "Write a message", maxlength: String(MESSAGE_MAX_BYTES) });
    this.counter = h("span", { class: "muted small counter", "aria-live": "polite" });
    this.sendButton = h("button", { type: "submit", class: "btn send", text: "Send" });
    this.input.addEventListener("input", () => {
      this._key = null; // edited: a new message
      this.sendError = null;
      if (this.selected) this.messaging.drafts.set(this.selected, this.input.value);
      this._grow();
      this._updateComposer();
    });
    this.input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
        ev.preventDefault();
        this._send();
      }
    });
    this.composerError = h("p", { class: "msg-error small", role: "alert" });
    this.composerNote = h("p", { class: "muted small" });
    this.composer = h(
      "form",
      { class: "composer", onsubmit: (ev) => { ev.preventDefault(); this._send(); } },
      this.composerError,
      this.composerNote,
      h("div", { class: "composer-row" }, this.input, this.sendButton),
      this.counter,
    );
  }

  _buildAddForm() {
    this.nameInput = h("input", { type: "text", maxlength: "32", autocomplete: "off", "aria-label": "Contact name", placeholder: "Name, for example My phone" });
    this.addressInput = h("input", { type: "text", maxlength: "80", autocomplete: "off", spellcheck: false, "aria-label": "LXMF address", placeholder: "LXMF address (32 characters)", class: "mono" });
    this.addError = h("p", { class: "msg-error small", role: "alert" });
    this.addForm = h(
      "form",
      { class: "add-form", onsubmit: (ev) => { ev.preventDefault(); this._add(); } },
      h("label", { class: "small", text: "Name" }), this.nameInput,
      h("label", { class: "small", text: "LXMF address" }), this.addressInput,
      h("p", { class: "muted small", text: "In Sideband or Ratspeak, the address is shown on your own profile or under “My address”." }),
      this.addError,
      h("div", { class: "row" }, h("button", { type: "submit", class: "btn", text: "Add contact" }), h("button", { type: "button", class: "btn-quiet", text: "Cancel", onclick: () => { this.adding = false; this._render(); } })),
    );
  }

  _grow() {
    this.input.style.height = "auto";
    this.input.style.height = `${Math.min(this.input.scrollHeight, 200)}px`;
  }

  // -- actions ----------------------------------------------------------------------------------
  async _send() {
    const contact = this.selected;
    const text = this.input.value;
    if (!contact || this.sending || !text.trim() || !this._canSend()) return;
    if (byteLength(text) > MESSAGE_MAX_BYTES) {
      this.sendError = errorText("too_long");
      return this._updateComposer();
    }
    this._key = this._key || newIdempotencyKey(); // the same press, retried, is one message
    this.sending = true;
    this._updateComposer();
    try {
      await this.messaging.send(contact, text, this._key);
      this.messaging.drafts.delete(contact);
      if (this.selected === contact) this.input.value = "";
      this._key = null;
      this.sendError = null;
      this._stickToBottom = true;
    } catch (err) {
      this.sendError = errorText(err && err.code);
    } finally {
      this.sending = false;
      this._grow();
      this._render();
      if (this.selected === contact) this.input.focus();
    }
  }

  async _add() {
    const name = this.nameInput.value.trim();
    const address = normaliseAddress(this.addressInput.value);
    if (!name || name.length > 32) return this._addFailed("invalid_name");
    if (!address) return this._addFailed("invalid_address");
    try {
      const id = await this.messaging.addContact(name, address);
      this.adding = false;
      this.nameInput.value = this.addressInput.value = "";
      this.addError.textContent = "";
      if (id) this._select(id);
      else this._render();
    } catch (err) {
      this._addFailed(err && err.code);
    }
  }

  _addFailed(code) {
    this.addError.textContent = errorText(code);
    (code === "invalid_name" ? this.nameInput : this.addressInput).focus();
  }

  async _act(fn) {
    this.actionError = null;
    try {
      await fn();
    } catch (err) {
      this.actionError = errorText(err && err.code);
    }
    this._render();
  }

  _select(contact) {
    if (this.selected && this.selected !== contact) this.messaging.close(this.selected);
    this.selected = contact;
    this.renaming = false;
    this.actionError = null;
    this.sendError = null;
    this._key = null;
    this.input.value = (contact && this.messaging.drafts.get(contact)) || "";
    this._stickToBottom = true;
    if (contact) this.messaging.open(contact);
    this._render();
    if (contact) (this.chatPane.querySelector(".chat-head h2") || this.input).focus();
  }

  // -- rendering --------------------------------------------------------------------------------
  /** ctx = { summary (messagingSummary or null), language, now } */
  update(ctx) {
    this._ctx = ctx;
    this._render();
  }

  _canSend() {
    const s = this._ctx && this._ctx.summary;
    return Boolean(s && s.state === "running" && this.messaging.available !== false);
  }

  _render() {
    const ctx = this._ctx;
    if (!ctx) return;
    const m = this.messaging;
    const summary = ctx.summary;
    this.status.replaceChildren(this._statusLine(summary));
    const off = !summary || summary.state === "disabled";
    if (off) {
      this.element.dataset.open = "";
      this.listPane.replaceChildren(h("h2", { text: "Messaging is off" }), h("p", { class: "small", text: MESSAGING_OFF_TEXT }), h("p", { class: "muted small", text: KEPT_WHILE_OFF }));
      this.chatPane.hidden = true;
      return;
    }
    this.chatPane.hidden = false;
    if (this.selected && m.phase === "ready" && !m.conversations.some((c) => c.id === this.selected)) this.selected = null;
    if (this.selected) this.element.dataset.open = "true";
    else delete this.element.dataset.open;
    this._renderList(ctx, summary);
    this._renderChat(ctx);
    if (this.selected && !(globalThis.document && document.hidden)) {
      const item = m.conversations.find((c) => c.id === this.selected);
      if (item && item.unread) m.markRead(this.selected);
    }
  }

  _statusLine(summary) {
    if (!summary || summary.state === "disabled") return chip("neutral", "Messaging is off");
    if (summary.state === "running" && this.messaging.available === false) {
      return h("span", {}, chip("warn", "Reconnecting"), h("span", { class: "muted small", text: errorText(this.messaging.error) }));
    }
    if (summary.state === "running") return chip("good", "Messaging is working");
    if (summary.state === "starting") return h("span", {}, chip("info", "Starting"), h("span", { class: "muted small", text: summary.message || "Messaging is starting. Messages you write are sent once it is ready." }));
    return h("span", {}, chip("bad", summary.label), h("span", { class: "muted small", text: summary.message || "" }));
  }

  _renderList(ctx, summary) {
    const m = this.messaging;
    const parts = [];
    parts.push(
      h(
        "div",
        { class: "my-address" },
        h("div", { class: "label small", text: "ito's address" }),
        summary.address
          ? h("div", { class: "address" }, h("code", { text: summary.address, "aria-label": "ito's LXMF address" }), copyButton(summary.address))
          : h("p", { class: "muted small", text: "The address appears once messaging is running." }),
      ),
    );
    const head = h(
      "div",
      { class: "section-head" },
      h("h2", { text: "Conversations" }),
      this.adding ? null : h("button", { type: "button", class: "btn-quiet", onclick: () => { this.adding = true; this._render(); this.nameInput.focus(); } }, icon("mdi:account-plus"), "Add contact"),
    );
    parts.push(head);
    if (this.adding) parts.push(this.addForm);
    if (m.phase === "loading" || m.phase === "idle") parts.push(h("div", { class: "skeleton", style: "height:120px", "aria-label": "Loading conversations" }));
    else if (m.phase === "error") {
      parts.push(h("p", { class: "msg-error small", role: "alert", text: errorText(m.error) }), h("button", { type: "button", class: "btn-quiet", text: "Try again", onclick: () => m.refresh() }));
    } else if (!m.conversations.length && !this.adding) {
      parts.push(
        h(
          "div",
          { class: "empty-state" },
          h("p", { class: "title", text: "No conversations yet" }),
          h("ol", { class: "small" }, EMPTY_STEPS.map((s) => h("li", { text: s }))),
        ),
      );
    } else {
      parts.push(h("ul", { class: "conversations", role: "list" }, m.conversations.map((c) => this._conversationItem(ctx, c))));
    }
    this.listPane.replaceChildren(...parts);
  }

  _conversationItem(ctx, c) {
    const last = c.last;
    const preview = last ? `${last.outgoing ? (last.auto ? "Automatic reply: " : "You: ") : ""}${last.text}` : c.heard ? "No messages yet" : "No messages yet · not heard on the network yet";
    return h(
      "li",
      {},
      h(
        "button",
        { type: "button", class: "conversation", "aria-current": c.id === this.selected ? "true" : null, onclick: () => this._select(c.id) },
        h("span", { class: "avatar", "aria-hidden": "true", text: c.strangers ? "?" : initials(c.name) }),
        h(
          "span",
          { class: "who" },
          h("span", { class: "name", text: c.name }),
          h("span", { class: "preview muted small", text: preview }),
        ),
        h(
          "span",
          { class: "meta" },
          last && last.at ? h("span", { class: "muted small", text: this._time(ctx, last.at, true) }) : null,
          c.unread ? h("span", { class: "badge", "aria-label": `${c.unread} unread`, text: c.unread > 99 ? "99+" : String(c.unread) }) : null,
        ),
      ),
    );
  }

  _renderChat(ctx) {
    const m = this.messaging;
    const c = this.selected ? m.conversations.find((x) => x.id === this.selected) : null;
    if (!c) {
      this.chatPane.replaceChildren(h("div", { class: "chat-empty muted", text: m.conversations.length ? "Choose a conversation." : "Add a contact to start a conversation." }));
      return;
    }
    const history = m.history(c.id);
    const oldLog = this.chatPane.querySelector(".log");
    const atBottom = !oldLog || oldLog.scrollHeight - oldLog.scrollTop - oldLog.clientHeight < 48;
    const log = h("div", { class: "log", role: "log", "aria-label": `Messages with ${c.name}`, "aria-live": "polite" });
    if (!history.complete && history.messages.length) {
      log.append(h("button", { type: "button", class: "btn-quiet older", text: history.loading ? "Loading…" : "Show earlier messages", onclick: () => m.loadOlder(c.id) }));
    }
    let day = null;
    for (const msg of history.messages) {
      if (msg.at) {
        const d = new Date(msg.at);
        if (!day || !sameDay(day, d)) {
          day = d;
          log.append(h("div", { class: "day muted small", text: this._day(ctx, d) }));
        }
      }
      log.append(this._bubble(ctx, msg));
    }
    for (const p of m.pendingFor(c.id)) log.append(this._bubble(ctx, { outgoing: true, text: p.text, at: null, state: "sending", local: true }));
    if (history.loading && !history.messages.length) log.append(h("div", { class: "skeleton", style: "height:80px", "aria-label": "Loading messages" }));
    else if (!history.messages.length && !m.pendingFor(c.id).length) log.append(h("p", { class: "muted small chat-empty", text: c.strangers ? "No messages." : `No messages with ${c.name} yet. Say hello!` }));
    if (history.error) log.append(h("p", { class: "msg-error small", role: "alert", text: errorText(history.error) }));
    const parts = [this._chatHead(c), this.actionError ? h("p", { class: "msg-error small", role: "alert", text: this.actionError }) : null, log];
    if (c.strangers) parts.push(h("p", { class: "muted small composer-note", text: STRANGERS_NOTE }));
    else parts.push(this.composer);
    this.chatPane.replaceChildren(...parts.filter(Boolean));
    this._updateComposer();
    if (atBottom || this._stickToBottom) log.scrollTop = log.scrollHeight;
    else if (oldLog) log.scrollTop = oldLog.scrollTop;
    this._stickToBottom = false;
  }

  _chatHead(c) {
    const m = this.messaging;
    const back = h("button", { type: "button", class: "btn-quiet back", "aria-label": "Back to conversations", onclick: () => this._select(null) }, icon("mdi:arrow-left"), h("span", { class: "back-text", text: "Back" }));
    if (this.renaming) {
      const input = h("input", { type: "text", maxlength: "32", value: c.name, "aria-label": "New name" });
      return h(
        "form",
        { class: "chat-head", onsubmit: (ev) => { ev.preventDefault(); const name = input.value.trim(); if (!name) return; this.renaming = false; this._act(() => m.renameContact(c.id, name)); } },
        back,
        input,
        h("button", { type: "submit", class: "btn", text: "Save" }),
        h("button", { type: "button", class: "btn-quiet", text: "Cancel", onclick: () => { this.renaming = false; this._render(); } }),
      );
    }
    const menu = c.strangers
      ? null
      : h(
          "details",
          { class: "menu" },
          h("summary", { "aria-label": "Contact options" }, icon("mdi:dots-vertical"), h("span", { class: "sr", text: "Contact options" })),
          h(
            "div",
            { class: "menu-items" },
            h("button", { type: "button", text: "Rename", onclick: () => { this.renaming = true; this._render(); } }),
            h("button", { type: "button", text: "Delete conversation", onclick: () => { if (globalThis.confirm(`Delete the conversation with ${c.name}? Messages still waiting to be sent are kept.`)) this._act(() => m.clearConversation(c.id)); } }),
            h("button", { type: "button", class: "danger", text: "Remove contact", onclick: () => { if (globalThis.confirm(`Remove ${c.name}? Their conversation is deleted and ito stops accepting their messages.`)) this._act(() => m.removeContact(c.id)); } }),
          ),
        );
    return h(
      "div",
      { class: "chat-head" },
      back,
      h("span", { class: "avatar", "aria-hidden": "true", text: c.strangers ? "?" : initials(c.name) }),
      h(
        "div",
        { class: "who" },
        h("h2", { tabindex: "-1", text: c.name }),
        c.address ? h("div", { class: "address small" }, h("code", { text: c.address, "aria-label": `${c.name}'s LXMF address` }), copyButton(c.address)) : null,
      ),
      menu,
    );
  }

  _bubble(ctx, msg) {
    const out = msg.outgoing;
    const meta = [];
    if (msg.at) meta.push(h("time", { text: this._time(ctx, msg.at) }));
    if (out && msg.state) {
      const tone = msg.retrying ? "warn" : DELIVERY_TONE[msg.state] || "neutral";
      meta.push(h("span", { class: "state", "data-tone": tone }, msg.state === "delivered" ? icon("mdi:check-all") : null, deliveryWords(msg)));
    }
    const retry =
      out && !msg.local && msg.id && (RETRYABLE.includes(msg.state) || msg.retrying) && !msg.auto
        ? h("button", { type: "button", class: "btn-quiet retry", text: msg.retrying ? "Try now" : "Send again", onclick: () => this._act(() => this.messaging.retry(msg.id)) })
        : null;
    return h(
      "div",
      { class: `bubble ${out ? "out" : "in"}${msg.auto ? " auto" : ""}${msg.local ? " local" : ""}` },
      msg.auto ? h("div", { class: "auto-label small", text: "Automatic reply" }) : null,
      h("div", { class: "text", text: msg.text }),
      h("div", { class: "bubble-meta small" }, meta, retry),
    );
  }

  _updateComposer() {
    const can = this._canSend();
    const bytes = byteLength(this.input.value);
    this.input.disabled = !can;
    this.sendButton.disabled = !can || this.sending || !this.input.value.trim() || bytes > MESSAGE_MAX_BYTES;
    this.sendButton.textContent = this.sending ? "Sending…" : "Send";
    this.counter.textContent = bytes > MESSAGE_MAX_BYTES * 0.8 ? `${bytes.toLocaleString()} of ${MESSAGE_MAX_BYTES.toLocaleString()} bytes` : "";
    this.composerError.textContent = this.sendError || "";
    this.composerError.hidden = !this.sendError;
    const summary = this._ctx && this._ctx.summary;
    this.composerNote.textContent = can ? "" : summary && summary.state === "running" ? "Reconnecting to messaging. You can send again once it is back." : "Messaging is not running, so messages cannot be sent right now.";
    this.composerNote.hidden = can;
  }

  _time(ctx, at, short = false) {
    const d = new Date(at);
    const now = new Date(ctx.now || Date.now());
    const opts = sameDay(d, now) ? { hour: "2-digit", minute: "2-digit" } : short ? { day: "numeric", month: "short" } : { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" };
    try {
      return new Intl.DateTimeFormat(ctx.language || undefined, opts).format(d);
    } catch (_err) {
      return d.toLocaleString();
    }
  }

  _day(ctx, d) {
    const now = new Date(ctx.now || Date.now());
    if (sameDay(d, now)) return "Today";
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (sameDay(d, yesterday)) return "Yesterday";
    try {
      return new Intl.DateTimeFormat(ctx.language || undefined, { weekday: "long", day: "numeric", month: "long" }).format(d);
    } catch (_err) {
      return d.toDateString();
    }
  }
}
