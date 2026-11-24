// The jobs pages' pure parts: routing, where the back chevron goes, D1's layout, and
// the rule that a status reaches the page as the source's word and never as markup.
//
// The source composes every word (`{word, tone}`); the page prints it. So the tests
// that matter here are the ones that hold the page to printing: a tone it does not
// know still renders the word, and no renderer reaches for innerHTML.

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import {
  extractFunction, evaluate, suite, check, lacksMatch, stripComments, done,
} from "./harness.mjs";

// A top-level `const NAME = ...;` from the source, evaluated.
function constOf(name, src) {
  const m = new RegExp(`^const ${name} = ([\\s\\S]*?);[ \\t]*(?://[^\\n]*)?$`, "m").exec(src);
  if (!m) throw new Error(`const ${name} not found`);
  return new Function(`return ${m[1]};`)();
}

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(HERE, "../../packages/thalamus-console/src/thalamus_console/static");
const jobs = fs.readFileSync(path.join(STATIC, "jobs.js"), "utf8");
const surface = fs.readFileSync(path.join(STATIC, "surface.js"), "utf8");

const env = evaluate(
  ["parseRoute", "backTarget", "columnWidths", "graphLayout", "routeEdge"].map((n) => extractFunction(n, jobs)).join("\n"),
  ["parseRoute", "backTarget", "graphLayout", "routeEdge"],
  { CANVAS: constOf("CANVAS", jobs) },
);
const { parseRoute, backTarget, graphLayout, routeEdge } = env;

suite("routes");
check("empty hash is the list", parseRoute("").screen === "list");
check("a job", parseRoute("#/job/weekly-digest").job === "weekly-digest");
check("a job's run param", parseRoute("#/job/weekly-digest?run=abc").params.run === "abc");
check("history beats job", parseRoute("#/job/x/history").screen === "history");
check("a change", parseRoute("#/change/43ade4c").sha === "43ade4c");
check("a run", parseRoute("#/run/r1").run === "r1");
check("repo", parseRoute("#/repo?all=1").params.all === "1");
check("a commit", parseRoute("#/commit/5f1f622").screen === "commit");
check("a stage job id survives encoding",
  parseRoute("#/job/" + encodeURIComponent("weekly-digest:plan")).job === "weekly-digest:plan");
check("unknown routes fall back to the list", parseRoute("#/nonsense").screen === "list");

suite("back chevron goes up the tree, never into history");
check("list → roster", backTarget({ screen: "list" }) === "./");
check("job → list", backTarget({ screen: "job", job: "a" }) === "#/");
check("history → its job", backTarget({ screen: "history", job: "a b" }) === "#/job/a%20b");
check("change → its job when known", backTarget({ screen: "change" }, { job: "a" }) === "#/job/a");
check("change → list when not", backTarget({ screen: "change" }) === "#/");
check("commit → repo", backTarget({ screen: "commit" }) === "#/repo");

suite("D1 layout");
const C = constOf("CANVAS", jobs);
const { boxes } = graphLayout([
  { id: "a", col: 0, row: 0 },
  { id: "b", col: 4, row: 3, job: "x", title: "career-evidence-staleness", stages: [{ name: "plan" }, { name: "research" }] },
], 7);
check("columns before a wide one keep the plain pitch", boxes.b.x - boxes.a.x === 4 * C.colW);
check("row pitch", boxes.b.y - boxes.a.y === 3 * C.rowH);
check("a staged job grows to hold its stages", boxes.b.h > boxes.a.h);
check("a staged or long-named job's column is the comp's wide one", boxes.b.w === C.wideNodeW);

// Points along an orthogonal or cubic path: the corners, and for a cubic its two ends.
function corners(d) {
  const pts = [];
  let x = 0, y = 0;
  for (const [, cmd, args] of d.matchAll(/([MHVC])([^MHVC]*)/g)) {
    const n = args.trim().split(/[ ,]+/).map(Number);
    if (cmd === "M") { [x, y] = n; } else if (cmd === "H") { x = n[0]; } else if (cmd === "V") { y = n[0]; }
    else if (cmd === "C") { [x, y] = n.slice(4, 6); }
    pts.push([x, y]);
  }
  return pts;
}
function crosses(d, box) {
  const pts = corners(d);
  for (let i = 1; i < pts.length; i++) {
    const [ax, ay] = pts[i - 1], [bx, by] = pts[i];
    const x0 = Math.min(ax, bx), x1 = Math.max(ax, bx), y0 = Math.min(ay, by), y1 = Math.max(ay, by);
    if (x0 < box.x + box.w && x1 > box.x && y0 < box.y + box.h && y1 > box.y) return true;
  }
  return false;
}
// D1's case: a table two columns left of a model job one row up, with a planned node
// in the column between, on the straight line's way.
const L = graphLayout([
  { id: "games", col: 2, row: 1 }, { id: "ghost", col: 3, row: 0 }, { id: "weekly", col: 3, row: 1 },
  { id: "coach", col: 4, row: 0, job: "coach", title: "coach" },
], 7).boxes;
const route = routeEdge(L.games, L.coach, [L.ghost, L.weekly]);
check("an edge leaves the right edge of its source", route.startsWith(`M${L.games.x + L.games.w},`));
check("and ends on the left edge of its target", corners(route).at(-1)[0] === L.coach.x);
check("an edge crosses no other node", !crosses(route, L.ghost) && !crosses(route, L.weekly), route);
const near = routeEdge(L.weekly, L.coach, [L.ghost, L.games]);
check("an unobstructed edge between neighbouring columns is a cubic", near.includes(" C"));

suite("the banner hides once its receipt has been read on this device");
const B = evaluate(extractFunction("sameCommit", jobs) + "\n" + extractFunction("bannerShown", jobs),
  ["bannerShown"], {});
const banner = { title: "t", line: "l", change: "43ade4c" };
check("shown when nothing was read", B.bannerShown(banner, []) === true);
check("hidden once that commit was read", B.bannerShown(banner, ["43ade4c"]) === false);
check("an abbreviation of the same commit counts", B.bannerShown(banner, ["43ade4cc6e33"]) === false);
check("another commit's receipt does not hide it", B.bannerShown(banner, ["5f1f622"]) === true);
check("no banner, nothing shown", B.bannerShown(null, []) === false);

suite("tones and words");
const tone = evaluate(extractFunction("toneClass", surface), ["toneClass"],
  { TONES: ["ok", "danger", "pending", "muted", "accent"] });
check("a known tone maps to its class", tone.toneClass("danger") === "tone-danger");
check("an unknown tone still renders, muted", tone.toneClass("brand-new") === "tone-muted");

suite("no data path is markup");
for (const [name, src] of [["jobs.js", jobs], ["surface.js", surface]]) {
  lacksMatch(`${name} never assigns innerHTML`, stripComments(src), /\.innerHTML\s*=|insertAdjacentHTML|outerHTML\s*=/);
}
// The page prints the source's word; it does not branch on what the word says.
lacksMatch("jobs.js never compares a status word", stripComments(jobs), /\.word\s*===?|===?\s*[a-z.]*\.word\b/);

done();
