// SPDX-License-Identifier: Apache-2.0
// A safe subset of Nomad Network's micron markup (ADR 0027 point 7), parsed into plain data.
// Written for ito from the format as users write it; it shares no code with Nomad Network.
//
// Supported: headings (> >> >>>, < resets the section depth), dividers (-), comments and page
// directives (#), literal blocks (a line `=), bold (`!), italic (`*), underline (`_), reset (``),
// alignment (`c `l `r `a), escapes (\) and links (`[label`target] or `[target]). Colours (`F `f
// `B `b) are read and ignored, so that remote pages cannot make text unreadable. Input fields
// (`<…>) become a "not supported" marker. The result is data only: the view turns it into DOM
// nodes with textContent (ui/pages.js), so nothing in a page can become HTML, script or style.

export const MAX_LINES = 5000;
const HEX = /^[0-9a-f]{32}$/i;
const PAGE = /^\/page\/[A-Za-z0-9_-][A-Za-z0-9_./-]{0,199}\.mu$/;

/** A link target as {address, path}, or null when ito cannot follow it (web, files, LXMF …). */
export function resolveLink(target, current) {
  let text = String(target || "").trim();
  let address = current || null;
  const colon = text.indexOf(":");
  if (colon >= 0) {
    const before = text.slice(0, colon);
    if (before === "") text = text.slice(1);
    else if (HEX.test(before)) {
      address = before.toLowerCase();
      text = text.slice(colon + 1);
    } else return null; // http:, https:, lxmf@ … : never followed
  } else if (HEX.test(text)) return { address: text.toLowerCase(), path: "/page/index.mu" };
  if (text === "") text = "/page/index.mu";
  if (!address || !PAGE.test(text) || text.split("/").includes("..") || text.includes("//")) return null;
  return { address, path: text };
}

function parseLink(body) {
  // body: "label`target`fields" | "target`fields" | "target" (fields are ignored: no forms).
  const parts = body.split("`");
  if (parts.length === 1) return { label: parts[0], target: parts[0] };
  return { label: parts[0] || parts[1], target: parts[1] };
}

/** One line of inline markup into spans; `state` carries emphasis across lines, as in micron. */
function parseInline(text, state) {
  const spans = [];
  let buf = "";
  const flush = () => {
    if (buf) spans.push({ text: buf, bold: state.bold, italic: state.italic, underline: state.underline });
    buf = "";
  };
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === "\\" && i + 1 < text.length) {
      buf += text[++i];
      continue;
    }
    if (ch !== "`" || i + 1 >= text.length) {
      buf += ch;
      continue;
    }
    const tag = text[++i];
    if (tag === "!" || tag === "*" || tag === "_") {
      flush();
      const key = tag === "!" ? "bold" : tag === "*" ? "italic" : "underline";
      state[key] = !state[key];
    } else if (tag === "`") {
      flush();
      state.bold = state.italic = state.underline = false;
      state.align = "left";
    } else if (tag === "F" || tag === "B") i += 3; // a colour: ignored
    else if (tag === "f" || tag === "b") {
      // colour reset: nothing to do
    } else if (tag === "c" || tag === "l" || tag === "r" || tag === "a") {
      state.align = { c: "center", l: "left", r: "right", a: "left" }[tag];
    } else if (tag === "[") {
      const end = text.indexOf("]", i + 1);
      if (end < 0) {
        buf += text.slice(i + 1);
        break;
      }
      flush();
      const link = parseLink(text.slice(i + 1, end));
      spans.push({ link: { label: link.label, target: link.target }, bold: state.bold, italic: state.italic, underline: state.underline });
      i = end;
    } else if (tag === "<") {
      const end = text.indexOf(">", i + 1);
      flush();
      spans.push({ field: true });
      i = end < 0 ? text.length : end;
    } else if (tag === "=") {
      // inline literal toggle: treated as plain text from here on in this line
      buf += text.slice(i + 1);
      break;
    }
    // any other tag is dropped, never shown as markup
  }
  flush();
  return spans;
}

/**
 * Micron text into blocks: {type: "heading", level, depth, align, spans} | {type: "text", depth,
 * align, spans} | {type: "divider", depth} | {type: "literal", depth, text} | {type: "space"}.
 * At most MAX_LINES lines; `truncated` says whether more were dropped.
 */
export function parseMicron(source) {
  const lines = String(source ?? "").replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  const state = { bold: false, italic: false, underline: false, align: "left" };
  let depth = 0;
  let literal = null;
  const truncated = lines.length > MAX_LINES;
  for (const raw of lines.slice(0, MAX_LINES)) {
    if (raw.trim() === "`=") {
      if (literal === null) literal = [];
      else {
        blocks.push({ type: "literal", depth, text: literal.join("\n") });
        literal = null;
      }
      continue;
    }
    if (literal !== null) {
      literal.push(raw);
      continue;
    }
    if (raw.startsWith("#")) continue; // comments and page directives (#!c=…)
    if (raw.startsWith("<")) {
      depth = 0;
      const rest = raw.replace(/^<+/, "");
      if (rest.trim()) blocks.push({ type: "text", depth, align: state.align, spans: parseInline(rest, state) });
      continue;
    }
    if (raw.startsWith(">")) {
      const level = Math.min(raw.match(/^>+/)[0].length, 3);
      depth = level;
      blocks.push({ type: "heading", level, depth: level - 1, align: state.align, spans: parseInline(raw.replace(/^>+/, ""), state) });
      continue;
    }
    if (/^-.?$/u.test(raw)) {
      blocks.push({ type: "divider", depth });
      continue;
    }
    if (raw.trim() === "") {
      blocks.push({ type: "space" });
      continue;
    }
    blocks.push({ type: "text", depth, align: state.align, spans: parseInline(raw, state) });
  }
  if (literal !== null) blocks.push({ type: "literal", depth, text: literal.join("\n") });
  return { blocks, truncated };
}

/** Plain text of a page's first heading, for a bookmark's default title. */
export function pageTitle(source) {
  for (const block of parseMicron(source).blocks) {
    if (block.type === "heading") {
      const text = block.spans.map((s) => s.text || s.link?.label || "").join("").trim();
      if (text) return text.slice(0, 64);
    }
  }
  return null;
}
