// The room dialogue composer. What matters here is what the client does NOT decide.
//
// The pane composer types into a window the operator is watching, where answering a
// permission prompt on purpose is a primary use. The dialogue addresses members
// nobody is looking at, so the Enter after the text could answer a prompt the sender
// never saw — and the whole defence against that lives in the server's pre-flight.
// A client that duplicated any part of that rule would be a second policy about who
// is safe to type into, and two policies drift.
//
// So these tests pin two things: the client forwards and renders rather than judging,
// and a refusal reaches the operator verbatim instead of becoming a generic failure.

import {
  readApp, extractFunction, evaluate, stripComments,
  suite, check, contains, lacks, lacksMatch, done,
} from "./harness.mjs";
import { HARNESS_STATUSES } from "./statuses.mjs";

const src = readApp();
const source = [
  extractFunction("openDialogue", src),
  extractFunction("closeDialogue", src),
  extractFunction("runDialogue", src),
].join("\n");

function load({ ok = true, data = {} } = {}) {
  const posts = [];
  const els = {
    dialogue: { hidden: true },
    dialogueRoom: { textContent: "" },
    dialogueText: { value: "", focus() {} },
    dialoguePartial: { checked: false },
    dialogueGo: { disabled: false },
    dialogueCheck: { disabled: false },
    dialogueLog: { hidden: true, textContent: "" },
  };
  const api = evaluate(
    source + "\nfunction _room(){ return dialogueRoom; }",
    ["openDialogue", "closeDialogue", "runDialogue", "_room"],
    {
      els,
      dialogueRoom: null,
      postJson: async (path, body) => { posts.push({ path, body }); return { ok, data }; },
      poll: () => {},
      setTimeout: (fn) => fn(),
    },
  );
  return { api, els, posts };
}

suite("dialogue: opening targets one room");
{
  const { api, els } = load();
  api.openDialogue("alpha");
  check("shows the panel", els.dialogue.hidden === false);
  check("names the room it will address", els.dialogueRoom.textContent === "alpha");
  check("starts disabled — an empty message still costs every recipient a turn",
    els.dialogueGo.disabled === true);
  check("clears any previous result", els.dialogueLog.textContent === "");
}

{
  const { api, els } = load();
  api.openDialogue("");
  check("a falsy room opens nothing: `any` and `solo` name no addressable room",
    els.dialogue.hidden === true);
}

suite("dialogue: the request is a forward, not a decision");
{
  const { api, els, posts } = load({ ok: true, data: { note: "2/2 delivered" } });
  api.openDialogue("alpha");
  els.dialogueText.value = "  stand up  ";
  els.dialoguePartial.checked = true;
  await api.runDialogue(false);

  check("posts exactly once", posts.length === 1, `got ${posts.length}`);
  check("to the dispatch endpoint", posts[0].path === "api/dispatch");
  check("carrying the room", posts[0].body.room === "alpha");
  check("with the message trimmed", posts[0].body.message === "stand up");
  check("and the partial flag as the operator set it", posts[0].body.partial === true);
  check("dryRun false on a real say", posts[0].body.dryRun === false);
  contains("renders the server's own note", els.dialogueLog.textContent, "2/2 delivered");
}

suite("dialogue: check-only is a dry run on the server");
{
  const { api, els, posts } = load({ ok: true, data: { note: "would deliver to 2" } });
  api.openDialogue("alpha");
  els.dialogueText.value = "ping";
  await api.runDialogue(true);
  check("asks the server for the dry run", posts[0].body.dryRun === true);
  check("does not decide reachability itself — one request, no filtering",
    posts.length === 1);
}

suite("dialogue: a refusal reaches the operator verbatim");
{
  const refusal =
    "refusing the whole fan-out: 1 of 3 target(s) cannot be delivered to — " +
    "`alpha-homelab` is `waiting`";
  const { api, els } = load({ ok: false, data: { error: refusal } });
  api.openDialogue("alpha");
  els.dialogueText.value = "ping";
  await api.runDialogue(false);

  contains("names the target that refused", els.dialogueLog.textContent, "alpha-homelab");
  contains("and why", els.dialogueLog.textContent, "waiting");
  lacks("without flattening it to a generic failure",
    els.dialogueLog.textContent, "unknown error");
  check("re-enables the button so the operator can fix and retry",
    els.dialogueGo.disabled === false);
}

suite("dialogue: an empty message never reaches the server");
{
  const { api, posts } = load();
  api.openDialogue("alpha");
  await api.runDialogue(false);
  check("nothing posted for an empty box", posts.length === 0);
}

{
  const { api, posts } = load();
  api.openDialogue("alpha");
  await api.runDialogue(false);
  check("nor for whitespace only", posts.length === 0);
}

// ---------------------------------------------------------------------------
// The one-owner guard
//
// One invariant, stated once: *forbidden is a second reader of a field the server
// has already reduced for policy.* The harness session status is read for policy in
// `harness/dispatch.py` — the pre-flight refuses to type into a `waiting` session —
// and reduced to the `blocked` boolean in `console/server.py`. A client that read
// that field again would be a second policy about the same fact, and two policies
// drift. Which is why a row is handed `observed` / `blocked` / `blocked_since` and
// no status string at all.
//
// The guard binds to the *shape* of a second reading, not to the spelling of a
// status word. A word list is a proxy for the invariant and fails from both ends: it
// fires on a local named `busy` holding an in-flight flag, which decides nothing, and
// it misses `el.textContent = w.status`, which reaches straight past the reduction
// while spelling none of the words.
//
// Comments are exempt (see `stripComments`) — explaining the ban is not committing
// the offence, and the old scan taxed the source for describing its own invariant.

const STATUS = HARNESS_STATUSES.join("|");
// A status *literal*: the value in quotes. Bare identifiers are never matched — that
// is what made the word list unusable. `\x60` is a backtick, spelled in hex to stay
// readable inside these template strings.
const LIT = String.raw`(?:"(?:${STATUS})"|'(?:${STATUS})'|\x60(?:${STATUS})\x60)`;
const RE = String.raw`/[^/\n]*\b(?:${STATUS})\b[^/\n]*/[a-z]*`;   // a regex over the vocabulary

// A. No branching on a status value.
const BRANCHES = [
  ["compares against a status literal",
    String.raw`(?:[!=]==?\s*${LIT}|${LIT}\s*[!=]==?)`],
  ["switches on a status",
    String.raw`\bcase\s+${LIT}|\bswitch\s*\([^)]*\bstatus\b[^)]*\)`],
  // Substring sniffing is branching with the `if` hidden.
  ["sniffs a status literal",
    String.raw`\.(?:includes|startsWith|endsWith|indexOf|search|match|test)\s*\(\s*(?:${LIT}|${RE})`],
  ["tests a status regex", String.raw`${RE}\s*\.\s*test\b`],
  // A lookup table is an opinion with the `if` factored out. Anchored to key
  // position — `{`, `,` or a line start — so `cond ? "idle" : "busy"` is not a hit:
  // that branches on `cond`, not on a status value.
  ["maps from status literals", String.raw`(?:[{,]|^|\n)\s*${LIT}\s*:`],
];

// C. Mechanism names stay literal bans. A different failure — the client
// re-implementing tmux delivery rather than misreading a status — and so a different
// rule. Its real guard is behavioural (the dialogue posts exactly once, to
// `api/dispatch`); this is a cheap belt on that.
const MECHANISM = [
  ["addresses a pane", String.raw`\bpanes?\b`],
  ["sends keys", String.raw`\bsend[-_]?keys\b`],
];

// B. No status field on a row at all — applied to the row renderers only, below.
const ROW_FIELDS = [
  ["reads a status field", String.raw`\.status\w*`],
  ["reads a status field by subscript", String.raw`\[\s*(["'\x60])status\1\s*\]`],
];

function guard(label, text) {
  const code = stripComments(text);
  for (const [what, pattern] of [...BRANCHES, ...MECHANISM]) {
    lacksMatch(`${label} never ${what}`, code, new RegExp(pattern, "i"));
  }
  return code;
}

/** Every check that fires on `text` — the guard's verdict, as data. */
function violations(text) {
  const code = stripComments(text);
  return [...BRANCHES, ...MECHANISM, ...ROW_FIELDS]
    .filter(([, p]) => new RegExp(p, "i").test(code))
    .map(([what]) => what);
}

suite("dialogue: the client holds no view of who is reachable");
{
  guard("the dialogue", source);
}

suite("rows: the client renders liveness, it does not decide it");
{
  // The same rule over the renderers that draw a session row, because that is where
  // a blocked-session indicator gets drawn. Keep this list pointed at whatever
  // renders the roster: a renderer that leaves it is unguarded, and a renamed one
  // fails extraction loudly rather than passing vacuously.
  const rowSource = [
    extractFunction("renderRail", src),
    extractFunction("renderAdminWindows", src),
    extractFunction("renderDistill", src),
  ].join("\n");
  const rowCode = guard("a row renderer", rowSource);

  // B. No status field on a row at all. The payload serves none, so any read is
  // off-contract by construction — which is what closes the verbatim-render hole,
  // and closes it by contract rather than by vocabulary: there is nothing there to
  // render. This does not prejudge which words a row may *display*. If the server
  // composes a state string under its own field name, the row prints it and this
  // check never sees it — the ban is on reading the policy field, not on showing a
  // word.
  //
  // Scoped to the row renderers deliberately. `.status` elsewhere in the client is a
  // different field entirely — a tool call's `pending`, or an HTTP response code —
  // so widening this to any function that fetches would be a false positive.
  for (const [what, pattern] of ROW_FIELDS) {
    lacksMatch(`a row renderer never ${what}`, rowCode, new RegExp(pattern, "i"));
  }
}

suite("the guard catches what it claims to");
{
  // A guard written as a regex passes just as quietly when it matches nothing at all,
  // so the shapes it must catch are asserted rather than assumed. Each of these is a
  // second reading of the reduced field, spelled a different way.
  for (const [shape, snippet] of [
    ["equality, field first", `if (w.status === "waiting") return;`],
    ["equality, literal first", `if ("busy" !== s.state) return;`],
    ["a switch over status", `switch (session.status) { default: break; }`],
    ["a case on a literal", `case "idle": draw(); break;`],
    ["substring sniffing", `if (s.includes("busy")) pulse();`],
    ["a regex test", `if (/waiting/.test(s)) pill();`],
    ["a regex handed to match", `const m = s.match(/idle/);`],
    ["a lookup table", `const LABEL = { "idle": "…", "busy": "working" };`],
    ["the verbatim render the word list missed", `el.textContent = w.status;`],
    ["a subscript read", `const s = w["status"];`],
    ["typing into a pane", `sendKeys(pane, text);`],
    // The state slot draws a server-composed word, so which states get a clock stays
    // on the server: the elapsed is drawn iff the stamp is non-null, never iff the
    // word is `busy`. Reading the word back to decide is the same second policy.
    ["a clock decided from the word", `if (w.activity === "busy") clock(w);`],
  ]) {
    check(`caught: ${shape}`, violations(snippet).length > 0, `missed: ${snippet}`);
  }
}

suite("the guard spares what the design requires");
{
  // §1 of the handoff spec says branch on `observed` first, and `blocked` *is* the
  // server's reduction — rendering it is the whole point. §4.1 requires the client to
  // branch on the distill enum, which is a display field authored in `console/distill.py`
  // with no second reader. None of that is a status read, and a guard that broke any
  // of it would be forcing the client to stop rendering.
  for (const [shape, snippet] of [
    ["an in-flight local that merely shares a name",
      `const busy = !!w.recycling || !!w.closing;`],
    ["branching on observed", `return w.observed ? row(w) : notInReach();`],
    ["branching on the reduction itself", `return w.blocked ? pill() : slot();`],
    ["the distill enum", `if (d.state === "stalled") band("stalled");`],
    ["the distill enum in a lookup", `const TONE = { stalled: "warn", failed: "bad" };`],
    ["a tool call's own status field", `const pending = (it.state || "pending");`],
    ["prose explaining the ban", `// never read w.status — the server already did`],
    // The reduced word arrives under a display name and is printed, not interpreted.
    // The client names neither `idle` nor `busy` in its own source.
    ["printing the composed state word", `slot.textContent = w.activity;`],
    ["a clock decided from the stamp", `if (w.activity_since) clock(w.activity_since);`],
  ]) {
    const hits = violations(snippet);
    check(`spared: ${shape}`, hits.length === 0, `flagged as: ${hits.join(", ")}`);
  }
}

done();
