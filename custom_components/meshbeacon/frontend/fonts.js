// SPDX-License-Identifier: Apache-2.0
// Inter 5.3.0 (SIL Open Font License 1.1, fonts/inter-5.3.0/OFL.txt), Latin subset, served with
// the integration: no font service, no CDN. Registered under a private family name so Home
// Assistant's own typography is untouched. If loading fails, the system font stack is used.

const WEIGHTS = [400, 500, 600, 700];
let started = false;

export function loadFonts() {
  if (started || typeof FontFace === "undefined" || !document.fonts) return;
  started = true;
  for (const weight of WEIGHTS) {
    const url = new URL(`./fonts/inter-5.3.0/inter-latin-${weight}-normal.woff2`, import.meta.url);
    const face = new FontFace("MeshBeacon Inter", `url("${url.pathname}") format("woff2")`, {
      weight: String(weight),
      style: "normal",
      display: "swap",
    });
    document.fonts.add(face);
    face.load().catch(() => {}); // system fonts remain in use
  }
}
