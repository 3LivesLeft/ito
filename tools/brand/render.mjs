// SPDX-License-Identifier: Apache-2.0
// Rasterise brand SVGs to PNG with Playwright's Chromium (a developer tool, not a dependency).
// Called by tools/brand/build.py with a JSON manifest:
//   [{svg, png, width, height, trim}]  width 0 = proportional to height.
// trim: crop the drawing to its visible bounding box (Home Assistant brand images are trimmed).
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const jobs = JSON.parse(readFileSync(process.argv[2], "utf8"));
const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 1 });
for (const job of jobs) {
  const source = readFileSync(job.svg, "utf8");
  await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent">${source}</body></html>`);
  const box = await page.evaluate(
    ({ trim }) => {
      const svg = document.querySelector("svg");
      const [, , w, h] = svg.getAttribute("viewBox").split(/\s+/).map(Number);
      if (!trim) return { x: 0, y: 0, w, h };
      const b = svg.getBBox(); // geometry only: widen by the largest stroke
      const pad = 6;
      return { x: b.x - pad, y: b.y - pad, w: b.width + 2 * pad, h: b.height + 2 * pad };
    },
    { trim: job.trim },
  );
  const height = job.height;
  const width = job.width || Math.round((box.w / box.h) * height);
  await page.evaluate(
    ({ box, width, height }) => {
      const svg = document.querySelector("svg");
      svg.setAttribute("viewBox", `${box.x} ${box.y} ${box.w} ${box.h}`);
      svg.setAttribute("width", width);
      svg.setAttribute("height", height);
      svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
      svg.style.display = "block";
    },
    { box, width, height },
  );
  await page.setViewportSize({ width, height });
  await page.locator("svg").screenshot({ path: job.png, omitBackground: true });
}
await browser.close();
