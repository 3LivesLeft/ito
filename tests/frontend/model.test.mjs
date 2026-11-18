// SPDX-License-Identifier: Apache-2.0
// Unit tests for the panel's pure functions. Run with: node --test tests/frontend
// (Node's built-in runner; no packages are installed.)

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";

import {
  PATH_POOL_TARGET,
  bucket,
  chartPaths,
  duration,
  formatNumber,
  nodeState,
  niceMax,
  numeric,
  pathsNote,
  peerState,
  precision,
  secondsSince,
  seriesFromHistory,
  seriesFromStatistics,
  tabFromPath,
} from "../../custom_components/meshbeacon/frontend/model.js";

const FRONTEND = new URL("../../custom_components/meshbeacon/frontend/", import.meta.url);

test("numeric treats unknown and unavailable as missing, never zero", () => {
  assert.equal(numeric({ state: "12.5" }), 12.5);
  assert.equal(numeric({ state: "0" }), 0);
  for (const state of ["unknown", "unavailable", "", "abc"]) assert.equal(numeric({ state }), null);
  assert.equal(numeric(undefined), null);
});

test("formatNumber groups digits and shows a dash for missing values", () => {
  assert.equal(formatNumber(2048, "en-GB"), "2,048");
  assert.equal(formatNumber(1.8, "en-GB", 1), "1.8");
  assert.equal(formatNumber(null, "en-GB"), "—");
  assert.equal(formatNumber(Number.NaN, "en-GB"), "—");
});

test("precision prefers the entity's display precision", () => {
  assert.equal(precision({ display_precision: 3 }, 1.23456), 3);
  assert.equal(precision(undefined, 1.5, 1), 1);
  assert.equal(precision(undefined, 42), 0);
  assert.equal(precision(undefined, 0.28), 2);
});

test("duration reads naturally", () => {
  assert.equal(duration(30), "under a minute");
  assert.equal(duration(7 * 60), "7 min");
  assert.equal(duration(3 * 3600), "3 h");
  assert.equal(duration(3 * 3600 + 5 * 60), "3 h 5 min");
  assert.equal(duration(5 * 86400), "5 days");
  assert.equal(duration(null), "—");
  assert.equal(duration(-1), "—");
});

test("secondsSince parses ISO timestamps and ignores unknown", () => {
  const now = Date.parse("2026-11-18T12:07:00Z");
  assert.equal(secondsSince({ state: "2026-11-18T12:00:00+00:00" }, now), 420);
  assert.equal(secondsSince({ state: "unknown" }, now), null);
});

test("history rows become a sorted series with gaps for unavailable values", () => {
  const series = seriesFromHistory([
    { s: "2", lu: 20 },
    { s: "1", lu: 10 },
    { s: "unavailable", lu: 30 },
    { s: "x" },
    null,
  ]);
  assert.deepEqual(series, [
    { t: 10_000, v: 1 },
    { t: 20_000, v: 2 },
    { t: 30_000, v: null },
  ]);
  assert.deepEqual(seriesFromHistory(undefined), []);
});

test("statistics rows use the hourly mean", () => {
  assert.deepEqual(seriesFromStatistics([{ start: 3_600_000, mean: 4 }, { start: 0, mean: null }]), [
    { t: 0, v: null },
    { t: 3_600_000, v: 4 },
  ]);
});

test("bucket takes time-weighted step values and leaves gaps as null", () => {
  // value 10 from t=0, 20 from t=50, unavailable from t=80, over [0,100) in 4 buckets
  const out = bucket(
    [
      { t: 0, v: 10 },
      { t: 50, v: 20 },
      { t: 80, v: null },
    ],
    0,
    100,
    4,
  );
  assert.deepEqual(out, [10, 10, 20, 20]);
  const gap = bucket([{ t: 60, v: 5 }], 0, 100, 4);
  assert.deepEqual(gap, [null, null, 5, 5]); // before the first row: unknown, not zero
  assert.deepEqual(bucket([], 0, 100, 3), [null, null, null]);
});

test("bucket splits a value that spans a boundary", () => {
  const out = bucket(
    [
      { t: 0, v: 0 },
      { t: 30, v: 10 },
    ],
    0,
    40,
    2,
  );
  assert.deepEqual(out, [0, 5]);
});

test("niceMax rounds up to a readable axis", () => {
  assert.equal(niceMax(0), 1);
  assert.equal(niceMax(1.8), 2);
  assert.equal(niceMax(2.2), 2.5);
  assert.equal(niceMax(78), 100);
  assert.equal(niceMax(2048), 2500);
});

test("chartPaths splits lines at gaps and keeps points inside the plot", () => {
  const { max, paths } = chartPaths([[1, 2, null, 2, 1]], 100, 50);
  assert.equal(max, 2);
  assert.equal((paths[0].line.match(/M/g) || []).length, 2);
  for (const n of paths[0].line.match(/-?\d+(\.\d+)?/g).map(Number)) assert.ok(n >= 0 && n <= 100);
  assert.deepEqual(chartPaths([[null, null]], 100, 50).paths[0], { line: "", area: "", dots: "" });
  assert.equal(chartPaths([[1, 2, 2]], 100, 50).paths[0].dots, ""); // a run, not isolated points
  assert.match(chartPaths([[null, null, 3]], 100, 50).paths[0].dots, /^M100,\d+(\.\d)?h0$/); // first minutes
});

test("node state: unavailable only when the main entities are", () => {
  const node = { entities: { status: "s.a", connectivity: "s.b", known_paths: "s.c", cpu: "s.d" } };
  const states = (v) => ({ "s.a": { state: v }, "s.b": { state: v }, "s.c": { state: v }, "s.d": { state: "1" } });
  assert.equal(nodeState(node, states("unavailable")), "unavailable");
  assert.equal(nodeState(node, states("running")), "ok");
  assert.equal(nodeState(node, states("unknown")), "ok");
  assert.equal(nodeState({ entities: {} }, {}), "unavailable");
});

test("peer state distinguishes connected, disconnected and missing peers", () => {
  const peer = (reported) => ({ reported, entities: { connected: "b.p" } });
  assert.equal(peerState(peer(true), { "b.p": { state: "on" } }), "connected");
  assert.equal(peerState(peer(true), { "b.p": { state: "off" } }), "disconnected");
  assert.equal(peerState(peer(true), { "b.p": { state: "unavailable" } }), "missing");
  assert.equal(peerState(peer(false), { "b.p": { state: "on" } }), "missing");
});

test("the known-paths note appears at Reticulum's unused-path target", () => {
  assert.equal(PATH_POOL_TARGET, 2048);
  assert.equal(pathsNote(2047), null);
  assert.equal(pathsNote(null), null);
  assert.match(pathsNote(2048), /busy network/);
});

test("tabs come from the route path, defaulting to the overview", () => {
  assert.equal(tabFromPath("/diagnostics"), "diagnostics");
  assert.equal(tabFromPath(""), "overview");
  assert.equal(tabFromPath("/messages"), "overview"); // no placeholder tabs
});

test("frontend files make no external requests and never use innerHTML", () => {
  const files = readdirSync(FRONTEND, { recursive: true }).filter((n) => n.endsWith(".js"));
  assert.ok(files.length >= 10, files.join());
  for (const name of files) {
    const source = readFileSync(new URL(name, FRONTEND), "utf8");
    const urls = (source.match(/https?:\/\/[^\s"'`)]+/g) || []).filter((u) => u !== "http://www.w3.org/2000/svg");
    assert.deepEqual(urls, [], `${name} refers to ${urls}`);
    assert.doesNotMatch(source, /\binnerHTML\b|\bouterHTML\b|insertAdjacentHTML|document\.write|\beval\(|new Function/, name);
    assert.doesNotMatch(source, /\bfetch\(|XMLHttpRequest|WebSocket\(|import\(\s*["'`]https?:/, name);
    assert.doesNotMatch(source, /localStorage|sessionStorage|indexedDB/, name); // no second history store
  }
});

test("the frontend folder holds only code and the bundled Inter font with its licence", () => {
  const top = readdirSync(FRONTEND).sort();
  assert.deepEqual(top, ["brand-mark.js", "fonts", "fonts.js", "meshbeacon-panel.js", "model.js", "sources", "tokens.js", "ui"]);
  assert.deepEqual(readdirSync(new URL("sources/", FRONTEND)).sort(), ["hass.js", "snapshot.js"]);
  assert.deepEqual(readdirSync(new URL("ui/", FRONTEND)).sort(), ["components.js", "controller.js", "dom.js", "style.js", "views.js"]);
  const fonts = readdirSync(new URL("fonts/inter-5.3.0/", FRONTEND)).sort();
  assert.deepEqual(fonts, [
    "OFL.txt",
    "inter-latin-400-normal.woff2",
    "inter-latin-500-normal.woff2",
    "inter-latin-600-normal.woff2",
    "inter-latin-700-normal.woff2",
  ]);
  const licence = readFileSync(new URL("fonts/inter-5.3.0/OFL.txt", FRONTEND), "utf8");
  assert.match(licence, /SIL Open Font License, Version 1\.1/);
});
