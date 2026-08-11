// Thalamus console — client. Polls /api/panes, renders the active session's
// screen, and drives every window by index — never changing the tmux active
// window, so a terminal attached to the same session stays where the operator
// left it.
"use strict";

// Every URL in this file is relative, so the app runs at the origin root or under
// whatever path a reverse proxy mounts it at. index.html canonicalizes a missing
// trailing slash before this file loads.

const POLL_MS = 1200;
const STALE_MS = 5000;

// `fetch` has no default timeout, and a phone gives it every chance to need one:
// a network handoff, a sleeping radio, a tailnet re-handshake. A request that
// stalls that way never settles — it neither resolves nor rejects — and the poll
// chain below is single-flight, so `pollInFlight` clears only in `poll()`'s
// `finally`. One stalled request therefore wedges the whole app until a reload:
// no transcript item ever lands again, and the view toggle stops repainting
// because every later `pollLoop()` returns at the latch. Both read as "the
// session paused". A request that cannot finish has to fail instead of hanging.
const REQ_TIMEOUT_MS = 10000;
// The latch is meant to be released by the timeout above. This is the backstop for
// the case that release never happens — belt and braces on the one failure that
// costs a reload.
const POLL_STUCK_MS = REQ_TIMEOUT_MS * 2;

// Same signature as `fetch`, so call sites read unchanged. AbortError surfaces as
// a rejection, which every caller already handles as "this poll failed".
function req(url, opts) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), REQ_TIMEOUT_MS);
  return fetch(url, Object.assign({}, opts, { signal: ctl.signal }))
    .finally(() => clearTimeout(timer));
}

// Per-session channel hue. `main` is fixed — it is the anchor every roster has —
// and every other scope draws a stable colour from its own name, so adding an
// expert manifest colours its tab without anyone editing a table here.
const MAIN_HUE = "#9a8cff";                                        // violet
const PALETTE = ["#e0a45c", "#4db6a6", "#6db3f2", "#e07a9c",       // amber, teal, sky, rose
                 "#8fce6b", "#c79bf0"];                            // moss, orchid
function hashHue(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (Math.imul(h, 31) + name.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
function hueFor(name, idx) {
  if (name === "main") return MAIN_HUE;
  return hashHue(name);
}
// In a room the colour comes from the ROOM, not the scope — so co-membership is
// what reads at a glance, which is the thing a room is. Two `homelab` tabs in
// different rooms are then different colours, and a room's `main` and `literature`
// are the same one. The room badge on the tab carries the name, because a palette
// of six cannot promise two rooms different colours.
function hueForRoom(room) { return hashHue("room:" + room); }
function hueOf(w) { return w.room ? hueForRoom(w.room) : hueFor(w.name, w.index); }

const els = {
  rail: document.getElementById("rail"),
  wsbar: document.getElementById("wsbar"),
  screen: document.getElementById("screen"),
  wrap: document.getElementById("screen-wrap"),
  msg: document.getElementById("msg"),
  hints: document.getElementById("hints"),
  send: document.getElementById("send"),
  form: document.getElementById("composer"),
  conn: document.getElementById("conn"),
  connLabel: document.getElementById("conn-label"),
  admin: document.getElementById("admin"),
  adminWindows: document.getElementById("admin-windows"),
  adminServices: document.getElementById("admin-services"),
  adminLog: document.getElementById("admin-log"),
  recycleNote: document.getElementById("recycle-note"),
  spawn: document.getElementById("spawn"),
  spawnScopes: document.getElementById("spawn-scopes"),
  spawnRooms: document.getElementById("spawn-rooms"),
  spawnDirs: document.getElementById("spawn-dirs"),
  spawnGo: document.getElementById("spawn-go"),
  spawnLog: document.getElementById("spawn-log"),
  spawnPip: document.getElementById("spawn-pip"),
  dialogue: document.getElementById("dialogue"),
  dialogueRoom: document.getElementById("dialogue-room"),
  dialogueText: document.getElementById("dialogue-text"),
  dialoguePartial: document.getElementById("dialogue-partial"),
  dialogueGo: document.getElementById("dialogue-go"),
  dialogueCheck: document.getElementById("dialogue-check"),
  dialogueLog: document.getElementById("dialogue-log"),
  dialogueX: document.getElementById("dialogue-x"),
  distillSec: document.getElementById("distill-sec"),
  distillList: document.getElementById("distill-list"),
  read: document.getElementById("read"),
  readWait: document.getElementById("read-wait"),
  viewToggle: document.getElementById("view-toggle"),
  sayToggle: document.getElementById("say-toggle"),
};

let windows = [];          // last known window list
let activeIdx = null;      // selected window index
let lastText = {};         // idx -> last captured screen (for change detection)
let lastOk = 0;            // ms of last good poll
let lastFitCols = 0;       // column count the current fit was computed for
let fitPx = 13;            // auto-fit size so a full pane line fits the viewport
// User nudge from fit. v2 key: nudges saved against the old (overflowing) fit
// baseline shouldn't carry over.
let fontDelta = +(localStorage.getItem("plane-font-delta2") || 0);

// ---- Workspaces (cwd contexts) ----
// A session is (expert, directory), not just expert — the same scope can be spawned
// in several projects, and the rail used to render both as an identical "homelab".
// `activeWs` is null for "all", else a cwd path the rail is filtered to.
let activeWs = localStorage.getItem("plane-workspace") || null;

function workspaces() {
  const seen = new Map(); // cwd -> label, in window order
  for (const w of windows) {
    if (w.cwd && !seen.has(w.cwd)) seen.set(w.cwd, w.cwd_label || w.cwd);
  }
  return [...seen].map(([path, label]) => ({ path, label }));
}
const multiWs = () => workspaces().length > 1;

// Rooms are the second dimension over the same set of windows. A session is now
// (expert, directory, room), and the two filters compose: they answer different
// questions — "what project" and "which collaboration" — and a session that is in
// a room is still somewhere.
let activeRoom = localStorage.getItem("plane-room") || null;
function roomsPresent() {
  return [...new Set(windows.map((w) => w.room).filter(Boolean))];
}
// Tabs the rail shows: all of them, or just the selected workspace's and room's.
const visibleWindows = () =>
  windows.filter((w) => (activeWs === null || w.cwd === activeWs) &&
                        (activeRoom === null || (w.room || "") === activeRoom));

function setChannelHue(hue) {
  document.documentElement.style.setProperty("--chan", hue);
}

function renderWsBar() {
  const ws = workspaces();
  const rooms = roomsPresent();
  // One directory and no rooms (the common case) → no bar at all, layout unchanged.
  if (ws.length < 2 && rooms.length === 0) {
    els.wsbar.hidden = true;
    els.wsbar.innerHTML = "";
    return;
  }
  els.wsbar.hidden = false;
  els.wsbar.innerHTML = "";
  const mk = (label, path, title) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ws" + (activeWs === path ? " on" : "");
    b.dataset.path = path === null ? "" : path;
    b.textContent = label;
    b.title = title || label;
    b.addEventListener("click", () => selectWorkspace(path));
    return b;
  };
  if (ws.length > 1) {
    els.wsbar.appendChild(mk("⌂ all", null, "Show every session"));
    for (const w of ws) {
      const count = windows.filter((x) => x.cwd === w.path).length;
      const full = (windows.find((x) => x.cwd === w.path) || {}).cwd_short || w.path;
      els.wsbar.appendChild(mk(`${w.label} ${count}`, w.path, full));
    }
  }
  if (!rooms.length) return;
  const mkRoom = (label, room, title, hue) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ws room-ws" + (activeRoom === room ? " on" : "");
    b.textContent = label;
    b.title = title;
    if (hue) b.style.setProperty("--chan-room", hue);
    b.addEventListener("click", () => selectRoom(activeRoom === room ? null : room));
    return b;
  };
  els.wsbar.appendChild(mkRoom("◈ any", null, "Sessions in every room, and outside"));
  for (const r of rooms) {
    const count = windows.filter((x) => x.room === r).length;
    els.wsbar.appendChild(
      mkRoom(`◈ ${r} ${count}`, r, `Only room ${r}`, hueForRoom(r)));
  }
  const solo = windows.filter((x) => !x.room).length;
  if (solo) els.wsbar.appendChild(mkRoom(`solo ${solo}`, "", "Only sessions in no room"));
  // Only when ONE room is selected. `null` is "any room" and `""` is "no room", and
  // neither names something a message could be addressed to — offering the control
  // there would invite a fan-out across rooms, which is the boundary a room is.
  if (activeRoom) {
    const say = document.createElement("button");
    say.type = "button";
    say.className = "ws room-ws room-say";
    say.textContent = "✎ say";
    say.title = `Say something to every live member of ${activeRoom}`;
    say.style.setProperty("--chan-room", hueForRoom(activeRoom));
    say.addEventListener("click", () => openDialogue(activeRoom));
    els.wsbar.appendChild(say);
  }
}

function selectRoom(room) {
  activeRoom = room;
  if (room === null) localStorage.removeItem("plane-room");
  else localStorage.setItem("plane-room", room);
  renderWsBar();
  renderRail();
  // The filter must never hide the window being viewed — the pane would keep
  // updating with no tab to explain where it came from.
  if (!visibleWindows().some((w) => w.index === activeIdx)) {
    const first = visibleWindows()[0];
    if (first) selectWindow(first.index);
  }
}

// Set the filter without touching the rail — for callers already inside a render
// pass (poll), which repaints once at the end.
function selectWorkspaceQuiet(path) {
  activeWs = path;
  if (path === null) localStorage.removeItem("plane-workspace");
  else localStorage.setItem("plane-workspace", path);
}

function selectWorkspace(path) {
  selectWorkspaceQuiet(path);
  renderWsBar();
  renderRail();
  // Filtering away the tab you were viewing would leave the screen showing a
  // session no visible tab points at — follow the filter into its first session.
  const vis = visibleWindows();
  if (vis.length && !vis.some((w) => w.index === activeIdx)) selectWindow(vis[0].index);
}

function renderRail() {
  els.rail.innerHTML = "";
  const showCwd = multiWs();
  for (const w of visibleWindows()) {
    const hue = hueOf(w);
    const tab = document.createElement("button");
    tab.className = "chan-tab" + (showCwd ? " two-line" : "");
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", String(w.index === activeIdx));
    tab.style.setProperty("--tab", hue);
    tab.dataset.idx = w.index;
    tab.title = (w.room ? `[${w.room}] ` : "") +
      (w.cwd_short ? `${w.name} — ${w.cwd_short}` : w.name);
    tab.innerHTML =
      `<span class="dot"></span>` +
      `<span class="tab-text">` +
      `<span class="nm">${w.room ? `<span class="room">◈</span>` : ""}` +
      `${escapeHtml(w.name)}</span>` +
      (showCwd ? `<span class="cwd">${escapeHtml(w.cwd_label || "?")}</span>` : "") +
      `</span>`;
    tab.classList.toggle("recycling", !!w.recycling);
    tab.addEventListener("click", () => selectWindow(w.index));
    els.rail.appendChild(tab);
  }
}

// Header hue, tab title, and the command cache follow the active window — including
// when poll() picks one for us (first load, or the viewed tab going away), which
// previously left the chrome showing the wrong channel.
let chromeIdx = null;
function syncActiveChrome() {
  if (activeIdx === chromeIdx) return;
  chromeIdx = activeIdx;
  const w = windows.find((x) => x.index === activeIdx);
  if (!w) return;
  setChannelHue(hueOf(w));
  document.title = w.cwd_label ? `${w.name} · ${w.cwd_label}` : `${w.name} · Thalamus`;
  commands = null; // project skills are per-directory; refetch for this window
}

function selectWindow(idx) {
  activeIdx = idx;
  syncActiveChrome();
  for (const tab of els.rail.children) {
    tab.setAttribute("aria-selected", String(+tab.dataset.idx === idx));
  }
  const cur = windows.find((x) => x.index === idx);
  renderedText = null; // force a repaint even if the new window's text matches
  pendingScreen = null;
  if (cur) renderScreen(cur.lines);
  computeFit(); // window widths can differ; refit for the one now shown
  els.msg.focus({ preventScroll: true });
}

let pendingScreen = null;   // capture waiting to paint while a selection is held
let renderedText = null;    // text currently painted (skip no-op repaints)

// Is there a live (non-collapsed) text selection inside the screen? On a phone the
// 1.2s repaint used to replace the pane every poll, wiping the highlight before it
// could be copied. While a selection is held we defer the repaint instead.
function selectionInScreen() {
  // A hidden pane holds no highlight worth protecting, and this is not a shortcut:
  // switching to the read view hides `.screen` with the selection still anchored
  // inside it, and the browser does not reliably collapse it. Without this line the
  // guard below answers "yes" forever, every repaint defers, and the pane is frozen
  // on the snapshot it held at the moment of the toggle — including after switching
  // back, since `applyView` resets `renderedText` but this check runs first.
  if (els.screen.hidden) return false;
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return false;
  return els.screen.contains(sel.anchorNode) && els.screen.contains(sel.focusNode);
}

// Escape HTML first, then wrap bare URLs as real <a>. Trailing sentence punctuation
// is left outside the link. Tap opens; long-press gives the native copy menu — so a
// login URL in the pane becomes reachable without fighting the text selector.
function linkify(text) {
  return escapeHtml(text).replace(
    /(https?:\/\/[^\s<>"'()]+[^\s<>"'().,;:!?])/g,
    (u) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${u}</a>`);
}

// ---- Markdown ----
// The transcript carries Claude's own markdown, and the read view was delivering it
// as literal characters: a fence arrived as three backticks and a language name, `**`
// bracketed every emphasis. Rendering it is not decoration. A code block is the one
// thing in a turn that must *not* reflow — a wrapped shell command is a misread
// command — and prose is the one thing that must. A single `white-space` rule cannot
// serve both, which is why this projects to block elements rather than tuning the
// wrap; `.rd-prose` drops to `normal` and structure carries the line breaks.
//
// Escaping happens ONCE, at the top of `mdInline`, and every later pass runs over
// already-escaped text and injects only tags written here. That ordering is the whole
// safety argument, and it is load-bearing: transcript text is not the operator's own
// writing, it is whatever a tool printed, so no path may reach innerHTML with raw
// input. Link hrefs are restricted to http(s) and site-relative for the same reason —
// a `javascript:` URL in a tool result must stay inert text.
//
// The subset is deliberate: fences, inline code, headings, lists, quotes, rules,
// emphasis, links, pipe tables. Both fences must own their line — triple backticks
// mid-sentence are prose, not a block. The closing alternative is `(?![\s\S])`,
// absolute end of input, and NOT `$`: under /m, `$` matches end of *line*, which
// closes every block after its first line.
const MD_FENCE = /^ {0,3}```([A-Za-z0-9_+#.-]*)[ \t]*\n([\s\S]*?)(?:^ {0,3}```[ \t]*$|(?![\s\S]))/gm;

// A table is the one block whose meaning is positional: the column a cell sits in
// is what the cell says. So it renders as a real table and holds its columns, the
// way a code block holds its lines, and scrolls on its own axis — the page still
// never scrolls sideways. Reflowing the columns to fit 390px would preserve every
// character and lose the thing the characters were arranged to say.
//
// A table is claimed only on a header row *plus* a delimiter row directly beneath
// it with a matching cell count — GFM's rule, and the reason a lone `---` under a
// sentence is still a rule under a paragraph. Both rows must carry a real `|`, so
// single-column tables are written `| Name |`; without that, every paragraph
// followed by `---` becomes a one-column table.
const MD_TDELIM = /^ {0,3}[|\-: \t]*-[|\-: \t]*$/; // shape only; cells checked in mdTableAt
const MD_TCELL = /^:?-+:?$/;                       // one delimiter cell, alignment optional
const MD_TBAR = /(?:^|[^\\])\|/;                   // a pipe that isn't escaped as `\|`
const MD_TBULLET = /^\s*(?:[-*+]|\d+[.)])\s/;      // a bullet outranks a table row

function renderMarkdown(text) {
  // NUL is the placeholder sentinel below; it has no business in a transcript.
  const src = String(text == null ? "" : text).replace(/\r\n/g, "\n").replace(/\u0000/g, "");
  let out = "";
  let last = 0;
  let m;
  MD_FENCE.lastIndex = 0;
  while ((m = MD_FENCE.exec(src)) !== null) {
    if (m[0] === "") { MD_FENCE.lastIndex++; continue; }   // zero-width guard
    out += mdBlocks(src.slice(last, m.index));
    out += mdCode(m[1], m[2]);
    last = MD_FENCE.lastIndex;
  }
  return out + mdBlocks(src.slice(last));
}

// An unterminated fence is normal, not an error: a turn can be written while the
// block is still open, and showing the code is better than showing the backticks.
function mdCode(lang, code) {
  const label = lang
    ? `<div class="rd-code-lang">${escapeHtml(lang)}</div>`
    : "";
  return `<div class="rd-codewrap">${label}` +
         `<pre class="rd-code"><code>${escapeHtml(code.replace(/\n+$/, ""))}</code></pre></div>`;
}

// Cells split on unescaped pipes; `\|` is a literal pipe and never a border. The
// split runs before any inline pass, so a pipe inside backticks still ends a cell —
// that is GFM's ordering, and the fix a writer reaches for (`\|`) works here too.
// A leading or trailing bar is a border, not an empty column.
function mdCells(row) {
  const s = row.trim();
  const cells = [];
  let cur = "";
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "\\" && s[i + 1] === "|") { cur += "|"; i++; continue; }
    if (s[i] === "|") { cells.push(cur); cur = ""; continue; }
    cur += s[i];
  }
  cells.push(cur);
  if (cells.length > 1 && s.startsWith("|") && !cells[0].trim()) cells.shift();
  if (cells.length > 1 && MD_TBAR.test(s) && s.endsWith("|") && !cells[cells.length - 1].trim()) cells.pop();
  return cells.map((c) => c.trim());
}

// Claim a table at `i` or return null — the caller keeps its line loop either way.
// The delimiter row must have exactly as many cells as the header: a row of dashes
// that happens to sit under a sentence is a rule, and a mismatch means whatever this
// is, it is not a table whose columns line up.
function mdTableAt(lines, i) {
  const head = lines[i], delim = lines[i + 1];
  if (delim == null || !MD_TBAR.test(head) || !MD_TBAR.test(delim)) return null;
  if (MD_TBULLET.test(head) || !MD_TDELIM.test(delim)) return null;
  const cols = mdCells(head);
  const spec = mdCells(delim);
  if (spec.length !== cols.length || !spec.every((c) => MD_TCELL.test(c))) return null;
  const rows = [];
  let end = i + 2;
  while (end < lines.length && lines[end].trim() && MD_TBAR.test(lines[end])
         && !MD_TBULLET.test(lines[end])) {
    rows.push(mdCells(lines[end]));
    end++;
  }
  return { html: mdTable(cols, spec, rows), end: end - 1 };
}

// Short rows are padded and long ones truncated to the header's width, because a
// ragged row would silently shift every cell after the gap into the wrong column.
function mdTable(cols, spec, rows) {
  const align = spec.map((c) =>
    c.endsWith(":") ? (c.startsWith(":") ? " rd-tc" : " rd-tr") : "");
  const cell = (tag, text, n) =>
    `<${tag} class="rd-td${align[n] || ""}">${mdInline(text || "")}</${tag}>`;
  const head = `<tr>${cols.map((c, n) => cell("th", c, n)).join("")}</tr>`;
  const body = rows.map((r) =>
    `<tr>${cols.map((_, n) => cell("td", r[n], n)).join("")}</tr>`).join("");
  return `<div class="rd-tablewrap"><table class="rd-table">` +
         `<thead>${head}</thead>` + (body ? `<tbody>${body}</tbody>` : "") +
         `</table></div>`;
}

function mdBlocks(chunk) {
  if (!chunk) return "";
  const out = [];
  let para = [];
  let list = null;
  let quote = [];
  const flushPara = () => {
    if (para.length) out.push(`<p class="rd-p">${mdInline(para.join("\n"))}</p>`);
    para = [];
  };
  const flushList = () => {
    if (list) {
      out.push(`<${list.tag} class="rd-list">` +
        list.items.map((i) => `<li>${mdInline(i)}</li>`).join("") + `</${list.tag}>`);
    }
    list = null;
  };
  const flushQuote = () => {
    if (quote.length) out.push(`<blockquote class="rd-quote">${mdInline(quote.join("\n"))}</blockquote>`);
    quote = [];
  };
  const flushAll = () => { flushPara(); flushList(); flushQuote(); };

  // Indexed rather than for-of: a table is the one block that cannot be recognised
  // from its own line — a header row is prose until the delimiter row under it says
  // otherwise — so the loop needs to look ahead and then skip what it consumed.
  const lines = chunk.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let m;
    if (!line.trim()) { flushAll(); continue; }
    if ((m = /^ {0,3}(#{1,6})\s+(.*)$/.exec(line))) {
      flushAll();
      out.push(`<div class="rd-h rd-h${m[1].length}">${mdInline(m[2].trim())}</div>`);
    } else if (/^ {0,3}([-*_])[ \t]*(?:\1[ \t]*){2,}$/.test(line)) {
      flushAll();
      out.push('<hr class="rd-hr">');
    } else if ((m = /^ {0,3}>\s?(.*)$/.exec(line))) {
      flushPara(); flushList();
      quote.push(m[1]);
    } else if ((m = mdTableAt(lines, i))) {
      // Ahead of the list branches, so a table may interrupt a paragraph the way
      // GFM allows; behind them by MD_TBULLET, so `- a | b` stays a bullet.
      flushAll();
      out.push(m.html);
      i = m.end;
    } else if ((m = /^\s*[-*+]\s+(.*)$/.exec(line))) {
      flushPara(); flushQuote();
      if (!list || list.tag !== "ul") { flushList(); list = { tag: "ul", items: [] }; }
      list.items.push(m[1]);
    } else if ((m = /^\s*\d+[.)]\s+(.*)$/.exec(line))) {
      flushPara(); flushQuote();
      if (!list || list.tag !== "ol") { flushList(); list = { tag: "ol", items: [] }; }
      list.items.push(m[1]);
    } else if (list && /^\s{2,}\S/.test(line)) {
      // A wrapped or continued list item belongs to the bullet above it, not to a
      // new paragraph that would break the list in half.
      list.items[list.items.length - 1] += "\n" + line.trim();
    } else {
      flushList(); flushQuote();
      para.push(line);
    }
  }
  flushAll();
  return out.join("");
}

function mdInline(raw) {
  // Held spans are finished HTML parked behind a sentinel so later passes cannot
  // reach inside them — emphasis must not fire inside code, and linkify must not
  // re-wrap an anchor it already made.
  const holds = [];
  const hold = (html) => `\u0000${holds.push(html) - 1}\u0000`;
  let s = escapeHtml(raw);
  s = s.replace(/`([^`\n]+)`/g, (_, c) => hold(`<code class="rd-ic">${c}</code>`));
  s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+|\/[^\s)]*)\)/g,
    (_, t, u) => hold(`<a href="${u}" target="_blank" rel="noopener noreferrer">${t}</a>`));
  s = s.replace(/(https?:\/\/[^\s<>"'()]+[^\s<>"'().,;:!?])/g,
    (u) => hold(`<a href="${u}" target="_blank" rel="noopener noreferrer">${u}</a>`));
  s = s.replace(/\*\*([^\s*][^*]*?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
  // Emphasis needs boundaries on both sides or `snake_case_name` and a bare `*`
  // in a glob become italics.
  s = s.replace(/(^|[\s(])[*_]([^\s*_][^*_]*?)[*_](?=[\s).,;:!?]|$)/g, "$1<em>$2</em>");
  s = s.replace(/\n/g, "<br>");
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => holds[+i]);
}

// Zero windows is a different failure from a window with no output, and it is the
// first thing a fresh install shows. The server answered, so the beacon is already
// green; without this the page is a blank rectangle that manages to look connected
// and broken at the same time. `thalamus console` deliberately serves before the
// roster exists — it prints that to its own stderr, which nobody holding a phone can
// read, so this is where that sentence actually reaches the operator. Say which
// session was looked for and how to make one: the console bridges a session, it
// never creates one.
function renderNoSession(session) {
  const s = session || "thalamus";
  els.screen.className = "screen-empty onboard";
  els.screen.textContent =
    `No windows in tmux session "${s}".\n\n` +
    `The console bridges a tmux session — it doesn't create one. ` +
    `Start the roster on the host:\n\n` +
    `  thalamus roster\n\n` +
    `Or bridge any tmux session you like:\n\n` +
    `  tmux new -d -s ${s} -n main`;
  renderedText = "";
}

function paintScreen(text) {
  if (!text || !text.trim()) {
    els.screen.className = "screen-empty";
    els.screen.textContent = "No output captured. The window may be idle — send a message or a key.";
  } else {
    els.screen.className = "screen";
    els.screen.innerHTML = linkify(text.replace(/\s+$/g, ""));
  }
  renderedText = text;
}

function renderScreen(text) {
  const sc = scroller();
  const atBottom = sc.scrollHeight - sc.scrollTop - sc.clientHeight < 40;
  if (selectionInScreen()) { pendingScreen = text; return; } // don't clobber a highlight
  if (text === renderedText) return;                         // unchanged; keep links stable
  pendingScreen = null;
  paintScreen(text);
  // Re-resolve: paintScreen swaps `.screen` for `.screen-empty` and back, so under a
  // frame the element that scrolls is not the one measured a moment ago.
  const after = scroller();
  if (atBottom) after.scrollTop = after.scrollHeight;
}

// When the user releases a selection, apply whatever repaint we deferred.
document.addEventListener("selectionchange", () => {
  if (pendingScreen !== null && !selectionInScreen()) {
    const t = pendingScreen;
    pendingScreen = null;
    renderScreen(t);
  }
});

// ---- Read view ----
// The pane mirror shows a *rendering* of a session — an 80-column repaint with the
// colours stripped by tmux and no structure left. This shows the session itself:
// the server projects Claude Code's own JSONL transcript into prose and one-line
// tool chips (console/transcript.py). Two things it buys on a phone that no amount
// of work on the mirror could — text that wraps to the screen instead of to fixed
// columns, and a forty-line diff that reads as `Edit src/foo.py`.
//
// It is a second view, never a replacement. A pending permission prompt is never
// written to the transcript at all, so a tool call with no result is either running
// or blocked on you and the feed cannot tell which. That is what the wait banner is
// for, and why the terminal stays one tap away.

let readMode = localStorage.getItem("plane-read-mode") === "1";
let readShownIdx = null;
const readState = new Map();
// How long a tool call may sit unresolved before we say so. Long enough that
// ordinary calls (a test run, a build) never trip it.
const PENDING_HINT_MS = 8000;

function readStateFor(idx) {
  let st = readState.get(idx);
  if (!st) {
    st = { seq: 0, sid: null, items: new Map(), nodes: new Map(), order: [],
           pendingSince: 0, reason: null };
    readState.set(idx, st);
  }
  return st;
}

function applyView() {
  els.viewToggle.textContent = readMode ? "term" : "read";
  els.viewToggle.classList.toggle("on", readMode);
  els.screen.hidden = readMode;
  els.read.hidden = !readMode;
  // Returning to the pane repaints from scratch, so a capture deferred before the
  // toggle is stale by definition — dropping it keeps it from being flushed over
  // fresher content by a later `selectionchange`.
  if (!readMode) { els.readWait.hidden = true; renderedText = null; pendingScreen = null; }
  else { readShownIdx = null; }   // force a re-attach of this window's nodes
}

function setReadMode(on) {
  readMode = on;
  localStorage.setItem("plane-read-mode", on ? "1" : "0");
  applyView();
  pollLoop();
}

els.viewToggle.addEventListener("click", () => setReadMode(!readMode));

// --- Speaking the latest reply -------------------------------------------
// One <audio> for the app, reused rather than recreated: a mobile browser grants
// playback permission to an element the user has activated, and a fresh element
// per tap starts from no permission every time.
const sayAudio = new Audio();
let saying = false;
let sayIdx = null;      // window the current utterance belongs to

function sayUrl(idx, restart, from) {
  let url = "api/say?index=" + encodeURIComponent(idx);
  if (restart) url += "&restart=1";
  if (from !== undefined && from !== null) url += "&from=" + encodeURIComponent(from);
  return url;
}

function setSayState(state) {
  // "" idle · "on" speaking · "done" caught up · "err" the last attempt failed
  els.sayToggle.classList.toggle("on", state === "on");
  els.sayToggle.classList.toggle("bad", state === "err");
  els.sayToggle.classList.toggle("done", state === "done");
  els.sayToggle.textContent = state === "on" ? "stop" : "say";
}

function stopSaying() {
  sayAudio.pause();
  saying = false;
  setSayState("");
}

function startSaying(idx, restart, from) {
  // Assign src and play in the same turn as the click. Awaiting anything first
  // and playing afterwards loses the user activation, and the phone — the device
  // this exists for — silently refuses to play.
  sayIdx = idx;
  sayAudio.src = sayUrl(idx, restart, from);
  saying = true;
  setSayState("on");
  sayAudio.play().catch(() => { saying = false; setSayState("err"); });
}

function speakActiveWindow(restart) {
  if (saying) { stopSaying(); return; }
  if (activeIdx === null) return;
  startSaying(activeIdx, restart, undefined);
}

/** Speak from a block the reader tapped, treating everything above it as heard. */
function speakFrom(idx, seq) {
  if (saying) sayAudio.pause();
  startSaying(idx, false, seq);
}

// Playback finished, so the listening position may move. Stopping early
// deliberately does not ack: the next tap resumes where your ears stopped, not
// where the synthesiser did.
function ackSpoken() {
  if (sayIdx === null) return;
  post("api/say/ack", { index: sayIdx }).catch(() => {});
}

sayAudio.addEventListener("ended", () => {
  saying = false;
  setSayState("");
  ackSpoken();
});
// A 204 means nothing new to say. The element reports it as an error because
// there is no audio to decode, so it is caught here and shown as "caught up"
// rather than as a failure.
sayAudio.addEventListener("error", () => {
  saying = false;
  setSayState(sayAudio.networkState === sayAudio.NETWORK_NO_SOURCE ? "done" : "err");
});
els.sayToggle.addEventListener("click", () => speakActiveWindow(false));
// Long-press re-reads the current turn from its start, for when you missed it
// rather than when you want what came next.
let sayHold = null;
els.sayToggle.addEventListener("pointerdown", () => {
  sayHold = setTimeout(() => { sayHold = null; stopSaying(); speakActiveWindow(true); }, 600);
});
for (const ev of ["pointerup", "pointerleave", "pointercancel"]) {
  els.sayToggle.addEventListener(ev, () => { clearTimeout(sayHold); sayHold = null; });
}

function readItemNode(idx, it) {
  const el = document.createElement("div");
  el.className = "rd rd-" + it.kind + (it.sidechain ? " rd-side" : "");
  if (it.kind === "tool") {
    el.innerHTML =
      `<div class="rd-head"><span class="rd-name"></span><span class="rd-sum"></span>` +
      `<span class="rd-dot"></span></div><div class="rd-ask" hidden></div>` +
      `<div class="rd-body" hidden></div>`;
    el.querySelector(".rd-head").addEventListener("click", () => toggleBody(idx, it.id, el));
  } else if (it.kind === "thinking") {
    el.innerHTML = `<div class="rd-head"><span class="rd-name">thinking</span>` +
                   `<span class="rd-sum"></span></div><div class="rd-body" hidden></div>`;
    el.querySelector(".rd-head").addEventListener("click", () => {
      const b = el.querySelector(".rd-body");
      b.textContent = it.text;
      b.hidden = !b.hidden;
    });
  } else if (it.kind === "prose") {
    // Tap a paragraph to start listening there. The gesture reads as "begin
    // here", so everything above it is recorded as already heard — which it
    // effectively is, since you just read it to find the place.
    //
    // The start point rides the audio URL rather than a POST that precedes it.
    // Marking first and then playing would put the play() call after an await
    // and spend the user activation, which is the one thing a phone will not
    // forgive.
    el.addEventListener("click", () => {
      if (window.getSelection && String(window.getSelection()).length) return; // selecting, not marking
      for (const other of els.read.querySelectorAll(".rd-mark")) other.classList.remove("rd-mark");
      el.classList.add("rd-mark");
      speakFrom(idx, it.seq);
    });
  }
  return el;
}

function updateReadNode(el, it) {
  if (it.kind === "tool") {
    el.querySelector(".rd-name").textContent = it.name;
    el.querySelector(".rd-sum").textContent =
      it.summary.startsWith(it.name) ? it.summary.slice(it.name.length).trim() : it.summary;
    el.querySelector(".rd-dot").className = "rd-dot " + (it.status || "pending");
    renderAsk(el.querySelector(".rd-ask"), it);
  } else if (it.kind === "thinking") {
    el.querySelector(".rd-sum").textContent = " ".concat(it.text).replace(/\s+/g, " ").slice(0, 90) + "…";
  } else {
    // Prose and operator turns are the point of this view: real wrapped text,
    // with the markdown it was written in actually rendered.
    el.innerHTML = renderMarkdown(it.text);
  }
}

// A question put to the operator, shown in full rather than collapsed to a chip:
// it is the one tool call in the feed that is not a report of work done but a
// request for something only the reader can supply. The dialog itself is a TUI
// modal that writes nothing while it is up, so without this the session simply
// stops — the read view's most confusing state, and the whole reason the pane had
// to be the only place a blocked session was visible.
//
// Built with textContent throughout. This is tool input, the same trust class as
// every other string in the feed, and it must not reach innerHTML.
function renderAsk(host, it) {
  if (!host) return;
  const asks = (it.ask || []).filter((q) => q && q.question);
  if (!asks.length) { host.hidden = true; return; }
  const pending = (it.status || "pending") === "pending";
  // Rebuilt only when something the reader can see actually changed.
  const stamp = asks.length + ":" + pending;
  if (host.dataset.stamp === stamp) return;
  host.dataset.stamp = stamp;
  host.hidden = false;
  host.className = "rd-ask" + (pending ? " waiting" : "");
  host.textContent = "";
  for (const q of asks) {
    const qEl = document.createElement("div");
    qEl.className = "rd-q";
    qEl.textContent = q.question;
    host.appendChild(qEl);
    if (q.options && q.options.length) {
      const ul = document.createElement("ul");
      ul.className = "rd-opts";
      for (const label of q.options) {
        const li = document.createElement("li");
        li.textContent = label;
        ul.appendChild(li);
      }
      host.appendChild(ul);
    }
  }
  if (pending) {
    // Say where to act, not just that action is needed. Typing an answer into the
    // composer is the trap: a modal discards the text and Enter actuates whatever
    // option is highlighted, so the answer would be silently wrong.
    const note = document.createElement("div");
    note.className = "rd-ask-note";
    note.textContent = "waiting on you — answer in term with ↑ ↓ and ⏎";
    host.appendChild(note);
  }
}

async function toggleBody(idx, id, el) {
  const body = el.querySelector(".rd-body");
  if (!body.hidden) { body.hidden = true; return; }
  body.hidden = false;
  if (body.dataset.loaded) return;
  body.textContent = "…";
  try {
    const r = await req(`api/read/body?index=${idx}&item=${id}`, { cache: "no-store" });
    const d = await r.json();
    body.textContent = d.body || "(no output)";
    body.dataset.loaded = "1";
  } catch (e) {
    body.textContent = "(could not load)";
  }
}

function renderRead(idx) {
  const st = readStateFor(idx);
  const sc = scroller();
  const atBottom = sc.scrollHeight - sc.scrollTop - sc.clientHeight < 60;

  if (st.reason) {
    els.read.className = "read read-note";
    // `pending` is the state every new window starts in and is not a fault: the
    // transcript is written on the first turn, so saying "can't tell which session"
    // here was both wrong and alarming — the session is known, it is just empty.
    els.read.textContent =
      st.reason === "no-package"
        ? "The read view needs the thalamus package alongside the console; this one is running as a bare tmux bridge."
      : st.reason === "pending"
        ? "Nothing written yet — this session hasn't taken its first turn. Send it a message and the transcript starts here."
      : "Can't tell which session is in this window yet. Sessions started before the console learned to record it resolve on their next restart (INFRA → restart).";
    readShownIdx = null;
    return;
  }
  els.read.className = "read";
  if (readShownIdx !== idx) {          // switched windows — re-attach this one's nodes
    els.read.textContent = "";
    // Only what has already been built: on a cold open the ids are known a beat
    // before their nodes exist, and the build loop below appends the rest in the
    // same ascending order.
    for (const id of st.order) {
      const built = st.nodes.get(id);
      if (built) els.read.appendChild(built);
    }
    readShownIdx = idx;
  }
  for (const id of st.order) {
    const it = st.items.get(id);
    let node = st.nodes.get(id);
    if (!node) {
      node = readItemNode(idx, it);
      st.nodes.set(id, node);
      els.read.appendChild(node);
    }
    if (node.dataset.seq !== String(it.seq)) {
      updateReadNode(node, it);
      node.dataset.seq = String(it.seq);
    }
  }
  if (!st.order.length) {
    els.read.className = "read read-note";
    els.read.textContent = "Nothing in this session's transcript yet.";
  }
  // A question is known to be blocked on the reader the moment it is asked, so it
  // says so immediately; an ordinary tool call has to wait out the hint delay,
  // since a slow one is normal and a banner over every test run is noise.
  const waiting = st.pendingSince &&
    (st.pendingAsk || Date.now() - st.pendingSince > PENDING_HINT_MS);
  els.readWait.hidden = !waiting;
  if (waiting) {
    els.readWait.textContent = st.pendingAsk
      ? "this session is waiting on your answer — open term and pick with ↑ ↓ then ⏎"
      : "a tool call is still open — if it's waiting for your approval, that prompt is in the terminal view";
  }
  if (atBottom) { const after = scroller(); after.scrollTop = after.scrollHeight; }
}

async function pollRead(idx) {
  const st = readStateFor(idx);
  const r = await req(`api/read?index=${idx}&since=${st.seq}`, { cache: "no-store" });
  if (!r.ok) throw new Error(r.status);
  const d = await r.json();
  if (!d.available) { st.reason = d.reason || "unresolved"; renderRead(idx); return; }
  st.reason = null;
  // A recycle or a /clear mints a new session id and a new transcript. Everything
  // held for the old one is about a process that no longer exists — drop it and let
  // the next poll cold-open the replacement.
  if (st.sid && d.session_id !== st.sid) {
    readState.delete(idx);
    readShownIdx = null;
    return;
  }
  st.sid = d.session_id;
  for (const it of d.items || []) {
    if (!st.items.has(it.id)) st.order.push(it.id);
    st.items.set(it.id, it);
  }
  st.order.sort((a, b) => a - b);
  st.seq = Math.max(st.seq, d.seq || 0);
  // The newest item on the *main* thread, not simply the newest item. A subagent
  // writes into the same transcript, so while the session sits blocked on a
  // question its sidechain keeps emitting — and a bare last-item test then reads
  // that traffic as progress and never says the session is waiting on you.
  let latest = null;
  for (let i = st.order.length - 1; i >= 0; i--) {
    const it = st.items.get(st.order[i]);
    if (it && !it.sidechain) { latest = it; break; }
  }
  if (latest && latest.kind === "tool" && latest.status === "pending") {
    if (!st.pendingSince) st.pendingSince = Date.now();
    st.pendingAsk = !!(latest.ask && latest.ask.length);
  } else {
    st.pendingSince = 0;
    st.pendingAsk = false;
  }
  renderRead(idx);
}

// A session filtered out of the rail still needs to be able to announce itself —
// otherwise picking a workspace makes you blind to the others. Its workspace chip
// carries the signal that its hidden tab's dot would have.
function updateWsSignal(next) {
  if (els.wsbar.hidden) return;
  for (const chip of els.wsbar.children) {
    const p = chip.dataset.path;
    const hidden = p && activeWs !== null && p !== activeWs;
    chip.classList.toggle("live", !!hidden && next.some((w) =>
      w.cwd === p && lastText[w.index] !== undefined && lastText[w.index] !== w.lines));
  }
}

function updateDots(next) {
  updateWsSignal(next);
  for (const tab of els.rail.children) {
    const idx = +tab.dataset.idx;
    const w = next.find((x) => x.index === idx);
    if (!w) continue;
    tab.classList.toggle("recycling", !!w.recycling);
    const changed = lastText[idx] !== undefined && lastText[idx] !== w.lines;
    tab.classList.toggle("active-live", changed);
    if (changed) {
      tab.classList.remove("pulse");
      void tab.offsetWidth; // restart animation
      tab.classList.add("pulse");
    }
  }
}

function setConn(state) {
  els.conn.className = "conn " + state;
  els.connLabel.textContent =
    state === "live" ? "live" : state === "stale" ? "no signal" : "connecting";
}

async function poll() {
  try {
    const r = await req("api/panes", { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    const data = await r.json();
    const next = data.windows || [];
    lastOk = Date.now();

    const changed = next.length !== windows.length ||
      next.some((w, i) => !windows[i] || windows[i].index !== w.index ||
                          windows[i].name !== w.name || windows[i].cwd !== w.cwd);

    windows = next;
    // A workspace that no longer has any session (its last tab was closed, or a
    // stale filter came back from localStorage) would hide every tab — drop it.
    if (activeWs !== null && !windows.some((w) => w.cwd === activeWs)) selectWorkspaceQuiet(null);
    // A just-spawned window is the highest index — jump to it once it appears, and
    // follow it into its workspace so the filter doesn't hide what we just opened.
    if (selectNewestOnNextPoll && windows.length) {
      const newest = windows.reduce((a, b) => (b.index > a.index ? b : a));
      selectNewestOnNextPoll = false;
      if (activeWs !== null && newest.cwd !== activeWs) selectWorkspaceQuiet(newest.cwd);
      activeIdx = newest.index;
    }
    if (activeIdx === null || !windows.some((w) => w.index === activeIdx)) {
      const vis = visibleWindows();
      const act = vis.find((w) => w.active) || vis[0];
      activeIdx = act ? act.index : null;
    }
    if (changed) { renderWsBar(); renderRail(); }
    syncActiveChrome();
    renderDistill(data.distill || []);

    updateDots(next);
    const cur = windows.find((w) => w.index === activeIdx);
    if (!cur) {
      // No window to read. The onboarding text lives in the pane element, so show
      // that regardless of which view is selected — a read view of nothing would
      // just be a second empty rectangle.
      els.screen.hidden = false;
      els.read.hidden = true;
      els.readWait.hidden = true;
      renderNoSession(data.session);
    } else if (readMode) {
      els.screen.hidden = true;
      els.read.hidden = false;
      await pollRead(cur.index).catch(() => {});
    } else {
      renderScreen(cur.lines);
    }
    if (cur && cur.closing) {
      els.recycleNote.hidden = false;
      els.recycleNote.textContent = "session ending & distilling to memory — this tab will close";
    } else if (cur && cur.recycling) {
      els.recycleNote.hidden = false;
      els.recycleNote.textContent = "session restarting — input is paused until the new process is up";
    } else {
      els.recycleNote.hidden = true;
    }
    if (!els.admin.hidden) renderAdminWindows();
    if (activeCols() !== lastFitCols) computeFit(); // e.g. an attached terminal resized it
    for (const w of next) lastText[w.index] = w.lines;

    setConn("live");
    // keep selection styling in sync
    for (const tab of els.rail.children) {
      tab.setAttribute("aria-selected", String(+tab.dataset.idx === activeIdx));
    }
  } catch (e) {
    if (Date.now() - lastOk > STALE_MS) setConn("stale");
  }
}

async function post(path, body) {
  try {
    await req(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setTimeout(poll, 120); // reflect the change fast
  } catch (e) { /* next poll will show state */ }
}

function sendMessage() {
  if (activeIdx === null) return;
  const text = els.msg.value;
  if (!text.trim()) return;
  post("api/send",{ index: activeIdx, text });
  els.msg.value = "";
  autosize();
  updateHints();
}

function autosize() {
  els.msg.style.height = "auto";
  els.msg.style.height = Math.min(els.msg.scrollHeight, window.innerHeight * 0.4) + "px";
}

// Auto-fit: pick a font size so the active window's full column width fits the
// screen area — no horizontal scroll — then apply the user's A−/A+ nudge on top.
function activeCols() {
  const w = windows.find((x) => x.index === activeIdx);
  return (w && w.width) || 60;
}
// Glyph advances don't scale linearly with font-size at small fractional sizes
// (hinting/rounding), so measure a full line AT the candidate size and step down
// until it truly fits — a linear estimate from a large probe overflows on some
// devices (seen on Pixel 9 Pro).
const probe = document.createElement("pre");
probe.style.cssText =
  "position:absolute;left:-9999px;top:0;visibility:hidden;white-space:pre;margin:0;padding:0";
document.body.appendChild(probe);
function lineWidthAt(px, cols) {
  probe.style.fontFamily = getComputedStyle(els.screen).fontFamily;
  probe.style.fontSize = px.toFixed(2) + "px";
  probe.textContent = "M".repeat(cols);
  return probe.getBoundingClientRect().width;
}
function computeFit() {
  const cs = getComputedStyle(els.screen);
  const padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
  // Under a frame the text is sized to the panel, not to the window.
  const box = framed() ? panelRect().w : els.wrap.clientWidth;
  const avail = box - padX - 1; // -1 guards rounding overflow
  const cols = activeCols();
  let px = (avail / cols) / (lineWidthAt(100, cols) / 100 / cols); // linear first guess
  px = Math.max(7, Math.min(30, px));
  for (let i = 0; i < 40 && px > 7 && lineWidthAt(px, cols) > avail; i++) px -= 0.1;
  fitPx = px;
  lastFitCols = cols;
  applyFont();
}
function applyFont() {
  const px = Math.max(7, Math.min(40, fitPx + fontDelta));
  document.documentElement.style.setProperty("--screen-size", px.toFixed(2) + "px");
  // The read view is not column-fitted — that is the whole difference between it
  // and the pane. Its text wraps to the screen, so sizing it by what makes 80
  // monospace columns fit would blow prose up to 24px on a desktop and shrink it
  // to nothing on a narrow phone. Fixed reading size, still moved by A−/A+.
  const rpx = Math.max(11, Math.min(26, 15 + fontDelta));
  document.documentElement.style.setProperty("--read-size", rpx.toFixed(2) + "px");
}

// ---- Slash-command hints ----
// Typing "/" at the start of the composer filters a strip of known commands
// (claude built-ins + user/project skills, served by /api/commands).
let commands = null;
let commandsPending = false;
// Fetch once per window, then call updateHints back exactly once. It must never
// re-enter updateHints on the cached path: a resolved promise chained back into
// its own caller is an infinite microtask loop, which starves the event loop and
// hangs the tab hard enough that Android kills the PWA (hit by picking a command
// off the strip, whose trailing space stops the regex below from matching).
async function loadCommands() {
  if (commands || commandsPending || activeIdx === null) return;
  const idx = activeIdx;
  commandsPending = true;
  let list = [];
  try {
    // Scoped to the active window — its project's .claude/skills, not the anchor's.
    const r = await req(`api/commands?index=${idx}`);
    if (r.ok) list = (await r.json()).commands || [];
  } catch (e) { /* strip just stays hidden */ }
  commandsPending = false;
  if (activeIdx !== idx) return; // switched under us; that window fetches its own
  commands = list;               // [] on failure: a remembered miss, not a refetch per keystroke
  updateHints();
}
function updateHints() {
  const v = els.msg.value;
  const m = v.match(/^\/([\w-]*)$/); // only while typing the command itself
  if (!m) { els.hints.hidden = true; return; }
  if (!commands) {
    els.hints.hidden = true;
    loadCommands();
    return;
  }
  const q = m[1].toLowerCase();
  const hits = commands.filter((c) => c.name.toLowerCase().startsWith(q)).slice(0, 12);
  if (!hits.length) { els.hints.hidden = true; return; }
  els.hints.innerHTML = "";
  for (const c of hits) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "hint";
    b.innerHTML = `<span class="hint-name">/${escapeHtml(c.name)}</span>` +
      (c.description ? `<span class="hint-desc">${escapeHtml(c.description)}</span>` : "");
    b.addEventListener("click", () => {
      els.msg.value = "/" + c.name + " ";
      els.hints.hidden = true;
      els.msg.focus({ preventScroll: true });
      autosize();
    });
    els.hints.appendChild(b);
  }
  els.hints.hidden = false;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---- Infra admin ----
// The gear panel. Restart replaces a window's claude process — MCP servers and
// hooks arm per process, so this is how wiring changes take effect. Everything the
// panel does could be typed into the composer by hand; this is the one-tap version.
function adminLog(line) {
  const t = new Date().toTimeString().slice(0, 8);
  els.adminLog.textContent += `[${t}] ${line}\n`;
  els.adminLog.scrollTop = els.adminLog.scrollHeight;
}
async function postJson(path, body) {
  const r = await req(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  let data = {};
  try { data = await r.json(); } catch (e) { /* log shows what we know */ }
  return { ok: r.ok, data };
}
function renderAdminWindows() {
  els.adminWindows.innerHTML = "";
  for (const w of windows) {
    const row = document.createElement("div");
    row.className = "admin-row";
    const state = w.closing ? "distilling…" : w.recycling ? "restarting…"
      : w.dead ? "dead" : (w.command || "");
    row.innerHTML =
      `<span class="admin-dot" style="--tab:${hueOf(w)}"></span>` +
      `<span class="admin-name">${escapeHtml(w.name)}` +
      (w.room ? `<span class="admin-room">◈ ${escapeHtml(w.room)}</span>` : "") +
      (w.cwd_label ? `<span class="admin-cwd" title="${escapeHtml(w.cwd_short || "")}">${escapeHtml(w.cwd_label)}</span>` : "") +
      `</span>` +
      (w.anchor ? `<span class="admin-viewing anchor">anchor</span>` : "") +
      (w.index === activeIdx ? `<span class="admin-viewing">viewing</span>` : "") +
      `<span class="admin-state${w.dead ? " bad" : ""}">${escapeHtml(state)}</span>`;
    const busy = !!w.recycling || !!w.closing;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "admin-act";
    btn.textContent = w.recycling ? "…" : w.dead ? "revive" : "restart";
    btn.disabled = busy;
    btn.addEventListener("click", () => recycle(w));
    row.appendChild(btn);
    // The main anchor stays put (the console's reference cwd); everything else can be
    // closed — /exit distills it to memory, then the window is removed.
    if (!w.anchor) {
      const cbtn = document.createElement("button");
      cbtn.type = "button";
      cbtn.className = "admin-act danger-lite";
      cbtn.textContent = w.closing ? "…" : "close";
      cbtn.disabled = busy;
      cbtn.addEventListener("click", () => closeWin(w));
      row.appendChild(cbtn);
    }
    els.adminWindows.appendChild(row);
  }
}
// Destructive-action prompts must name the directory too — "Restart homelab?" is
// ambiguous the moment the same expert runs in two projects, and the wrong answer
// ends a conversation.
const wlabel = (w) => (w.room ? `${w.room}-${w.name}` : w.name) +
  (w.cwd_label ? ` (${w.cwd_label})` : "");

async function recycle(w, quiet) {
  // Recycling the window you're conversing in ends that conversation. The console
  // can't know which window "you" are in beyond the one you're viewing, so the
  // viewed window gets the sharp warning.
  if (!quiet) {
    const msg = w.index === activeIdx
      ? `⚠ ${wlabel(w)} is the session you're viewing right now. Restarting ENDS the conversation in it — it /exits and distills cleanly, then respawns fresh. Restart anyway?`
      : `Restart ${wlabel(w)}? Sends /exit (distills), then respawns; force-kills only after 4 min.`;
    if (!confirm(msg)) return;
  }
  adminLog(`restart ${wlabel(w)} requested`);
  await postJson("api/recycle", { index: w.index });
  poll();
}
async function closeWin(w) {
  // Close = end the session and distill it (SessionEnd → thalamus extract), then the
  // window is removed. Same self-termination hazard as recycle for the viewed window.
  const msg = w.index === activeIdx
    ? `⚠ ${wlabel(w)} is the session you're viewing. Closing ENDS it — it /exits, distills to memory, and the tab disappears. Close it?`
    : `Close ${wlabel(w)}? Sends /exit (distills to memory), then removes the window. Force-kills only after 4 min.`;
  if (!confirm(msg)) return;
  adminLog(`close ${wlabel(w)} requested`);
  await postJson("api/close", { index: w.index });
  poll();
}

// ---- Spawn a session on demand ----
// Pick a scope (expert) + a directory; the server opens a detached pinned window via
// ---- Distillation widget ----
// A session's memory is written after its window is gone, by a detached process
// nothing else reports on. These rows are that process, made visible: one per
// session still distilling or finished badly. A clean finish is deliberately
// silent — the row simply stops appearing — so an empty list means "nothing owed",
// which is the state this is really here to let you confirm at a glance.
let distillSig = "";
const distillAges = new Map();     // session → the element showing its elapsed time

function shortAge(s) {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  const h = Math.floor(s / 3600);
  return `${h}h ${Math.floor((s % 3600) / 60)}m`;
}

function renderDistill(rows) {
  const bad = rows.some((r) => r.state === "error");
  const work = rows.some((r) => r.state === "active");
  els.spawnPip.hidden = !(bad || work);
  els.spawnPip.className = "spawn-pip" + (bad ? " bad" : work ? " work" : "");

  // Rebuilt only when the set of rows changes: at a 1.2s poll, replacing the nodes
  // every tick would restart the pulse animation each time. The elapsed time moves
  // on every tick and is therefore written in place rather than counted as a change.
  const sig = rows.map((r) => `${r.session}:${r.state}:${r.detail}`).join("|");
  if (sig === distillSig) {
    for (const r of rows) {
      const el = distillAges.get(r.session);
      if (el) el.textContent = `${r.session} · ${shortAge(r.age)}`;
    }
    return;
  }
  distillSig = sig;

  els.distillSec.hidden = rows.length === 0;
  els.distillList.innerHTML = "";
  distillAges.clear();
  for (const r of rows) {
    const row = document.createElement("div");
    row.className = "admin-row distill-row";

    const dot = document.createElement("span");
    dot.className = "admin-dot " + (r.state === "active" ? "work" : "bad");
    row.appendChild(dot);

    const name = document.createElement("span");
    name.className = "admin-name";
    const top = document.createElement("span");
    top.textContent = r.dir ? `${r.scope} · ${r.dir}` : r.scope;
    name.appendChild(top);
    const sub = document.createElement("span");
    if (r.state === "active") {
      sub.className = "admin-cwd";
      sub.textContent = `${r.session} · ${shortAge(r.age)}`;
      distillAges.set(r.session, sub);
    } else {
      // Straight from the extract log, so it is set as text, never as markup.
      sub.className = "distill-detail";
      sub.textContent = r.detail || "distillation failed";
    }
    name.appendChild(sub);
    row.appendChild(name);

    if (r.state === "active") {
      const state = document.createElement("span");
      state.className = "admin-state";
      state.textContent = "distilling";
      row.appendChild(state);
    } else {
      const x = document.createElement("button");
      x.type = "button";
      x.className = "distill-x";
      x.textContent = "✕";
      x.setAttribute("aria-label", `Dismiss ${r.session}`);
      x.addEventListener("click", () => dismissDistill(r.session));
      row.appendChild(x);
    }
    els.distillList.appendChild(row);
  }
}

async function dismissDistill(session) {
  await postJson("api/distill-dismiss", { session });
  distillSig = "";        // force a rebuild off the next poll's fresh list
  poll();
}

// `thalamus spawn`. Experts are no longer all booted at bring-up — only spawned when used.
let spawnOpts = null, spawnScope = null, spawnDir = null, selectNewestOnNextPoll = false;
// "" is solo — the ordinary roster. A room is chosen, or typed to make a new one:
// naming it IS creating it, since the launcher provisions the config dir on the way
// in. There is no separate create step to forget from a phone.
let spawnRoom = "";
async function openSpawn() {
  els.spawn.hidden = false;
  els.admin.hidden = true;
  els.spawnLog.hidden = true;
  els.spawnLog.textContent = "";
  if (!spawnOpts) {
    els.spawnScopes.textContent = "…";
    try {
      const r = await req("api/spawn-options", { cache: "no-store" });
      spawnOpts = await r.json();
    } catch (e) { spawnOpts = { scopes: [], dirs: [], rooms: [] }; }
  }
  renderSpawnChips();
}
function chip(text, on, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "chip" + (on ? " on" : "");
  b.textContent = text;
  b.addEventListener("click", onClick);
  return b;
}
function renderSpawnChips() {
  els.spawnScopes.innerHTML = "";
  for (const s of spawnOpts.scopes || []) {
    const c = chip(s, s === spawnScope, () => { spawnScope = s; renderSpawnChips(); });
    c.style.setProperty("--tab", hueFor(s, 0));
    els.spawnScopes.appendChild(c);
  }
  els.spawnDirs.innerHTML = "";
  for (const d of spawnOpts.dirs || []) {
    const label = (d.favorite ? "★ " : "") + d.label;
    els.spawnDirs.appendChild(
      chip(label, d.path === spawnDir, () => { spawnDir = d.path; renderSpawnChips(); }));
  }
  els.spawnRooms.innerHTML = "";
  const known = spawnOpts.rooms || [];
  // Rooms live and dead in one list: a room whose members have all been closed is
  // still a room (its config dir, and its members' transcripts, are still there),
  // and rejoining it is the normal way to pick a collaboration back up.
  const rooms = [...new Set([...known, ...windows.map((w) => w.room).filter(Boolean)])];
  els.spawnRooms.appendChild(
    chip("solo", spawnRoom === "", () => { spawnRoom = ""; renderSpawnChips(); }));
  for (const r of rooms) {
    const live = windows.filter((w) => w.room === r).length;
    const c = chip(live ? `◈ ${r} ${live}` : `◈ ${r}`, r === spawnRoom,
                   () => { spawnRoom = r; renderSpawnChips(); });
    c.style.setProperty("--tab", hueForRoom(r));
    els.spawnRooms.appendChild(c);
  }
  els.spawnRooms.appendChild(chip("+ new", false, newRoom));
  els.spawnGo.disabled = !(spawnScope && spawnDir);
}
// A prompt, not an inline field: it is the rarest action on the sheet, and a
// text input in the chip row would take the tap target every other choice needs
// at 60 columns.
function newRoom() {
  const name = (prompt("New room name (lowercase letters, digits, hyphens):") || "").trim();
  if (!name) return;
  if (!/^[a-z0-9][a-z0-9-]*$/.test(name)) {
    els.spawnLog.hidden = false;
    els.spawnLog.textContent =
      `"${name}" is not a room name — lowercase letters, digits and hyphens only.`;
    return;
  }
  spawnRoom = name;
  renderSpawnChips();
}
async function doSpawn() {
  if (!(spawnScope && spawnDir)) return;
  els.spawnGo.disabled = true;
  els.spawnLog.hidden = false;
  els.spawnLog.textContent = `spawning ${spawnScope} in ${spawnDir}` +
    (spawnRoom ? ` — room ${spawnRoom}` : "") + "…";
  const { ok, data } = await postJson("api/spawn",
    { scope: spawnScope, dir: spawnDir, room: spawnRoom });
  if (ok && data.ok) {
    els.spawnLog.textContent = data.output || "spawned.";
    selectNewestOnNextPoll = true;
    setTimeout(() => { els.spawn.hidden = true; poll(); }, 700);
  } else {
    els.spawnLog.textContent = "spawn failed:\n" + (data.output || "unknown error");
    els.spawnGo.disabled = false;
  }
}
// The Services section manages systemd --user units named with
// `thalamus console --service <unit>`. Nothing named → no section at all, rather
// than an empty box implying the console lost track of something.
async function loadServices() {
  const sec = document.getElementById("admin-services-sec");
  els.adminServices.textContent = "…";
  try {
    const r = await req("api/admin", { cache: "no-store" });
    const data = await r.json();
    const units = data.services || [];
    sec.hidden = units.length === 0;
    if (!units.length) return;
    els.adminServices.innerHTML = "";
    for (const s of units) {
      const row = document.createElement("div");
      row.className = "admin-row";
      const ok = s.state === "active";
      row.innerHTML =
        `<span class="admin-dot ${ok ? "ok" : "bad"}"></span>` +
        `<span class="admin-name">${escapeHtml(s.unit.replace(".service", ""))}</span>` +
        `<span class="admin-state${ok ? "" : " bad"}">${escapeHtml(s.state)}</span>`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "admin-act";
      btn.textContent = "restart";
      btn.addEventListener("click", async () => {
        if (!confirm(`Restart ${s.unit}? If it is the unit serving this page, ` +
                     "the console blips offline for a moment and comes back.")) return;
        adminLog(`restart ${s.unit}`);
        await postJson("api/service", { unit: s.unit });
        setTimeout(loadServices, 1500);
      });
      row.appendChild(btn);
      els.adminServices.appendChild(row);
    }
  } catch (e) {
    els.adminServices.textContent = "status unavailable";
  }
}
document.getElementById("admin-btn").addEventListener("click", () => {
  els.admin.hidden = !els.admin.hidden;
  if (!els.admin.hidden) { els.spawn.hidden = true; renderAdminWindows(); loadServices(); }
});
document.getElementById("admin-x").addEventListener("click", () => { els.admin.hidden = true; });
document.getElementById("spawn-btn").addEventListener("click", () => {
  if (els.spawn.hidden) openSpawn(); else els.spawn.hidden = true;
});
document.getElementById("spawn-x").addEventListener("click", () => { els.spawn.hidden = true; });
els.spawnGo.addEventListener("click", doSpawn);
document.getElementById("admin-restart-all").addEventListener("click", async () => {
  if (!windows.length) return;
  const viewing = windows.find((w) => w.index === activeIdx);
  if (!confirm(`Restart all ${windows.length} pinned sessions? Each /exits, distills, and respawns.` +
    (viewing ? ` ⚠ Includes ${wlabel(viewing)} — the session you're viewing; its conversation ends.` : ""))) return;
  for (const w of windows) await recycle(w, true);
});
document.getElementById("admin-roster").addEventListener("click", async () => {
  adminLog("roster sync…");
  const { data } = await postJson("api/roster", {});
  adminLog((data.output || "no output").trim());
  poll();
});

// ---- Desktop surface ----
// Two engines, picked by capability rather than by user-agent string: a rotated
// phone stays mobile (its pointer is still coarse), a narrow desktop window
// degrades to the mobile surface, and a tablet with a trackpad gets the surface it
// can actually drive. The mobile path is deliberately untouched by everything
// below this line — no keystroke capture, no poll change.
const DESKTOP_Q = window.matchMedia("(pointer: fine) and (min-width: 900px)");
let isDesktop = DESKTOP_Q.matches;

// ---- Frame theme (desktop only) ----
// The pane can render inside a panel drawn in a background image — the look a
// terminal emulator paints as GPU background art. That art never crosses the wire
// from the emulator, so no amount of emulator integration would transport it; what
// travels is the *data*. The server parses the frame file and is the single source
// of truth; here we reproduce the same contain-fit + panel inset in CSS, so a frame
// added there shows up with no copying. The file is a contract, not a dependency on
// any one emulator: anything emitting {name, path, panel} works. Absent or empty →
// the controls read "no frames" and do nothing. See docs/frame-themes.md.
let frames = [];
// Storage keys keep their `plane-` prefix deliberately. They are private to the
// browser and their only job is to stay stable — renaming them to match the app's
// name would silently reset every operator's saved preferences to buy nothing.
let frameIdx = +(localStorage.getItem("plane-frame-idx") || 0);
let frameOn = localStorage.getItem("plane-frame-on") === "1";
const frameDims = new Map(); // name -> {w,h}, needed to reproduce background-size:contain

const framed = () => isDesktop && frameOn && frames.length > 0;

// Under a frame the pane text is clipped to the panel and scrolls inside it, so the
// scrolling element moves from the wrap to the text node itself. Everything that
// pins scroll position has to ask rather than assume.
function scroller() { return framed() ? els.screen : els.wrap; }

function currentFrame() {
  if (!frames.length) return null;
  return frames[((frameIdx % frames.length) + frames.length) % frames.length];
}

// Where the panel lands, in wrap-local px. The art is contain-fit and centred, so the
// panel fractions (which are fractions of the IMAGE) have to be mapped through the
// letterbox offset — CSS alone can't express that.
function panelRect() {
  const W = els.wrap.clientWidth, H = els.wrap.clientHeight;
  const f = currentFrame();
  const dim = f && frameDims.get(f.name);
  if (!f || !dim) return { x: 0, y: 0, w: W, h: H };
  const scale = Math.min(W / dim.w, H / dim.h);
  const dw = dim.w * scale, dh = dim.h * scale;
  const ox = (W - dw) / 2, oy = (H - dh) / 2;
  return {
    x: ox + dw * f.panel.left,
    y: oy + dh * f.panel.top,
    w: Math.max(80, dw * (1 - f.panel.left - f.panel.right)),
    h: Math.max(60, dh * (1 - f.panel.top - f.panel.bottom)),
  };
}

function applyFrame() {
  const on = framed();
  els.wrap.classList.toggle("framed", on);
  if (!on) {
    els.wrap.style.backgroundImage = "";
    computeFit();
    return;
  }
  const f = currentFrame();
  els.wrap.style.backgroundImage = `url("frame/${encodeURIComponent(f.name)}")`;
  const r = panelRect();
  const s = els.wrap.style;
  s.setProperty("--panel-x", r.x.toFixed(1) + "px");
  s.setProperty("--panel-y", r.y.toFixed(1) + "px");
  s.setProperty("--panel-w", r.w.toFixed(1) + "px");
  s.setProperty("--panel-h", r.h.toFixed(1) + "px");
  computeFit();
}

// naturalWidth/Height rather than a server-side image parse: the browser has to
// decode the art anyway, so this costs nothing extra and keeps PNG/GIF/WebP support
// as whatever the browser handles.
function measureFrame(f) {
  if (frameDims.has(f.name)) return Promise.resolve();
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => { frameDims.set(f.name, { w: img.naturalWidth, h: img.naturalHeight }); resolve(); };
    img.onerror = resolve; // a frame that won't decode just never themes
    img.src = `frame/${encodeURIComponent(f.name)}`;
  });
}

async function loadFrames() {
  if (!isDesktop) return;
  try {
    const r = await req("api/frames");
    frames = (await r.json()).frames || [];
  } catch (e) { frames = []; }
  renderFrameLabel();
  if (!frames.length) return;
  await measureFrame(currentFrame());
  applyFrame();
  renderFrameLabel();
}

function setFrame(i) {
  if (!frames.length) return;
  frameIdx = ((i % frames.length) + frames.length) % frames.length;
  localStorage.setItem("plane-frame-idx", frameIdx);
  // Measure before applying, else the first paint of a new frame uses the previous
  // frame's dimensions and the panel lands in the wrong place for one tick.
  measureFrame(currentFrame()).then(() => { applyFrame(); renderFrameLabel(); });
}

function toggleFrame() {
  frameOn = !frameOn;
  localStorage.setItem("plane-frame-on", frameOn ? "1" : "0");
  if (frameOn && frames.length) {
    measureFrame(currentFrame()).then(() => { applyFrame(); renderFrameLabel(); });
  } else { applyFrame(); renderFrameLabel(); }
}

function nextFrame() {
  // With the theme off, next turns it back on where you left it.
  if (!frameOn) { toggleFrame(); return; }
  setFrame(frameIdx + 1);
}

function renderFrameLabel() {
  const el = document.getElementById("frame-label");
  if (!el) return;
  const f = currentFrame();
  el.textContent = !frames.length ? "no frames"
    : frameOn && f ? f.name.replace(/\.(png|gif|jpe?g|webp)$/i, "") : "theme off";
}

// ---- Desktop keystroke passthrough ----
// Native feel means keys reach tmux as you type, not a line at a time. Two things
// make that safe: printable characters coalesce into one send (a POST per keypress
// is a request storm and the responses can land out of order), and every send goes
// through one serial chain so ordering is exactly what was typed.
const KEY_COALESCE_MS = 24;
const FAST_POLL_MS = 100;
const FAST_WINDOW_MS = 3000; // how long typing keeps the poll hot
let passthrough = localStorage.getItem("plane-passthrough") !== "0";
let keyBuf = "";
let keyTimer = null;
let namedBuf = null;        // {key, count} — a run of the same held key
let namedTimer = null;
let sendChain = Promise.resolve();
let fastUntil = 0;
// One request may stand for at most this many repeats. A held key that outruns the
// cap starts another request rather than growing one without bound.
const KEY_REPEAT_CAP = 64;

// Named keys we forward. Anything not here and not printable is left to the browser.
const PASS_KEYS = {
  Enter: "enter", Escape: "escape", Tab: "tab", Backspace: "backspace",
  Delete: "delete", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left",
  ArrowRight: "right", Home: "home", End: "end", PageUp: "pageup", PageDown: "pagedown",
};

function queue(fn) { sendChain = sendChain.then(fn).catch(() => {}); }

function flushKeys() {
  clearTimeout(keyTimer);
  keyTimer = null;
  if (!keyBuf || activeIdx === null) { keyBuf = ""; return; }
  const text = keyBuf;
  keyBuf = "";
  const idx = activeIdx;
  queue(() => post("api/send", { index: idx, text, submit: false }));
}

function typeChar(ch) {
  flushNamed();   // ordering: a held key queued before this text lands before it
  keyBuf += ch;
  if (!keyTimer) keyTimer = setTimeout(flushKeys, KEY_COALESCE_MS);
}

// A held key repeats at ~30/s. Printable characters were already coalesced into one
// `api/send` per 24ms window, but every named key was its own request, and `queue`
// serialises them — so holding backspace for three seconds built a chain of ~90
// round trips, each spawning its own `tmux send-keys`, that went on draining long
// after the key came up. The UI is not doing anything else during that, which is
// what "locked up" looked like. Repeats now coalesce exactly like text does, into
// one request carrying a count.
function flushNamed() {
  clearTimeout(namedTimer);
  namedTimer = null;
  if (!namedBuf || activeIdx === null) { namedBuf = null; return; }
  const { key, count } = namedBuf;
  namedBuf = null;
  const idx = activeIdx;
  queue(() => post("api/key", { index: idx, key, count }));
}

function sendNamed(key) {
  flushKeys(); // ordering: buffered text must land before the control key
  if (activeIdx === null) return;
  if (namedBuf && namedBuf.key === key && namedBuf.count < KEY_REPEAT_CAP) {
    namedBuf.count++;
  } else {
    flushNamed();             // a different key ends the run, in order
    namedBuf = { key, count: 1 };
  }
  if (!namedTimer) namedTimer = setTimeout(flushNamed, KEY_COALESCE_MS);
}

function goFast() { fastUntil = Date.now() + FAST_WINDOW_MS; }

// Passthrough is suspended while a real input has focus, so the composer, the spawn
// sheet and the admin panel keep working normally.
function typingInField() {
  const a = document.activeElement;
  return !!a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.isContentEditable);
}

document.addEventListener("keydown", (e) => {
  // NOTE: F11 is the browser's own fullscreen and Chrome does not reliably deliver
  // it to the page — the `full` button in the desktop bar is the guaranteed path.
  if (isDesktop && !typingInField() && e.key === "F11") {
    e.preventDefault(); toggleFullscreen(); return;
  }
  // F9/F12 mirror the emulator's own frame bindings, so the same keys do the same
  // thing whether the pane is in a terminal or in this page.
  if (isDesktop && !typingInField() && e.key === "F9") {
    e.preventDefault(); nextFrame(); return;
  }
  if (isDesktop && !typingInField() && e.key === "F12") {
    e.preventDefault(); toggleFrame(); return;
  }
  if (!isDesktop || !passthrough || typingInField()) return;
  if (!els.admin.hidden || !els.spawn.hidden) return; // a panel is open; leave it alone
  if (activeIdx === null) return;
  if (e.altKey || e.metaKey) return;                  // browser/OS chords stay the browser's

  if (e.ctrlKey) {
    // Leave the copy/paste/find/reload chords to the browser — losing Ctrl-C for copy
    // would be a worse regression than not having Ctrl-C for SIGINT, and the keycap
    // in the composer still sends a real interrupt.
    if (["c", "v", "x", "a", "f", "r", "t", "w", "l", "n"].includes(e.key.toLowerCase())) return;
    if (/^[a-z]$/i.test(e.key)) {
      e.preventDefault(); goFast(); sendNamed("ctrl-" + e.key.toLowerCase()); return;
    }
    return;
  }
  if (e.key === "Tab" && e.shiftKey) { e.preventDefault(); goFast(); sendNamed("shift-tab"); return; }
  if (PASS_KEYS[e.key]) { e.preventDefault(); goFast(); sendNamed(PASS_KEYS[e.key]); return; }
  if (e.key.length === 1) { e.preventDefault(); goFast(); typeChar(e.key); return; }
}, true);

// Paste straight into the pane when passthrough owns the keyboard.
document.addEventListener("paste", (e) => {
  if (!isDesktop || !passthrough || typingInField() || activeIdx === null) return;
  const text = (e.clipboardData || window.clipboardData).getData("text");
  if (!text) return;
  e.preventDefault();
  goFast();
  flushKeys();
  const idx = activeIdx;
  queue(() => post("api/send", { index: idx, text, submit: false }));
});

function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  else document.documentElement.requestFullscreen().catch(() => {});
}

function setPassthrough(on) {
  passthrough = on;
  localStorage.setItem("plane-passthrough", on ? "1" : "0");
  document.body.classList.toggle("passthrough", isDesktop && on);
  const b = document.getElementById("pass-toggle");
  if (b) {
    b.setAttribute("aria-pressed", String(on));
    b.textContent = on ? "keys: direct" : "keys: composer";
  }
}

// Desktop chrome. Built here rather than in index.html so the mobile DOM is
// byte-identical to what it would be without this file's desktop half.
function buildDesktopBar() {
  if (!isDesktop || document.getElementById("deskbar")) return;
  const bar = document.createElement("div");
  bar.className = "deskbar";
  bar.id = "deskbar";
  bar.innerHTML =
    '<button type="button" id="frame-toggle" title="Frame theme on/off (F12)">frame</button>' +
    '<button type="button" id="frame-next" title="Next frame (F9)">▸</button>' +
    '<span class="frame-label" id="frame-label"></span>' +
    '<button type="button" id="pass-toggle" title="Send keystrokes straight to the pane" aria-pressed="true">keys: direct</button>' +
    '<button type="button" id="full-toggle" title="Fullscreen (F11)">full</button>';
  document.querySelector("header").appendChild(bar);
  document.getElementById("full-toggle").addEventListener("click", toggleFullscreen);
  document.getElementById("pass-toggle").addEventListener("click", () => setPassthrough(!passthrough));
  document.getElementById("frame-toggle").addEventListener("click", toggleFrame);
  document.getElementById("frame-next").addEventListener("click", nextFrame);
  renderFrameLabel();
}

// A capability change (window dragged to another monitor, browser resized across
// the breakpoint) switches engines live — tear the desktop half down rather than
// leaving it stranded on a surface that no longer qualifies.
function onDesktopChange() {
  const was = isDesktop;
  isDesktop = DESKTOP_Q.matches;
  if (was === isDesktop) return;
  if (isDesktop) { buildDesktopBar(); setPassthrough(passthrough); loadFrames(); }
  else {
    document.body.classList.remove("passthrough");
    // A frame is a desktop-only surface: strip it rather than leaving art behind a
    // mobile layout that never sized itself to a panel.
    els.wrap.classList.remove("framed");
    els.wrap.style.backgroundImage = "";
    computeFit();
    const bar = document.getElementById("deskbar");
    if (bar) bar.remove();
    computeFit();
  }
}
DESKTOP_Q.addEventListener("change", onDesktopChange);

// ---- wiring ----
els.form.addEventListener("submit", (e) => { e.preventDefault(); sendMessage(); });
els.msg.addEventListener("input", () => { autosize(); updateHints(); });
els.msg.addEventListener("keydown", (e) => {
  // Enter sends; Shift+Enter (or the ⏎ keycap) for a literal newline in the field.
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  // Shift+Tab from a real keyboard cycles the agent's permission mode, same as the
  // `mode` keycap.
  if (e.key === "Tab" && e.shiftKey) {
    e.preventDefault();
    sendNamed("shift-tab");
  }
});
for (const b of document.querySelectorAll(".keycap")) {
  // Through `sendNamed`, not a bare post: a tap must queue behind whatever text or
  // held key is still buffered, or it arrives out of order.
  b.addEventListener("click", () => sendNamed(b.dataset.key));
}
function nudgeFont(d) {
  fontDelta += d;
  localStorage.setItem("plane-font-delta2", fontDelta);
  applyFont();
}
document.getElementById("font-up").addEventListener("click", () => nudgeFont(1));
document.getElementById("font-dn").addEventListener("click", () => nudgeFont(-1));

let fitTimer = null;
function scheduleFit() {
  clearTimeout(fitTimer);
  // A resize moves the letterbox, so under a frame the panel has to be re-placed
  // before the text is re-fitted to it — applyFrame ends in computeFit.
  fitTimer = setTimeout(() => { framed() ? applyFrame() : computeFit(); }, 120);
}
window.addEventListener("resize", scheduleFit);
window.addEventListener("orientationchange", scheduleFit);

// ---- Install (add to home screen) ----
const installBar = document.getElementById("install-bar");
const installMsg = document.getElementById("install-msg");
const installDo = document.getElementById("install-do");
let deferredPrompt = null;

function inStandalone() {
  return window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
}
function showInstallBar(msg, showButton) {
  if (inStandalone() || localStorage.getItem("plane-install-dismissed") === "1") return;
  installMsg.textContent = msg;
  installDo.hidden = !showButton;
  installBar.hidden = false;
}
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredPrompt = e;
  showInstallBar("Install Thalamus as an app.", true);
});
installDo.addEventListener("click", async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  await deferredPrompt.userChoice;
  deferredPrompt = null;
  installBar.hidden = true;
});
document.getElementById("install-x").addEventListener("click", () => {
  installBar.hidden = true;
  localStorage.setItem("plane-install-dismissed", "1");
});
window.addEventListener("appinstalled", () => { installBar.hidden = true; });
// iOS Safari never fires beforeinstallprompt — guide the user to the Share sheet.
if (/iphone|ipad|ipod/i.test(navigator.userAgent) && !inStandalone()) {
  showInstallBar("Install: tap Share, then “Add to Home Screen.”", false);
}
// Android fallback: if Chrome hasn't offered the prompt after a few seconds
// (already installed, or installability check failed), point at the browser menu.
if (/android/i.test(navigator.userAgent) && !inStandalone()) {
  setTimeout(() => {
    if (!deferredPrompt && installBar.hidden) {
      showInstallBar("Install: tap ⋮ menu → “Add to Home screen” → Install.", false);
    }
  }, 4000);
}

applyFont();
computeFit();
setConn("connecting");
buildDesktopBar();
setPassthrough(passthrough);
loadFrames();

// Adaptive poll. Was `setInterval(poll, POLL_MS)`, which could stack overlapping
// requests whenever a poll outran its own interval; a self-scheduling chain can't.
// The next tick is armed from a single completion callback once the data has landed
// — never by chaining the promise back into poll() itself, which is the shape that
// starved the event loop in 8b483c0. The floor is 100ms of real network work, so
// there is no microtask-starvation path here.
let pollTimer = null;
let pollInFlight = false;
let pollAgain = false;
let pollStartedAt = 0;
function pollDelay() {
  return (isDesktop && passthrough && Date.now() < fastUntil) ? FAST_POLL_MS : POLL_MS;
}
// Single-flight. `clearTimeout` cancels a pending *timer*; it cannot cancel a `poll()`
// that is already awaiting its fetch. Every caller here is an event — the view toggle,
// a tab becoming visible — so without this guard a tap during an in-flight poll runs a
// second one beside the first, and two responses race to paint the same pane. The
// caller's intent is "refresh now", not "refresh concurrently", so a request that
// arrives mid-flight is remembered and served the moment the current one lands.
function pollLoop() {
  clearTimeout(pollTimer);
  if (pollInFlight) {
    // A latch held longer than a request can legally take means the promise never
    // settled and never will. Releasing it costs at worst one overlapping poll;
    // holding it costs every future repaint, which is the failure this guards.
    if (pollStartedAt && Date.now() - pollStartedAt > POLL_STUCK_MS) {
      setConn("stale");
    } else {
      pollAgain = true;
      return;
    }
  }
  pollInFlight = true;
  pollStartedAt = Date.now();
  poll().finally(() => {
    pollInFlight = false;
    clearTimeout(pollTimer);
    const soon = pollAgain;
    pollAgain = false;
    pollTimer = setTimeout(pollLoop, soon ? 0 : pollDelay());
  });
}
applyView();
pollLoop();
document.addEventListener("visibilitychange", () => { if (!document.hidden) pollLoop(); });

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
  // A deploy while the app is open: the updated SW skipWaiting+claims this page,
  // which fires controllerchange — reload so the fresh shell shows immediately.
  // Guard: on the FIRST-ever install there was no previous controller; claiming
  // then must not reload the page out from under the user.
  let hadController = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (hadController) location.reload();
    hadController = true;
  });
}

// ---- The room dialogue ----
// A composer addressed to a ROOM instead of a window. The difference from the pane
// composer is not the fan-out, it is the blindness: sending into a window you are
// watching lets you answer a permission prompt on purpose, while a room message goes
// to members nobody is looking at, where the Enter after the text would answer a
// prompt the sender never saw. So every refusal here comes from the server's
// pre-flight — this file decides nothing about who is safe to type into, and a copy
// of that rule living in the client would be a second policy that drifts.
let dialogueRoom = null;

function openDialogue(room) {
  if (!room) return;
  dialogueRoom = room;
  els.dialogueRoom.textContent = room;
  els.dialogueLog.hidden = true;
  els.dialogueLog.textContent = "";
  els.dialogueText.value = "";
  els.dialogueGo.disabled = true;
  els.dialogue.hidden = false;
  els.dialogueText.focus();
}

function closeDialogue() {
  els.dialogue.hidden = true;
  dialogueRoom = null;
}

// `check only` is a real dry run on the server: it pre-flights every member and
// writes nothing, which is how an operator asks "would this land?" without the send
// that answers it destructively.
async function runDialogue(dryRun) {
  const text = (els.dialogueText.value || "").trim();
  if (!dialogueRoom || !text) return;
  els.dialogueGo.disabled = true;
  els.dialogueCheck.disabled = true;
  els.dialogueLog.hidden = false;
  els.dialogueLog.textContent = dryRun
    ? `checking ${dialogueRoom}…`
    : `saying to ${dialogueRoom}…`;
  const { ok, data } = await postJson("api/dispatch", {
    room: dialogueRoom,
    message: text,
    partial: !!els.dialoguePartial.checked,
    dryRun: !!dryRun,
  });
  // The refusal text names the target that refused and what to do about it, so it is
  // rendered verbatim rather than replaced with a generic failure line.
  els.dialogueLog.textContent = ok
    ? (data.note || "delivered.")
    : "refused:\n" + (data.error || "unknown error");
  els.dialogueCheck.disabled = false;
  els.dialogueGo.disabled = false;
  if (ok && !dryRun) setTimeout(poll, 200);
}

if (els.dialogueText) {
  els.dialogueText.addEventListener("input", () => {
    els.dialogueGo.disabled = !els.dialogueText.value.trim();
  });
  els.dialogueGo.addEventListener("click", () => runDialogue(false));
  els.dialogueCheck.addEventListener("click", () => runDialogue(true));
  els.dialogueX.addEventListener("click", closeDialogue);
}
