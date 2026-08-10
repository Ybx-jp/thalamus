// Two defects that froze the pane mirror, both triggered by tapping `read`.
//
// The selection guard defers a repaint while text is highlighted, so a selection
// survives the 1.2s repaint long enough to be copied. Switching views hides the
// pane with the selection still anchored inside it, and the guard then answered
// "yes" forever — every capture deferred, the pane stuck on the snapshot it held
// at the toggle, and switching back could not clear it.
//
// The poll loop is single-flight because `clearTimeout` cancels a pending timer
// and not a `poll()` already awaiting its fetch. Both the toggle and
// `visibilitychange` call it directly, so two responses could race to paint one
// pane, the older sometimes landing last.

import {
  readApp, extractFunction, extractRegion, evaluate,
  suite, check, done,
} from "./harness.mjs";


const src = readApp();

// ---- the selection guard ----

const guardSrc = extractFunction("selectionInScreen", src);
const inScreen = { nodeName: "SPAN" };
const screenEl = (hidden) => ({ hidden, contains: (n) => n === inScreen });
const liveSelection = { isCollapsed: false, rangeCount: 1, anchorNode: inScreen, focusNode: inScreen };

const guard = (screen, selection) =>
  evaluate(guardSrc, ["selectionInScreen"], {
    els: { screen },
    window: { getSelection: () => selection },
  }).selectionInScreen();

suite("pane — selection guard");
check("a hidden pane ignores a stranded selection (the freeze)",
  guard(screenEl(true), liveSelection) === false);
check("a visible pane still protects a live highlight",
  guard(screenEl(false), liveSelection) === true);
check("a collapsed selection is not a highlight",
  guard(screenEl(false), { ...liveSelection, isCollapsed: true }) === false);
check("a selection outside the pane is ignored",
  guard(screenEl(false), { isCollapsed: false, rangeCount: 1, anchorNode: {}, focusNode: {} }) === false);
check("no selection at all", guard(screenEl(false), null) === false);
check("an empty range is not a highlight",
  guard(screenEl(false), { ...liveSelection, rangeCount: 0 }) === false);

// ---- the poll loop ----

const loopSrc = extractRegion("let pollTimer = null;", "\napplyView();", src);

let running = 0, peak = 0, runs = 0;
const poll = async () => {
  running++; runs++;
  peak = Math.max(peak, running);
  await new Promise((r) => setTimeout(r, 25));
  running--;
};
// pollDelay() comes from the extracted source, so its real branch is exercised.
const { pollLoop } = evaluate(loopSrc, ["pollLoop"], {
  poll, isDesktop: false, passthrough: false, fastUntil: 0,
  FAST_POLL_MS: 5, POLL_MS: 15, POLL_STUCK_MS: 10_000, setConn: () => {},
});

suite("pane — poll is single-flight");
pollLoop();                        // the running loop
setTimeout(() => pollLoop(), 4);   // tapping `read` mid-flight
setTimeout(() => pollLoop(), 8);   // an impatient second tap
setTimeout(() => {
  check("never two poll bodies at once (was the race)", peak === 1, `peak=${peak}`);
  check("a request arriving mid-flight is still served", runs >= 2, `runs=${runs}`);
  check("the loop keeps polling afterwards", runs >= 3, `runs=${runs}`);
}, 220);

// ---- a request that never settles ----
//
// `fetch` has no default timeout, and the latch clears only in poll()'s `finally`.
// A stalled request — a phone changing networks, a sleeping radio — therefore used
// to wedge the app until a reload: no transcript item ever landed again, and the
// view toggle stopped repainting because every later pollLoop() returned at the
// latch. Both symptoms read to the operator as "the session paused".

let stuckRuns = 0;
const { pollLoop: stuckLoop } = evaluate(loopSrc, ["pollLoop"], {
  poll: () => { stuckRuns++; return new Promise(() => {}); },   // never settles
  isDesktop: false, passthrough: false, fastUntil: 0,
  FAST_POLL_MS: 5, POLL_MS: 15, POLL_STUCK_MS: 40, setConn: () => {},
});

// Suites are announced from inside the timeline: `suite()` prints when it is
// called, and every check in this file lands on a timer.
setTimeout(() => {
  suite("pane — a stalled request cannot wedge the app");
  stuckLoop();
}, 240);
setTimeout(() => stuckLoop(), 250);   // still in flight and not yet stuck
setTimeout(() => {
  check("a stalled poll does not start a parallel one", stuckRuns === 1, `runs=${stuckRuns}`);
}, 260);
setTimeout(() => stuckLoop(), 300);   // past the stuck threshold
setTimeout(() => {
  check("a poll that never settles is not fatal (was: reload required)",
    stuckRuns === 2, `runs=${stuckRuns}`);
  askSuite();
  done();
}, 320);

// ---- the question block ----
//
// A question is the one tool call the reader must act on rather than watch, so it
// renders open instead of collapsing to a chip. It is tool input — the same trust
// class as everything else in the feed — so it must reach the DOM as text, never
// as markup.

function fakeEl() {
  const el = {
    children: [], className: "", _text: "", hidden: false, dataset: {},
    appendChild(c) { el.children.push(c); return c; },
    get textContent() { return el._text; },
    set textContent(v) { el._text = v; el.children.length = 0; },
  };
  return el;
}
const askDoc = { createElement: () => fakeEl() };
const { renderAsk } = evaluate(extractFunction("renderAsk", src), ["renderAsk"],
  { document: askDoc });

// Options nest inside a list, so flattening has to walk the whole subtree.
const flat = (el) =>
  [el.textContent, ...el.children.map(flat)].filter(Boolean).join(" | ");
const ASK = [{ question: "Which format?", header: "F",
               options: ["DS&A / live coding", "System design"], multi: true }];

function askSuite() {
  suite("read — a question renders open");

  const pendingEl = fakeEl();
  renderAsk(pendingEl, { ask: ASK, status: "pending" });
  check("the question is shown", flat(pendingEl).includes("Which format?"));
  check("the options are shown", flat(pendingEl).includes("DS&A / live coding"));
  check("it says where to answer", flat(pendingEl).includes("term"));
  check("an unanswered question is marked waiting",
    pendingEl.className.includes("waiting"));
  check("it is visible", pendingEl.hidden === false);

  const doneEl = fakeEl();
  renderAsk(doneEl, { ask: ASK, status: "done" });
  check("an answered question drops the waiting state",
    !doneEl.className.includes("waiting"));
  check("an answered question keeps no stale call to action",
    !flat(doneEl).includes("waiting on you"));

  const plainEl = fakeEl();
  renderAsk(plainEl, { status: "pending" });
  check("an ordinary tool call renders no question block", plainEl.hidden === true);

  const emptyEl = fakeEl();
  renderAsk(emptyEl, { ask: [{ options: ["x"] }], status: "pending" });
  check("a question with no text is not a question", emptyEl.hidden === true);

  // Markup in the option labels must arrive as text. The fake records assignments
  // to textContent only — an innerHTML path would leave the children empty.
  const evilEl = fakeEl();
  renderAsk(evilEl, { ask: [{ question: "<img onerror=x>", options: ["<script>"] }],
                      status: "pending" });
  check("markup in a question is text, not markup",
    flat(evilEl).includes("<img onerror=x>") && evilEl.children.length > 0);

  const stampEl = fakeEl();
  renderAsk(stampEl, { ask: ASK, status: "pending" });
  const built = stampEl.children.length;
  renderAsk(stampEl, { ask: ASK, status: "pending" });
  check("an unchanged question is not rebuilt", stampEl.children.length === built);
}
