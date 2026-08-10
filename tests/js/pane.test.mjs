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
  FAST_POLL_MS: 5, POLL_MS: 15,
});

suite("pane — poll is single-flight");
pollLoop();                        // the running loop
setTimeout(() => pollLoop(), 4);   // tapping `read` mid-flight
setTimeout(() => pollLoop(), 8);   // an impatient second tap
setTimeout(() => {
  check("never two poll bodies at once (was the race)", peak === 1, `peak=${peak}`);
  check("a request arriving mid-flight is still served", runs >= 2, `runs=${runs}`);
  check("the loop keeps polling afterwards", runs >= 3, `runs=${runs}`);
  done();
}, 220);
