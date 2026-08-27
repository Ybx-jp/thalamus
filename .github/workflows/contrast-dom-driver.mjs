// Drives tests/js/contrast-dom.js across the console's views and reports per view.
//
// The walker measures what is on screen, so coverage is per view and a clean report is
// a claim about the views actually rendered. This drives each view, states its element
// count with its verdict, and treats a view that rendered too little as a failure —
// because zero failures over zero elements reads exactly like a passing surface.
//
// `minElements` is a floor on the denominator, not a target. It is set well below what
// each view renders when it works, so it fires on "this view did not open" rather than
// on ordinary variation in roster size.

import { readFileSync } from "node:fs";
import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8378/";
const WALKER = readFileSync("tests/js/contrast-dom.js", "utf8");
const STRICT = process.env.STRICT_VIEWS !== "false";

/** Each view, how to reach it, and the least it may render and still count as rendered. */
const VIEWS = [
  {
    name: "roster",
    minElements: 20,
    open: async () => {},
  },
  {
    name: "opened-row",
    minElements: 25,
    // Opening a row is what paints `--panel` under text and puts chips on `--panel-hi`,
    // which is where the two tightest pairs on this surface live.
    open: async (page) => {
      await page.locator(".srow, .chan-tab").first().click({ timeout: 5000 });
      await page.waitForTimeout(600);
    },
  },
  {
    name: "read-view",
    minElements: 15,
    // The view the first manual run never measured, and the one the compounding
    // defect lived in: `.rd-side` x `.rd-thinking` x `.rd-name` is reachable only
    // where a subagent's tool calls are rendered.
    // `#view-toggle` by id, not `.viewcap` by class. `.viewcap` is shared with
    // `#say-toggle`, which sits earlier in index.html and ships `hidden` — it is
    // opt-in per device. `.first()` therefore resolved to a permanently invisible
    // button, and Playwright waited out its actionability timeout rather than
    // reporting no match, so this view had never been measured on any run.
    //
    // No `if (count())` guard around the click either: a missing toggle is this
    // walker failing to reach the view it exists for, and skipping the click
    // silently would open the same hole one level up.
    open: async (page) => {
      await page.locator("#view-toggle").click({ timeout: 5000 });
      await page.waitForTimeout(800);
    },
  },
];

const problems = [];
const summary = [];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 430, height: 932 } });

page.on("console", (m) => {
  if (m.type() === "error") problems.push(`page console error: ${m.text()}`);
});

for (const view of VIEWS) {
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);

  try {
    await view.open(page);
  } catch (e) {
    problems.push(`${view.name}: could not be opened — ${e.message.split("\n")[0]}`);
    summary.push({ view: view.name, measured: 0, failures: "not opened" });
    continue;
  }

  await page.addScriptTag({ content: WALKER });

  // The self-check first, always. A clean report from a broken checker is the most
  // expensive output here, and the checker has two documented ways to be silently
  // wrong: reading a transparent background as opaque, and failing to compound
  // `opacity` down the ancestor chain.
  const selfCheck = await page.evaluate(() => window.contrastSelfCheck());
  if (selfCheck.length) {
    problems.push(`${view.name}: the checker itself is wrong — ${selfCheck.join("; ")}`);
    summary.push({ view: view.name, measured: 0, failures: "checker unsound" });
    continue;
  }

  const measured = await page.evaluate(() => window.contrastMeasured());
  const failures = await page.evaluate(() => window.contrastReport());

  await page.screenshot({ path: `/tmp/contrast-${view.name}.png`, fullPage: true });

  // The denominator assertion. A view that rendered nothing produces an empty failure
  // list, which is the same output a flawless view produces.
  if (measured < view.minElements) {
    const note =
      `${view.name}: measured ${measured} text elements, below the ${view.minElements} ` +
      `this view renders when it opens — a clean report over this few is not evidence ` +
      `the view is legible, only that it was not there`;
    if (STRICT) problems.push(note);
    else console.log(`WARNING ${note}`);
  }

  for (const f of failures) {
    problems.push(
      `${view.name}: ${f.ratio}:1 (floor ${f.floor}) at ${f.where} — "${f.text}"` +
      (f.effectiveAlpha < 1 ? `  [effective alpha ${f.effectiveAlpha}]` : ""));
  }

  summary.push({ view: view.name, measured, failures: failures.length });
}

await browser.close();

console.log("\n--- coverage, stated with every verdict ---");
for (const row of summary) {
  console.log(`  ${String(row.view).padEnd(12)} measured=${String(row.measured).padEnd(5)} failures=${row.failures}`);
}
const total = summary.reduce((n, r) => n + (Number(r.measured) || 0), 0);
console.log(`  total elements measured across ${summary.length} views: ${total}`);

if (problems.length) {
  console.log("\n--- problems ---");
  for (const p of problems) console.log(`  ${p}`);
  console.log(`\n${problems.length} problem(s).`);
  process.exit(1);
}

console.log(`\nno element below floor, over ${total} measured. Coverage is these ` +
            `${summary.length} views and no others.`);
