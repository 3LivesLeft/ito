// SPDX-License-Identifier: Apache-2.0
// Branded components (docs/branding.md §6.2). They take plain values, never a data source or
// Home Assistant objects, so any delivery can use them.

import { MARKS } from "../brand-mark.js";
import { chartPaths, formatNumber, lastValue, peakValue } from "../model.js";
import { h, icon, s } from "./dom.js";

const CHART_W = 600;
const CHART_H = 150;

/** The MeshBeacon mark, built element by element from generated geometry (no markup parsed). */
export function brandMark(size = "small", label = null) {
  const svg = s("svg", { viewBox: "0 0 256 256", focusable: "false" });
  if (label) {
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
  } else svg.setAttribute("aria-hidden", "true");
  for (const [tag, cls, attrs] of MARKS[size]) svg.append(s(tag, { ...attrs, class: `mk-${cls}` }));
  return svg;
}

/** Header wordmark: mark + "ito" (always lower case). */
export function brandTitle() {
  return h("h1", { class: "brand" }, brandMark("small"), h("span", { class: "word", text: "ito" }));
}

// A distinct shape per state, so status never depends on colour alone (WCAG 1.4.1).
const STATUS_SHAPES = {
  online: "M7 12.5l3.2 3.2L17 9", // tick
  partial: "M12 7v6M12 16.5v.5", // exclamation
  offline: "M8 8l8 8M16 8l-8 8", // cross
  isolated: "M7 12h10", // dash
  unknown: "M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.4M12 16.5v.5", // question mark
};

export function statusMark(state, label) {
  const svg = s("svg", { viewBox: "0 0 24 24", "aria-hidden": "true", focusable: "false" });
  svg.append(
    s("path", {
      d: STATUS_SHAPES[state] || STATUS_SHAPES.unknown,
      fill: "none",
      stroke: "currentColor",
      "stroke-width": "2.4",
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
    }),
  );
  return h("div", { class: "status-mark", role: "img", "aria-label": label }, svg);
}

export function chip(tone, text) {
  return h("span", { class: "chip", "data-tone": tone, text });
}

export function banner(tone, title, text) {
  return h(
    "div",
    { class: "card banner", "data-tone": tone, role: "status" },
    h("div", {}, h("strong", { text: title }), h("span", { class: "muted small", text })),
  );
}

export function value(text, unitText) {
  return h("div", { class: "value" }, text, unitText && text !== "—" ? h("span", { class: "u", text: unitText }) : null);
}

export function tile(label, iconName, valueNode, note) {
  return h(
    "div",
    { class: "card tile" },
    h("div", { class: "label" }, icon(iconName), h("span", { text: label })),
    valueNode,
    note ? h("div", { class: "muted small", text: note }) : null,
  );
}

/** Centred message (empty, not connected, error) with the mark and at most one action. */
export function message({ title, lines, alert = false, action = null }) {
  return h(
    "main",
    {},
    h(
      "div",
      { class: "card center", role: alert ? "alert" : null },
      h("div", { class: "art" }, brandMark("full")),
      h("h2", { text: title }),
      lines.map((text) => h("p", { class: "muted small", text })),
      action ? h("button", { class: "btn", type: "button", text: action.label, onclick: action.onClick }) : null,
    ),
  );
}

export function skeletonPage(label) {
  const block = (height) => h("div", { class: "card skeleton", style: `height:${height}px`, "aria-hidden": "true" });
  return h(
    "main",
    { "aria-busy": "true" },
    h("span", { class: "sr", text: label }),
    block(112),
    h("div", { class: "tiles" }, [1, 2, 3, 4].map(() => block(112))),
    block(220),
  );
}

export function segmented(label, options, selected, onSelect) {
  return h(
    "div",
    { class: "seg", role: "group", "aria-label": label },
    options.map((o) =>
      h("button", {
        type: "button",
        "aria-pressed": String(selected === o.key),
        text: o.label,
        onclick: () => selected !== o.key && onSelect(o.key),
      }),
    ),
  );
}

export function tabs(label, items, selected, onSelect) {
  return h(
    "nav",
    { role: "tablist", "aria-label": label },
    items.map((t) =>
      h("button", {
        role: "tab",
        type: "button",
        "aria-selected": String(selected === t.key),
        "aria-controls": "content",
        text: t.label,
        onclick: () => onSelect(t.key),
      }),
    ),
  );
}

/**
 * Chart card. series: [{label, color, values (bucketed, null = gap), current (number|null)}].
 * state: "loading" | "unavailable" | "ready". unavailableText explains a missing history.
 */
export function chartCard({ title, series, unit = "", digits = 1, floor = 0, wide = false, state, rangeLabel, language, unavailableText, emptyText }) {
  const card = h("section", { class: `card${wide ? " wide" : ""}`, "aria-label": title });
  const legend = h("div", { class: "legend" });
  const setLegend = (index) => {
    legend.replaceChildren(
      ...series.map((x) => {
        const v = index === null ? x.current : x.values[index];
        const shown = v === null || v === undefined ? "—" : `${formatNumber(v, language, digits)} ${unit}`.trim();
        return h("span", { style: `--c:${x.color}`, text: `${x.label ? `${x.label} ` : ""}${shown}` });
      }),
    );
  };
  setLegend(null);
  card.append(h("div", { class: "chart-head" }, h("h2", { text: title }), legend));
  if (state === "loading") {
    card.append(h("div", { class: "skeleton", style: "height:150px", "aria-hidden": "true" }));
    return card;
  }
  if (state === "unavailable") {
    card.append(h("div", { class: "empty", text: unavailableText }));
    return card;
  }
  const lists = series.map((x) => x.values);
  if (!lists.some((l) => l.some((v) => v !== null))) {
    card.append(h("div", { class: "empty", text: emptyText }));
    return card;
  }
  const { max, paths } = chartPaths(lists, CHART_W, CHART_H, floor);
  const svg = s("svg", { viewBox: `0 0 ${CHART_W} ${CHART_H}`, preserveAspectRatio: "none", role: "img" });
  const summary = series.map(
    (x, i) =>
      `${x.label || title} peak ${formatNumber(peakValue(lists[i]), language, digits)} ${unit}, latest ${formatNumber(lastValue(lists[i]), language, digits)} ${unit}`,
  );
  svg.setAttribute("aria-label", `${title}, ${rangeLabel}: ${summary.join("; ")}`);
  for (const f of [0.25, 0.5, 0.75, 1]) svg.append(s("line", { class: "grid", x1: 0, x2: CHART_W, y1: CHART_H * (1 - f), y2: CHART_H * (1 - f) }));
  paths.forEach((p, i) => {
    svg.append(s("path", { class: "area", d: p.area, fill: series[i].color }));
    svg.append(s("path", { class: "line", d: p.line, stroke: series[i].color }));
    if (p.dots) svg.append(s("path", { class: "dot", d: p.dots, stroke: series[i].color }));
  });
  const cursor = s("line", { class: "cursor", y1: 0, y2: CHART_H, x1: 0, x2: 0 });
  svg.append(cursor);
  const n = Math.max(...lists.map((l) => l.length));
  const move = (ev) => {
    const rect = svg.getBoundingClientRect();
    if (!rect.width) return;
    const index = Math.round(Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width)) * (n - 1));
    const x = n === 1 ? CHART_W / 2 : (index / (n - 1)) * CHART_W;
    cursor.setAttribute("x1", x);
    cursor.setAttribute("x2", x);
    cursor.style.visibility = "visible";
    setLegend(index);
  };
  svg.addEventListener("pointermove", move);
  svg.addEventListener("pointerdown", move);
  svg.addEventListener("pointerleave", () => {
    cursor.style.visibility = "hidden";
    setLegend(null);
  });
  card.append(
    h("div", { class: "plot" }, svg, h("span", { class: "ymax", text: `${formatNumber(max, language, max < 10 ? 1 : 0)} ${unit}` })),
    h("div", { class: "axis" }, h("span", { text: `${rangeLabel} ago` }), h("span", { text: "Now" })),
  );
  return card;
}

/** Copy text to the clipboard; the button says whether it worked. */
export function copyButton(text) {
  const button = h("button", { type: "button", class: "copy", text: "Copy" });
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
    } catch (_err) {
      button.textContent = "Select and copy";
    }
  });
  return button;
}
