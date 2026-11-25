// The pages render the jobs-source spec's own examples.
//
// `jobs_source.openapi.json` is the one agreement between the console's pages, a jobs
// source and qe's contract cases. tests/test_console_jobs_spec.py checks every example
// in it against its schema; this file renders those same examples through the shipped
// renderers, so a field the spec names and a page no longer reads, or the reverse,
// fails here instead of on the phone. The renderers are lifted from jobs.js, surface.js
// and board.js by name and run over a DOM small enough to read in full below.

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { extractFunction, evaluate, suite, check, done } from "./harness.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PKG = path.resolve(HERE, "../../packages/thalamus-console/src/thalamus_console");
const STATIC = path.join(PKG, "static");
const read = (f) => fs.readFileSync(path.join(STATIC, f), "utf8");
const jobs = read("jobs.js");
const surface = read("surface.js");
const board = read("board.js");
const spec = JSON.parse(fs.readFileSync(path.join(PKG, "jobs_source.openapi.json"), "utf8"));
const example = (name) => spec.components.schemas[name].examples[0];

// ---- a DOM just big enough for h() ----
class Node {}
class Text extends Node {
  constructor(s) { super(); this.data = String(s); }
  get textContent() { return this.data; }
}
class El extends Node {
  constructor(tag) {
    super();
    this.tagName = tag; this.children = []; this.attrs = {}; this.className = "";
    this.style = { setProperty: (k, v) => { this.style[k] = v; } };
  }
  appendChild(c) { this.children.push(c); return c; }
  replaceChildren(...c) { this.children = c; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener() {}
  remove() {}
  set textContent(s) { this.children = [new Text(s)]; }
  get textContent() { return this.children.map((c) => c.textContent).join(""); }
}
const document = {
  createElement: (t) => new El(t),
  createElementNS: (_, t) => new El(t),
  createTextNode: (s) => new Text(s),
  getElementById: () => null,
  body: new El("body"),
};
const constOf = (name, src) => {
  // Up to the `;` that ends a line, allowing a trailing `// comment` after it.
  const m = new RegExp(`^const ${name} = ([\\s\\S]*?);[ \\t]*(?://[^\\n]*)?$`, "m").exec(src);
  if (!m) throw new Error(`const ${name} not found`);
  return new Function(`return ${m[1]};`)();
};

const surfaceFns = ["h", "appendKids", "toneClass", "statusWord", "hashHue", "scopeHue", "switchEl", "toast", "findingCard"];
const jobsFns = ["listView", "bannerShown", "sameCommit", "jobRow", "link", "jobView", "runPicker", "stageItem", "progressBar", "jobActions",
  "armTwice", "historyView", "historyItem", "changeView", "gateCard", "diffCard", "changeFoot", "runView",
  "findingRow", "repoView", "columnWidths", "graphLayout", "routeEdge", "graphView", "graphNode", "laneView", "selectEl",
  "sharedItem", "commonIndent", "pickJob"];
const F = evaluate(
  [...surfaceFns.map((n) => extractFunction(n, surface)), ...jobsFns.map((n) => extractFunction(n, jobs))].join("\n"),
  [...surfaceFns, ...jobsFns],
  {
    document, Node, window: {}, location: { hash: "" },
    TONES: constOf("TONES", surface), PALETTE: constOf("PALETTE", surface), MAIN_HUE: constOf("MAIN_HUE", surface),
    RATINGS: constOf("RATINGS", surface), CANVAS: constOf("CANVAS", jobs), canvasState: constOf("canvasState", jobs),
    LANE: constOf("LANE", jobs),
    api: async () => ({}), apiPost: async () => ({}), route: () => {}, replayOnHead: () => {},
    setTimeout: () => 0, clearTimeout: () => {},
  },
);

// Every status word and every display line in an example must reach the page's text.
function words(obj, out = []) {
  if (Array.isArray(obj)) obj.forEach((x) => words(x, out));
  else if (obj && typeof obj === "object") {
    if (typeof obj.word === "string" && typeof obj.tone === "string") out.push(obj.word);
    for (const [k, v] of Object.entries(obj)) {
      if (["line", "title", "subject", "summary", "heading", "meta", "observation", "hidden"].includes(k) && typeof v === "string") out.push(v);
      words(v, out);
    }
  }
  return out;
}

function renders(name, node, data, skip = []) {
  const text = node.textContent;
  const missing = words(data).filter((w) => !skip.includes(w) && !text.includes(w));
  check(`${name}: every word and line in the spec's example is printed`, missing.length === 0,
    missing.slice(0, 3).join(" | "));
}

suite("jobs pages render the spec's examples");
renders("JobList (J1)", F.listView(example("JobList")), example("JobList"));
const job = example("Job");
// The run picker prints its own label ("run  <label>  on <version>"), and the pinned
// line belongs to the desktop inspector, not J2.
renders("Job (J2)", F.jobView(job, { job: job.id, params: {} }), job, [job.pinned.title, job.pinned.line]);
renders("History (J3)", F.historyView(example("History"), { job: "weekly-digest", params: {} }, true), example("History"));
renders("ChangeReceipt (J4)", F.changeView(example("ChangeReceipt")), example("ChangeReceipt"));
// A run's title is the page header (setChrome), not part of the view; a rejected
// finding is drawn as its headline and why it was rejected (J5), without the meta line.
const rejectedMeta = example("Run").findings.items.filter((x) => x.rejected).map((x) => x.meta);
renders("Run (J5)", F.runView(example("Run")), example("Run"), [example("Run").title, ...rejectedMeta]);
renders("Repo (J6)", F.repoView(example("Repo"), true), example("Repo"));
const graph = example("Graph");
const g = F.graphView(graph);
check("Graph (D1): every node's title is drawn", graph.nodes.every((n) => g.textContent.includes(n.title)));
const lane = F.laneView(graph.lane);
check("Graph (D1): every lane mark is drawn", graph.lane.jobs.every((j) => j.marks.every((m) => lane.textContent.includes(m.text))));

suite("the tone vocabulary is the spec's");
const specTones = spec.components.schemas.Tone.enum;
const pageTones = constOf("TONES", surface);
check("the page knows exactly the spec's tones", JSON.stringify([...specTones].sort()) === JSON.stringify([...pageTones].sort()),
  `spec ${specTones} · page ${pageTones}`);
for (const t of specTones) {
  check(`surface.css colours tone ${t}`, read("surface.css").includes(`.tone-${t} {`));
}

suite("board renders the spec's eval example");
const B = evaluate(extractFunction("evalModel", board) + "\n" + extractFunction("barsModel", board) + "\n" +
  extractFunction("lineModel", board), ["evalModel"], {});
const num = B.evalModel("number", example("Eval"));
check("a number keeps its value and comparison", num.value === example("Eval").value && num.compare === example("Eval").compare);

done();
