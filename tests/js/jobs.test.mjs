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

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(HERE, "../../packages/thalamus-console/src/thalamus_console/static");
const jobs = fs.readFileSync(path.join(STATIC, "jobs.js"), "utf8");
const surface = fs.readFileSync(path.join(STATIC, "surface.js"), "utf8");

const env = evaluate(
  ["parseRoute", "backTarget", "graphLayout", "edgePath"].map((n) => extractFunction(n, jobs)).join("\n"),
  ["parseRoute", "backTarget", "graphLayout", "edgePath"],
  { CANVAS: { colW: 142, nodeW: 128, nodeH: 56, rowH: 120, top: 44, left: 16 } },
);
const { parseRoute, backTarget, graphLayout, edgePath } = env;

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
const boxes = graphLayout([
  { id: "a", col: 0, row: 0 },
  { id: "b", col: 4, row: 3, stages: [{ name: "plan" }, { name: "research" }, { name: "assess" }] },
]);
check("column pitch", boxes.b.x - boxes.a.x === 4 * 142);
check("row pitch", boxes.b.y - boxes.a.y === 3 * 120);
check("a staged job grows to hold its stages", boxes.b.h > boxes.a.h && boxes.b.w > boxes.a.w);
const d = edgePath(boxes.a, boxes.b);
check("an edge leaves the right edge of its source", d.startsWith(`M${boxes.a.x + boxes.a.w},`));
check("and ends on the left edge of its target", d.includes(` ${boxes.b.x},`));

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
