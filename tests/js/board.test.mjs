// The board page (static/board.js): the pure parts — how an eval result becomes a
// render model, how the grid places and pushes widgets, and how the app-widget host
// routes and gates messages from sandboxed frames. The host's rule is that a message
// is identified by the window that sent it and by nothing it says about itself, so
// that is asserted directly rather than through a browser.

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import {
  extractFunction, evaluate, stripComments,
  suite, check, lacksMatch, done,
} from "./harness.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(HERE, "../../packages/thalamus-console/src/thalamus_console/static");
const src = fs.readFileSync(path.join(STATIC, "board.js"), "utf8");
const html = fs.readFileSync(path.join(STATIC, "board.html"), "utf8");

const NAMES = ["overlaps", "clampBox", "placeWidget", "firstFreeSlot", "normalizeLayout", "phoneOrder", "phoneFlow",
  "cellAt", "barsModel", "lineModel", "evalModel", "cardTitle", "windowLabel", "compareLabel", "writeGate",
  "routeAppMessage"];
const F = evaluate(NAMES.map((n) => extractFunction(n, src)).join("\n"), NAMES);

const box = (id, x, y, w, h) => ({ id, x, y, w, h });
const at = (ws, id) => { const o = ws.find((w) => w.id === id); return [o.x, o.y, o.w, o.h].join(","); };
const anyOverlap = (ws) => ws.some((a, i) => ws.some((b, j) => i < j && F.overlaps(a, b)));

suite("board — grid boxes");
check("a box is clamped to 4 columns and 3 rows", JSON.stringify(F.clampBox({ x: 3, y: -2, w: 9, h: 7 }, 4, 3))
  === JSON.stringify({ x: 0, y: 0, w: 4, h: 3 }));
check("a box past the right edge is pulled back inside", at([Object.assign({ id: "a" }, F.clampBox({ x: 3, y: 1, w: 2, h: 1 }, 4, 3))], "a") === "2,1,2,1");
check("w and h below 1 become 1", at([Object.assign({ id: "a" }, F.clampBox({ x: 0, y: 0, w: 0, h: -1 }, 4, 3))], "a") === "0,0,1,1");
check("touching edges do not overlap", !F.overlaps(box("a", 0, 0, 1, 2), box("b", 1, 0, 1, 2))
  && !F.overlaps(box("a", 0, 0, 2, 2), box("b", 0, 2, 2, 1)));
check("a shared cell overlaps", F.overlaps(box("a", 0, 0, 2, 2), box("b", 1, 1, 1, 1)));

suite("board — placing pushes down, never sideways, never up");
{
  const ws = [box("a", 0, 0, 1, 2), box("b", 1, 0, 2, 2), box("c", 3, 0, 1, 2), box("d", 0, 2, 2, 3)];
  const moved = F.placeWidget(ws, "a", 1, 0, 1, 2, 4, 3);
  check("the moved widget takes the cell it was dropped on", at(moved, "a") === "1,0,1,2");
  check("what it landed on goes below it", at(moved, "b") === "1,2,2,2");
  check("the push cascades to what that lands on", at(moved, "d") === "0,4,2,3");
  check("a widget it did not touch stays", at(moved, "c") === "3,0,1,2");
  check("nothing overlaps afterwards", !anyOverlap(moved));
  check("the input layout is untouched", at(ws, "a") === "0,0,1,2" && at(ws, "b") === "1,0,2,2");
  const grown = F.placeWidget(ws, "c", 3, 0, 1, 3, 4, 3);
  check("a resize pushes too", at(grown, "c") === "3,0,1,3" && !anyOverlap(grown));
  const wide = F.placeWidget(ws, "a", 0, 0, 4, 1, 4, 3);
  check("a full-width resize pushes the whole row", !anyOverlap(wide) && at(wide, "b") === "1,1,2,2");
  check("an unknown id changes nothing", JSON.stringify(F.placeWidget(ws, "zz", 0, 0, 1, 1, 4, 3)) === JSON.stringify(ws));
}

suite("board — free slots and stored layouts");
{
  const ws = [box("a", 0, 0, 1, 2), box("b", 1, 0, 2, 2), box("c", 3, 0, 1, 2)];
  check("the first free slot is the first row with room", JSON.stringify(F.firstFreeSlot(ws, 2, 2, 4)) === '{"x":0,"y":2}');
  check("a 1-wide slot finds a hole beside a 1-wide widget",
    JSON.stringify(F.firstFreeSlot([box("a", 0, 0, 1, 1)], 1, 1, 4)) === '{"x":1,"y":0}');
  const fixed = F.normalizeLayout([box("a", 0, 0, 2, 2), box("b", 1, 1, 2, 2), { id: "c", kind: "note", w: 1, h: 1 }], 4, 3);
  check("an overlapping stored layout is settled", !anyOverlap(fixed));
  check("a widget with no box is given one", Number.isFinite(fixed[2].x) && Number.isFinite(fixed[2].y));
  check("a widget's other fields survive normalizing", fixed[2].kind === "note");
  check("the phone reads boxes row by row, left to right",
    F.phoneOrder([box("x", 3, 0, 1, 2), box("y", 0, 2, 2, 3), box("z", 0, 0, 1, 2), box("w", 1, 0, 2, 2)]).join("") === "zwxy");
  // B1: two narrow numbers share a row; a narrow card with no narrow neighbour (the
  // Controls card after a wide inbox) takes the whole row.
  const flow = F.phoneFlow([box("blitz", 0, 0, 1, 2), box("steps", 3, 0, 1, 2), box("series", 1, 0, 2, 2),
    box("inbox", 0, 2, 2, 3), box("controls", 2, 2, 1, 3)]);
  const spans = flow.spans;
  check("two narrow cards of one desktop row share a phone row", spans.blitz === 1 && spans.steps === 1
    && flow.order.join(",") === "blitz,steps,series,inbox,controls", flow.order.join(","));
  check("a narrow card alone on its row stretches to full width", spans.controls === 2, JSON.stringify(spans));
  check("a wide card stays full width", spans.inbox === 2);
}

suite("board — the cell under a pointer");
{
  const rect = { left: 100, top: 50, width: 4 * 100 + 3 * 16 };   // 100 px columns, 16 px gaps
  check("the top-left cell", JSON.stringify(F.cellAt(110, 60, rect, 4, 72, 16)) === '{"x":0,"y":0}');
  check("the second column starts past the first gap", F.cellAt(100 + 116 + 1, 60, rect, 4, 72, 16).x === 1);
  check("the third row", F.cellAt(110, 50 + 2 * 88 + 5, rect, 4, 72, 16).y === 2);
  check("left of the grid clamps to column 0", F.cellAt(0, 60, rect, 4, 72, 16).x === 0);
  check("right of the grid clamps to the last column", F.cellAt(9999, 60, rect, 4, 72, 16).x === 3);
}

suite("board — eval result to render model");
{
  const n = F.evalModel("number", { value: "7 of 16", compare: "previous 6 weeks: 10 of 64", period: "W47", foot: "chess_weekly" });
  check("a number prints the source's value verbatim", n.value === "7 of 16" && n.compare === "previous 6 weeks: 10 of 64");
  check("the edit-mode footer names the table", n.foot === "chess_weekly");
  check("a result with no source line has none", n.source === null);
  const src = F.evalModel("number", { value: "7", foot: "chess_weekly", source: { text: "from chess.com games", job: "chess-sync" } });
  check("the view-mode source keeps its words and its job", src.source.text === "from chess.com games" && src.source.job === "chess-sync");
  check("a source with no job links nowhere", F.evalModel("number", { source: { text: "from job runs", job: null } }).source.job === null);
  check("the title is the widget's, then the period", F.cardTitle("Blitz lost on time", n.period, "Number")
    === "Blitz lost on time · W47");
  check("no period, no suffix", F.cardTitle("Steps today", null, "Number") === "Steps today");
  check("an untitled widget falls back to its kind", F.cardTitle("", null, "Number") === "Number");
  check("a null compare stays null", F.evalModel("number", { value: "742", compare: null }).compare === null);
  const b = F.evalModel("series", { bars: [{ label: "W41", value: 0, text: "0" }, { label: "W42", value: 3 }, { label: "W47", value: 7, text: "7" }] });
  check("counts draw as bars", b.chart === "bars" && b.bars.length === 3);
  check("bars scale to the tallest", b.bars[2].frac === 1 && Math.abs(b.bars[1].frac - 3 / 7) < 1e-9 && b.bars[0].frac === 0);
  check("every bar carries its value as text", b.bars[1].text === "3" && b.bars[0].text === "0");
  check("only the last bar is the current one", b.bars.map((x) => x.current).join() === "false,false,true");
  const l = F.evalModel("series", { line: [{ label: "Jun 2025", value: 11.8, text: "11.8%" }, { label: "Jul", value: 14 },
    { label: "Nov 2026", value: 26.7, text: "26.7%" }] });
  check("shares draw as a line", l.chart === "line" && l.line.points.length === 3);
  check("the line's ends are labelled with the source's text", l.line.first.text === "11.8%" && l.line.last.text === "26.7%"
    && l.line.first.label === "Jun 2025" && l.line.last.label === "Nov 2026");
  check("gridlines run from zero to above the top value", l.line.grid[0] === 1 && Math.abs(l.line.grid[3]) < 1e-9);
  check("the top value sits below the top gridline", l.line.points[2].fy > 0 && Math.abs(l.line.points[2].fy - (1 - 1 / 1.1)) < 1e-9);
  const t = F.evalModel("tail", { rows: [{ time: "10:55", source: "usage", kind: "app_resumed", app: "com.example" }] });
  check("the tail keeps time, source and kind and drops everything else",
    JSON.stringify(t.rows[0]) === '{"time":"10:55","source":"usage","kind":"app_resumed"}');
  const i = F.evalModel("inbox", { more: "3 more to rate", items: [
    { id: "f1", meta: "Career discovery · blind spot · still open", title: "t", observation: "o", label: "useful",
      source: { text: "evidence", url: null, run: "r1" } },
    { id: "f2", meta: "Resume library check · entry out of date", title: null, observation: "only an observation",
      source: { text: "pull #359", url: "https://example.com/o/r/pull/359", run: null } }, null] });
  check("inbox items keep their rating or null", i.items[0].label === "useful" && i.items[1].label === null);
  check("an inbox item keeps meta, title, observation and source verbatim", i.items[0].meta === "Career discovery · blind spot · still open"
    && i.items[0].title === "t" && i.items[0].source.run === "r1" && i.items[1].source.url.endsWith("/pull/359"));
  check("an untitled finding keeps a null title, so its observation is the headline", i.items[1].title === null
    && i.items[1].observation === "only an observation");
  check("a malformed item is dropped", i.items.length === 2);
  check("the inbox keeps how many are left to rate", i.more === "3 more to rate");
  const c = F.evalModel("control", { items: [{ type: "mute", scope: "career", label: "career notifications", line: "muted until Dec 7", on: false },
    { type: "run", job: "chess-weekly-review", label: "Run chess review now" },
    { type: "auto_apply", job: "career-discover:plan", label: "auto-apply career-discover:plan", on: true }, { type: "shell", cmd: "rm" }] });
  check("controls keep switches, run buttons and auto-apply only", c.items.length === 3 && c.items[0].on === false
    && c.items[1].job === "chess-weekly-review" && c.items[2].on === true);
  check("a note is its text alone", F.evalModel("note", { text: "q", line: "ignored" }).text === "q"
    && !("line" in F.evalModel("note", { text: "q", line: "ignored" })));
  check("a table keeps columns and rows", F.evalModel("table", { columns: ["job"], rows: [["a", 1]] }).rows[0].join() === "a,1");
  const app = F.evalModel("app", { app: "chess-positions",
    tile: { foot: "app · chess positions", source: { text: "from Sunday's chess review", job: "chess-coach" } } });
  check("an app tile's footers come from its tile", app.foot === "app · chess positions"
    && app.source.text === "from Sunday's chess review" && app.source.job === "chess-coach");
  check("an unknown kind renders as unknown, not as a crash", F.evalModel("gauge", {}).unknown === true);
  check("a missing result is survivable", F.evalModel("series", null).bars.length === 0);
}

suite("board — app writes: 4 KB and one a second");
{
  check("a small row passes", F.writeGate(null, 1000, { n: 2, move: "Qd4" }, 4096, 1000).ok);
  const big = F.writeGate(null, 1000, { pad: "x".repeat(5000) }, 4096, 1000);
  check("a row over the cap is refused with its size", !big.ok && /5010 bytes/.test(big.error));
  // 2050 two-byte characters: 2058 characters of JSON, 4108 bytes.
  const multibyte = F.writeGate(null, 1000, { s: "é".repeat(2050) }, 4096, 1000);
  check("the cap counts bytes, not characters", !multibyte.ok && /4108 bytes/.test(multibyte.error));
  check("a second write inside a second is refused", !F.writeGate(1000, 1999, { n: 1 }, 4096, 1000).ok);
  check("a write a second later passes", F.writeGate(1000, 2000, { n: 1 }, 4096, 1000).ok);
  check("a non-object row is refused", !F.writeGate(null, 0, "row", 4096, 1000).ok && !F.writeGate(null, 0, [1], 4096, 1000).ok
    && !F.writeGate(null, 0, null, 4096, 1000).ok);
}

suite("board — app messages are routed by source only");
{
  const tileWin = { name: "tile" }, fullWin = { name: "full" }, stranger = { name: "other" };
  const reg = new Map([[tileWin, { widgetId: "w1", app: "chess-positions", mode: "tile" }],
                       [fullWin, { widgetId: "w1", app: "chess-positions", mode: "full" }]]);
  check("a window the host did not register is dropped", F.routeAppMessage(reg, stranger, { thalamus: "app/ready" }) === null);
  const spoof = F.routeAppMessage(reg, tileWin, { thalamus: "app/write", id: "x", row: {}, app: "other-app", widget: "w9" });
  check("an app or widget named in the body is ignored", spoof.entry.app === "chess-positions" && spoof.entry.widgetId === "w1");
  check("ready asks for data", F.routeAppMessage(reg, tileWin, { thalamus: "app/ready" }).act === "data");
  check("a tile may open", F.routeAppMessage(reg, tileWin, { thalamus: "app/open" }).act === "open");
  check("a tile may not close", F.routeAppMessage(reg, tileWin, { thalamus: "app/close" }) === null);
  check("the full-screen frame may close", F.routeAppMessage(reg, fullWin, { thalamus: "app/close" }).act === "close");
  check("the full-screen frame may not open another", F.routeAppMessage(reg, fullWin, { thalamus: "app/open" }) === null);
  check("a resize is clamped", F.routeAppMessage(reg, tileWin, { thalamus: "app/resize", height: 99999 }).height === 640);
  check("a write echoes the app's own id", F.routeAppMessage(reg, tileWin, { thalamus: "app/write", id: "c1", row: { n: 1 } }).id === "c1");
  check("an oversized id is not echoed", F.routeAppMessage(reg, tileWin, { thalamus: "app/write", id: "x".repeat(65), row: {} }).id === null);
  check("a non-protocol message is dropped", F.routeAppMessage(reg, tileWin, "hello") === null
    && F.routeAppMessage(reg, tileWin, { thalamus: "app/eval" }) === null);
}

suite("board — editor words for the source's enums");
check("current week reads as this week", F.windowLabel("current", "week") === "this week");
check("current day reads as today", F.windowLabel("current", "day") === "today");
check("all reads as all time", F.windowLabel("all", "month") === "all time");
check("an unknown window prints its id", F.windowLabel("rolling", "week") === "rolling");
check("compare 6 weeks", F.compareLabel(6, "week") === "previous 6 weeks, summed");
check("compare 1 month is singular", F.compareLabel(1, "month") === "previous 1 month, summed");
check("no compare", F.compareLabel(null, "week") === "nothing");

suite("board — the sandbox and the page policy");
{
  const code = stripComments(src);
  check("app frames are sandboxed to allow-scripts alone", /sandbox:\s*"allow-scripts"/.test(code));
  lacksMatch("nothing grants allow-same-origin", code, /allow-same-origin/);
  lacksMatch("nothing writes markup from a string", code, /\.(inner|outer)HTML\s*=|insertAdjacentHTML/);
  check("app frames send no referrer", /referrerpolicy:\s*"no-referrer"/.test(code));
  check("the page carries the CSP with frame-src 'self'",
    /http-equiv="Content-Security-Policy"[\s\S]*?frame-src 'self'/.test(html) && /script-src 'self';/.test(html));
  check("the host answers with targetOrigin \"*\" only to a registered window",
    /function post\(win, msg\)/.test(code) && /routeAppMessage\(apps, ev\.source, ev\.data\)/.test(code));
}

done();
