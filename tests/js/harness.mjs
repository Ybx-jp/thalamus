// Test harness for the console's client code.
//
// `app.js` is a classic browser script: it touches `document` at load, so node
// cannot import it and a DOM fake big enough to load it would be a larger fiction
// than the tests. Instead this lifts named functions out of the source text and
// evaluates them with the few globals they actually use injected as parameters.
// What is under test is therefore the shipped source, not a copy of it — the cost
// is that renaming a function breaks extraction, which surfaces as a loud failure
// rather than a silently-passing test.
//
// Run one file directly (`node tests/js/markdown.test.mjs`) or all of them through
// pytest, which shells out here (`tests/test_console_js.py`).

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const APP_JS = path.resolve(HERE, "../../src/thalamus/console/static/app.js");

export function readApp() {
  return fs.readFileSync(APP_JS, "utf8");
}

// Brace matching that steps over comments and string literals, so a `}` inside a
// message or a URL cannot end a function early. Regex literals are not tracked:
// the `{n,m}` quantifiers this file uses are balanced, and an unbalanced brace
// inside a regex would show up immediately as an extraction failure.
function matchBraces(src, from) {
  let depth = 0, i = src.indexOf("{", from);
  if (i < 0) throw new Error("no block found");
  let quote = null, comment = null;
  for (; i < src.length; i++) {
    const c = src[i], next = src[i + 1];
    if (comment === "line") { if (c === "\n") comment = null; continue; }
    if (comment === "block") { if (c === "*" && next === "/") { comment = null; i++; } continue; }
    if (quote) {
      if (c === "\\") { i++; continue; }
      if (c === quote) quote = null;
      continue;
    }
    if (c === "/" && next === "/") { comment = "line"; i++; continue; }
    if (c === "/" && next === "*") { comment = "block"; i++; continue; }
    if (c === '"' || c === "'" || c === "`") { quote = c; continue; }
    if (c === "{") depth++;
    else if (c === "}" && --depth === 0) return i + 1;
  }
  throw new Error("unbalanced braces");
}

/** Source text of `function <name>(...) { ... }`, exactly as shipped. */
export function extractFunction(name, src = readApp()) {
  const re = new RegExp(`(?:^|\\n)(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = re.exec(src);
  if (!m) throw new Error(`function ${name}() not found in app.js`);
  const start = m.index + (m[0].startsWith("\n") ? 1 : 0);
  return src.slice(start, matchBraces(src, start));
}

/** Source text from `startMark` up to (not including) `endMark`. */
export function extractRegion(startMark, endMark, src = readApp()) {
  const a = src.indexOf(startMark);
  if (a < 0) throw new Error(`region start not found: ${startMark}`);
  const b = src.indexOf(endMark, a);
  if (b < 0) throw new Error(`region end not found: ${endMark}`);
  return src.slice(a, b);
}

/**
 * Evaluate extracted source with globals injected, and hand back the names asked
 * for. `globals` is an object; its keys become parameters in that scope.
 */
export function evaluate(source, exportNames, globals = {}) {
  const keys = Object.keys(globals);
  const body = `${source}\nreturn {${exportNames.join(",")}};`;
  return new Function(...keys, body)(...keys.map((k) => globals[k]));
}

// The console's own escapeHtml, which the extracted renderers close over.
export const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---- a very small runner ----

let passed = 0;
const failures = [];
let suiteName = "";

export function suite(name) {
  suiteName = name;
  console.log(`\n${name}`);
}

export function check(name, ok, detail = "") {
  if (ok) {
    passed++;
    console.log(`  ok   ${name}`);
  } else {
    failures.push(`${suiteName} :: ${name}${detail ? `\n       ${detail}` : ""}`);
    console.log(`  FAIL ${name}${detail ? `\n       ${detail}` : ""}`);
  }
}

/** Assert `haystack` contains `needle`, showing the actual output when it doesn't. */
export function contains(name, haystack, needle) {
  check(name, haystack.includes(needle), haystack.includes(needle) ? "" : `got: ${haystack}`);
}

export function lacks(name, haystack, needle) {
  check(name, !haystack.includes(needle), haystack.includes(needle) ? `got: ${haystack}` : "");
}

/**
 * Assert no part of `haystack` matches `re`, naming the offending line when one does.
 *
 * For guards that bind to a shape rather than a word: the whole text is tested, so a
 * pattern may span lines, and the report gives the line number and the matched text
 * instead of dumping the source. Pass a regex without `g` — `lastIndex` on a shared
 * literal would make the second call lie.
 */
export function lacksMatch(name, haystack, re) {
  const m = re.exec(haystack);
  if (!m) return check(name, true);
  const line = haystack.slice(0, m.index).split("\n").length;
  check(name, false, `line ${line}: ${m[0].trim()}`);
}

/**
 * Blank out whole-line comments, keeping line numbers intact.
 *
 * A guard on what the code *does* must not fire on a comment that quotes the very
 * shape it forbids in order to explain the ban. Only comments occupying a whole line
 * are removed: deciding whether a trailing `//` sits inside a string needs a real JS
 * parser, and guessing wrong there would blind a guard rather than merely tighten it.
 * Trailing comments stay in the scanned text — the failure names the line, so a
 * comment that trips one is obvious and one edit away.
 */
export function stripComments(src) {
  const out = [];
  let inBlock = false;
  for (const line of src.split("\n")) {
    const t = line.trim();
    if (inBlock) {
      out.push("");
      if (t.includes("*/")) inBlock = false;
    } else if (t.startsWith("/*")) {
      out.push("");
      if (!t.includes("*/")) inBlock = true;
    } else {
      out.push(t.startsWith("//") ? "" : line);
    }
  }
  return out.join("\n");
}

export function done() {
  console.log(`\n${passed} passed, ${failures.length} failed`);
  if (failures.length) {
    console.log("\nfailures:\n" + failures.map((f) => "  - " + f).join("\n"));
    process.exit(1);
  }
  process.exit(0);
}
