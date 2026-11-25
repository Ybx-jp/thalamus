// The board: widgets the operator pins over what his jobs measure (Penpot B1–B4, D2).
//
// The jobs source reduces and this page renders. A widget is a kind plus a binding;
// the page asks the source to evaluate each one (`POST board/eval`) and draws the
// result. It never computes a number, never decides a status, and never branches on a
// word the source sent — every word on a widget is the source's, printed verbatim.
// The wire shapes are scratchpad/contract.md §Board and §App widgets, mirrored in
// docs/console.md.
//
// Layout model: a widget's x, y, w, h are cells of the DESKTOP grid (4 columns, w 1–4,
// h 1–3). The phone does not have a layout of its own; it reads the same boxes in
// row-major order and flows them two columns wide (see `phoneOrder`), so one saved
// layout serves both and editing on either moves the same widgets.
"use strict";

const COLS = 4;
const MAX_H = 3;
const ROW_PX = 72;          // one grid row; h2 = 160 px and h3 = 248 px, D2's two card heights
const GAP_PX = 16;
const WRITE_CAP_BYTES = 4096;
const WRITE_MIN_MS = 1000;
const APP_ID = /^[A-Za-z0-9._-]+$/;
const DESKTOP = window.matchMedia("(min-width: 1024px)");

// The range chip's choices, sent to eval as `range`. The comps draw one value
// ("8 weeks") and are silent on the rest; these span a week to a year because the
// widgets they drive are weekly and monthly series. Defined here, not by the source,
// because a range is a request parameter the source interprets, like a page size.
const RANGES = [
  { id: "1w", label: "1 week" },
  { id: "4w", label: "4 weeks" },
  { id: "8w", label: "8 weeks" },
  { id: "26w", label: "26 weeks" },
  { id: "52w", label: "1 year" },
];

// The eight kinds, with B2's (phone) and D2's (desktop) descriptions — the designer
// wrote both, each for its surface, so each surface prints its own.
const KINDS = [
  { kind: "number", label: "Number", phone: "one value, with a comparison", desk: "one value, with a comparison" },
  { kind: "series", label: "Series", phone: "a line or bars over time", desk: "a line or bars over time" },
  { kind: "table", label: "Table", phone: "rows from a table or a query", desk: "rows from a table or a query" },
  { kind: "tail", label: "Live tail", phone: "the newest raw events", desk: "the newest raw events as they land" },
  { kind: "inbox", label: "Inbox", phone: "findings to rate", desk: "findings to rate useful or not" },
  { kind: "control", label: "Control", phone: "a switch or a run button", desk: "a switch or a run button for a job" },
  { kind: "note", label: "Note", phone: "a question or a pin", desk: "a question or a pin, in words" },
  { kind: "app", label: "App", phone: "a small page, sandboxed", desk: "a small page you or a job built, sandboxed" },
];

// A new widget's size, in desktop cells. Chosen so each kind's comp content fits
// without a scrollbar at ROW_PX: D2 draws the number and the note at h2, the charts,
// table, inbox and controls at h3, and the app tile needs C1's ~260 px.
const DEFAULT_SIZE = {
  number: [1, 2], series: [2, 2], table: [2, 3], tail: [1, 3],
  inbox: [2, 3], control: [1, 3], note: [1, 2], app: [2, 3],
};

// B3 designs the Number editor only. Every other kind gets the same form pattern —
// a stack of labelled selects, a live preview above, one primary button below — with
// the fields its binding needs and nothing more. Title is on every kind. The fields are the bindings
// the source validates (sensorium board.py): it takes structured fields only, never a
// query, and refuses anything outside them with a reason the preview prints.
const KIND_FIELDS = {
  number: ["title", "source", "value", "where", "period", "window", "compare"],
  series: ["title", "source", "value", "where", "period", "count", "style"],
  table: ["title", "source", "columns", "where", "limit"],
  tail: ["title", "where", "limit"],
  inbox: ["title", "where", "limit"],
  control: ["title", "mute", "run"],
  note: ["title", "text"],
  app: ["title", "app"],
};
// Row limits per kind, inside the source's bounds (table and tail 1–50, inbox 1–20).
const LIMITS = { table: [5, 10, 20, 50], tail: [6, 12, 20, 50], inbox: [3, 5, 10, 20] };
// The periods a series spans, and how many earlier periods a number sums to compare.
const COUNTS = [4, 6, 8, 12, 18, 26, 52];
const COMPARES = [null, 1, 2, 3, 4, 6, 8, 12, 26, 52];
// Tail and inbox read fixed tables; their "Only rows where" offers that table's filters.
const FIXED_SOURCE = { tail: "events", inbox: "findings" };
// A new widget's title where the designer named one (N5: the inbox is "Rate what jobs
// found"); every other kind starts untitled and prints its kind until he names it.
const DEFAULT_TITLE = { inbox: "Rate what jobs found" };
// How many findings an inbox shows once "N more to rate ›" is tapped: the source's cap.
const INBOX_OPEN_LIMIT = 20;

// ---------------------------------------------------------------- layout (pure)

/** Do two boxes share a cell? */
function overlaps(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

/** A box held to the grid: w 1–cols, h 1–maxH, inside the columns, never above row 0. */
function clampBox(box, cols, maxH) {
  const int = (v, d) => (Number.isFinite(Number(v)) ? Math.round(Number(v)) : d);
  const w = Math.min(cols, Math.max(1, int(box.w, 1)));
  const h = Math.min(maxH, Math.max(1, int(box.h, 1)));
  const x = Math.min(cols - w, Math.max(0, int(box.x, 0)));
  const y = Math.max(0, int(box.y, 0));
  return { x, y, w, h };
}

/**
 * Put widget `id` at (x, y) with size (w, h) and push whatever it lands on downward,
 * cascading, until nothing overlaps. Returns new objects; the input is untouched, so
 * a drag can re-place from its starting snapshot on every cell it crosses.
 *
 * The collision rule is react-grid-layout's and gridstack's vertical push: the moved
 * widget wins its cells, the others give way downward in reading order. Unlike both,
 * nothing floats back up afterwards — D2 draws an empty cell on the board ("drop a
 * widget here"), so a gap he leaves is his, and the board does not repack itself
 * under his hand.
 */
function placeWidget(widgets, id, x, y, w, h, cols, maxH) {
  const out = widgets.map((o) => Object.assign({}, o));
  const moved = out.find((o) => o.id === id);
  if (!moved) return out;
  Object.assign(moved, clampBox({ x, y, w, h }, cols, maxH));
  const settled = [moved];
  const rest = out.filter((o) => o !== moved).sort((a, b) => a.y - b.y || a.x - b.x);
  for (const o of rest) {
    for (;;) {
      const hits = settled.filter((s) => overlaps(s, o));
      if (!hits.length) break;
      o.y = Math.max(...hits.map((s) => s.y + s.h));
    }
    settled.push(o);
  }
  return out;
}

/** The first top-left cell, in reading order, where a w×h box overlaps nothing. */
function firstFreeSlot(widgets, w, h, cols) {
  const bottom = widgets.reduce((m, o) => Math.max(m, o.y + o.h), 0);
  for (let y = 0; y <= bottom; y++) {
    for (let x = 0; x + w <= cols; x++) {
      const box = { x, y, w, h };
      if (!widgets.some((o) => overlaps(o, box))) return { x, y };
    }
  }
  return { x: 0, y: bottom };
}

/**
 * Widgets as stored may be missing a box or overlap (a board written by hand, or by
 * an older page). Clamp each, then settle them in reading order with the same push
 * the drag uses, so what is drawn is always a legal layout.
 */
function normalizeLayout(widgets, cols, maxH) {
  const placed = [];
  for (const w of widgets) {
    const size = clampBox(w, cols, maxH);
    const hasBox = Number.isFinite(Number(w.x)) && Number.isFinite(Number(w.y));
    const at = hasBox ? size : Object.assign(size, firstFreeSlot(placed, size.w, size.h, cols));
    const o = Object.assign({}, w, at);
    for (;;) {
      const hits = placed.filter((s) => overlaps(s, o));
      if (!hits.length) break;
      o.y = Math.max(...hits.map((s) => s.y + s.h));
    }
    placed.push(o);
  }
  return placed;
}

/** The phone's order: the desktop boxes read row by row, left to right. */
function phoneOrder(widgets) {
  return widgets.slice().sort((a, b) => a.y - b.y || a.x - b.x).map((w) => w.id);
}

// The phone's flow: reading order, except that a narrow card pulls the next narrow card
// from its own desktop row up beside it (B1 puts the two numbers side by side and the
// wide series under them). A narrow card left with no narrow neighbour stretches to
// both columns rather than leaving a dead one. Display only; the stored layout is
// untouched. Returns the order and each card's span (1 or 2).
function phoneFlow(widgets) {
  const byId = new Map(widgets.map((w) => [w.id, w]));
  const queue = phoneOrder(widgets).map((id) => byId.get(id));
  const order = [];
  const spans = {};
  while (queue.length) {
    const w = queue.shift();
    order.push(w.id);
    if (Math.min(2, w.w) === 2) { spans[w.id] = 2; continue; }
    const k = queue.findIndex((o) => o.y === w.y && Math.min(2, o.w) === 1);
    if (k < 0) { spans[w.id] = 2; continue; }
    const [mate] = queue.splice(k, 1);
    order.push(mate.id);
    spans[w.id] = 1;
    spans[mate.id] = 1;
  }
  return { order, spans };
}

/** The grid cell under a point, given the grid's box and its metrics. */
function cellAt(px, py, rect, cols, rowPx, gapPx) {
  const colW = (rect.width - gapPx * (cols - 1)) / cols;
  const x = Math.floor((px - rect.left + gapPx / 2) / (colW + gapPx));
  const y = Math.floor((py - rect.top + gapPx / 2) / (rowPx + gapPx));
  return { x: Math.min(cols - 1, Math.max(0, x)), y: Math.max(0, y) };
}

// ---------------------------------------------------------- render model (pure)

/** Bars, scaled to the tallest. The last bar is the current window and is drawn bright. */
function barsModel(items) {
  const list = Array.isArray(items) ? items : [];
  const vals = list.map((it) => Math.max(0, Number(it && it.value) || 0));
  const max = Math.max(0, ...vals);
  return list.map((it, i) => ({
    label: String((it && it.label) ?? ""),
    text: it && it.text != null ? String(it.text) : String(vals[i]),
    frac: max > 0 ? vals[i] / max : 0,
    current: i === list.length - 1,
  }));
}

/**
 * A line in unit coordinates (0–1, y downward), with its first and last points
 * labelled with the source's own text. The axis gets four unlabelled gridlines from
 * zero to a little above the top value: the source sends values and their printed
 * text but no axis, and a tick label would be the page inventing a unit.
 */
function lineModel(items) {
  const list = Array.isArray(items) ? items : [];
  const vals = list.map((it) => Number(it && it.value) || 0);
  const lo = Math.min(0, ...vals);
  let hi = Math.max(lo, ...vals);
  hi = hi > lo ? lo + (hi - lo) * 1.1 : lo + 1;
  const fy = (v) => 1 - (v - lo) / (hi - lo);
  const n = list.length;
  const points = vals.map((v, i) => ({ fx: n > 1 ? i / (n - 1) : 0.5, fy: fy(v) }));
  const end = (i) => (n ? { label: String(list[i].label ?? ""), text: String(list[i].text ?? vals[i]),
                           fx: points[i].fx, fy: points[i].fy } : null);
  return {
    points,
    first: end(0),
    last: n > 1 ? end(n - 1) : null,
    grid: [0, 1, 2, 3].map((k) => fy(lo + ((hi - lo) * k) / 3)),
  };
}

/**
 * An eval result as a render model: plain data, no DOM. Unknown fields are dropped
 * here, which is where the board's own rules live — the tail shows time, source and
 * kind and nothing else (N2: "kinds only, no app names on the board"), whatever the
 * source sends.
 */
function evalModel(kind, r) {
  const res = r && typeof r === "object" ? r : {};
  const tile = res.tile && typeof res.tile === "object" ? res.tile : {};
  const foot = res.foot != null ? res.foot : tile.foot;
  // Two footers (N5): `source` is the view-mode line, where the numbers come from in
  // words and the job its link opens; `foot` keeps the table and column names, and is
  // shown only while the board is being edited.
  const src = res.source != null ? res.source : tile.source;
  const base = {
    kind,
    foot: foot != null ? String(foot) : null,
    source: src && typeof src === "object" && src.text
      ? { text: String(src.text), job: src.job ? String(src.job) : null } : null,
  };
  const arr = (v) => (Array.isArray(v) ? v : []);
  const str = (v) => (v == null ? "" : String(v));
  switch (kind) {
    case "number":
      // `period` names what the value covers ("W47"); the title prints it after the
      // widget's own title, B1's "Blitz lost on time · W47".
      return Object.assign(base, {
        value: str(res.value), compare: res.compare != null ? str(res.compare) : null,
        period: res.period != null && res.period !== "" ? str(res.period) : null,
      });
    case "series":
      if (Array.isArray(res.line)) return Object.assign(base, { chart: "line", line: lineModel(res.line) });
      return Object.assign(base, { chart: "bars", bars: barsModel(res.bars) });
    case "table":
      return Object.assign(base, {
        columns: arr(res.columns).map(str),
        rows: arr(res.rows).map((row) => arr(row).map(str)),
      });
    case "tail":
      return Object.assign(base, {
        rows: arr(res.rows).map((x) => ({ time: str(x && x.time), source: str(x && x.source), kind: str(x && x.kind) })),
      });
    case "inbox":
      return Object.assign(base, {
        items: arr(res.items).filter((x) => x && typeof x === "object").map((x) => ({
          id: str(x.id), meta: str(x.meta), title: x.title ? str(x.title) : null, observation: str(x.observation),
          source: x.source && typeof x.source === "object" && x.source.text
            ? { text: str(x.source.text), url: x.source.url ? str(x.source.url) : null,
                run: x.source.run ? str(x.source.run) : null } : null,
          label: x.label ? str(x.label) : null,
        })),
        more: res.more ? str(res.more) : null,
      });
    case "control":
      return Object.assign(base, {
        items: arr(res.items).filter((x) => x && ["mute", "run", "auto_apply"].includes(x.type)).map((x) => {
          if (x.type === "mute") {
            return { type: "mute", scope: str(x.scope), label: str(x.label), line: x.line ? str(x.line) : null, on: !!x.on };
          }
          if (x.type === "auto_apply") return { type: "auto_apply", job: str(x.job), label: str(x.label), on: !!x.on };
          return { type: "run", job: str(x.job), label: str(x.label) };
        }),
      });
    case "note":
      // A note is pinned text and nothing else (designer ruling, 2026-11-24).
      return Object.assign(base, { text: str(res.text) });
    case "app":
      return Object.assign(base, { app: str(res.app) });
    default:
      return Object.assign(base, { unknown: true });
  }
}

/** The title a card prints: the widget's own, then the period its value covers. */
function cardTitle(widgetTitle, period, fallback) {
  const t = widgetTitle || fallback;
  return period ? t + " · " + period : t;
}

/** The words for a Window choice, given the period the value is bucketed by. */
function windowLabel(id, period) {
  const p = period || "day";
  if (id === "current") return p === "day" ? "today" : "this " + p;
  if (id === "latest") return "the latest " + p + " with rows";
  if (id === "all") return "all time";
  return String(id);
}

/** The words for a Compare choice: N earlier periods, summed, or nothing. */
function compareLabel(n, period) {
  if (n == null) return "nothing";
  return `previous ${n} ${period || "day"}${n === 1 ? "" : "s"}, summed`;
}

// ------------------------------------------------------ app widget host (pure)

/**
 * May this write go out? A row is capped at `cap` bytes of JSON and one write per
 * `minMs` per app. Returns {ok, bytes} or {ok: false, error}.
 */
function writeGate(lastMs, nowMs, row, cap, minMs) {
  if (!row || typeof row !== "object" || Array.isArray(row)) return { ok: false, error: "row must be an object" };
  let bytes;
  try { bytes = new TextEncoder().encode(JSON.stringify(row)).length; }
  catch (_) { return { ok: false, error: "row is not JSON" }; }
  if (bytes > cap) return { ok: false, error: `row is ${bytes} bytes; the cap is ${cap}` };
  if (lastMs != null && nowMs - lastMs < minMs) return { ok: false, error: "one write per second" };
  return { ok: true, bytes };
}

/**
 * What a message from an app frame asks for, or null to drop it. The frame is found by
 * `source` — the window that posted — and by nothing in the body: an app cannot name
 * another widget, because it is never asked who it is. A tile may open itself; only
 * the full-screen frame may close.
 */
function routeAppMessage(registry, source, data) {
  const entry = registry.get(source);
  if (!entry) return null;
  if (!data || typeof data !== "object" || typeof data.thalamus !== "string") return null;
  const id = (typeof data.id === "string" && data.id.length <= 64) || Number.isFinite(data.id) ? data.id : null;
  switch (data.thalamus) {
    case "app/ready": return { entry, act: "data" };
    case "app/write": return { entry, act: "write", id, row: data.row };
    case "app/open": return entry.mode === "tile" ? { entry, act: "open" } : null;
    case "app/close": return entry.mode === "full" ? { entry, act: "close" } : null;
    case "app/resize": {
      const px = Number(data.height);
      if (entry.mode !== "tile" || !Number.isFinite(px)) return null;
      return { entry, act: "resize", height: Math.min(640, Math.max(120, Math.round(px))) };
    }
    default: return null;
  }
}

// ---------------------------------------------------------------- page state

const S = {
  widgets: [],          // as saved
  version: null,        // the saved board's version, sent back as `base`
  draft: null,          // a copy while editing; null otherwise
  range: "8w",
  scope: "all",
  opened: new Set(),    // inbox widget ids whose "N more to rate ›" was tapped (view only, not saved)
  scopes: null,         // scope names, from the jobs list (lazy)
  jobs: null,           // runnable jobs, from the jobs list (lazy)
  sources: null,        // GET board/sources (lazy)
  suggestions: [],      // GET board's suggestions: B4's list and B2's "from your jobs"
  apps: null,           // GET apps (lazy)
  results: new Map(),   // widget id -> render model | {error}
  gen: new Map(),       // widget id -> eval generation, so a stale answer is dropped
  cards: new Map(),     // widget id -> card element, kept so an app frame is not reloaded
  selected: null,       // desktop edit: the selected widget id
  dockView: "add",      // desktop edit: "add" | "editor"
  dockHidden: false,    // desktop edit: the dock folded away by its ✕
  loaded: false,
  error: null,
};
const apps = new Map();       // contentWindow -> {widgetId, app, mode, frame}
const lastWrite = new Map();  // app id -> ms of its last accepted write

const mainEl = document.getElementById("main");
const dockEl = document.getElementById("dock");
const chipsEl = document.getElementById("chips");
const editBtn = document.getElementById("edit");
const hintEl = document.getElementById("hint");

function live() { return S.draft || S.widgets; }
function editing() { return S.draft != null; }
function newId() {
  const b = new Uint8Array(6);
  crypto.getRandomValues(b);
  return "w-" + Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}
function kindInfo(kind) { return KINDS.find((k) => k.kind === kind) || { kind, label: kind, phone: "", desk: "" }; }

// ---------------------------------------------------------------- loading

async function load() {
  try {
    const b = await api("board");
    S.widgets = normalizeLayout(Array.isArray(b.widgets) ? b.widgets : [], COLS, MAX_H);
    S.version = b.version ?? null;
    S.suggestions = Array.isArray(b.suggestions) ? b.suggestions : [];
    S.error = null;
  } catch (e) {
    S.error = e;
  }
  S.loaded = true;
  S.results.clear();
  render();
  evalAll();
}

function evalAll() { for (const w of live()) evalWidget(w); }

async function evalWidget(w) {
  const g = (S.gen.get(w.id) || 0) + 1;
  S.gen.set(w.id, g);
  let model;
  try {
    // An opened inbox asks for more rows; the saved widget keeps its own limit.
    const asked = S.opened.has(w.id)
      ? Object.assign({}, w, { binding: Object.assign({}, w.binding, { limit: INBOX_OPEN_LIMIT }) }) : w;
    const r = await apiPost("board/eval", { widget: asked, range: S.range, scope: S.scope });
    model = evalModel(w.kind, r);
  } catch (e) {
    model = { kind: w.kind, error: e.message || String(e) };
  }
  if (S.gen.get(w.id) !== g) return;
  S.results.set(w.id, model);
  const card = S.cards.get(w.id);
  if (card) fillCard(card, w, model);
}

async function ensureSources() {
  if (S.sources) return S.sources;
  try { S.sources = await api("board/sources"); }
  catch (e) { S.sources = { sources: [], error: e.message }; }
  return S.sources;
}

// Scopes and runnable jobs come from the jobs list: the board has no list of its own,
// and the scope chip filters by the same scopes the jobs page groups under.
async function ensureJobs() {
  if (S.scopes) return;
  try {
    const d = await api("jobs");
    const groups = Array.isArray(d.groups) ? d.groups : [];
    S.scopes = groups.map((g) => g.name).filter((n) => n);
    S.jobs = [].concat(...groups.map((g) => g.jobs || [])).filter((j) => j.runnable)
      .map((j) => ({ id: j.id, name: j.name || j.id }));
  } catch (_) {
    S.scopes = [];
    S.jobs = [];
  }
}

async function ensureApps() {
  if (S.apps) return S.apps;
  try { S.apps = (await api("apps")).apps || []; }
  catch (_) { S.apps = []; }
  return S.apps;
}

// ---------------------------------------------------------------- chips

function renderChips() {
  const chip = (label, value, options, onchange) => {
    const sel = h("select.b-chip-sel", { "aria-label": label },
      options.map((o) => h("option", { value: o.id, selected: o.id === value }, o.label)));
    sel.addEventListener("change", () => onchange(sel.value));
    return h("label.b-chip", h("span.b-chip-k", label), sel);
  };
  const scopes = [{ id: "all", label: "all" }].concat((S.scopes || []).map((s) => ({ id: s, label: s })));
  chipsEl.replaceChildren(
    chip("range", S.range, RANGES, (v) => { S.range = v; evalAll(); }),
    chip("scope", S.scope, scopes, (v) => { S.scope = v; evalAll(); }));
}

// ---------------------------------------------------------------- board

function render() {
  editBtn.textContent = editing() ? "done" : "edit";
  editBtn.classList.toggle("on", editing());
  editBtn.hidden = !S.loaded || !!S.error;
  hintEl.hidden = !editing();
  document.body.classList.toggle("b-editing", editing());
  renderChips();
  // B4 draws no chips: on an empty board there is nothing for them to drive.
  chipsEl.hidden = S.loaded && !S.error && !live().length && !editing();
  if (S.error) {
    S.cards.clear();
    mainEl.replaceChildren(errorBox(S.error));
    return;
  }
  if (!S.loaded) {
    mainEl.replaceChildren(h("p.s-empty", "loading the board…"));
    return;
  }
  if (!live().length && !editing()) {
    S.cards.clear();
    mainEl.replaceChildren(emptyBoard());
    renderDock();
    return;
  }
  renderGrid();
  renderDock();
}

// B4. The suggestions are the source's ("from what your jobs already measure").
function emptyBoard() {
  const sugg = S.suggestions;
  return h("div.b-empty",
    h("h2.b-empty-t", "Nothing pinned yet"),
    h("p.b-empty-s", "Start from what your jobs already measure."),
    h("div.b-sugg-list", sugg.map((s) => h("div.b-sugg-card",
      h("div.grow", h("div.b-sugg-t", s.title || ""), h("div.b-sugg-l.mono", s.line || "")),
      h("button.s-link.b-add", { type: "button", onclick: () => addSuggestion(s) }, "add")))),
    h("button.s-btn.b-empty-add", { type: "button", onclick: () => { startEditing(); openAdd(); } }, "Add widget"));
}

function renderGrid() {
  let grid = mainEl.querySelector(".b-grid");
  if (!grid) {
    grid = h("div.b-grid");
    grid.style.setProperty("--row", ROW_PX + "px");
    grid.style.setProperty("--gap", GAP_PX + "px");
    mainEl.replaceChildren(grid);
    S.cards.clear();
  }
  const ws = live();
  const ids = new Set(ws.map((w) => w.id));
  for (const [id, card] of S.cards) {
    if (!ids.has(id)) { card.remove(); S.cards.delete(id); }
  }
  for (const w of ws) {
    let card = S.cards.get(w.id);
    if (!card) {
      card = h("section.b-card", { "data-id": w.id });
      S.cards.set(w.id, card);
      grid.appendChild(card);
      fillCard(card, w, S.results.get(w.id));
    }
  }
  pruneApps();
  layoutGrid(grid);
}

/** Position every card from the live layout without rebuilding any of them. */
function layoutGrid(grid) {
  const ws = live();
  const { order, spans } = phoneFlow(ws);
  for (const w of ws) {
    const card = S.cards.get(w.id);
    if (!card) continue;
    card.style.setProperty("--x", w.x + 1);
    card.style.setProperty("--y", w.y + 1);
    card.style.setProperty("--w", w.w);
    card.style.setProperty("--h", w.h);
    card.style.setProperty("--pw", spans[w.id]);
    card.style.order = order.indexOf(w.id);
    card.classList.toggle("sel", editing() && S.selected === w.id);
    if (card._slots) paintFoot(card._slots, w, S.results.get(w.id));
    card.querySelectorAll(".b-tools").forEach((t) => t.remove());
    if (editing() && S.selected === w.id) card.appendChild(toolsFor(w));
  }
  let drop = grid.querySelector(".b-drop");
  if (editing()) {
    const size = firstFreeFor(ws);
    if (!drop) {
      drop = h("button.b-drop", { type: "button", onclick: () => openAdd(drop._slot) },
        h("span.b-drop-desk", "+ drop a widget here"), h("span.b-drop-phone", "+ add a widget"));
      grid.appendChild(drop);
    }
    drop._slot = size;
    drop.style.setProperty("--x", size.x + 1);
    drop.style.setProperty("--y", size.y + 1);
    drop.style.setProperty("--w", size.w);
    drop.style.setProperty("--h", size.h);
  } else if (drop) {
    drop.remove();
  }
  const bottom = ws.reduce((m, w) => Math.max(m, w.y + w.h), 0);
  grid.style.setProperty("--rows", bottom + (editing() ? 3 : 0));
}

// The dashed cell D2 draws sits in the first gap a 2×2 widget fits; on a board too
// full for that, the first 1×2, then 1×1.
function firstFreeFor(ws) {
  let best = null;
  for (const [w, hh] of [[2, 2], [1, 2], [1, 1]]) {
    const at = firstFreeSlot(ws, w, hh, COLS);
    if (!best || at.y < best.y) best = Object.assign(at, { w, h: hh });
  }
  return best;
}

// A card is built once and then refilled in place. Its body element is never
// detached, because moving an iframe in the document reloads it: an app tile keeps
// its frame (and the app its state) across every re-evaluation and every drag.
function cardSlots(card, id) {
  if (card._slots) return card._slots;
  const title = h("span.b-card-t");
  const handle = h("button.b-handle", { type: "button", title: "drag to move" }, "⠿");
  const slots = {
    title, handle,
    body: h("div.b-card-b"),
    foot: h("div.b-foot"),
    resize: h("span.b-resize", { "aria-hidden": "true", title: "drag the corner to resize" }),
  };
  card.replaceChildren(h("div.b-card-h", title, handle), slots.body, slots.foot, slots.resize);
  card._slots = slots;
  if (id) wireCard(card, id);
  return slots;
}

function fillCard(card, w, model) {
  const s = cardSlots(card, card.dataset.id);
  card.dataset.kind = w.kind;
  const titleText = cardTitle(w.title, model && model.period, kindInfo(w.kind).label);
  s.title.textContent = titleText;
  s.handle.setAttribute("aria-label", "Move " + titleText);
  const frame = s.body.querySelector(":scope > iframe.b-app-frame");
  const keep = w.kind === "app" && frame && model && !model.error && frame.dataset.app === model.app;
  if (!keep) s.body.replaceChildren(...[].concat(cardBody(w, model)).filter((x) => x != null));
  paintFoot(s, w, model);
}

// The footer alone, repainted whenever edit mode turns on or off: the body is left as it
// is (an app frame must not reload), only the line under it changes.
function paintFoot(s, w, model) {
  s.foot.replaceChildren();
  const foot = cardFoot(w, model);
  if (foot) s.foot.append(foot);
  s.foot.hidden = !foot;
}

// A card's last line. Editing: the table and column names, in mono (D2). Viewing: where
// the numbers come from, in words, linking the job that writes them (C1 "from chess.com
// games ›"); an inbox instead offers the findings it is not showing (B1 "3 more to rate ›").
function cardFoot(w, m) {
  if (!m || m.error) return null;
  if (editing()) return m.foot ? h("span.b-foot-names.mono", m.foot) : null;
  if (w.kind === "inbox") {
    if (!m.more) return null;
    return h("button.s-link.b-more", { type: "button", onclick: () => { S.opened.add(w.id); evalWidget(w); } },
      m.more + " ›");
  }
  if (!m.source) return null;
  return m.source.job
    ? h("a.b-src", { href: "jobs.html#/job/" + encodeURIComponent(m.source.job) }, m.source.text + " ›")
    : h("span.b-src", m.source.text);
}

function cardBody(w, m) {
  if (!m) return h("div.b-wait.muted", "…");
  if (m.error) return h("div.b-wid-err", "could not evaluate · " + m.error);
  if (m.unknown) return h("div.muted", "this page cannot draw a “" + w.kind + "” widget");
  switch (w.kind) {
    case "number": return numberBody(m);
    case "series": return m.chart === "line" ? lineBody(m.line) : barsBody(m.bars);
    case "table": return tableBody(m);
    case "tail": return tailBody(m);
    case "inbox": return inboxBody(w, m);
    case "control": return controlBody(w, m);
    case "note": return noteBody(m);
    case "app": return appTile(w, m);
    default: return null;
  }
}

function numberBody(m) {
  return [
    h("div.b-num.mono", m.value),
    m.compare ? h("div.b-cmp", m.compare) : null,
  ];
}

// Bars for counts. Every bar carries its value as text above it, so the bar's height
// is never the only way to read a number; the current window is the bright one and
// is also the rightmost, labelled with its week.
function barsBody(bars) {
  if (!bars.length) return h("div.muted.b-none", "no rows in this range");
  return h("div.b-bars", { role: "img", "aria-label": bars.map((b) => b.label + " " + b.text).join(", ") },
    bars.map((b) => h("div.b-bar" + (b.current ? ".cur" : ""),
      // The value sits on top of its bar; the column keeps 1.1rem for it at full height.
      h("span.b-bar-col",
        h("span.b-bar-v.mono", b.text),
        h("span.b-bar-fill", { style: { height: `max(2px, calc(${b.frac.toFixed(4)} * (100% - 1.1rem)))` } })),
      h("span.b-bar-l.mono", b.label))));
}

const SVGNS = "http://www.w3.org/2000/svg";
function svg(tag, attrs) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, String(v));
  return el;
}

// A line for shares. The path is drawn in a stretched SVG with non-scaling strokes;
// the labels are HTML placed by percentage, so text never stretches with the chart.
function lineBody(L) {
  if (!L.points.length) return h("div.muted.b-none", "no rows in this range");
  const pct = (f) => (f * 100).toFixed(2) + "%";
  const chart = svg("svg", { class: "b-line-svg", viewBox: "0 0 100 100", preserveAspectRatio: "none", "aria-hidden": "true" });
  for (const fy of L.grid) {
    chart.appendChild(svg("line", { x1: 0, x2: 100, y1: fy * 100, y2: fy * 100, class: "b-grid-ln",
                                    "vector-effect": "non-scaling-stroke" }));
  }
  chart.appendChild(svg("polyline", {
    points: L.points.map((p) => `${p.fx * 100},${p.fy * 100}`).join(" "),
    class: "b-line-ln", "vector-effect": "non-scaling-stroke",
  }));
  const plot = h("div.b-line-plot", chart,
    [L.first, L.last].filter(Boolean).map((e, i) => [
      h("span.b-line-dot", { style: { left: pct(e.fx), top: pct(e.fy) } }),
      h("span.b-line-v.mono" + (i ? ".last" : ""), { style: { left: pct(e.fx), top: pct(e.fy) } }, e.text),
    ]));
  const label = [L.first, L.last].filter(Boolean).map((e) => e.label + " " + e.text).join(" to ");
  return h("div.b-line", { role: "img", "aria-label": label }, plot,
    h("div.b-line-ax.mono", h("span", L.first ? L.first.label : ""), h("span", L.last ? L.last.label : "")));
}

function tableBody(m) {
  if (!m.rows.length) return h("div.muted.b-none", "no rows");
  return h("div.b-table-wrap", h("table.b-table",
    h("thead", h("tr", m.columns.map((c) => h("th.mono", c)))),
    h("tbody", m.rows.map((row) => h("tr", row.map((c, j) => h("td" + (j ? ".mono" : ""), c)))))));
}

// The newest row is ink, the rest muted: order already says which is newest, the
// colour only reinforces it.
function tailBody(m) {
  if (!m.rows.length) return h("div.muted.b-none", "no events in this range");
  return h("div.b-tail.mono", m.rows.map((r, i) => h("div.b-tail-r" + (i ? "" : ".newest"),
    h("span", r.time), h("span", r.source), h("span", r.kind))));
}

// B1's "Rate what jobs found": a caption, then each finding as surface.js's findingCard.
// "evidence ›" opens the run on the jobs page, where the finding sits among what its run
// read and spent.
function inboxBody(w, m) {
  const cap = h("div.b-inbox-cap", "Your ratings tune what each job reports.");
  if (!m.items.length) return [cap, h("div.muted.b-none", "nothing left to rate")];
  return [cap, h("div.b-inbox", m.items.map((it) =>
    findingCard(it, (run) => "jobs.html#/run/" + encodeURIComponent(run))))];
}

function controlBody(w, m) {
  if (!m.items.length) return h("div.muted.b-none", "no switches or jobs bound");
  return h("div.b-ctl", m.items.map((it) => {
    if (it.type === "mute") {
      // The switch is the label's subject ("career notifications"): on = they arrive.
      // Switching off sends no date: the source mutes for its own default span and
      // composes the line that says until when, which is printed beside the switch.
      return h("div.b-ctl-row",
        h("div.grow", h("div.b-ctl-l", it.label), it.line ? h("div.b-ctl-s.muted", it.line) : null),
        switchEl(it.on, it.label, async (on) => {
          await apiPost("scopes/" + encodeURIComponent(it.scope) + "/notifications", { on });
          evalWidget(w);
        }));
    }
    if (it.type === "auto_apply") {
      return h("div.b-ctl-row", h("div.grow", h("div.b-ctl-l", it.label)),
        switchEl(it.on, it.label, async (on) => {
          await apiPost("jobs/" + encodeURIComponent(it.job) + "/auto-apply", { on });
          evalWidget(w);
        }));
    }
    const btn = h("button.s-btn.b-run", { type: "button" }, it.label);
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        const r = await apiPost("jobs/" + encodeURIComponent(it.job) + "/run", {});
        toast("started" + (r.unit ? " · " + r.unit : ""));
      } catch (e) { toast(e.message); }
      finally { btn.disabled = false; }
    });
    return btn;
  }));
}

function noteBody(m) {
  return [h("div.b-note", m.text)];
}

// ------------------------------------------------------------ app widget host

// The tile is the app's; the host draws its title and footer around it and nothing
// inside. `allow-scripts` and nothing else: no allow-same-origin (the frame would
// share this page's origin and could call the console's API directly), no
// allow-popups, no allow-top-navigation, no allow-forms.
function appFrame(app, mode) {
  const src = "api/jobs/apps/" + encodeURIComponent(app) + "/files/index.html" + (mode === "tile" ? "#tile" : "");
  const f = h("iframe.b-app-frame", { sandbox: "allow-scripts", referrerpolicy: "no-referrer", src,
                                       title: app + (mode === "tile" ? " tile" : ""), "data-app": app });
  return f;
}

function registerFrame(frame, widgetId, app, mode) {
  if (frame.contentWindow) apps.set(frame.contentWindow, { widgetId, app, mode, frame });
}

function appTile(w, m) {
  if (!APP_ID.test(m.app || "")) return h("div.b-wid-err", "the source named no app");
  const f = appFrame(m.app, "tile");
  // Registered once it is in the document, which is when it gets a window.
  queueMicrotask(() => { if (f.isConnected) registerFrame(f, w.id, m.app, "tile"); });
  return f;
}

function pruneApps() {
  for (const [win, e] of apps) if (!e.frame.isConnected) apps.delete(win);
}

let overlay = null;
function openApp(entry) {
  if (overlay) return;
  const f = appFrame(entry.app, "full");
  overlay = h("div.b-app-full", { role: "dialog", "aria-label": entry.app }, f);
  document.body.appendChild(overlay);
  document.body.classList.add("b-app-open");
  registerFrame(f, entry.widgetId, entry.app, "full");
  // The app's back chevron posts app/close. A page that never does must not trap him:
  // the system back gesture and Escape close it too.
  history.pushState({ boardApp: true }, "");
}
function closeApp(fromHistory) {
  if (!overlay) return;
  overlay.remove();
  overlay = null;
  document.body.classList.remove("b-app-open");
  pruneApps();
  if (!fromHistory && history.state && history.state.boardApp) history.back();
}
window.addEventListener("popstate", () => closeApp(true));
window.addEventListener("keydown", (e) => { if (e.key === "Escape" && overlay) closeApp(false); });

function post(win, msg) { try { win.postMessage(msg, "*"); } catch (_) { /* frame gone */ } }

async function sendData(win, app) {
  try { post(win, { thalamus: "app/data", data: await api("apps/" + encodeURIComponent(app) + "/data") }); }
  catch (e) { post(win, { thalamus: "app/data", data: null, error: e.message }); }
}

window.addEventListener("message", async (ev) => {
  const r = routeAppMessage(apps, ev.source, ev.data);
  if (!r) return;
  const win = ev.source;
  const app = r.entry.app;
  if (r.act === "data") return sendData(win, app);
  if (r.act === "open") return openApp(r.entry);
  if (r.act === "close") return closeApp(false);
  if (r.act === "resize") { r.entry.frame.style.height = r.height + "px"; return; }
  if (r.act === "write") {
    const now = Date.now();
    const gate = writeGate(lastWrite.get(app) ?? null, now, r.row, WRITE_CAP_BYTES, WRITE_MIN_MS);
    if (!gate.ok) return post(win, { thalamus: "app/written", id: r.id, ok: false, error: gate.error });
    lastWrite.set(app, now);
    try {
      // The body is the row itself (sensorium apps.write takes it whole and checks it
      // against the app's write grant); the reply carries the fresh granted data.
      const res = await apiPost("apps/" + encodeURIComponent(app) + "/write", r.row);
      const msg = { thalamus: "app/written", id: r.id, ok: true };
      if (res.data !== undefined) msg.data = res.data;
      post(win, msg);
    } catch (e) {
      post(win, { thalamus: "app/written", id: r.id, ok: false, error: e.message });
    }
  }
});

// ---------------------------------------------------------------- editing

function startEditing() {
  if (editing()) return;
  S.draft = S.widgets.map((w) => Object.assign({}, w));
  S.selected = null;
  S.dockView = "add";
  S.dockHidden = false;
  ensureSources().then(() => { if (editing()) renderDock(); });
  ensureJobs();
  render();
}

async function finishEditing() {
  const draft = S.draft;
  editBtn.disabled = true;
  try {
    const r = await apiPost("board", { widgets: draft, base: S.version });
    S.widgets = draft;
    S.version = r.version ?? S.version;
    S.draft = null;
    closeEditor();
    render();
  } catch (e) {
    if (e.status === 409) {
      S.draft = null;
      closeEditor();
      toast("The board was saved from somewhere else meanwhile. Reloaded it; these edits were not kept.");
      await load();
    } else {
      toast(e.message);
    }
  } finally {
    editBtn.disabled = false;
  }
}

editBtn.addEventListener("click", () => (editing() ? finishEditing() : startEditing()));

document.getElementById("back").addEventListener("click", (e) => {
  if (editing() && JSON.stringify(S.draft) !== JSON.stringify(S.widgets)
      && !confirm("Leave the board without saving these edits?")) e.preventDefault();
});

function addWidget(w, slot) {
  if (!editing()) startEditing();
  const [dw, dh] = DEFAULT_SIZE[w.kind] || [1, 2];
  const size = clampBox({ w: w.w || dw, h: w.h || dh, x: 0, y: 0 }, COLS, MAX_H);
  const at = slot && slot.x != null ? { x: slot.x, y: slot.y } : firstFreeSlot(S.draft, size.w, size.h, COLS);
  const widget = Object.assign({}, w, { id: newId() }, size, at);
  S.draft = placeWidget(S.draft.concat([widget]), widget.id, at.x, at.y, size.w, size.h, COLS, MAX_H);
  S.selected = widget.id;
  render();
  evalWidget(S.draft.find((x) => x.id === widget.id));
  return widget;
}

// A suggestion added from B4, outside edit mode, is pinned in one tap — the page
// saves straight away rather than leaving him in an edit mode he did not ask for.
// Inside edit mode it joins the draft like anything else.
async function addSuggestion(s) {
  const wasEditing = editing();
  addWidget(Object.assign({}, s.widget || {}));
  if (!wasEditing) await finishEditing();
  else closeSheet();
}

function removeWidget(id) {
  S.draft = S.draft.filter((w) => w.id !== id);
  if (S.selected === id) S.selected = null;
  render();
}

function copyWidget(id) {
  const src = S.draft.find((w) => w.id === id);
  if (!src) return;
  const copy = Object.assign({}, src, { binding: JSON.parse(JSON.stringify(src.binding || {})) });
  delete copy.id;
  addWidget(copy);
}

function toolsFor(w) {
  return h("div.b-tools",
    h("button", { type: "button", onclick: (e) => { e.stopPropagation(); openEditor(w.kind, w); } }, "edit"),
    h("span", { "aria-hidden": "true" }, " · "),
    h("button", { type: "button", onclick: (e) => { e.stopPropagation(); copyWidget(w.id); } }, "copy"),
    h("span", { "aria-hidden": "true" }, " · "),
    h("button", { type: "button", onclick: (e) => { e.stopPropagation(); removeWidget(w.id); } }, "remove"));
}

// ----------------------------------------------------- dragging (pointer events)
//
// Pointer events rather than HTML5 drag-and-drop: the latter never fires on touch.
// A drag re-places from the layout it started with on every cell it crosses, so
// pushing a neighbour down and then moving away lets the neighbour back up.

let drag = null;

function wireCard(card, id) {
  const handle = card.querySelector(".b-handle");
  const corner = card.querySelector(".b-resize");
  handle.addEventListener("pointerdown", (e) => beginDrag(e, id, "move"));
  corner.addEventListener("pointerdown", (e) => beginDrag(e, id, "resize"));
  card.addEventListener("click", (e) => {
    if (!editing() || e.target.closest("button, a, input, select, label, iframe")) return;
    if (DESKTOP.matches) { S.selected = id; layoutGrid(mainEl.querySelector(".b-grid")); }
    else { const w = S.draft.find((x) => x.id === id); if (w) openEditor(w.kind, w); }
  });
}

function beginDrag(e, id, mode) {
  if (!editing() || (mode === "resize" && !DESKTOP.matches)) return;
  e.preventDefault();
  const grid = mainEl.querySelector(".b-grid");
  const start = S.draft.map((w) => Object.assign({}, w));
  const w0 = start.find((w) => w.id === id);
  const rect = grid.getBoundingClientRect();
  const c0 = cellAt(e.clientX, e.clientY, rect, COLS, ROW_PX, GAP_PX);
  drag = { id, mode, start, w0, c0, grid, key: "", pid: e.pointerId, target: e.currentTarget };
  e.currentTarget.setPointerCapture(e.pointerId);
  S.selected = id;
  S.cards.get(id)?.classList.add("dragging");
  layoutGrid(grid);
}

window.addEventListener("pointermove", (e) => {
  if (!drag || e.pointerId !== drag.pid) return;
  const { id, mode, start, w0, c0, grid } = drag;
  let next;
  if (DESKTOP.matches) {
    const c = cellAt(e.clientX, e.clientY, grid.getBoundingClientRect(), COLS, ROW_PX, GAP_PX);
    const box = mode === "move"
      ? { x: w0.x + c.x - c0.x, y: w0.y + c.y - c0.y, w: w0.w, h: w0.h }
      // A resize grows from the top-left corner, which stays put: the width is capped
      // at the columns to its right rather than letting clampBox slide it left.
      : { x: w0.x, y: w0.y, w: Math.min(COLS - w0.x, w0.w + c.x - c0.x), h: w0.h + c.y - c0.y };
    const b = clampBox(box, COLS, MAX_H);
    const key = [b.x, b.y, b.w, b.h].join(",");
    if (key === drag.key) return;
    drag.key = key;
    next = placeWidget(start, id, b.x, b.y, b.w, b.h, COLS, MAX_H);
  } else {
    // The phone flows the boxes, so a drop target is a card, not a cell: dropping on
    // a card takes its place and pushes it on down the reading order.
    const under = document.elementsFromPoint(e.clientX, e.clientY)
      .map((el) => el.closest && el.closest(".b-card")).find((el) => el && el.dataset.id !== id);
    const t = under && start.find((w) => w.id === under.dataset.id);
    const key = t ? t.id : "";
    if (!t || key === drag.key) return;
    drag.key = key;
    next = placeWidget(start, id, t.x, t.y, w0.w, w0.h, COLS, MAX_H);
  }
  S.draft = next;
  layoutGrid(grid);
});

function endDrag(e) {
  if (!drag || e.pointerId !== drag.pid) return;
  S.cards.get(drag.id)?.classList.remove("dragging");
  drag = null;
  layoutGrid(mainEl.querySelector(".b-grid"));
}
window.addEventListener("pointerup", endDrag);
window.addEventListener("pointercancel", endDrag);

// ------------------------------------------------- add panel (B2 sheet / D2 dock)

let sheet = null;
let pendingSlot = null;

function addPanel(onClose) {
  const desk = DESKTOP.matches;
  const search = h("input.b-search", { type: "search", placeholder: "search tables, jobs, widgets",
                                       "aria-label": "search tables, jobs, widgets" });
  const kindsEl = h("div.b-kinds");
  const suggEl = h("div.b-from");
  const draw = () => {
    const q = search.value.trim().toLowerCase();
    const hit = (...s) => !q || s.join(" ").toLowerCase().includes(q);
    kindsEl.replaceChildren(...KINDS.filter((k) => hit(k.label, k.phone, k.desk)).map((k) => {
      const b = h("button.b-kind", { type: "button", "data-kind": k.kind },
        h("span.b-kind-t", k.label), h("span.b-kind-d", desk ? k.desk : k.phone));
      wireKind(b, k.kind);
      return b;
    }));
    const sugg = S.suggestions.filter((s) => hit(s.title, s.line));
    suggEl.replaceChildren(
      ...(sugg.length ? [h("div.s-label.b-from-h", "from your jobs")] : []),
      ...sugg.map((s) => h("div.b-from-r",
        h("div.grow", h("div.b-from-t", s.title || ""), h("div.b-from-l", s.line || "")),
        h("button.s-link.b-add", { type: "button", onclick: () => addSuggestion(s) }, "add"))));
  };
  search.addEventListener("input", draw);
  draw();
  ensureSources().then(draw);
  return h("div.b-addp",
    h("div.b-addp-h", h("h2.b-addp-t", "Add widget"),
      onClose ? h("button.b-x", { type: "button", "aria-label": "Close", onclick: onClose }, "✕") : null),
    search,
    desk ? h("div.s-label.b-kinds-h", "kinds") : null,
    kindsEl, suggEl);
}

// A kind is tapped (opens its editor at the first free slot, or the slot the dashed
// cell offered) or, on the desktop, dragged onto the grid (opens its editor at the
// cell it was dropped on).
function wireKind(btn, kind) {
  btn.addEventListener("pointerdown", (e) => {
    if (!DESKTOP.matches) return;
    const sx = e.clientX, sy = e.clientY;
    let ghost = null;
    const move = (ev) => {
      if (!ghost && Math.hypot(ev.clientX - sx, ev.clientY - sy) < 6) return;
      if (!ghost) {
        ghost = h("div.b-ghost", kindInfo(kind).label);
        document.body.appendChild(ghost);
      }
      ghost.style.left = ev.clientX + 8 + "px";
      ghost.style.top = ev.clientY + 8 + "px";
    };
    const up = (ev) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      if (!ghost) return;
      ghost.remove();
      btn._dragged = true;
      const grid = mainEl.querySelector(".b-grid");
      if (!grid) return;
      const r = grid.getBoundingClientRect();
      if (ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top) return;
      openEditor(kind, null, cellAt(ev.clientX, ev.clientY, r, COLS, ROW_PX, GAP_PX));
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
  btn.addEventListener("click", () => {
    if (btn._dragged) { btn._dragged = false; return; }
    openEditor(kind, null, pendingSlot);
  });
}

function openAdd(slot) {
  if (!editing()) startEditing();
  pendingSlot = slot || null;
  if (DESKTOP.matches) {
    S.dockView = "add";
    S.dockHidden = false;
    renderDock();
    return;
  }
  closeSheet();
  sheet = h("div.b-sheet-wrap",
    h("div.b-scrim", { onclick: closeSheet }),
    h("div.b-sheet", { role: "dialog", "aria-label": "Add widget" },
      h("div.b-grab", { "aria-hidden": "true" }), addPanel(null)));
  document.body.appendChild(sheet);
}
function closeSheet() { if (sheet) { sheet.remove(); sheet = null; } }

function renderDock() {
  // The dock's ✕ folds it away for more board; the dashed cell brings it back.
  const show = editing() && DESKTOP.matches && !S.dockHidden;
  dockEl.hidden = !show;
  if (!show) return;
  if (S.dockView === "editor" && editorEl) {
    if (editorEl.parentNode !== dockEl) dockEl.replaceChildren(editorEl);
    return;
  }
  dockEl.replaceChildren(addPanel(() => { S.dockHidden = true; renderDock(); }));
}

// ------------------------------------------------------------- editor (B3)

let editorEl = null;
let previewTimer = 0;

function closeEditor() {
  clearTimeout(previewTimer);
  if (editorEl) editorEl.remove();
  editorEl = null;
  S.dockView = "add";
  if (editing()) renderDock();
}

// "Only rows where" is one filter: the source accepts up to six, B3 draws one select.
// A widget saved with more keeps the rest untouched; the select edits the first.
function whereOptions(src) {
  const out = [{ id: "", label: "all rows" }];
  for (const f of (src && src.filters) || []) {
    for (const v of f.values || []) out.push({ id: JSON.stringify({ column: f.column, value: v }), label: `${f.column} = ${v}` });
  }
  return out;
}

/**
 * Open the editor for `kind`: an existing widget to change, or a new one to add at
 * `slot`. On the phone it is B3, a screen of its own; on the desktop it takes the dock.
 */
async function openEditor(kind, existing, slot) {
  if (!editing()) startEditing();
  closeSheet();
  clearTimeout(previewTimer);
  const meta = await ensureSources();
  if (KIND_FIELDS[kind].includes("mute") || KIND_FIELDS[kind].includes("run")) await ensureJobs();
  if (kind === "app") await ensureApps();
  const sources = meta.sources || [];
  const draft = existing
    ? JSON.parse(JSON.stringify(existing))
    : { kind, title: DEFAULT_TITLE[kind] || "", binding: {} };
  draft.binding = draft.binding || {};
  if (!existing && KIND_FIELDS[kind].includes("source") && sources[0]) draft.binding.source = sources[0].name;

  const form = h("div.b-form");
  const preview = h("div.b-preview");
  // Inert: the preview's switches and buttons are pictures of the widget, not the
  // widget — a tap there must not mute a scope or start a job.
  const cardHost = h("section.b-card.b-card-prev", { inert: true });
  preview.append(h("div.s-label", "preview"), cardHost);

  const field = (label, control) => h("label.b-field", h("span.b-field-l", label), control);
  const select = (options, value, onchange, mono) => {
    const sel = h("select.b-sel" + (mono ? ".mono" : ""),
      options.map((o) => h("option", { value: o.id, selected: String(o.id) === String(value ?? "") }, o.label)));
    sel.addEventListener("change", () => { onchange(sel.value); refresh(); });
    return sel;
  };
  const b = draft.binding;
  const srcOf = () => sources.find((x) => x.name === (FIXED_SOURCE[kind] || b.source)) || null;
  // A source whose rows are week or month labels is bucketed by that; a timestamped
  // one by the period the binding picks (the source's rule, board.py `_period`).
  const fixedPeriod = () => { const t = srcOf() && srcOf().time; return t === "week" || t === "month" ? t : null; };
  const periodOf = () => fixedPeriod() || b.period || "day";
  const checks = (legend, items, isOn, onToggle, empty) => h("fieldset.b-checks", h("legend.b-field-l", legend),
    items.length ? items.map((it) => {
      const c = h("input", { type: "checkbox", checked: isOn(it.id) });
      c.addEventListener("change", () => { onToggle(it.id, c.checked); refresh(); });
      return h("label.b-check", c, h("span", it.label));
    }) : h("div.muted.b-none", empty));

  const build = () => {
    const rows = [];
    for (const f of KIND_FIELDS[kind]) {
      if (f === "title") {
        const t = h("input.b-in", { type: "text", value: draft.title || "", maxlength: 120,
                                    placeholder: "what this widget shows" });
        t.addEventListener("input", () => { draft.title = t.value; refresh(); });
        rows.push(field("Title", t));
      } else if (f === "source") {
        rows.push(field("Source", select(sources.map((x) => ({ id: x.name, label: x.name })), b.source,
          (v) => { b.source = v; delete b.value; delete b.where; delete b.columns; build(); }, true)));
      } else if (f === "value") {
        const vals = (srcOf() && srcOf().values) || [];
        if (b.value == null && vals[0]) b.value = vals[0].id;
        rows.push(field("Value", select(vals, b.value, (v) => { b.value = v; }, true)));
      } else if (f === "where") {
        const list = Array.isArray(b.where) ? b.where : [];
        rows.push(field("Only rows where", select(whereOptions(srcOf()), list[0] ? JSON.stringify(list[0]) : "",
          (v) => { b.where = (v ? [JSON.parse(v)] : []).concat(list.slice(1)); }, true)));
      } else if (f === "period") {
        if (fixedPeriod()) continue;
        const ids = Array.isArray(meta.periods) && meta.periods.length ? meta.periods : ["day", "week", "month"];
        if (b.period == null) b.period = ids[0];
        rows.push(field("By", select(ids.map((id) => ({ id, label: id })), b.period, (v) => { b.period = v; build(); })));
      } else if (f === "window") {
        const ids = Array.isArray(meta.windows) && meta.windows.length ? meta.windows : ["latest", "current", "all"];
        if (b.window == null) b.window = ids.includes("current") ? "current" : ids[0];
        rows.push(field("Window", select(ids.map((id) => ({ id, label: windowLabel(id, periodOf()) })), b.window,
          (v) => { b.window = v; })));
      } else if (f === "compare") {
        if (b.compare === undefined) b.compare = null;
        rows.push(field("Compare with", select(COMPARES.map((n) => ({ id: n == null ? "" : n, label: compareLabel(n, periodOf()) })),
          b.compare == null ? "" : b.compare, (v) => { b.compare = v ? Number(v) : null; })));
      } else if (f === "count") {
        if (b.count == null) b.count = 8;
        rows.push(field("Over", select(COUNTS.map((n) => ({ id: n, label: `the last ${n} ${periodOf()}s` })), b.count,
          (v) => { b.count = Number(v); })));
      } else if (f === "style") {
        if (b.style == null) b.style = "bars";
        rows.push(field("Draw as", select([{ id: "bars", label: "bars, for counts" }, { id: "line", label: "a line, for shares" }],
          b.style, (v) => { b.style = v; })));
      } else if (f === "columns") {
        const cols = (srcOf() && srcOf().columns) || [];
        if (!Array.isArray(b.columns)) b.columns = cols.slice(0, 4);
        rows.push(checks("Columns (up to 8)", cols.map((c) => ({ id: c, label: c })), (id) => b.columns.includes(id),
          (id, on) => { b.columns = on ? b.columns.concat([id]).slice(0, 8) : b.columns.filter((x) => x !== id); },
          "the source lists no columns"));
      } else if (f === "limit") {
        const opts = LIMITS[kind];
        if (b.limit == null) b.limit = opts[1];
        rows.push(field("Rows", select(opts.map((n) => ({ id: n, label: n + " rows" })), b.limit,
          (v) => { b.limit = Number(v); })));
      } else if (f === "text") {
        const t = h("textarea.b-in.b-ta", { rows: 3, maxlength: 500, placeholder: "a question, or something to keep in view" });
        t.value = b.text || "";
        t.addEventListener("input", () => { b.text = t.value; refresh(); });
        rows.push(field("Text", t));
      } else if (f === "app") {
        const opts = (S.apps || []).map((a) => ({ id: a.id, label: a.title || a.id }));
        if (b.app == null && opts[0]) b.app = opts[0].id;
        rows.push(field("App", opts.length ? select(opts, b.app, (v) => { b.app = v; })
          : h("div.muted.b-none", "the jobs source lists no apps")));
      } else if (f === "mute" || f === "run") {
        // binding.items holds both kinds in order: switches first, then run buttons.
        // An auto-apply item (bound elsewhere) is kept as it is; this form offers none.
        b.items = Array.isArray(b.items) ? b.items : [];
        const key = f === "mute" ? "scope" : "job";
        const items = f === "mute" ? (S.scopes || []).map((x) => ({ id: x, label: x + " notifications" }))
                                   : (S.jobs || []).map((j) => ({ id: j.id, label: "run " + j.name }));
        rows.push(checks(f === "mute" ? "Notification switches" : "Run buttons", items,
          (id) => b.items.some((it) => it.type === f && it[key] === id),
          (id, on) => {
            const rest = b.items.filter((it) => !(it.type === f && it[key] === id));
            b.items = on ? rest.concat([{ type: f, [key]: id }]) : rest;
            b.items.sort((x, y) => ["mute", "run", "auto_apply"].indexOf(x.type) - ["mute", "run", "auto_apply"].indexOf(y.type));
          },
          f === "mute" ? "no scopes listed" : "no runnable jobs listed"));
      }
    }
    form.replaceChildren(...rows);
    refresh();
  };

  let pgen = 0;
  const refresh = () => {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(async () => {
      const g = ++pgen;
      const probe = Object.assign({ id: draft.id || "preview" }, draft);
      let model;
      try { model = evalModel(kind, await apiPost("board/eval", { widget: probe, range: S.range, scope: S.scope })); }
      catch (e) { model = { kind, error: e.message }; }
      if (g !== pgen || !cardHost.isConnected) return;
      // The preview never hosts a live app frame: one tile per app on screen.
      if (kind === "app") {
        cardHost.replaceChildren(h("div.b-card-h", h("span.b-card-t", draft.title || "App")),
          h("div.b-card-b.muted", model.error ? "could not evaluate · " + model.error : "the app draws its tile here"),
          ...(model.foot ? [h("div.b-foot.mono", model.foot)] : []));
      } else {
        fillCard(cardHost, draft, model);
      }
    }, 250);
  };

  const save = h("button.s-btn.primary.b-save", { type: "button" }, existing ? "Save changes" : "Add to board");
  save.addEventListener("click", () => {
    if (existing) {
      S.draft = S.draft.map((w) => (w.id === existing.id ? Object.assign({}, w, draft) : w));
      closeEditor();
      render();
      const fresh = S.cards.get(existing.id);
      if (fresh) fillCard(fresh, draft, S.results.get(existing.id));
      evalWidget(S.draft.find((w) => w.id === existing.id));
    } else {
      closeEditor();
      addWidget(draft, slot);
    }
  });
  const remove = existing && !DESKTOP.matches
    ? h("button.s-btn.danger.b-remove", { type: "button", onclick: () => { closeEditor(); removeWidget(existing.id); } },
      "Remove from board")
    : null;

  const head = h("div.s-head.b-ed-head",
    h("button.s-back", { type: "button", "aria-label": "Back", onclick: () => closeEditor() }, "‹"),
    h("span.s-title", kindInfo(kind).label));
  editorEl = h("div.b-editor", { role: "dialog", "aria-label": kindInfo(kind).label + " widget" },
    head, h("div.b-ed-body", preview, form), h("div.b-ed-foot", remove, save));
  if (DESKTOP.matches) {
    S.dockView = "editor";
    S.dockHidden = false;
    dockEl.hidden = false;
    dockEl.replaceChildren(editorEl);
  } else {
    document.body.appendChild(editorEl);
  }
  build();
}

// The layout changes across 1024 px: the dock and the sheet belong to different
// surfaces, so crossing it puts the add panel where the new surface keeps it.
DESKTOP.addEventListener("change", () => {
  closeSheet();
  closeEditor();
  render();
});

ensureJobs().then(renderChips);
load();
