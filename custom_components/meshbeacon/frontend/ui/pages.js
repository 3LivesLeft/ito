// SPDX-License-Identifier: Apache-2.0
// The Pages tab (v0.6.0, ADR 0027): browse Nomad Network pages, see heard nodes, and publish
// your own. Remote pages are untrusted: they are parsed by ../micron.js into data and built here
// with h() (textContent and attributes only), never as HTML. Only Nomad Network links are
// followed, and only inside this viewer. Nothing is kept in browser storage; the history lives in
// memory and ends with the page.
//
// The view is built once and then updated in place, so typing, focus, the on-screen keyboard and
// the scroll position survive live status updates.

import { parseMicron, pageTitle, resolveLink } from "../micron.js";
import { duration } from "../model.js";
import { chip, copyButton, segmented } from "./components.js";
import { h } from "./dom.js";

export const PAGES_STYLE = `
.pages { width: 100%; max-width: 980px; min-width: 0; margin: 0 auto; display: grid; gap: var(--mb-space-lg); }
.pages > *, .pages .browse > *, .pages .host > *, .pages .card { min-width: 0; }
.pages .bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between; }
.pages .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.pages .grow { flex: 1 1 220px; min-width: 0; }
.pages label { display: grid; gap: 6px; font-size: 14px; font-weight: 500; }
.pages input, .pages textarea { width: 100%; min-height: 44px; padding: 10px; border: 1px solid var(--mb-line); border-radius: var(--mb-radius-sm); background: var(--mb-bg); color: var(--mb-text); font: inherit; font-size: 16px; }
.pages textarea { min-height: 260px; resize: vertical; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 15px; line-height: 1.45; }
.pages .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap: anywhere; }
.pages button { font: inherit; min-height: 44px; padding: 8px 14px; border: 1px solid var(--mb-line); border-radius: var(--mb-radius-pill); background: var(--mb-surface); color: var(--mb-text); cursor: pointer; }
.pages button.btn { color: var(--mb-on-accent); background: var(--mb-accent-text); border: 0; font-weight: 600; }
.pages button.danger { color: var(--mb-bad-text); }
.pages button:disabled { opacity: .55; cursor: not-allowed; }
.pages .list { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.pages .item { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; justify-content: space-between; padding: 12px; border: 1px solid var(--mb-line); border-radius: var(--mb-radius-sm); }
.pages .item .pmeta { display: grid; gap: 2px; min-width: 0; flex: 1 1 220px; }
.pages .item .name { font-weight: 600; overflow-wrap: anywhere; }
.pages .viewer { min-height: 160px; overflow-wrap: anywhere; }
.pages .viewer .page { font-size: 15px; line-height: 1.55; }
.pages .viewer p { margin: 0; min-height: 1.4em; white-space: pre-wrap; }
.pages .viewer h3, .pages .viewer h4, .pages .viewer h5 { margin: 12px 0 4px; font-weight: 600; }
.pages .viewer h3 { font-size: 20px; } .pages .viewer h4 { font-size: 17px; } .pages .viewer h5 { font-size: 15px; }
.pages .viewer hr { border: 0; border-top: 1px solid var(--mb-line); margin: 10px 0; }
.pages .viewer pre { margin: 6px 0; padding: 10px; background: var(--mb-bg); border-radius: var(--mb-radius-sm); overflow-x: auto; white-space: pre; font-size: 14px; }
.pages .viewer .mlink { display: inline; min-height: 0; padding: 0 2px; border: 0; border-radius: 3px; background: none; color: var(--mb-accent-text); text-decoration: underline; text-underline-offset: 3px; font: inherit; cursor: pointer; }
.pages .viewer .mlink-off { text-decoration: underline dotted; color: var(--mb-muted); }
.pages .viewer .field { font-size: 13px; color: var(--mb-muted); border: 1px dashed var(--mb-line); border-radius: 4px; padding: 0 4px; }
.pages .viewer .center { text-align: center; } .pages .viewer .right { text-align: right; }
.pages .where { font-size: 13px; color: var(--mb-muted); overflow-wrap: anywhere; }
.pages .status-line { min-height: 1.5em; }
.pages .confirm { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; width: 100%; padding-top: 8px; border-top: 1px solid var(--mb-line); }
.pages .empty-state { display: grid; gap: 8px; }
.pages .hidden { display: none !important; }
@media (max-width: 500px) { .pages .item { padding: 10px; } }
@media (prefers-reduced-motion: reduce) { .pages * { transition: none !important; } }
`;

const FETCH_ERRORS = {
  no_path: "ito could not find a route to that node. It may be offline, or not yet heard on your network. Try again later.",
  unreachable: "The node did not answer. It may be offline or out of range.",
  timeout: "The node took too long to answer (30 seconds). It may be far away or offline.",
  not_found: "That node does not have this page.",
  not_a_node: "That address is not a Nomad Network node. (It may be someone's messaging address.)",
  too_large: "That page is too large to show (more than 256 KiB).",
  invalid: "Enter a node address: 32 characters, digits 0–9 and letters a–f.",
  rate_limited: "Many pages were requested in a short time. Wait a minute, then try again.",
  busy: "Two pages are already loading. Wait for them to finish.",
  unavailable: "Pages are starting or restarting. Try again in a moment.",
  disabled: "Nomad Network pages are switched off.",
};
const HOST_STATES = {
  off: ["Not publishing", "neutral"],
  waiting: ["Waiting for Reticulum", "neutral"],
  starting: ["Starting…", "warn"],
  running: ["Publishing", "good"],
  backoff: ["Restarting…", "warn"],
  paused: ["Stopped after repeated failures", "bad"],
  error: ["Stopped", "bad"],
};
const HISTORY_MAX = 50;
const INDEX = "/page/index.mu";

export function fetchError(code) {
  return FETCH_ERRORS[code] || "The page could not be loaded.";
}

function shortAddress(address) {
  return address ? `${address.slice(0, 8)}…${address.slice(-4)}` : "";
}

function ago(at, now) {
  return at ? `${duration(now / 1000 - at)} ago` : "never";
}

/** Parsed micron as DOM nodes; links call onLink({address, path}) and nothing else. */
export function renderMicron(source, current, onLink) {
  const { blocks, truncated } = parseMicron(source);
  const root = h("div", { class: "page" });
  const spanNodes = (spans) =>
    spans.map((span) => {
      if (span.field) return h("span", { class: "field", text: "form field (not supported)" });
      let node;
      if (span.link) {
        const target = resolveLink(span.link.target, current);
        const label = span.link.label || span.link.target || "link";
        node = target
          ? h("button", { type: "button", class: "mlink", text: label, onclick: () => onLink(target) })
          : h("span", { class: "mlink-off", text: label, title: "ito opens only Nomad Network pages" });
      } else node = document.createTextNode(span.text);
      if (span.underline) node = h("u", {}, node);
      if (span.italic) node = h("em", {}, node);
      if (span.bold) node = h("strong", {}, node);
      return node;
    });
  for (const block of blocks) {
    const indent = block.depth ? `margin-left:${Math.min(block.depth, 3) * 12}px` : null;
    const align = block.align === "center" ? "center" : block.align === "right" ? "right" : null;
    if (block.type === "heading") root.append(h(`h${block.level + 2}`, { class: align, style: indent }, spanNodes(block.spans)));
    else if (block.type === "divider") root.append(h("hr", { style: indent }));
    else if (block.type === "literal") root.append(h("pre", { style: indent, text: block.text }));
    else if (block.type === "space") root.append(h("p", { "aria-hidden": "true" }));
    else root.append(h("p", { class: align, style: indent }, spanNodes(block.spans)));
  }
  if (truncated) root.append(h("p", { class: "muted small", text: "This page is very long; ito shows only its first 5,000 lines." }));
  return root;
}

export class PagesView {
  /**
   * @param {object} o
   * @param {(path: string, body?: object) => Promise<object>} o.request the dashboard API
   * @param {() => Promise<void>} [o.onEnable] switches the option on and applies it
   */
  constructor({ request, onEnable = null, now = () => Date.now() }) {
    Object.assign(this, { request, onEnable, now });
    this.data = null; // the last overview
    this.nodes = [];
    this.history = [];
    this.index = -1;
    this.generation = 0;
    this.editing = null; // {id|null, original}
    this.shown = false;
    this.mode = "browse";
    this.element = h("section", { class: "pages", "aria-label": "Nomad Network pages" });
    this._build();
  }

  // -- life cycle ------------------------------------------------------------------------------
  show(shown) {
    this.shown = shown;
    clearInterval(this.timer);
    if (!shown) return;
    this.refresh();
    this.timer = setInterval(() => { if (!document.hidden) this.refresh(); }, 10_000);
  }

  /** True while the editor holds unsaved text (the dashboard then never reloads by itself). */
  dirty() {
    return Boolean(this.editing) && (this.titleInput.value !== this.editing.title || this.textInput.value !== this.editing.content);
  }

  async _api(body) {
    return this.request("pages", body);
  }

  async refresh() {
    try {
      this.data = await this._api({ op: "overview" });
    } catch (error) {
      this.data = error && error.code === "disabled" ? { disabled: true } : { error: error?.code || "unavailable" };
    }
    if (this.data.ok && this.data.service?.state === "running" && this.mode === "browse") {
      try {
        this.nodes = (await this._api({ op: "nodes" })).nodes || [];
      } catch (_) {
        // keep the last list: a temporary refusal is not a reason to empty it
      }
    }
    this.update();
  }

  // -- skeleton (built once) -------------------------------------------------------------------
  _build() {
    this.off = h("div", { class: "card empty-state hidden" });
    this.modeBar = h("div", { class: "bar" });
    this.serviceLine = h("p", { class: "muted small status-line", role: "status", "aria-live": "polite" });

    // Browse
    this.addressInput = h("input", { type: "text", inputmode: "text", autocomplete: "off", autocapitalize: "none", spellcheck: false, class: "mono", maxlength: "260", placeholder: "Node address (32 characters)", "aria-label": "Nomad Network node address" });
    const form = h("form", { class: "row", onsubmit: (e) => { e.preventDefault(); this.openTyped(); } },
      h("div", { class: "grow" }, this.addressInput), h("button", { type: "submit", class: "btn", text: "Open" }));
    this.backButton = h("button", { type: "button", text: "Back", "aria-label": "Back", onclick: () => this.step(-1) });
    this.forwardButton = h("button", { type: "button", text: "Forward", "aria-label": "Forward", onclick: () => this.step(1) });
    this.reloadButton = h("button", { type: "button", text: "Reload", onclick: () => this.load(false) });
    this.markButton = h("button", { type: "button", text: "Bookmark", onclick: () => this.toggleBookmark() });
    this.where = h("p", { class: "where" });
    this.loadLine = h("p", { class: "status-line", role: "status", "aria-live": "polite" });
    this.viewer = h("div", { class: "viewer", tabindex: "-1", "aria-label": "Page" });
    this.nodesList = h("ul", { class: "list", "aria-label": "Heard nodes" });
    this.marksList = h("ul", { class: "list", "aria-label": "Bookmarks" });
    this.browse = h("div", { class: "browse", style: "display:grid;gap:var(--mb-space-lg)" },
      h("div", { class: "card", style: "display:grid;gap:12px" },
        h("h2", { text: "Read a page" }),
        h("p", { class: "muted small", text: "Paste a Nomad Network node address, or open one of the nodes below." }),
        form,
        h("div", { class: "row" }, this.backButton, this.forwardButton, this.reloadButton, this.markButton),
        this.where, this.loadLine, this.viewer),
      h("div", { class: "card", style: "display:grid;gap:12px" }, h("h2", { text: "Bookmarks" }), this.marksList),
      h("div", { class: "card", style: "display:grid;gap:12px" },
        h("h2", { text: "Nodes heard by ito" }),
        h("p", { class: "muted small", text: "Nodes announce themselves now and then. Being heard does not mean a node is online now: ito says “reachable” only after a page actually loaded in the last 10 minutes." }),
        this.nodesList));

    // Host
    this.hostState = h("div", { class: "row" });
    this.hostMessage = h("p", { class: "small" });
    this.addressBox = h("div", { style: "display:grid;gap:6px" });
    this.hostToggle = h("button", { type: "button", class: "btn", onclick: () => this.setHosting() });
    this.nameInput = h("input", { type: "text", maxlength: "32", autocomplete: "off", "aria-describedby": "pages-name-help" });
    this.descInput = h("input", { type: "text", maxlength: "200", autocomplete: "off" });
    for (const input of [this.nameInput, this.descInput]) input.addEventListener("input", () => { this._siteTouched = true; });
    this.siteFeedback = h("p", { class: "small", role: "status", "aria-live": "polite" });
    const site = h("form", { style: "display:grid;gap:12px", onsubmit: (e) => { e.preventDefault(); this.saveSite(); } },
      h("label", {}, "Node name", this.nameInput),
      h("p", { id: "pages-name-help", class: "muted small", text: "Other people see this name when your node announces itself. Avoid personal details." }),
      h("label", {}, "Description (optional, shown on your welcome page)", this.descInput),
      h("div", { class: "row" }, h("button", { type: "submit", text: "Save details" })), this.siteFeedback);
    this.pagesList = h("ul", { class: "list", "aria-label": "Your pages" });
    this.pagesFeedback = h("p", { class: "small", role: "status", "aria-live": "polite" });

    // Editor
    this.titleInput = h("input", { type: "text", maxlength: "64", autocomplete: "off" });
    this.textInput = h("textarea", { spellcheck: true, "aria-describedby": "pages-format-help" });
    this.textInput.addEventListener("input", () => this._count());
    this.counter = h("span", { class: "muted small" });
    this.preview = h("div", { class: "viewer card hidden", "aria-label": "Preview" });
    this.previewButton = h("button", { type: "button", text: "Preview", "aria-pressed": "false", onclick: () => this.togglePreview() });
    this.editorFeedback = h("p", { class: "small", role: "status", "aria-live": "polite" });
    this.linksButton = h("button", { type: "button", text: "Add links to my pages", onclick: () => this.insertLinks() });
    this.editor = h("div", { class: "card hidden", style: "display:grid;gap:12px" },
      h("h2", { text: "Edit page" }),
      h("label", {}, "Title (shown in your page list)", this.titleInput),
      h("label", {}, "Page text", this.textInput),
      h("p", { id: "pages-format-help", class: "muted small", text: "Nomad Network’s micron format: start a line with > for a heading, write `!bold`! or `*italic`*, a line with just - for a divider, and `[Label`:/page/name.mu] for a link to another of your pages." }),
      h("div", { class: "row" }, this.counter),
      h("div", { class: "row" },
        h("button", { type: "button", class: "btn", text: "Save and publish", onclick: () => this.savePage(true) }),
        h("button", { type: "button", text: "Save draft", onclick: () => this.savePage(false) }),
        this.previewButton, this.linksButton,
        h("button", { type: "button", text: "Close", onclick: () => this.closeEditor() })),
      this.editorFeedback, this.preview);

    this.host = h("div", { class: "host hidden", style: "display:grid;gap:var(--mb-space-lg)" },
      h("div", { class: "card", style: "display:grid;gap:12px" },
        h("h2", { text: "Publish your own pages" }), this.hostState, this.hostMessage, this.addressBox,
        h("div", { class: "row" }, this.hostToggle)),
      h("div", { class: "card" }, site),
      this.editor,
      h("div", { class: "card", style: "display:grid;gap:12px" },
        h("div", { class: "bar" }, h("h2", { text: "Your pages" }), h("button", { type: "button", text: "New page", onclick: () => this.openEditor(null) })),
        this.pagesFeedback, this.pagesList));

    this.element.append(h("style", { text: PAGES_STYLE }), this.off, this.modeBar, this.serviceLine, this.browse, this.host);
    this._marks = "";
    this._nodes = "";
    this._pages = "";
    this.update();
  }

  // -- updates (in place) ----------------------------------------------------------------------
  update() {
    const data = this.data;
    const disabled = Boolean(data?.disabled);
    this.off.classList.toggle("hidden", !disabled);
    for (const el of [this.modeBar, this.serviceLine, this.browse, this.host]) el.classList.toggle("hidden", disabled);
    if (disabled) return this._renderOff();
    if (this._modeShown !== this.mode) {
      this._modeShown = this.mode;
      this.modeBar.replaceChildren(segmented("Pages", [{ key: "browse", label: "Browse" }, { key: "host", label: "My pages" }], this.mode, (key) => this.setMode(key)));
    }
    this.browse.classList.toggle("hidden", this.mode !== "browse");
    this.host.classList.toggle("hidden", this.mode !== "host");
    const service = data?.service;
    this.serviceLine.textContent = !data
      ? "Loading…"
      : data.error
        ? fetchError(data.error)
        : service.state === "running"
          ? ""
          : service.message || "Pages are starting.";
    if (!data?.ok) return;
    this._updateBrowse();
    this._updateHost();
  }

  _renderOff() {
    if (this.off.childElementCount) return;
    const button = h("button", { type: "button", class: "btn", text: "Switch on pages" });
    const feedback = h("p", { class: "small", role: "status", "aria-live": "polite" });
    button.addEventListener("click", async () => {
      if (!this.onEnable) return;
      button.disabled = true;
      feedback.textContent = "Switching on pages. ito restarts briefly…";
      try {
        await this.onEnable();
        feedback.textContent = "Pages are on.";
        await this.refresh();
      } catch (error) {
        feedback.textContent = error?.problems?.join(" ") || "Pages could not be switched on. Open Settings and try again.";
      } finally {
        button.disabled = false;
      }
    });
    this.off.append(
      h("h2", { text: "Nomad Network pages are off" }),
      h("p", { text: "Read small pages that other people publish over Reticulum, and publish your own, even when the internet is down." }),
      h("ol", {}, h("li", { text: "Switch on pages (ito restarts briefly)." }), h("li", { text: "Open a node from the list, or paste a node address." }), h("li", { text: "To publish, open My pages and give your node a name." })),
      h("div", { class: "row" }, button), feedback,
    );
  }

  setMode(mode) {
    this.mode = mode;
    this.update();
    this.modeBar.querySelector('[aria-pressed="true"]')?.focus(); // the rebuilt control keeps focus
    if (mode === "browse") this.refresh();
  }

  _updateBrowse() {
    const now = this.now();
    const marks = this.data.site.bookmarks;
    const marksKey = JSON.stringify(marks);
    if (marksKey !== this._marks) {
      this._marks = marksKey;
      this.marksList.replaceChildren(
        ...(marks.length
          ? marks.map((m) => h("li", { class: "item" },
              h("div", { class: "pmeta" }, h("span", { class: "name", text: m.title }), h("span", { class: "where mono", text: `${shortAddress(m.address)} ${m.path}` })),
              h("div", { class: "row" },
                h("button", { type: "button", text: "Open", "aria-label": `Open ${m.title}`, onclick: () => this.go({ address: m.address, path: m.path }) }),
                h("button", { type: "button", text: "Remove", "aria-label": `Remove bookmark ${m.title}`, onclick: () => this._act({ op: "bookmark_remove", address: m.address, path: m.path }) }))))
          : [h("li", { class: "muted small", text: "No bookmarks yet. Open a page and choose Bookmark." })]),
      );
    }
    const nodesKey = JSON.stringify(this.nodes.map((n) => [n.address, n.name, Math.floor((now / 1000 - n.last_heard) / 60), n.path_known, n.reachable]));
    if (nodesKey !== this._nodes) {
      this._nodes = nodesKey;
      const items = this.nodes.slice(0, 200).map((n) => {
        const name = n.name || "Unnamed node";
        const chips = [];
        if (n.own) chips.push(chip("good", "Your node"));
        if (n.reachable) chips.push(chip("good", "Reachable"));
        else if (n.heard_recently) chips.push(chip("neutral", "Heard recently"));
        else chips.push(chip("neutral", "Not heard lately"));
        if (!n.path_known) chips.push(chip("neutral", "No route now"));
        return h("li", { class: "item" },
          h("div", { class: "pmeta" }, h("span", { class: "name", text: name }),
            h("span", { class: "where", text: `Last heard ${ago(n.last_heard, now)} · ${shortAddress(n.address)}` }),
            h("div", { class: "row" }, chips)),
          h("button", { type: "button", text: "Open", "aria-label": `Open ${name}`, onclick: () => this.go({ address: n.address, path: INDEX }) }));
      });
      this.nodesList.replaceChildren(...(items.length ? items : [h("li", { class: "muted small", text: "No nodes heard yet. Nodes appear here as they announce themselves; this can take a while after ito starts." })]));
    }
    const current = this.history[this.index];
    this.backButton.disabled = this.index <= 0;
    this.forwardButton.disabled = this.index >= this.history.length - 1;
    this.reloadButton.disabled = this.markButton.disabled = !current;
    const marked = current && marks.some((m) => m.address === current.address && m.path === current.path);
    this.markButton.textContent = marked ? "Remove bookmark" : "Bookmark";
    this.markButton.setAttribute("aria-pressed", String(Boolean(marked)));
  }

  _updateHost() {
    const { site, service, address } = this.data;
    const [label, tone] = HOST_STATES[service.hosting_state] || HOST_STATES.off;
    this.hostState.replaceChildren(chip(tone, label), h("span", { class: "muted small", text: site.hosting ? "Hosting is on." : "Hosting is off." }));
    this.hostMessage.textContent = service.hosting_message || (site.hosting ? "New or changed pages can take up to a minute to appear for others." : "Your pages are kept, but nobody can read them while hosting is off.");
    this.hostToggle.textContent = site.hosting ? "Stop publishing" : "Start publishing";
    if (this._address === (address || "")) return this._updatePages(site);
    this._address = address || "";
    this.addressBox.replaceChildren(
      ...(address
        ? [h("span", { class: "small", text: "Your node's address — share it so that others can read your pages:" }),
           h("div", { class: "row" }, h("code", { class: "mono", text: address, "aria-label": "Your node's address" }), copyButton(address),
             h("button", { type: "button", text: "Open my node", onclick: () => { this.setMode("browse"); this.go({ address, path: INDEX }); } }))]
        : [h("span", { class: "muted small", text: "Your node's address appears once you have started publishing." })]),
    );
    this._updatePages(site);
  }

  _updatePages(site) {
    if (!this._siteTouched) {
      this.nameInput.value = site.node_name;
      this.descInput.value = site.description;
    }
    const key = JSON.stringify(site.pages) + String(this._confirming);
    if (key === this._pages) return;
    this._pages = key;
    const rows = site.pages.map((p) => {
      const state = !p.published ? chip("neutral", "Draft") : p.changed ? chip("warn", "Published · unpublished changes") : chip("good", "Published");
      const row = h("li", { class: "item" },
        h("div", { class: "pmeta" }, h("span", { class: "name", text: p.title }), h("span", { class: "where mono", text: `/page/${p.id}.mu` }), h("div", { class: "row" }, state)),
        h("div", { class: "row" },
          h("button", { type: "button", text: "Edit", "aria-label": `Edit ${p.title}`, onclick: () => this.openEditor(p.id) }),
          p.published && !p.changed
            ? h("button", { type: "button", text: "Unpublish", "aria-label": `Unpublish ${p.title}`, onclick: () => this._act({ op: "page_unpublish", id: p.id }, "Unpublished. Others can no longer read it.") })
            : h("button", { type: "button", text: "Publish", "aria-label": `Publish ${p.title}`, onclick: () => this._act({ op: "page_publish", id: p.id }, "Published. It can take up to a minute to appear for others.") }),
          h("button", { type: "button", class: "danger", text: "Delete", "aria-label": `Delete ${p.title}`, onclick: () => { this._confirming = p.id; this._pages = ""; this._updateHost(); } })));
      if (this._confirming === p.id) {
        const yes = h("button", { type: "button", class: "danger", text: "Delete page", onclick: () => {
          this._confirming = null;
          if (this.editing?.id === p.id) {
            this.editing = null;
            this.editor.classList.add("hidden");
          }
          this._act({ op: "page_delete", id: p.id }, "Page deleted.");
        } });
        row.append(h("div", { class: "confirm", role: "alertdialog", "aria-label": "Confirm delete" },
          h("span", { class: "small", text: `Delete “${p.title}”? This cannot be undone.` }), yes,
          h("button", { type: "button", text: "Cancel", onclick: () => { this._confirming = null; this._pages = ""; this._updateHost(); } })));
        queueMicrotask(() => yes.focus());
      }
      return row;
    });
    this.pagesList.replaceChildren(...(rows.length ? rows : [h("li", { class: "muted small", text: "No pages yet. Start publishing to get a welcome page, or choose New page." })]));
  }

  // -- browsing --------------------------------------------------------------------------------
  openTyped() {
    const text = this.addressInput.value.trim().replace(/^<|>$/g, "");
    const target = resolveLink(text, null);
    if (!target) {
      this.loadLine.textContent = fetchError("invalid");
      this.addressInput.focus();
      return;
    }
    this.go(target);
  }

  go(target) {
    this.history = this.history.slice(0, this.index + 1);
    this.history.push(target);
    if (this.history.length > HISTORY_MAX) this.history.shift();
    this.index = this.history.length - 1;
    this.load(true);
  }

  step(delta) {
    const next = this.index + delta;
    if (next < 0 || next >= this.history.length) return;
    this.index = next;
    this.load(true);
  }

  async load(focus) {
    const current = this.history[this.index];
    if (!current) return;
    const generation = ++this.generation;
    const node = this.nodes.find((n) => n.address === current.address);
    this.where.textContent = `${node?.name || shortAddress(current.address)} · ${current.path}`;
    this.loadLine.textContent = "Connecting to the node… this can take up to 30 seconds.";
    this.viewer.setAttribute("aria-busy", "true");
    this._updateBrowse();
    let answer;
    try {
      answer = await this._api({ op: "fetch", address: current.address, path: current.path });
    } catch (error) {
      answer = { ok: false, error: error?.code };
    }
    if (generation !== this.generation) return; // a newer navigation won
    this.viewer.removeAttribute("aria-busy");
    if (answer.ok) {
      this.lastContent = answer.content;
      this.viewer.replaceChildren(renderMicron(answer.content, current.address, (target) => this.go(target)));
      this.loadLine.textContent = "";
      if (focus) this.viewer.focus({ preventScroll: false });
    } else {
      this.lastContent = null;
      this.viewer.replaceChildren(h("p", { class: "muted", text: fetchError(answer.error) }));
      this.loadLine.textContent = "";
    }
    this.refreshNodesSoon();
  }

  refreshNodesSoon() {
    clearTimeout(this._nodesTimer);
    this._nodesTimer = setTimeout(() => this.refresh(), 500);
  }

  async toggleBookmark() {
    const current = this.history[this.index];
    if (!current || !this.data?.ok) return;
    const marked = this.data.site.bookmarks.some((m) => m.address === current.address && m.path === current.path);
    const node = this.nodes.find((n) => n.address === current.address);
    const title = (pageTitle(this.lastContent || "") || node?.name || `Node ${shortAddress(current.address)}`).replace(/[\u0000-\u001f\u007f]/g, "").slice(0, 64);
    await this._act(marked ? { op: "bookmark_remove", ...current } : { op: "bookmark_add", ...current, title: title || "Page" });
  }

  // -- hosting -------------------------------------------------------------------------------
  async _act(body, done = "") {
    this.pagesFeedback.textContent = "";
    try {
      await this._api(body);
      this.pagesFeedback.textContent = done;
    } catch (error) {
      this.pagesFeedback.textContent = error?.message || fetchError(error?.code);
      if (body.op?.startsWith("bookmark")) this.loadLine.textContent = this.pagesFeedback.textContent;
    }
    await this.refresh();
  }

  async saveSite() {
    this.siteFeedback.textContent = "Saving…";
    try {
      await this._api({ op: "site_save", node_name: this.nameInput.value.trim(), description: this.descInput.value.trim() });
      this._siteTouched = false;
      this.siteFeedback.textContent = "Saved.";
    } catch (error) {
      this.siteFeedback.textContent = error?.message || fetchError(error?.code);
    }
    await this.refresh();
  }

  async setHosting() {
    const enabled = !this.data?.site?.hosting;
    if (enabled && this.nameInput.value.trim() && this.nameInput.value.trim() !== this.data.site.node_name) await this.saveSite();
    try {
      const answer = await this._api({ op: "hosting", enabled });
      this.pagesFeedback.textContent = enabled
        ? answer.created_default
          ? "Publishing. ito created a welcome page for you: edit it below."
          : "Publishing. Others can read your published pages in a minute or so."
        : "Publishing stopped. Your pages are kept.";
    } catch (error) {
      this.pagesFeedback.textContent = error?.message || fetchError(error?.code);
      if (error?.code === "needs_name") this.nameInput.focus();
    }
    await this.refresh();
  }

  async openEditor(id) {
    if (this.dirty() && !globalThis.confirm("Discard your unsaved changes to this page?")) return;
    let page = { id: null, title: "", content: "" };
    if (id) {
      try {
        page = await this._api({ op: "page_get", id });
      } catch (error) {
        this.pagesFeedback.textContent = error?.message || fetchError(error?.code);
        return;
      }
    }
    this.editing = { id: page.id, title: page.title, content: page.content };
    this.titleInput.value = page.title;
    this.textInput.value = page.content;
    this.linksButton.classList.toggle("hidden", page.id !== "index");
    this.editorFeedback.textContent = "";
    this.preview.classList.add("hidden");
    this.previewButton.setAttribute("aria-pressed", "false");
    this.editor.classList.remove("hidden");
    this._count();
    this.titleInput.focus();
  }

  closeEditor() {
    if (this.dirty() && !globalThis.confirm("Discard your unsaved changes to this page?")) return;
    this.editing = null;
    this.editor.classList.add("hidden");
  }

  _count() {
    const bytes = new TextEncoder().encode(this.textInput.value).length;
    this.counter.textContent = `${Math.ceil(bytes / 1024)} of 32 KiB used`;
    if (!this.preview.classList.contains("hidden")) this._renderPreview();
  }

  togglePreview() {
    const show = this.preview.classList.contains("hidden");
    this.preview.classList.toggle("hidden", !show);
    this.previewButton.setAttribute("aria-pressed", String(show));
    if (show) this._renderPreview();
  }

  _renderPreview() {
    this.preview.replaceChildren(
      h("p", { class: "muted small", text: "Preview: how Nomad Network browsers will show this page (links are not followed here)." }),
      renderMicron(this.textInput.value, this.data?.address || null, () => {}),
    );
  }

  insertLinks() {
    const pages = (this.data?.site?.pages || []).filter((p) => p.id !== "index" && p.published);
    const lines = pages.map((p) => `\`[${p.title.replace(/[`[\]\\]/g, "")}\`:/page/${p.id}.mu]`);
    const text = lines.length ? lines.join("\n") : "(No other published pages yet.)";
    const input = this.textInput;
    const at = input.selectionEnd ?? input.value.length;
    input.setRangeText(`${at && input.value[at - 1] !== "\n" ? "\n" : ""}${text}\n`, at, at, "end");
    input.focus();
    this._count();
  }

  async savePage(publish) {
    if (!this.editing) return;
    this.editorFeedback.textContent = "Saving…";
    const body = { op: "page_save", title: this.titleInput.value.trim(), content: this.textInput.value };
    if (this.editing.id) body.id = this.editing.id;
    try {
      const saved = await this._api(body);
      this.editing = { id: saved.id, title: body.title, content: body.content };
      if (publish) await this._api({ op: "page_publish", id: saved.id });
      this.editorFeedback.textContent = publish
        ? this.data?.site?.hosting ? "Saved and published. It can take up to a minute to appear for others." : "Saved and published. Start publishing above so that others can read it."
        : "Draft saved. Others still see the published version, if any.";
    } catch (error) {
      this.editorFeedback.textContent = error?.message || fetchError(error?.code);
    }
    await this.refresh();
  }
}
