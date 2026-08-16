// The rail's pulse reads an opaque change token, not the pane text.
//
// `/api/panes` serves `screen_rev` per window: a value that differs when that
// window's screen differs and holds when it holds. Its format is not promised, so
// the client may only compare it for equality — parsing it, or deriving "changed"
// from the text itself, puts the client on the wrong side of the spec's first line
// (the server owns that state) and blocks dropping `lines` from the poll.
//
// The trap this guards is not the comparison, it is the pairing: read from one
// field and store from another and the pulse fires on every poll, or never. Both
// sides go through `revOf`, and the two detection sites are checked for any
// surviving mention of the text field.

import {
  readApp, extractFunction, evaluate, stripComments,
  suite, check, lacksMatch, done,
} from "./harness.mjs";


const src = readApp();
const revSrc = extractFunction("revOf", src);
const revOf = evaluate(revSrc, ["revOf"]).revOf;

suite("screen_rev — the token the client compares");

check("the token is preferred over the text when the server serves it",
  revOf({ screen_rev: "a1b2", lines: "hello" }) === "a1b2");

check("a server that does not serve it falls back to the text",
  revOf({ lines: "hello" }) === "hello");

// An empty token is a real answer — a failed capture is stable, and no text is not
// a change. `??`-style fallback on a falsy value would silently switch fields.
check("an empty token is a token, not a missing one",
  revOf({ screen_rev: "", lines: "hello" }) === "");

// The point of the token: the server may report "unchanged" for text the client
// cannot see, and "changed" without the client diffing anything.
check("equal tokens read as unchanged even when the text differs",
  revOf({ screen_rev: "a1b2", lines: "one" }) === revOf({ screen_rev: "a1b2", lines: "two" }));

check("differing tokens read as changed even when the text matches",
  revOf({ screen_rev: "a1b2", lines: "same" }) !== revOf({ screen_rev: "c3d4", lines: "same" }));


// ---- the pulse ----

const dots = (prev, next) => {
  const tabs = next.map((w) => {
    const cls = new Set();
    return {
      dataset: { idx: String(w.index) },
      classList: {
        toggle: (n, on) => (on ? cls.add(n) : cls.delete(n)),
        add: (n) => cls.add(n),
        remove: (n) => cls.delete(n),
        has: (n) => cls.has(n),
      },
      offsetWidth: 0,
    };
  });
  const env = evaluate(
    [revSrc, extractFunction("updateWsSignal", src), extractFunction("updateDots", src)].join("\n"),
    ["updateDots"],
    {
      els: { rail: { children: tabs }, wsbar: { hidden: true, children: [] } },
      lastRev: prev,
      activeWs: null,
    },
  );
  env.updateDots(next);
  return tabs.map((t) => t.classList.has("active-live"));
};

suite("screen_rev — the rail pulse");

check("a window whose token moved is live",
  dots({ 0: "a1b2" }, [{ index: 0, screen_rev: "c3d4", lines: "x" }])[0] === true);

check("a window whose token held is not",
  dots({ 0: "a1b2" }, [{ index: 0, screen_rev: "a1b2", lines: "x" }])[0] === false);

// The first poll has nothing to compare against. Firing there would flash every
// tab on load.
check("a window seen for the first time does not pulse",
  dots({}, [{ index: 0, screen_rev: "a1b2", lines: "x" }])[0] === false);

// The pairing bug: text moving under a held token must not register, or the client
// is still deriving change from the screen.
check("text moving under a held token does not pulse",
  dots({ 0: "a1b2" }, [{ index: 0, screen_rev: "a1b2", lines: "moved" }])[0] === false);


// ---- the field the detection sites must not read ----
//
// Extraction failing here is the intended loud failure, not a flake: if either
// function is renamed, this stops guarding and says so.

suite("screen_rev — no text comparison survives");

for (const name of ["updateDots", "updateWsSignal"]) {
  lacksMatch(`${name} does not read the pane text`,
    stripComments(extractFunction(name, src)), /\.lines\b/);
}

done();
