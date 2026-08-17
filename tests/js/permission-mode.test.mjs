// What the opened row is allowed to say about a session's permission mode.
//
// Three claims are forbidden and they fail in different directions, which is why this
// is a suite and not one assertion:
//
//   1. Rendering a mode the console was not given. `permission_mode` is `""` when the
//      transcript holds no permission-mode record, and the parse covers the whole
//      transcript — so `""` means *no such record*, never `manual`, and never "we
//      joined late" (spec §1). The operational consequence of a manual session is
//      carried by `needs you`, which is observed rather than inferred.
//   2. Confusing "no record exists" with "we could not read this session". Those are
//      different facts about different things — one about the session, one about the
//      instrument — and telling them apart is the entire reason `permission_mode_read`
//      is a field of its own (§5.2).
//   3. Reporting the press as done. `BTab` cycles blind; the only evidence it landed
//      is a mode we can read back. A control that fills in before the readback is the
//      problem §5.2 exists to solve.

import {
  readApp, extractFunction, evaluate,
  suite, check, done,
} from "./harness.mjs";


const src = readApp();

function fakeEl(tag) {
  const cls = new Set();
  const el = {
    tag, children: [], _text: "", disabled: false, type: "", attrs: {},
    classList: {
      add: (n) => cls.add(n), remove: (n) => cls.remove(n),
      toggle: (n, on) => (on ? cls.add(n) : cls.delete(n)),
      has: (n) => cls.has(n),
    },
    setAttribute(k, v) { el.attrs[k] = String(v); },
    getAttribute(k) { return el.attrs[k]; },
    addEventListener() {},
    appendChild(c) { el.children.push(c); return c; },
    get className() { return [...cls].join(" "); },
    set className(v) { cls.clear(); v.split(/\s+/).filter(Boolean).forEach((n) => cls.add(n)); },
    get textContent() { return el._text; },
    set textContent(v) { el._text = v; el.children.length = 0; },
  };
  return el;
}

// `modeState` is a plain Map in the client, so the test owns one and seeds it.
const draw = (state) => {
  const modeState = new Map([[7, { read: "", mode: "", phase: "idle", before: "", polls: 0, ...state }]]);
  const env = evaluate(
    [extractFunction("modeStateFor", src), extractFunction("modeNote", src),
     extractFunction("modeControl", src)].join("\n"),
    ["modeControl"],
    // `MODE_LADDER` is lifted from the client rather than restated, so a segment
    // added there without a thought for this file fails here instead of quietly
    // going unasserted.
    { document: { createElement: (t) => fakeEl(t) }, modeState, MODE_LADDER: ladder() },
  );
  return env.modeControl({ index: 7, name: "designer" });
};

/** The client's own ladder, read out of the source. */
function ladder() {
  const m = src.match(/MODE_LADDER\s*=\s*\[([^\]]*)\]/);
  if (!m) throw new Error("MODE_LADDER not found in app.js");
  return m[1].split(",").map((s) => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean);
}

const flat = (el) => [el.textContent, ...el.children.map(flat)].filter(Boolean).join(" | ");
const descend = (el) => [el, ...el.children.flatMap(descend)];
const button = (el) => descend(el).find((c) => c.tag === "button" && !c.classList.has("mode-chip"));
const chips = (el) => descend(el).filter((c) => c.classList.has("mode-chip"));
// The section heading also carries `mode-label`; the label under test is the one that
// speaks about *this session*, which is the one that is not the heading.
const label = (el) => descend(el).find(
  (c) => c.tag === "span" && c.classList.has("mode-label") && !c.classList.has("mode-head"));

// The ladder the spec names, plus the words the transcripts actually carry. None of
// them may appear on a row that was given no mode.
const MODES = ["manual", "acceptEdits", "auto", "default", "plan", "dontAsk", "bypassPermissions"];


suite("permission mode — absence is not a mode");

{
  const box = draw({ read: "ok", mode: "" });
  const text = flat(box);
  check("it says there is no record, in those words",
    text.includes("no mode recorded"));
  for (const m of MODES) {
    check(`it does not name \`${m}\``, !text.includes(m));
  }
  // The typeface is the claim: a value that was read is monospace, a non-observation
  // is not. Same split the state slot uses, and it survives greyscale.
  check("the absence is not set in the voice of a reading",
    label(box).classList.has("unseen"));
  check("the control is still offered — the mode is unknown, not unreachable",
    !!button(box));
}


suite("permission mode — a read value is shown as read");

{
  const box = draw({ read: "ok", mode: "acceptEdits" });
  check("the mode is named", flat(box).includes("acceptEdits"));
  check("no part of a reading is dressed as a non-observation",
    !descend(box).some((c) => c.classList.has("unseen")));
}


// B3 draws a segmented picker; J states why it cannot always be one. The keycap
// advances one step and does not set, so random access is only available when we know
// where the ladder is — the segment's distance from the current position IS the
// number of presses. A mode we cannot place has no distance, so there is no picker to
// draw and the control degrades to the single step the hardware actually offers.
suite("permission mode — the picker exists only where a distance does");

{
  const box = draw({ read: "ok", mode: "acceptEdits" });
  const cs = chips(box);
  check("every rung of the ladder is a segment", cs.length === ladder().length);
  check("the segments are the ladder, in its order",
    cs.map((c) => c.textContent).join(",") === ladder().join(","));
  const on = cs.filter((c) => c.classList.has("on"));
  check("exactly one segment is selected", on.length === 1);
  check("the selected segment is the mode that was read",
    on[0].textContent === "acceptEdits");
  // The fill is not the only carrier: a reader in greyscale, and a screen reader,
  // both get the selection from `aria-pressed`.
  check("selection is exposed to assistive tech, not just painted",
    on[0].getAttribute("aria-pressed") === "true"
    && cs.filter((c) => c.getAttribute("aria-pressed") === "false").length === cs.length - 1);
  check("a picker replaces the step control rather than joining it", !button(box));
}

for (const m of ["", "default", "dontAsk", "plan"]) {
  const box = draw({ read: "ok", mode: m });
  check(`\`${m || "(no record)"}\` has no position, so it draws no segments`,
    chips(box).length === 0);
  check(`\`${m || "(no record)"}\` still offers the one step the key can take`,
    !!button(box));
}

// The spec's ladder is `manual|acceptEdits|auto`, and the transcripts on this box
// carry `default`, `dontAsk` and `plan` as well. The row prints what it was given
// rather than mapping it onto a vocabulary of ours — a mode with no segment is still
// this session's mode, and silently renaming it would be the row asserting something
// nobody recorded.
for (const m of ["default", "dontAsk", "plan"]) {
  check(`\`${m}\` is printed rather than mapped onto the ladder`,
    flat(draw({ read: "ok", mode: m })).includes(m));
}


suite("permission mode — unreadable is not unset");

for (const reason of ["unresolved", "pending", "no-package"]) {
  const box = draw({ read: reason, mode: "" });
  const text = flat(box);
  check(`\`${reason}\` reads as the console failing, not the session`,
    text.includes("cannot read this session's mode") && text.includes(reason));
  check(`\`${reason}\` does not claim there is no record`,
    !text.includes("no mode recorded"));
  // Offering a control whose result we could not read back would be asking the
  // operator to act blind — the one thing the readback loop exists to prevent.
  check(`\`${reason}\` offers no control`, !button(box));
}


suite("permission mode — the press is not the act");

{
  const box = draw({ read: "ok", mode: "auto", phase: "awaiting" });
  check("the control says the readback is outstanding",
    flat(box).includes("awaiting readback"));
  check("no segment can be pressed while one is outstanding",
    chips(box).every((c) => c.disabled === true));
  check("the mode still shown is the one last read, not the one asked for",
    chips(box).find((c) => c.classList.has("on")).textContent === "auto");
}

// The degraded control keeps the same promise in its own shape.
{
  const box = draw({ read: "ok", mode: "", phase: "awaiting" });
  const b = button(box);
  check("the step control says the readback is outstanding",
    b.textContent === "awaiting readback");
  check("it is outlined rather than filled", b.classList.has("awaiting"));
  check("it cannot be pressed again while outstanding", b.disabled === true);
}

{
  const box = draw({ read: "ok", mode: "auto", phase: "unconfirmed" });
  check("a readback that never arrived says so",
    flat(box).includes("could not confirm"));
  check("and the control comes back", chips(box).every((c) => c.disabled === false));
}

{
  const box = draw({ read: "ok", mode: "auto", phase: "idle" });
  check("a settled row makes no claim about a readback",
    !flat(box).includes("awaiting") && !flat(box).includes("could not confirm"));
}

done();
