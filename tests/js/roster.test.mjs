// The session row: one row per session carrying its whole life.
//
// Three lists used to show the same sessions and disagree, so what is pinned here is
// mostly *what the row is not allowed to decide*. Liveness arrives already reduced —
// `observed`, `blocked`, `activity`, and the distill state — and the row prints it.
// The tests that matter are the ones where two states are true at once, because that
// is where a renderer starts inventing a policy.

import {
  readApp, extractFunction, evaluate,
  suite, check, done,
} from "./harness.mjs";

const src = readApp();
const api = evaluate(
  [
    extractFunction("fmtDur", src),
    extractFunction("fmtOpened", src),
    extractFunction("rowState", src),
    extractFunction("baseName", src),
    extractFunction("groupSessions", src),
    extractFunction("annotateCollisions", src),
  ].join("\n"),
  ["fmtDur", "fmtOpened", "rowState", "baseName", "groupSessions", "annotateCollisions"],
);
const { fmtDur, fmtOpened, rowState, groupSessions, annotateCollisions } = api;

const NOW = 1_700_000_000;
const GRACE = 240;
const state = (w, d, now = NOW) => rowState(w, d, now, GRACE);

suite("clocks: elapsed is relative, opened is absolute");
{
  check("seconds pad", fmtDur(3) === "0:03", fmtDur(3));
  check("under a minute", fmtDur(42) === "0:42", fmtDur(42));
  check("minutes past ten", fmtDur(388) === "6:28", fmtDur(388));
  check("minutes do not roll into hours early", fmtDur(1264) === "21:04", fmtDur(1264));
  check("an hour switches form", fmtDur(24_420) === "6h47m", fmtDur(24_420));
  // The digits stop being read at this scale: `146h26m` is four significant figures
  // nobody consumes that way, and it crowds out the magnitude that does matter.
  check("a day switches again", fmtDur(527_206) === "6d 2h", fmtDur(527_206));
  check("just under a day keeps hours", fmtDur(86_399) === "23h59m", fmtDur(86_399));
  check("zero is a clock, not blank", fmtDur(0) === "0:00", fmtDur(0));
  // A stamp from the future would otherwise render a negative clock.
  check("never counts backwards", fmtDur(-30) === "0:00", fmtDur(-30));

  const at = new Date(2026, 7, 15, 18, 38, 12).getTime() / 1000;
  check("opened is wall-clock, stable across polls", fmtOpened(at) === "18:38", fmtOpened(at));
  check("no stamp draws no clock", fmtOpened(0) === "" && fmtOpened(null) === "");
}

suite("the slot: one word, and the order is the design's");
{
  const w = { observed: true, blocked: false, activity: "idle" };
  check("an ordinary row says the word the server composed",
    state(w).text === "idle", state(w).text);
  check("and draws no clock without a stamp", !state(w).text.includes(":"));

  const busy = { observed: true, blocked: false, activity: "busy",
                 activity_since: NOW - 388 };
  check("a stamp is what makes it tick", state(busy).text === "busy 6:28", state(busy).text);

  // The elapsed is drawn iff the stamp is present. A client that read the word back
  // to decide would be a second policy about which states are worth timing.
  const oddBusy = { observed: true, blocked: false, activity: "busy" };
  check("the word alone never conjures a clock", state(oddBusy).text === "busy",
    state(oddBusy).text);
}

suite("the slot: what we cannot see is not what we saw");
{
  const unseen = { observed: false, blocked: null, activity: "" };
  const s = state(unseen);
  check("says it cannot see", s.text === "not in reach", s.text);
  check("and says it in a different voice — never monospace", s.mono === false);

  const fine = state({ observed: true, blocked: false, activity: "idle" });
  check("a state that was actually read stays monospace", fine.mono === true);
}

suite("the slot: the one state that cannot resolve without a human");
{
  const blocked = { observed: true, blocked: true, blocked_since: NOW - 24_420 };
  const s = state(blocked);
  check("carries the pill", s.pill === "needs you", String(s.pill));
  check("and the duration, which is the finding",
    s.text === "stopped 6h47m ago", s.text);

  // Measured on this box: the anchor was blocked 6h47m while three sibling windows
  // read false. The pill says which; only the clock says how bad.
  const brief = state({ observed: true, blocked: true, blocked_since: NOW - 90 });
  check("a fresh block reads as one", brief.text === "stopped 1:30 ago", brief.text);
}

suite("the slot: an operation in flight outranks the state it is resolving");
{
  const restarting = { observed: true, blocked: false, recycling: NOW - 42 };
  check("restarting shows its own clock",
    state(restarting).text === "restarting 0:42", state(restarting).text);
  check("closing likewise",
    state({ closing: NOW - 12, observed: true }).text === "closing 0:12");

  // The ruled case. The restart IS the resolution of blocked and the operator
  // started it, so `needs you` there would ask for an action already taken. The
  // finding is not lost: it is counted off `blocked`, and if the restart does not
  // land, grace expiry promotes the row to a band louder than the pill.
  const both = { observed: true, blocked: true, blocked_since: NOW - 24_420,
                 recycling: NOW - 42 };
  check("a blocked row mid-restart shows the restart",
    state(both).text === "restarting 0:42", state(both).text);
  check("and does not draw the pill", !state(both).pill);
  check("but the row is still blocked in the data the count reads",
    both.blocked === true);
}

suite("the slot: a window that ended outranks every liveness word");
{
  // The console knows why it cannot read a descriptor here, so `not in reach` would
  // claim a blindness it does not have — and a stale `waiting` would ask the operator
  // to answer a prompt that no longer exists.
  const gone = { dead: true, observed: false, blocked: null, activity: "" };
  check("says the window ended", state(gone).text === "ended", state(gone).text);
  check("not that we cannot see it", state(gone).text !== "not in reach");
  check("and in the voice of something read", state(gone).mono === true);

  const stale = { dead: true, observed: true, blocked: true, blocked_since: NOW - 90 };
  check("a corpse never asks for a human", !state(stale).pill);

  // Ending is not failing, so it takes no band. When work actually was lost, the
  // distill record says so and bands this same row above.
  check("and it is not terminal geometry", state(gone).band === "");
  const lost = state({ dead: true }, { state: "unknown", op: "close" });
  check("but a record of lost work still bands it", lost.band !== "");
}

suite("the band: terminal states take the geometry, not a colour");
{
  const failed = state(null, { state: "error", detail: "unparseable YAML",
                               detail_truncated: false });
  check("failed loses the slot", failed.text === "" && failed.band !== "");
  check("and names itself", failed.band === "distillation failed", failed.band);
  check("carrying the detail verbatim", failed.detail === "unparseable YAML");

  const killed = state(null, { state: "unknown", op: "recycle" });
  check("a killed window says what never ran",
    killed.band === "never distilled — window was restarted, SessionEnd never ran",
    killed.band);
  check("and says which act killed it",
    state(null, { state: "unknown", op: "close" }).band.includes("closed"));
  check("without guessing when it was not recorded",
    state(null, { state: "unknown", op: "" }).band.includes("killed"));

  // G3's self-reporting leak. No new detection: a served grace and a start stamp
  // are sufficient, so a worker that leaks its flag crosses the deadline and says so
  // instead of reading `restarting` forever.
  const leaked = state({ observed: true, recycling: NOW - 600 }, null);
  check("a restart past grace stops claiming to be restarting", leaked.text === "");
  check("and reports its own age", leaked.band.includes("240s grace"), leaked.band);
  check("with the elapsed it has burned", leaked.elapsed === "10:00", leaked.elapsed);

  const inGrace = state({ observed: true, recycling: NOW - 100 }, null);
  check("inside grace it is still just a restart",
    inGrace.text === "restarting 1:40" && inGrace.band === "");
}

suite("the band: stalled is not terminal, but abandoned is");
{
  const stalled = state(null, { state: "stalled", age: 1264 });
  check("keeps the slot — it may still complete",
    stalled.band === "" && stalled.text === "distilling 21:04 · stalled", stalled.text);
  const active = state(null, { state: "active", age: 134 });
  check("as does a live distillation", active.text === "distilling 2:14", active.text);

  // "May still complete" is true at half an hour and false at six days, where the
  // calm row reports work in progress that will never move again — the meaningless
  // silence this design exists to remove, wearing a state word.
  const gone = state(null, { state: "abandoned", age: 527_206 });
  check("past the threshold it takes the band", gone.band !== "" && gone.text === "");
  check("and says how long nothing has moved",
    gone.band === "distillation abandoned — nothing has moved in 6d 2h", gone.band);
  // A failed extraction has a traceback to act on; this has nothing, so the two do
  // not share a sentence even though they share the channel.
  check("in its own words, not a failure's", !gone.band.includes("failed"));
  check("and with no detail line to repeat itself", gone.detail === "");
}

suite("rows: a record outliving its window is the steady state");
{
  // Verified live: the join produces zero hits, because every current record belongs
  // to a session whose window is already gone. So the common terminal row has no
  // entry in windows[] at all and must render from the record alone.
  const groups = groupSessions([], [{ session: "b8a0cb9c", scope: "designer",
    dir: "thalamus", project: "", repo_root: "", state: "error", detail: "boom" }]);
  check("the orphan still becomes a row", groups.length === 1 &&
    groups[0].rows.length === 1, JSON.stringify(groups.length));
  check("with no window behind it", groups[0].rows[0].w === null);

  const joined = groupSessions(
    [{ name: "homelab", session_id: "e3bc5756-ac07-4755", project: "", observed: true }],
    [{ session: "e3bc5756", state: "active", age: 10, project: "" }]);
  check("a record with a live window joins onto it, not beside it",
    joined[0].rows.length === 1, String(joined[0].rows.length));
  check("on the first eight of the session id", joined[0].rows[0].d.state === "active");
}

suite("groups: the key is the project, and a cwd is never it");
{
  const groups = groupSessions([
    { name: "a", project: "thalamus", repo_root: "/home/op/code/thalamus" },
    { name: "b", project: "thalamus", repo_root: "/home/op/code/thalamus/.claude/worktrees/d4v2" },
    { name: "c", project: "", repo_root: "" },
  ], []);

  check("two repo roots and one project are one group", groups.length === 2,
    String(groups.length));
  const named = groups[0];
  check("named by the project", named.label === "thalamus", named.label);
  check("holding both copies", named.rows.length === 2, String(named.rows.length));

  // The group answers which project; the row answers which copy.
  check("and the row whose copy differs says so", named.rows[1].showCwd === true);
  check("while the row matching the group's root stays quiet",
    named.rows[0].showCwd === false);
}

suite("groups: the no-project group trails, and is self-liquidating");
{
  const groups = groupSessions([
    { name: "orphan", project: "", repo_root: "" },
    { name: "known", project: "thalamus", repo_root: "/home/op/code/thalamus" },
  ], []);
  check("named groups sort first", groups[0].label === "thalamus", groups[0].label);
  check("the unnamed one trails", groups[1].known === false && groups[1].key === "");

  // Today's live roster: no session started before the hook recorded a project, so
  // every window lands here. That is the transitional state rendering correctly, not
  // a failure — it shrinks visibly as sessions recycle and disappears when empty.
  const all = groupSessions(
    Array.from({ length: 9 }, (_, i) => ({ name: `w${i}`, project: "", repo_root: "" })), []);
  check("a roster with no keys at all is one group, not nine",
    all.length === 1 && all[0].rows.length === 9, String(all.length));
  check("and it is the unnamed one", all[0].known === false);

  // Falling back to a cwd would group ~/code/thalamus and ~/code/thalamus/lab as two
  // projects. A guessed hierarchy is worse than none: it looks like a real one.
  const cwds = groupSessions([
    { name: "a", project: "", repo_root: "", cwd_label: "thalamus" },
    { name: "b", project: "", repo_root: "", cwd_label: "lab" },
  ], []);
  check("a cwd label never becomes a group", cwds.length === 1, String(cwds.length));
}

suite("rows: the index appears on collision and only on collision");
{
  const opened = new Date(2026, 7, 15, 9, 14, 0).getTime() / 1000;
  const rows = annotateCollisions([
    { w: { scope: "main", name: "main", started: opened, index: 3 } },
    { w: { scope: "main", name: "main", started: opened, index: 5 } },
    { w: { scope: "main", name: "main", started: opened + 3600, index: 7 } },
  ], "");
  check("byte-identical rows earn an index", rows[0].showIndex && rows[1].showIndex);
  check("the one an hour apart does not", rows[2].showIndex === false);

  const alone = annotateCollisions(
    [{ w: { scope: "designer", name: "designer", started: opened, index: 1 } }], "");
  check("a row nothing collides with stays clean", alone[0].showIndex === false);
}

done();
