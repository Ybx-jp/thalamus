// Thalamus control plane — client. Polls /api/panes, renders the active session's
// screen, and drives every window by index — never changing the tmux active
// window, so a terminal attached to the same session stays where the operator
// left it.
"use strict";

// Every URL in this file is relative, so the app runs at the origin root or under
// whatever path a reverse proxy mounts it at. index.html canonicalizes a missing
// trailing slash before this file loads.

const POLL_MS = 1200;
const STALE_MS = 5000;

// Per-session channel hue. `main` is fixed — it is the anchor every roster has —
// and every other scope draws a stable colour from its own name, so adding an
// expert manifest colours its tab without anyone editing a table here.
const MAIN_HUE = "#9a8cff";                                        // violet
const PALETTE = ["#e0a45c", "#4db6a6", "#6db3f2", "#e07a9c",       // amber, teal, sky, rose
                 "#8fce6b", "#c79bf0"];                            // moss, orchid
function hueFor(name, idx) {
  if (name === "main") return MAIN_HUE;
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (Math.imul(h, 31) + name.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

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
  spawnDirs: document.getElementById("spawn-dirs"),
  spawnGo: document.getElementById("spawn-go"),
  spawnLog: document.getElementById("spawn-log"),
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
// Tabs the rail shows: all of them, or just the selected workspace's.
const visibleWindows = () =>
  activeWs === null ? windows : windows.filter((w) => w.cwd === activeWs);

function setChannelHue(hue) {
  document.documentElement.style.setProperty("--chan", hue);
}

function renderWsBar() {
  const ws = workspaces();
  // One directory (the common case) → no bar at all, layout unchanged.
  if (ws.length < 2) {
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
  els.wsbar.appendChild(mk("⌂ all", null, "Show every session"));
  for (const w of ws) {
    const count = windows.filter((x) => x.cwd === w.path).length;
    const full = (windows.find((x) => x.cwd === w.path) || {}).cwd_short || w.path;
    els.wsbar.appendChild(mk(`${w.label} ${count}`, w.path, full));
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
    const hue = hueFor(w.name, w.index);
    const tab = document.createElement("button");
    tab.className = "chan-tab" + (showCwd ? " two-line" : "");
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", String(w.index === activeIdx));
    tab.style.setProperty("--tab", hue);
    tab.dataset.idx = w.index;
    tab.title = w.cwd_short ? `${w.name} — ${w.cwd_short}` : w.name;
    tab.innerHTML =
      `<span class="dot"></span>` +
      `<span class="tab-text">` +
      `<span class="nm">${escapeHtml(w.name)}</span>` +
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
  setChannelHue(hueFor(w.name, w.index));
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
  const sc = els.wrap;
  const atBottom = sc.scrollHeight - sc.scrollTop - sc.clientHeight < 40;
  if (selectionInScreen()) { pendingScreen = text; return; } // don't clobber a highlight
  if (text === renderedText) return;                         // unchanged; keep links stable
  pendingScreen = null;
  paintScreen(text);
  if (atBottom) sc.scrollTop = sc.scrollHeight;
}

// When the user releases a selection, apply whatever repaint we deferred.
document.addEventListener("selectionchange", () => {
  if (pendingScreen !== null && !selectionInScreen()) {
    const t = pendingScreen;
    pendingScreen = null;
    renderScreen(t);
  }
});

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
    const r = await fetch("api/panes", { cache: "no-store" });
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

    updateDots(next);
    const cur = windows.find((w) => w.index === activeIdx);
    if (cur) renderScreen(cur.lines);
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
    await fetch(path, {
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
  const avail = els.wrap.clientWidth - padX - 1; // -1 guards rounding overflow
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
    const r = await fetch(`api/commands?index=${idx}`);
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
  const r = await fetch(path, {
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
      `<span class="admin-dot" style="--tab:${hueFor(w.name, w.index)}"></span>` +
      `<span class="admin-name">${escapeHtml(w.name)}` +
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
    // The main anchor stays put (the plane's reference cwd); everything else can be
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
const wlabel = (w) => (w.cwd_label ? `${w.name} (${w.cwd_label})` : w.name);

async function recycle(w, quiet) {
  // Recycling the window you're conversing in ends that conversation. The plane
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
// `thalamus spawn`. Experts are no longer all booted at bring-up — only spawned when used.
let spawnOpts = null, spawnScope = null, spawnDir = null, selectNewestOnNextPoll = false;
async function openSpawn() {
  els.spawn.hidden = false;
  els.admin.hidden = true;
  els.spawnLog.hidden = true;
  els.spawnLog.textContent = "";
  if (!spawnOpts) {
    els.spawnScopes.textContent = "…";
    try {
      const r = await fetch("api/spawn-options", { cache: "no-store" });
      spawnOpts = await r.json();
    } catch (e) { spawnOpts = { scopes: [], dirs: [] }; }
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
  els.spawnGo.disabled = !(spawnScope && spawnDir);
}
async function doSpawn() {
  if (!(spawnScope && spawnDir)) return;
  els.spawnGo.disabled = true;
  els.spawnLog.hidden = false;
  els.spawnLog.textContent = `spawning ${spawnScope} in ${spawnDir}…`;
  const { ok, data } = await postJson("api/spawn", { scope: spawnScope, dir: spawnDir });
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
    const r = await fetch("api/admin", { cache: "no-store" });
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
                     "the plane blips offline for a moment and comes back.")) return;
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
let sendChain = Promise.resolve();
let fastUntil = 0;

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
  keyBuf += ch;
  if (!keyTimer) keyTimer = setTimeout(flushKeys, KEY_COALESCE_MS);
}

function sendNamed(key) {
  flushKeys(); // ordering: buffered text must land before the control key
  if (activeIdx === null) return;
  const idx = activeIdx;
  queue(() => post("api/key", { index: idx, key }));
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
    '<button type="button" id="pass-toggle" title="Send keystrokes straight to the pane" aria-pressed="true">keys: direct</button>' +
    '<button type="button" id="full-toggle" title="Fullscreen (F11)">full</button>';
  document.querySelector("header").appendChild(bar);
  document.getElementById("full-toggle").addEventListener("click", toggleFullscreen);
  document.getElementById("pass-toggle").addEventListener("click", () => setPassthrough(!passthrough));
}

// A capability change (window dragged to another monitor, browser resized across
// the breakpoint) switches engines live — tear the desktop half down rather than
// leaving it stranded on a surface that no longer qualifies.
function onDesktopChange() {
  const was = isDesktop;
  isDesktop = DESKTOP_Q.matches;
  if (was === isDesktop) return;
  if (isDesktop) { buildDesktopBar(); setPassthrough(passthrough); }
  else {
    document.body.classList.remove("passthrough");
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
    if (activeIdx !== null) post("api/key",{ index: activeIdx, key: "shift-tab" });
  }
});
for (const b of document.querySelectorAll(".keycap")) {
  b.addEventListener("click", () => {
    if (activeIdx !== null) post("api/key",{ index: activeIdx, key: b.dataset.key });
  });
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
  fitTimer = setTimeout(computeFit, 120);
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

// Adaptive poll. Was `setInterval(poll, POLL_MS)`, which could stack overlapping
// requests whenever a poll outran its own interval; a self-scheduling chain can't.
// The next tick is armed from a single completion callback once the data has landed
// — never by chaining the promise back into poll() itself, which is the shape that
// starved the event loop in 8b483c0. The floor is 100ms of real network work, so
// there is no microtask-starvation path here.
let pollTimer = null;
function pollDelay() {
  return (isDesktop && passthrough && Date.now() < fastUntil) ? FAST_POLL_MS : POLL_MS;
}
function pollLoop() {
  clearTimeout(pollTimer);
  poll().finally(() => {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(pollLoop, pollDelay());
  });
}
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
