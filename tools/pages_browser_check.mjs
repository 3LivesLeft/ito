// SPDX-License-Identifier: Apache-2.0
// Drives the Pages tab in Chromium (started by tools/pages_browser_check.py). Loopback only.
import { createRequire } from "node:module";
import assert from "node:assert/strict";

const { chromium, devices } = createRequire(import.meta.url)("playwright");
const url = process.argv[2];
const device = process.argv[3];
const origin = new URL(url).origin;

async function check(name, context) {
  const page = await context.newPage();
  const problems = [];
  const outside = [];
  page.on("console", (m) => { if (m.type() === "error") problems.push(m.text()); });
  page.on("pageerror", (e) => problems.push(String(e)));
  page.on("dialog", (d) => { problems.push(`dialog: ${d.message()}`); d.dismiss(); });
  page.on("request", (r) => { if (!r.url().startsWith(origin)) outside.push(r.url()); });
  await page.goto(`${url}#pages`);
  await page.getByRole("button", { name: "Open Hill <b>farm</b>" }).click();
  await page.getByRole("heading", { name: "Hostile test page" }).waitFor();
  const viewer = page.locator(".viewer").first();
  // Hostile content stays text: no element of the page's own making, no script run, no request.
  assert.equal(await viewer.locator("script, img, iframe, a, style").count(), 0, "elements from page content");
  assert.ok((await viewer.textContent()).includes("<script>window.__pwned = 1</script>"));
  assert.equal(await page.evaluate(() => window.__pwned), undefined, "page content ran");
  assert.equal(await viewer.getByRole("button", { name: "Run me" }).count(), 0, "a javascript: link became clickable");
  assert.equal(await viewer.getByRole("button", { name: "Web link" }).count(), 0, "a web link became clickable");
  await page.screenshot({ path: `${process.env.SHOT_DIR || "."}/pages-${name}-browse.png` });
  // Every card fits the screen, however wide the page's content is.
  const widest = await page.evaluate(() => Math.max(...[...document.querySelector("ito-dashboard").shadowRoot.querySelectorAll(".pages .card")].map((c) => c.getBoundingClientRect().right)));
  assert.ok(widest <= (await page.evaluate(() => window.innerWidth)), `a card is ${widest}px wide`);
  // A Nomad link opens inside the viewer; Back returns.
  await viewer.getByRole("button", { name: "Next page" }).click();
  await page.getByText("You followed a link.").waitFor();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await page.getByRole("heading", { name: "Hostile test page" }).waitFor();
  // Bookmark, then remove it again.
  await page.getByRole("button", { name: "Bookmark" }).click();
  await page.getByRole("button", { name: "Remove bookmark Hostile test page" }).waitFor();
  await page.getByRole("button", { name: "Remove bookmark", exact: true }).click();
  await page.getByText("No bookmarks yet.").waitFor();
  // An invalid address explains itself.
  await page.getByLabel("Nomad Network node address").fill("not an address");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByText("Enter a node address").waitFor();

  // Hosting: name, start, the default page, editing that survives live updates.
  await page.getByRole("button", { name: "My pages" }).click();
  await page.getByLabel("Node name").fill("Test node");
  await page.getByRole("button", { name: "Start publishing" }).click();
  await page.getByText("ito created a welcome page for you").waitFor();
  await page.getByLabel("Your node's address").waitFor();
  await page.getByRole("button", { name: "Edit Welcome" }).click();
  const text = page.getByLabel("Page text");
  await text.click();
  await text.press("ControlOrMeta+End");
  await text.pressSequentially("\nTyped on a phone");
  await page.waitForTimeout(11_000); // one live update (every 10 s) while typing
  assert.equal(await page.evaluate(() => document.querySelector("ito-dashboard").shadowRoot.activeElement?.tagName), "TEXTAREA", "focus lost");
  assert.ok((await text.inputValue()).includes("Typed on a phone"), "text lost");
  await page.getByRole("button", { name: "Preview" }).click();
  await page.locator(".viewer.card").getByText("Typed on a phone").waitFor();
  await page.getByRole("button", { name: "Save and publish" }).click();
  await page.getByText("Saved and published").waitFor();
  await page.getByRole("button", { name: "New page" }).click();
  await page.getByLabel("Title (shown in your page list)").fill("Second");
  await page.getByLabel("Page text").fill("Second page");
  await page.getByRole("button", { name: "Save draft" }).click();
  await page.getByText("Draft saved").waitFor();
  await page.getByRole("button", { name: "Delete Second" }).click();
  await page.getByRole("button", { name: "Delete page" }).click();
  await page.getByText("Page deleted.").waitFor();
  assert.equal(await page.getByRole("button", { name: "Edit Second" }).count(), 0);
  // Layout: no sideways scrolling at this size.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert.ok(overflow <= 1, `horizontal overflow ${overflow}px`);
  assert.deepEqual(outside, [], "requests outside the dashboard");
  assert.deepEqual(problems, [], "console errors or dialogs");
  await page.screenshot({ path: `${process.env.SHOT_DIR || "."}/pages-${name}.png`, fullPage: false });
  console.log(`ok: ${name}`);
}

const sizes = { iphone: devices["iPhone 13"], ipad: devices["iPad Mini"], desktop: { viewport: { width: 1280, height: 900 } } };
const browser = await chromium.launch();
const context = await browser.newContext({ ...sizes[device], extraHTTPHeaders: { "X-Remote-User-Groups": "system-admin" } });
let failed = false;
try {
  await check(device, context);
} catch (error) {
  failed = true;
  console.error(`FAILED ${device}: ${error.message}`);
}
await browser.close();
process.exit(failed ? 1 : 0);
