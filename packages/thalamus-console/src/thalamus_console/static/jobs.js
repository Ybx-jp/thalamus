// The jobs pages: J1 list, J2 pipeline, J3 history, J4 change receipt, J5 run, J6 repo
// and a commit, plus D1, the desktop canvas. Everything shown comes from the jobs
// source through /api/jobs/ (thalamus_console/jobs_source.py); the wire shapes are in
// docs/console.md. The source composes every word and line; this file lays them out.
//
// Routes live in the hash so the back chevron, the browser's back and a reload all
// land where they should without a server route per screen:
//   #/                J1 (D1 on a desktop-width window)
//   #/job/<id>        J2, optionally ?run=<run id>
//   #/job/<id>/history J3
//   #/change/<sha>    J4
//   #/run/<id>        J5
//   #/repo            J6
//   #/commit/<sha>    a commit opened from J6 or J4's "Open commit in repos"
"use strict";

const main = document.getElementById("main");
const titleEl = document.getElementById("title");
const backEl = document.getElementById("back");
const headAct = document.getElementById("head-act");

// Desktop canvas threshold. D1 is drawn at 1440 wide with a 390 px inspector; below
// 1024 the graph's seven columns no longer fit beside it, so narrower windows get the
// phone screens. Chosen here: the comps give one desktop width and no breakpoint.
const DESKTOP_MIN_PX = 1024;

// ---- routing ----

function parseRoute(hash) {
  const raw = (hash || "").replace(/^#/, "");
  const [path, query] = raw.split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  const params = {};
  for (const pair of (query || "").split("&")) {
    if (!pair) continue;
    const [k, v] = pair.split("=");
    params[decodeURIComponent(k)] = decodeURIComponent(v || "");
  }
  if (parts[0] === "job" && parts[1] && parts[2] === "history") {
    return { screen: "history", job: parts[1], params };
  }
  if (parts[0] === "job" && parts[1]) return { screen: "job", job: parts[1], params };
  if (parts[0] === "change" && parts[1]) return { screen: "change", sha: parts[1], params };
  if (parts[0] === "run" && parts[1]) return { screen: "run", run: parts[1], params };
  if (parts[0] === "repo") return { screen: "repo", params };
  if (parts[0] === "commit" && parts[1]) return { screen: "commit", sha: parts[1], params };
  return { screen: "list", params };
}

// Where the chevron goes. Up the tree rather than history.back(): a screen opened from
// a notification or a pasted link has no history to go back through, and the chevron
// must still lead somewhere that makes sense. J1's parent is the roster.
function backTarget(route, ctx) {
  switch (route.screen) {
    case "list": return "./";
    case "job": return "#/";
    case "history": return "#/job/" + encodeURIComponent(route.job);
    case "change": return ctx && ctx.job ? "#/job/" + encodeURIComponent(ctx.job) : "#/";
    case "run": return ctx && ctx.job ? "#/job/" + encodeURIComponent(ctx.job) : "#/";
    case "repo": return "#/";
    case "commit": return "#/repo";
    default: return "#/";
  }
}

function link(hash) { return hash; }

function setChrome(title, back) {
  titleEl.textContent = title;
  backEl.setAttribute("href", back);
  headAct.replaceChildren();
}

let renderSeq = 0;

async function route() {
  const r = parseRoute(location.hash);
  const seq = ++renderSeq;
  const desktop = window.innerWidth >= DESKTOP_MIN_PX;
  document.body.classList.toggle("desk", desktop && r.screen === "list");
  try {
    if (r.screen === "list" && desktop) await renderCanvas(r, seq);
    else if (r.screen === "list") await renderList(r, seq);
    else if (r.screen === "job") await renderJob(r, seq);
    else if (r.screen === "history") await renderHistory(r, seq);
    else if (r.screen === "change") await renderChange(r, seq);
    else if (r.screen === "run") await renderRun(r, seq);
    else if (r.screen === "repo") await renderRepo(r, seq);
    else if (r.screen === "commit") await renderCommit(r, seq);
  } catch (e) {
    if (seq !== renderSeq) return;
    setChrome("jobs", backTarget(r));
    main.replaceChildren(errorBox(e));
  }
}

// Only the newest navigation may paint: a slow answer for a screen already left must
// not overwrite the one the operator is looking at.
function paint(seq, ...nodes) {
  if (seq !== renderSeq) return false;
  main.replaceChildren(...nodes);
  return true;
}

// ---- J1 ----

async function renderList(r, seq) {
  setChrome("jobs", "./");
  const data = await api("jobs");
  paint(seq, listView(data, changesRead()));
}

// The J1 banner announces an applied change until its receipt (J4) has been opened on
// this device; the source's 7-day window stays the outer limit (designer ruling,
// 2026-11-24). Kept per device in localStorage, keyed by commit, newest 50.
const READ_KEY = "thalamus.jobs.changes-read";

function changesRead() {
  try {
    const v = JSON.parse(localStorage.getItem(READ_KEY) || "[]");
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch (_) { return []; }
}

function markChangeRead(sha) {
  if (!sha) return;
  const read = changesRead().filter((x) => !sameCommit(x, sha));
  read.push(sha);
  try { localStorage.setItem(READ_KEY, JSON.stringify(read.slice(-50))); } catch (_) { /* private mode */ }
}

// Two abbreviations of one commit: one is a prefix of the other.
function sameCommit(a, b) {
  return !!a && !!b && (a.startsWith(b) || b.startsWith(a));
}

function bannerShown(banner, read) {
  return !!banner && !read.some((sha) => sameCommit(sha, banner.change));
}

function listView(data, read = []) {
  const out = [];
  if (bannerShown(data.banner, read)) {
    out.push(h("a.j-banner", { href: link("#/change/" + encodeURIComponent(data.banner.change)) },
      h("span.grow",
        h("span.j-banner-title", data.banner.title),
        h("span.j-banner-line.mono", data.banner.line)),
      h("span.j-banner-go", "review ›")));
  }
  out.push(h("div.j-sect",
    h("span.grow", h("span.s-label", "jobs"),
      h("span.j-sect-sub", "from the jobs source, its timers and its git log")),
    h("span.muted.small", data.summary || ""),
    h("a.s-link.j-repo-link", { href: "#/repo" }, "repo ›")));
  for (const g of data.groups || []) {
    out.push(h("div.j-group", h("span.grow", g.name || "no scope yet"), h("span.muted.small", g.note || "")));
    const rows = h("div.j-group-rows", { style: { "--scope": scopeHue(g.name) } });
    for (const j of g.jobs || []) rows.appendChild(jobRow(j));
    out.push(rows);
  }
  if (!(data.groups || []).length) out.push(h("p.s-empty", "The jobs source lists no jobs."));
  return h("div", out);
}

function jobRow(j) {
  return h("a.j-row", { href: link("#/job/" + encodeURIComponent(j.id)) },
    h("span.grow",
      h("span.j-row-name", j.name),
      h("span.j-row-line", j.line || "")),
    statusWord(j.status, "j-row-status"),
    // The comps' "···" overflow. Its only action so far is the job's history, so it
    // goes straight there rather than opening a one-item menu.
    h("a.j-more", { href: link("#/job/" + encodeURIComponent(j.id) + "/history"),
                    "aria-label": "History of " + j.name, onclick: (e) => e.stopPropagation() }, "···"));
}

// ---- J2 ----

async function renderJob(r, seq) {
  const q = r.params.run ? "?run=" + encodeURIComponent(r.params.run) : "";
  const data = await api("jobs/" + encodeURIComponent(r.job) + q);
  setChrome(data.name || r.job, backTarget(r));
  paint(seq, jobView(data, r));
}

function jobView(d, r) {
  const out = [];
  out.push(h("div.j-jobhead", { style: { "--scope": scopeHue(d.scope) } },
    h("div.j-jobhead-line", d.header && d.header.line),
    h("div.j-jobhead-sub.mono", d.header && d.header.sub)));
  if (d.run) out.push(runPicker(d, r));
  if (d.drift) {
    out.push(h("div.j-drift",
      h("span.grow", h("span.j-drift-title", d.drift.title), h("span.j-drift-line.mono", d.drift.line)),
      d.run && d.actions && d.actions.replay
        ? h("button.s-link", { type: "button", onclick: () => replayOnHead(d) }, "replay on HEAD ›")
        : null));
  }
  const steps = h("ol.j-steps");
  for (const s of d.stages || []) steps.appendChild(stageItem(s));
  out.push(steps);
  if (!d.run) out.push(h("p.s-empty", "No runs yet."));
  out.push(jobActions(d));
  return h("div.j-job", out);
}

function runPicker(d, r) {
  const runs = d.runs || [];
  const i = Math.max(0, runs.findIndex((x) => x.id === d.run.id));
  const go = (k) => {
    const target = runs[k];
    if (target) location.hash = "#/job/" + encodeURIComponent(d.id) + "?run=" + encodeURIComponent(target.id);
  };
  // Runs are newest first, so "◂" (older) is the next index. Left: when it ran and the
  // version it ran on, the version cut to seven characters and an ellipsis (N5: they never
  // overlap, whatever its length). Right: what the run produced, the source's words.
  return h("div.j-runpick",
    h("button.j-arrow", { type: "button", "aria-label": "Older run", disabled: i >= runs.length - 1,
                          onclick: () => go(i + 1) }, "◂"),
    h("a.grow.j-runpick-label.mono", { href: "#/run/" + encodeURIComponent(d.run.id) },
      h("span.j-runpick-when", d.run.label + " · "),
      h("span.j-runpick-ver", { title: d.run.version || "" }, d.run.version || "")),
    statusWord(d.run.outcome, "j-runpick-out"),
    h("button.j-arrow", { type: "button", "aria-label": "Newer run", disabled: i <= 0,
                          onclick: () => go(i - 1) }, "▸"));
}

function stageItem(s) {
  // The dot repeats the stage's tone; the card prints a status word only when the stage
  // is not the normal case (running, failed, found nothing), and its out line says what.
  const dotTone = s.reached && (s.tone || s.status) ? toneClass(s.tone || s.status.tone) : "";
  const card = h("div.j-stage" + (s.changed ? ".changed" : "") + (s.reached ? "" : ".unreached"),
    h("div.j-stage-top", h("span.j-stage-name", s.name), statusWord(s.status)),
    (s.lines || []).map((l) => h("div.j-stage-line", l)),
    (s.mono || []).map((l) => h("div.j-stage-line.mono.muted", l)),
    s.out ? h("div.j-stage-out.mono", "out " + s.out) : null,
    s.progress ? progressBar(s.progress) : null,
    s.changed ? h("div.j-stage-changed.small", "changed since this run") : null);
  return h("li.j-step", h("span.j-dot" + (s.reached ? ".on" : "") + (dotTone ? "." + dotTone : ""),
    { "aria-hidden": "true" }), card);
}

// Tool calls used of the cap: one fill (N5). The search and fetch split stays in the
// line above the bar, in the source's words ("45 of 60 calls · 12 search · 33 fetch").
function progressBar(p) {
  const cap = Math.max(p.cap || 0, p.used || 0, 1);
  return h("div.j-bar", { role: "img", "aria-label": `${p.used} of ${p.cap} calls` },
    h("span.j-bar-fill", { style: { width: (100 * (p.used || 0) / cap) + "%" } }));
}

function jobActions(d) {
  const run = h("button.s-btn.primary", { type: "button", disabled: !(d.actions && d.actions.run_now) },
    "Run now");
  armTwice(run, "Start a run ›", async () => {
    await apiPost("jobs/" + encodeURIComponent(d.id) + "/run", {});
    toast("Started " + d.name);
  });
  const replay = h("button.s-btn", { type: "button", disabled: !(d.run && d.actions && d.actions.replay) },
    "Replay…");
  replay.addEventListener("click", () => replayOnHead(d));
  return h("div.j-actions",
    run, replay,
    h("a.s-btn.j-btnlink", { href: "#/job/" + encodeURIComponent(d.id) + "/history" }, "History"));
}

// A button that spends something — a model run, a revert — takes two taps: the first
// changes its words to say what the second will do, and it falls back after four
// seconds. Not in the comps; chosen so a stray tap on a phone cannot start a paid run.
function armTwice(btn, armedText, action) {
  const idle = btn.textContent;
  let armed = 0;
  btn.addEventListener("click", async () => {
    if (!armed) {
      btn.textContent = armedText;
      armed = setTimeout(() => { armed = 0; btn.textContent = idle; }, 4000);
      return;
    }
    clearTimeout(armed);
    armed = 0;
    btn.disabled = true;
    try { await action(); } catch (e) { toast(e.message); }
    finally { btn.disabled = false; btn.textContent = idle; }
  });
}

// "Replay…": the selected run's stored input, re-run on HEAD. One confirmation sheet
// rather than a menu, because HEAD is the only target the source offers.
function replayOnHead(d) {
  const sheet = h("div.j-sheet", { role: "dialog", "aria-label": "Replay" });
  const close = () => sheet.remove();
  sheet.appendChild(h("div.j-sheet-card",
    h("div.j-sheet-title", "Replay run " + d.run.label + " on HEAD"),
    d.replay_note ? h("p.muted.small", d.replay_note) : null,
    h("div.j-sheet-acts",
      h("button.s-btn", { type: "button", onclick: close }, "Cancel"),
      h("button.s-btn.primary", { type: "button", onclick: async (e) => {
        e.target.disabled = true;
        try {
          await apiPost("runs/" + encodeURIComponent(d.run.id) + "/replay", { on: "HEAD" });
          toast("Replay started");
          close();
        } catch (err) { toast(err.message); e.target.disabled = false; }
      } }, "Replay"))));
  sheet.addEventListener("click", (e) => { if (e.target === sheet) close(); });
  document.body.appendChild(sheet);
}

// ---- J3 ----

async function renderHistory(r, seq) {
  const replays = r.params.replays !== "0";
  const data = await api("jobs/" + encodeURIComponent(r.job) + "/history?replays=" + (replays ? 1 : 0));
  setChrome(r.job + " · history", backTarget(r));
  paint(seq, historyView(data, r, replays));
}

function historyView(d, r, replays) {
  const toggle = switchEl(replays, "Show replays", (on) => {
    location.hash = "#/job/" + encodeURIComponent(r.job) + "/history" + (on ? "" : "?replays=0");
  });
  const cols = d.columns || [];
  const out = [
    h("div.s-row", h("span.grow", "show replays"), toggle),
    h("div.j-hist-head.mono.muted", h("span.grow", "run"), cols.map((c) => h("span.j-hist-col", c))),
  ];
  for (const it of d.items || []) out.push(historyItem(it, cols));
  if (d.more) out.push(h("a.s-link.j-more-link", { href: "#/repo" }, "older versions in the repo ›"));
  return h("div.j-hist", { style: { "--cols": String(Math.max(cols.length, 1)) } }, out);
}

function historyItem(it, cols) {
  if (it.type === "commit") {
    const target = it.change ? "#/change/" + encodeURIComponent(it.change) : "#/commit/" + encodeURIComponent(it.sha);
    return h("a.j-hist-commit" + (it.head || it.tag ? ".marked" : ""), { href: target },
      h("span.j-sha.mono" + (it.head || it.tag ? ".tone-accent" : ".muted"), it.sha),
      h("span.grow", h("span.j-hist-subject", it.subject), h("span.j-hist-line", it.line)));
  }
  if (it.type === "empty") return h("div.j-hist-empty", it.text);
  if (it.type === "shared") return sharedItem(it);
  if (it.type === "replays") {
    const grid = h("div.j-grid", { role: "table", "aria-label": it.title });
    (it.grid || []).forEach((row, k) => {
      const label = (it.rows || [])[k] || "";
      grid.appendChild(h("div.j-grid-row", { role: "row" },
        h("span.j-grid-label.small.muted", { role: "rowheader" }, label),
        row.map((cell) => h("span.j-cell." + toneClass(cell.tone), { role: "cell", title: cell.word },
          h("span.j-cell-word", cell.word)))));
    });
    return h("div.j-hist-run.replays",
      h("span.grow", h("span.j-hist-title", it.title), h("span.j-hist-line", it.line)),
      grid, it.note ? h("span.j-hist-note.small.muted", it.note) : null);
  }
  // A run: one cell per stage, or one span across them all for a single-stage job.
  const cells = it.span
    ? h("span.j-span.mono." + toneClass(it.span.tone), it.span.text)
    : h("span.j-cells", (it.cells || []).map((c) => c
      ? h("span.j-runcell.mono." + toneClass(c.tone), c.text) : h("span.j-runcell.none", "—")));
  return h("a.j-hist-run", { href: "#/run/" + encodeURIComponent(it.id) },
    h("span.grow", h("span.j-hist-title", it.title), h("span.j-hist-line", it.line)), cells);
}

// Commits between two of a job's versions that touched shared code only: one faint
// row that opens in place to list them, each linking to its commit.
function sharedItem(it) {
  const list = h("div.j-shared-list", { hidden: true },
    (it.commits || []).map((c) => h("a.j-commit.j-shared-commit", { href: "#/commit/" + encodeURIComponent(c.sha) },
      h("span.j-sha.mono.muted", c.sha),
      h("span.grow", h("span.j-hist-subject", c.subject), h("span.j-hist-line", c.line)))));
  const btn = h("button.j-shared", { type: "button", "aria-expanded": "false" }, it.text);
  btn.addEventListener("click", () => {
    list.hidden = !list.hidden;
    btn.setAttribute("aria-expanded", list.hidden ? "false" : "true");
  });
  return h("div.j-shared-wrap", btn, list);
}

// ---- J4 ----

async function renderChange(r, seq) {
  const d = await api("changes/" + encodeURIComponent(r.sha));
  setChrome("change " + d.sha, backTarget(r, { job: (d.job || "").split(":")[0] }));
  if (paint(seq, changeView(d))) markChangeRead(d.sha);
}

function changeView(d) {
  const out = [h("div.j-change-head", h("h1.j-h1", d.title), h("div.muted.small", d.line))];
  if (d.gate) out.push(gateCard(d.gate));
  for (const f of d.diff || []) out.push(diffCard(f));
  out.push(changeFoot(d));
  return h("div.j-change", out);
}

function gateCard(g) {
  const table = h("div.j-gate-table", { role: "table" },
    h("div.j-gate-row.head.mono.muted", { role: "row" },
      h("span", { role: "columnheader" }, ""), h("span", { role: "columnheader" }, "before"),
      h("span", { role: "columnheader" }, "after")),
    (g.rows || []).map((row) => h("div.j-gate-row", { role: "row" },
      h("span", { role: "rowheader" }, row.label), h("span.mono.muted", row.before), h("span.mono.strong", row.after))));
  // A check is a word and a mark: "✓" or "✗" after the label, in the tone. The mark
  // is a glyph, not colour, so greyscale keeps it.
  const checks = h("div.j-checks", (g.checks || []).map((c) =>
    h("span." + (c.passed ? "tone-ok" : "tone-danger"), c.label + (c.passed ? " ✓" : " ✗"))));
  return h("section.s-card.j-gate",
    h("div.s-label." + toneClass(g.status && g.status.tone), g.status && g.status.word),
    h("div.j-gate-line", g.line), table, h("hr.j-hr"), checks,
    g.note ? h("p.j-gate-note", g.note) : null);
}

// The indentation every non-blank line of a hunk shares, so a prompt nested in a list
// does not start each diff line halfway across a phone.
function commonIndent(lines) {
  let min = Infinity;
  for (const l of lines) {
    if (!l.text || !l.text.trim()) continue;
    min = Math.min(min, l.text.length - l.text.trimStart().length);
  }
  return Number.isFinite(min) ? min : 0;
}

function diffCard(f) {
  const lines = f.lines || [];
  const cut = commonIndent(lines);
  // The +/- sits in its own gutter column; a wrapped line hangs under its text, so
  // the sign stays readable on every visual line of it.
  return h("section.s-card.j-diff",
    h("div.j-diff-head.mono", h("span.grow", f.path), h("span.muted", `+${f.added} −${f.removed}`)),
    h("div.j-diff-body.mono", lines.map((l) =>
      h("div.j-diff-line." + (l.op === "+" ? "add" : l.op === "-" ? "del" : "ctx"),
        h("span.j-diff-op", { "aria-hidden": l.op === " " ? "true" : null }, l.op === " " ? "" : l.op),
        h("span.j-diff-text", l.text.slice(Math.min(cut, l.text.length - l.text.trimStart().length)))))));
}

function changeFoot(d) {
  const job = d.auto_apply_job || d.job;
  const toggle = switchEl(d.auto_apply, "Auto-apply for this job", async (on) => {
    await apiPost("jobs/" + encodeURIComponent(job) + "/auto-apply", { on });
    toast(on ? "Auto-apply is on" : "Auto-apply is paused");
  });
  const revert = h("button.s-btn.danger", { type: "button", disabled: !(d.revert && d.revert.available) }, "Revert");
  armTwice(revert, "Revert ›", async () => {
    const res = await apiPost("changes/" + encodeURIComponent(d.sha) + "/revert", {});
    toast("Reverted as " + (res.commit || "a new commit") + "; auto-apply paused");
    route();
  });
  return h("div.j-foot",
    h("div.j-foot-row", h("span.grow", "auto-apply for this job"), toggle),
    h("div.j-foot-acts", revert,
      h("a.s-btn.j-btnlink", { href: "#/commit/" + encodeURIComponent(d.sha) }, "Open commit in repos ›")),
    h("p.small.muted", d.revert && !d.revert.available && d.revert.reason
      ? d.revert.reason : "Reverting pauses auto-apply for this job first."));
}

// ---- J5 ----

async function renderRun(r, seq) {
  if (r.params.view === "events") return renderEvents(r, seq);
  const all = r.params.findings === "all";
  const d = await api("runs/" + encodeURIComponent(r.run) + (all ? "?findings=all" : ""));
  setChrome(d.title || "run", backTarget(r, { job: d.job }));
  paint(seq, runView(d));
}

function runView(d) {
  const out = [h("div.j-jobhead", { style: { "--scope": "var(--accent)" } },
    h("div.j-runhead", h("span.grow.j-runhead-job", d.job), statusWord(d.status)),
    h("div.j-jobhead-sub.mono", d.line))];
  out.push(h("div.j-tiles", (d.tiles || []).map((t) => h("div.s-card.j-tile",
    h("div.j-tile-label", t.label), h("div.j-tile-value.mono", t.value), h("div.j-tile-sub.small.muted", t.sub)))));
  const f = d.findings || {};
  out.push(h("div.j-sect.j-find-head", h("span.s-label", f.heading || "findings"),
    (f.items || []).some((x) => !x.rejected)
      ? h("span.j-find-cap", "Rate each one: your ratings tune what this job reports.") : null));
  for (const item of f.items || []) out.push(findingRow(item));
  if (f.hidden) out.push(h("p.j-find-hidden", f.hidden));
  if (f.more) out.push(h("a.s-link.j-more-link", { href: "#/run/" + encodeURIComponent(d.id) + "?findings=all" },
    `${f.more} more kept findings ›`));
  if (d.events) out.push(h("a.s-link.j-more-link", { href: "#/run/" + encodeURIComponent(d.id) + "?view=events" },
    `raw stream · ${d.events} events ›`));
  return h("div.j-run", out);
}

// A kept finding is surface.js's findingCard. Its "evidence ›" opens the run's raw
// stream: J5 is already the run, and the stream is where the quotes it cites were read.
function findingRow(item) {
  if (item.rejected) {
    return h("div.j-finding.rejected",
      h("div.j-finding-title", item.title || item.observation),
      h("div.tone-danger.small", item.rejected.word),
      item.rejected.line ? h("div.muted.small", item.rejected.line) : null);
  }
  return h("div.j-finding", findingCard(item, (run) => "#/run/" + encodeURIComponent(run) + "?view=events"));
}

// The raw stream: what the run's model session emitted, one line per event, as text.
// Web pages a research stage fetched pass through here, so nothing in it is markup.
async function renderEvents(r, seq) {
  const d = await api("runs/" + encodeURIComponent(r.run) + "/events");
  setChrome("raw stream", "#/run/" + encodeURIComponent(r.run));
  const list = h("ol.j-events.mono");
  let last = 0;
  const add = (events) => events.forEach((e) => {
    last = e.seq;
    list.appendChild(h("li.j-event", h("span.muted", String(e.seq).padStart(4, " ") + " "),
      h("span.j-event-type", e.type + (e.subtype ? "/" + e.subtype : "")), " ", e.text));
  });
  add(d.events || []);
  const more = h("button.s-link.j-more-link", { type: "button", hidden: !d.more, onclick: async () => {
    try {
      const next = await api("runs/" + encodeURIComponent(r.run) + "/events?after=" + last);
      add(next.events || []);
      more.hidden = !next.more;
    } catch (e) { toast(e.message); }
  } }, "more ›");
  paint(seq, h("div", list, more));
}

// ---- J6 ----

async function renderRepo(r, seq) {
  const jobsOnly = r.params.all !== "1";
  const d = await api("repo?jobs_only=" + (jobsOnly ? 1 : 0));
  setChrome(d.name || "repo", backTarget(r));
  paint(seq, repoView(d, jobsOnly));
}

function repoView(d, jobsOnly) {
  const toggle = switchEl(jobsOnly, "Only commits that changed a job", (on) => {
    location.hash = "#/repo" + (on ? "" : "?all=1");
  });
  return h("div.j-repo",
    h("div.j-jobhead", { style: { "--scope": "var(--muted)" } },
      h("div.j-runhead", h("span.grow.j-runhead-job", d.name), statusWord(d.status)),
      h("div.j-jobhead-sub", d.line)),
    h("div.s-row", h("span.grow", "only commits that changed a job"), toggle),
    h("div.j-sect", h("span.s-label.grow", "commits"), h("span.muted.small", d.summary || "")),
    (d.commits || []).map((c) => h("a.j-commit", { href: "#/commit/" + encodeURIComponent(c.sha) },
      h("span.j-sha.mono" + (c.tag ? ".tone-accent" : ".muted"), c.sha),
      h("span.grow", h("span.j-hist-subject", c.subject), h("span.j-hist-line", c.line)),
      c.tag ? h("span.j-pill", c.tag) : null)),
    h("a.s-link.j-more-link", { href: "#/" }, `jobs on this checkout · ${d.jobs || 0} ›`));
}

async function renderCommit(r, seq) {
  const d = await api("commits/" + encodeURIComponent(r.sha));
  setChrome(d.sha, backTarget(r));
  paint(seq, h("div.j-change",
    h("div.j-change-head", h("h1.j-h1", d.subject), h("div.muted.small", d.line),
      d.tag ? h("span.j-pill", d.tag) : null),
    d.body ? h("pre.j-body.mono", d.body) : null,
    d.change ? h("a.s-link.j-more-link", { href: "#/change/" + encodeURIComponent(d.change) }, "replay gate receipt ›") : null,
    (d.runs || []).length ? h("div.j-sect", h("span.s-label", "runs on this commit")) : null,
    (d.runs || []).map((x) => h("a.j-commit", { href: "#/run/" + encodeURIComponent(x.id) },
      h("span.grow", x.label), statusWord(x.outcome))),
    (d.files || []).map(diffCard)));
}

// ---- D1, the desktop canvas ----

// Row pitch is tighter than J2's cards: D1 has to show the graph and the version lane in
// one 980 px viewport (designer review, 2026-11-24). A column holding a staged job or a
// long job name is wide (the comp's 172 px model-job column), so names break at their
// hyphens only when they are longer than that.
const CANVAS = { colW: 142, wideW: 186, nodeW: 128, wideNodeW: 172, nodeH: 56, rowH: 96, top: 44, left: 16 };

function columnWidths(nodes, count) {
  const widths = [];
  for (let c = 0; c < count; c++) {
    const wide = nodes.some((n) => n.col === c && ((n.stages || []).length || (n.job && (n.title || "").length > 16)));
    widths.push(wide ? CANVAS.wideW : CANVAS.colW);
  }
  return widths;
}

// Pixel boxes for nodes laid out by (col, row). A row grows to its tallest node and
// every row below moves down, so a staged job never covers the row under it.
function graphLayout(nodes, count) {
  const widths = columnWidths(nodes, Math.max(count || 0, ...nodes.map((n) => n.col + 1)));
  const colX = [];
  widths.reduce((x, w, c) => { colX[c] = x; return x + w; }, CANVAS.left);
  const heightOf = (n) => CANVAS.nodeH + ((n.stages || []).length ? 14 + n.stages.length * 30 : 0);
  const rowSpan = {};
  for (const n of nodes) rowSpan[n.row] = Math.max(rowSpan[n.row] || 0, heightOf(n) + CANVAS.rowH - CANVAS.nodeH);
  const rowTop = {};
  let y = CANVAS.top;
  const maxRow = Math.max(-1, ...nodes.map((n) => n.row));
  for (let r = 0; r <= maxRow; r++) {
    rowTop[r] = y;
    y += rowSpan[r] || CANVAS.rowH;
  }
  const boxes = {};
  for (const n of nodes) {
    const wide = widths[n.col] === CANVAS.wideW;
    boxes[n.id] = { x: colX[n.col], y: rowTop[n.row], w: wide ? CANVAS.wideNodeW : CANVAS.nodeW, h: heightOf(n) };
  }
  return { boxes, colX, widths, width: CANVAS.left * 2 + widths.reduce((a, b) => a + b, 0) };
}

// An edge from the right edge of one box to the left edge of another, crossing no other
// box. Where nothing stands in its way it is a cubic; otherwise it runs orthogonally:
// out into the gutter, along a horizontal channel that clears every box it passes over,
// and back in through the gutter before its target.
function routeEdge(a, b, others) {
  const x1 = a.x + a.w, y1 = a.y + Math.min(a.h, CANVAS.nodeH) / 2;
  const x2 = b.x, y2 = b.y + Math.min(b.h, CANVAS.nodeH) / 2;
  const pad = 6;
  const span = others.filter((o) => o.x < x2 && o.x + o.w > x1);
  const clear = (y) => span.every((o) => y < o.y - pad || y > o.y + o.h + pad);
  const lo = Math.min(y1, y2), hi = Math.max(y1, y2);
  const blocked = span.some((o) => o.y - pad < hi && o.y + o.h + pad > lo);
  if (!blocked) {
    const dx = Math.max(16, (x2 - x1) / 2);
    return `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`;
  }
  const candidates = [y1, y2];
  for (const o of span) candidates.push(o.y - 2 * pad, o.y + o.h + 2 * pad);
  const ych = candidates.filter(clear).sort((p, q) => (Math.abs(p - y1) + Math.abs(p - y2)) - (Math.abs(q - y1) + Math.abs(q - y2)))[0];
  const gx1 = x1 + 4, gx2 = x2 - 4;
  return `M${x1},${y1} H${gx1} V${ych} H${gx2} V${y2} H${x2}`;
}

const canvasState = { job: null, view: "graph", scope: "", tab: "versions", compare: null, version: null, run: null };

async function renderCanvas(r, seq) {
  setChrome("jobs", "./");
  const [graph, list] = await Promise.all([api("graph"), api("jobs")]);
  const firstJob = (graph.nodes || []).find((n) => n.job && (n.stages || []).length) ||
    (graph.nodes || []).find((n) => n.job);
  canvasState.job = r.params.job || canvasState.job || (firstJob && firstJob.job);
  const q = canvasState.run ? "?run=" + encodeURIComponent(canvasState.run) : "";
  const job = canvasState.job ? await api("jobs/" + encodeURIComponent(canvasState.job) + q).catch(() => null) : null;
  const history = canvasState.job
    ? await api("jobs/" + encodeURIComponent(canvasState.job) + "/history?replays=1").catch(() => null) : null;
  if (seq !== renderSeq) return;
  paint(seq, canvasView(graph, list, job, history));
}

function versionsOf(history) {
  return (history && history.items || []).filter((i) => i.type === "commit");
}

// Pick a job in the graph: its run and version selections start over.
function pickJob(id) {
  canvasState.job = id;
  canvasState.compare = null;
  canvasState.version = null;
  canvasState.run = null;
  route();
}

function canvasView(graph, list, job, history) {
  const scopes = [...new Set((graph.nodes || []).map((n) => n.scope).filter(Boolean))].sort();
  const versions = versionsOf(history);
  // The comp's toolbar selectors. "version" picks the version the inspector compares
  // with HEAD and marks it in the Versions list; "run" picks the run whose stages and
  // pinned input the inspector shows. Both follow the job picked in the graph.
  const versionSel = selectEl(versions.map((c) => c.sha), canvasState.version || (versions[0] && versions[0].sha) || "",
    (sha) => { const c = versions.find((x) => x.sha === sha); return c && c.head ? `${sha} HEAD` : sha; },
    (sha) => { canvasState.version = sha; canvasState.compare = null; route(); });
  const runs = (job && job.runs) || [];
  const runSel = selectEl(["", ...runs.map((x) => x.id)], canvasState.run || "",
    (id) => (id ? (runs.find((x) => x.id === id) || {}).label || id : "latest"),
    (id) => { canvasState.run = id || null; route(); });
  const bar = h("div.d-bar",
    h("div.d-seg", ["graph", "grid"].map((v) => h("button.d-segbtn" + (canvasState.view === v ? ".on" : ""),
      { type: "button", "aria-pressed": canvasState.view === v ? "true" : "false",
        onclick: () => { canvasState.view = v; route(); } }, v))),
    h("label.d-select", "scope ",
      selectEl(["", ...scopes], canvasState.scope, (v) => v || "all", (v) => { canvasState.scope = v; route(); })),
    h("span.grow"),
    h("label.d-select.mono", "version ", versionSel),
    h("label.d-select.mono", "run ", runSel));
  const body = canvasState.view === "grid"
    ? h("div.d-gridview", history ? historyView(history, { job: canvasState.job, params: {} }, true)
      : h("p.s-empty", "Pick a job in the graph."))
    : graphView(graph);
  return h("div.d-wrap",
    h("div.d-left", bar, body, laneView(graph.lane)),
    inspector(job, history, list));
}

function selectEl(values, current, label, onchange) {
  const s = h("select.d-sel");
  for (const v of values) {
    const o = h("option", { value: v }, label(v));
    if (v === current) o.selected = true;
    s.appendChild(o);
  }
  s.addEventListener("change", () => onchange(s.value));
  return s;
}

function graphView(graph) {
  const nodes = (graph.nodes || []).filter((n) => !canvasState.scope || !n.scope || n.scope === canvasState.scope);
  const keep = new Set(nodes.map((n) => n.id));
  const { boxes, colX, width } = graphLayout(nodes, (graph.columns || []).length);
  const height = Math.max(...Object.values(boxes).map((b) => b.y + b.h), 200) + 24;
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("class", "d-edges");
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  svg.setAttribute("aria-hidden", "true");
  for (const [a, b] of graph.edges || []) {
    if (!keep.has(a) || !keep.has(b)) continue;
    const p = document.createElementNS(svgNS, "path");
    const others = Object.entries(boxes).filter(([id]) => id !== a && id !== b).map(([, box]) => box);
    p.setAttribute("d", routeEdge(boxes[a], boxes[b], others));
    const sel = nodes.find((n) => n.id === b && n.job === canvasState.job) ||
      nodes.find((n) => n.id === a && n.job === canvasState.job);
    p.setAttribute("class", sel ? "on" : "");
    svg.appendChild(p);
  }
  const layer = h("div.d-graph", { style: { width: width + "px", height: height + "px" } }, svg,
    (graph.columns || []).map((c, k) => h("span.d-col.s-label", { style: { left: colX[k] + "px" } }, c)),
    nodes.map((n) => graphNode(n, boxes[n.id])),
    (graph.note || []).map((t) => {
      // A caption sits under the node in its cell; with no node there, under the row.
      const host = nodes.find((n) => n.row === t.row && n.col === t.col);
      const top = host ? boxes[host.id].y + boxes[host.id].h + 6 : CANVAS.top + t.row * CANVAS.rowH + CANVAS.nodeH + 6;
      return h("span.d-note.small.muted", { style: { left: (colX[t.col] || CANVAS.left) + "px", top: top + "px" } }, t.text);
    }));
  return h("div.d-graphwrap", layer);
}

function graphNode(n, box) {
  const selected = n.job && n.job === canvasState.job;
  const el = h((n.job ? "button" : "div") + ".d-node" + (n.planned ? ".planned" : "") + (selected ? ".sel" : ""),
    { type: n.job ? "button" : null, style: { left: box.x + "px", top: box.y + "px", width: box.w + "px",
      minHeight: box.h + "px", "--scope": n.scope ? scopeHue(n.scope) : "transparent" },
      onclick: n.job ? () => pickJob(n.job) : null },
    h("span.d-node-title", n.title), h("span.d-node-line", n.line),
    statusWord(n.status, "d-node-status"),
    (n.stages || []).length ? h("span.d-stages", n.stages.map((s) =>
      h("span.d-stage.mono", h("span.grow", s.name), h("span", s.text)))) : null);
  return el;
}

// The version lane: one row per job, commits along the bottom, a mark where a job ran
// on a version. Marks are text ("1", "6 replays", "next"), so the lane reads without
// its tones. The commit axis is pinned at the bottom of the canvas column, always in
// view; the job rows above it scroll on their own once there are more than four.
const LANE = { x0: 170, rowH: 30, rowsMax: 4, axisH: 66 };

function laneView(lane) {
  if (!lane || !(lane.commits || []).length) return null;
  const commits = lane.commits;
  const step = Math.max(56, Math.min(82, 840 / Math.max(commits.length, 1)));
  const xOf = {};
  commits.forEach((c, k) => { xOf[c.sha] = LANE.x0 + k * step; });
  const jobs = lane.jobs || [];
  const rows = jobs.map((j, k) => h("div.d-lane-row", { style: { top: (k * LANE.rowH) + "px" } },
    h("span.d-lane-name.small.muted", j.name),
    (j.marks || []).filter((m) => m.sha in xOf).map((m) => h("span.d-mark.mono." + toneClass(m.tone),
      { style: { left: (xOf[m.sha] - 20) + "px" } }, m.text))));
  const axis = commits.map((c) => h("span.d-tick.mono" + (c.tag || c.head ? ".tone-accent" : ".muted"),
    { style: { left: (xOf[c.sha] - 28) + "px" } },
    h("span.d-tick-dot" + (c.tag || c.head ? ".on" : "")), c.sha, h("br"), c.time,
    c.tag ? h("span.d-tag.small", c.tag) : null));
  const width = LANE.x0 + commits.length * step + 40;
  const section = h("section.d-lane",
    h("div.d-lane-in", { style: { width: width + "px" } },
      h("span.s-label.d-lane-label", "versions" + (lane.repo ? " · " + lane.repo : "")),
      h("div.d-lane-rows", { style: { height: Math.min(jobs.length, LANE.rowsMax) * LANE.rowH + "px", width: width + "px" } },
        h("div.d-lane-rows-in", { style: { height: jobs.length * LANE.rowH + "px" } }, rows)),
      h("div.d-lane-axis", { style: { height: LANE.axisH + "px" } }, axis)));
  // When the commits outgrow the pane, open scrolled to the newest, so it is the oldest
  // that sit past the edge.
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(() => { section.scrollLeft = section.scrollWidth; });
  }
  return section;
}

const VERSIONS_SHOWN = 5;

function inspector(job, history, list) {
  if (!job) return h("aside.d-insp", h("p.s-empty", "Pick a job in the graph."));
  const tabs = ["config", "runs", "versions"];
  const tabBar = h("div.d-tabs", { role: "tablist" }, tabs.map((t) => h("button.d-tab" + (canvasState.tab === t ? ".on" : ""),
    { type: "button", role: "tab", "aria-selected": canvasState.tab === t ? "true" : "false",
      onclick: () => { canvasState.tab = t; route(); } }, t[0].toUpperCase() + t.slice(1))));
  let body;
  if (canvasState.tab === "config") {
    body = h("ol.j-steps.compact", (job.stages || []).map(stageItem));
  } else if (canvasState.tab === "runs") {
    body = h("div", (job.runs || []).map((x) => h("a.j-commit", { href: "#/run/" + encodeURIComponent(x.id) },
      h("span.grow", h("span.j-hist-subject", x.label), h("span.j-hist-line.mono", "on " + x.version)), statusWord(x.status))));
  } else {
    const commits = versionsOf(history);
    const picked = canvasState.version;
    body = h("div",
      h("ol.d-versions", commits.slice(0, VERSIONS_SHOWN).map((c) => {
        const on = c.head || c.tag || (picked && sameCommit(picked, c.sha));
        return h("li.d-version" + (on ? ".on" : ""),
          h("a.mono" + (on ? ".tone-accent" : ".muted"),
            { href: c.change ? "#/change/" + encodeURIComponent(c.change) : "#/commit/" + encodeURIComponent(c.sha) }, c.sha),
          h("div.j-hist-subject", c.subject), h("div.j-hist-line", c.line));
      })),
      commits.length > VERSIONS_SHOWN || (history && history.more)
        ? h("a.s-link.d-all", { href: "#/job/" + encodeURIComponent(job.id) + "/history" }, "all versions ›") : null);
  }
  const compare = canvasState.compare ? diffPanel(canvasState.compare) : null;
  const from = canvasState.version || (job.run && job.run.version);
  const pinned = job.run ? h("section.d-insp-sec",
    h("div.s-label", "pinned input"),
    h("div", job.pinned ? job.pinned.title : "run " + job.run.label),
    job.pinned && job.pinned.line ? h("div.small.muted", job.pinned.line) : null,
    h("div.j-foot-acts",
      h("button.s-btn.primary", { type: "button", disabled: !(job.actions && job.actions.replay),
        onclick: () => replayOnHead(job) }, "Replay HEAD on it"),
      h("button.s-btn", { type: "button", disabled: !from, onclick: async () => {
        try {
          canvasState.compare = await api("jobs/" + encodeURIComponent(job.id) + "/diff?from="
            + encodeURIComponent(from) + "&to=HEAD");
          route();
        } catch (e) { toast(e.message); }
      } }, "Compare versions"))) : null;
  const auto = h("section.d-insp-sec",
    h("div.s-label", "auto-apply"),
    h("div.j-foot-row", h("span.grow", "apply gated changes live"),
      switchEl(job.auto_apply, "Apply gated changes live", async (on) => {
        await apiPost("jobs/" + encodeURIComponent(job.auto_apply_job || job.id) + "/auto-apply", { on });
        toast(on ? "Auto-apply is on" : "Auto-apply is paused");
      })),
    job.gate_rule ? h("div.small.muted", job.gate_rule) : null);
  return h("aside.d-insp",
    h("div.d-insp-head", { style: { "--scope": scopeHue(job.scope) } },
      h("a.d-insp-title", { href: "#/job/" + encodeURIComponent(job.id) }, job.name),
      h("div.small.muted", job.header && job.header.line),
      h("div.small.muted.mono", job.header && job.header.sub)),
    tabBar, h("div.d-insp-body", body), compare, pinned, auto);
}

function diffPanel(d) {
  return h("section.d-insp-sec",
    h("div.j-foot-row", h("span.s-label.grow", `${d.from} → ${d.to}`),
      h("button.s-link", { type: "button", onclick: () => { canvasState.compare = null; route(); } }, "close")),
    (d.files || []).length ? d.files.map(diffCard) : h("p.small.muted", "No change to this job's prompts or config."));
}

// ---- boot ----

if (typeof window !== "undefined" && document.getElementById("main")) {
  window.addEventListener("hashchange", route);
  // A desktop window resized across the threshold swaps D1 and J1.
  let wasDesk = window.innerWidth >= DESKTOP_MIN_PX;
  window.addEventListener("resize", () => {
    const desk = window.innerWidth >= DESKTOP_MIN_PX;
    if (desk !== wasDesk) { wasDesk = desk; route(); }
  });
  // No timed poll: these screens change when a job runs, minutes apart at the
  // fastest. Coming back to the page is when the operator expects fresh numbers.
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") route(); });
  route();
}
