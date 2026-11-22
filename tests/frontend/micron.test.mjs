// SPDX-License-Identifier: Apache-2.0
// The safe micron subset (ADR 0027 point 7): remote pages become plain data, links resolve only
// to Nomad Network pages, and markup that ito does not support is dropped, never interpreted.

import assert from "node:assert/strict";
import { test } from "node:test";

import { MAX_LINES, pageTitle, parseMicron, resolveLink } from "../../custom_components/meshbeacon/frontend/micron.js";

const HERE = "ab".repeat(16);
const THERE = "cd".repeat(16);

test("headings, depth, dividers, comments and literal blocks", () => {
  const { blocks } = parseMicron("#!c=0\n# a comment\n>Title\ntext\n>>Sub\n-\n<\nback\n`=\n`!not bold`!\n<b>\n`=\n");
  assert.deepEqual(blocks.map((b) => b.type), ["heading", "text", "heading", "divider", "text", "literal", "space"]);
  assert.equal(blocks[0].level, 1);
  assert.equal(blocks[2].level, 2);
  assert.equal(blocks[4].depth, 0);
  assert.equal(blocks[5].text, "`!not bold`!\n<b>"); // literal: shown exactly, never parsed
});

test("emphasis spans, reset and escapes", () => {
  const [line] = parseMicron("a `!bold`! `*it`* `_u`_ \\`! `!b``plain").blocks;
  const bold = line.spans.find((s) => s.text === "bold");
  assert.equal(bold.bold, true);
  assert.equal(line.spans.find((s) => s.text === "it").italic, true);
  assert.equal(line.spans.find((s) => s.text === "u").underline, true);
  assert.ok(line.spans.some((s) => s.text.includes("`!"))); // escaped: literal text
  const plain = line.spans.find((s) => s.text === "plain");
  assert.equal(plain.bold, false);
});

test("colours are read and dropped, never applied", () => {
  const [line] = parseMicron("`Ff00`B000red on black`f`b").blocks;
  assert.deepEqual(line.spans, [{ text: "red on black", bold: false, italic: false, underline: false }]);
});

test("HTML and script in a page stay text", () => {
  const source = 'x <script>alert(1)</script>\nx <img src=x onerror=alert(1)>\n`[<b>x</b>`javascript:alert(1)]';
  const { blocks } = parseMicron(source);
  const text = JSON.stringify(blocks);
  assert.ok(text.includes("x <script>alert(1)</script>") && text.includes("onerror=alert(1)>"));
  assert.deepEqual(new Set(blocks.map((b) => b.type)), new Set(["text"]));
  const link = blocks[2].spans.find((s) => s.link);
  assert.equal(link.link.label, "<b>x</b>");
  assert.equal(resolveLink(link.link.target, HERE), null); // a javascript: target is never followed
});

test("input fields become an unsupported marker", () => {
  const [line] = parseMicron("Name: `<16|name`>").blocks;
  assert.ok(line.spans.some((s) => s.field));
});

test("links resolve only to Nomad Network pages", () => {
  assert.deepEqual(resolveLink(":/page/about.mu", HERE), { address: HERE, path: "/page/about.mu" });
  assert.deepEqual(resolveLink("/page/a/b.mu", HERE), { address: HERE, path: "/page/a/b.mu" });
  assert.deepEqual(resolveLink(`${THERE}:/page/index.mu`, HERE), { address: THERE, path: "/page/index.mu" });
  assert.deepEqual(resolveLink(THERE.toUpperCase(), HERE), { address: THERE, path: "/page/index.mu" });
  assert.deepEqual(resolveLink(`${THERE}:`, null), { address: THERE, path: "/page/index.mu" });
  for (const bad of ["https://example.org", "http:/page/x.mu", "lxmf@abc", ":/file/data.zip", ":/page/../x.mu", ":/page/x.html", ":/page//x.mu", "javascript:alert(1)", ":/media/x.png"]) {
    assert.equal(resolveLink(bad, HERE), null, bad);
  }
  assert.equal(resolveLink(":/page/x.mu", null), null); // no current node: nothing to resolve against
});

test("link label and target forms", () => {
  const [line] = parseMicron("`[Home`:/page/index.mu] `[:/page/x.mu] `[Form`:/page/f.mu`field=1]").blocks;
  const links = line.spans.filter((s) => s.link).map((s) => s.link);
  assert.deepEqual(links, [
    { label: "Home", target: ":/page/index.mu" },
    { label: ":/page/x.mu", target: ":/page/x.mu" },
    { label: "Form", target: ":/page/f.mu" },
  ]);
});

test("very long pages are cut at a fixed number of lines", () => {
  const { blocks, truncated } = parseMicron("x\n".repeat(MAX_LINES + 10));
  assert.equal(truncated, true);
  assert.ok(blocks.length <= MAX_LINES);
});

test("a page title for bookmarks comes from the first heading", () => {
  assert.equal(pageTitle("#c\n>`!Hello`! there\ntext"), "Hello there");
  assert.equal(pageTitle("no heading"), null);
});
