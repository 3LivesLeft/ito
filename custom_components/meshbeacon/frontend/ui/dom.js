// SPDX-License-Identifier: Apache-2.0
// DOM helpers. Every value is written with textContent or attributes, never parsed as HTML, so
// names and messages cannot inject markup (threat model T38).

const SVG = "http://www.w3.org/2000/svg"; // XML namespace identifier, not a request

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key in el && !key.includes("-")) el[key] = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function s(tag, attrs = {}) {
  const el = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}

/** A Material Design Icon when the host provides `ha-icon` (Home Assistant); otherwise nothing. */
export function icon(name) {
  return customElements.get("ha-icon") ? h("ha-icon", { icon: name, "aria-hidden": "true" }) : null;
}
