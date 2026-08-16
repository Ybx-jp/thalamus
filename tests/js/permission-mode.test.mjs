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
    tag, children: [], _text: "", disabled: false, type: "",
    classList: {
      add: (n) => cls.add(n), remove: (n) => cls.remove(n),
      toggle: (n, on) => (on ? cls.add(n) : cls.delete(n)),
      has: (n) => cls.has(n),
    },
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
    [extractFunction("modeStateFor", src), extractFunction("modeControl", src)].join("\n"),
    ["modeControl"],
    { document: { createElement: (t) => fakeEl(t) }, modeState },
  );
  return env.modeControl({ index: 7, name: "designer" });
};

const flat = (el) => [el.textContent, ...el.children.map(flat)].filter(Boolean).join(" | ");
const button = (el) => el.children.find((c) => c.tag === "button");
const label = (el) => el.children.find((c) => c.tag === "span" && c.classList.has("mode-label"));

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
  check("a reading is not dressed as a non-observation",
    !label(box).classList.has("unseen"));
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
  const b = button(box);
  check("the control says the readback is outstanding",
    b.textContent === "awaiting readback");
  check("it is outlined rather than filled", b.classList.has("awaiting"));
  check("it cannot be pressed again while outstanding", b.disabled === true);
  check("the mode still shown is the one last read, not the one asked for",
    flat(box).includes("auto"));
}

{
  const box = draw({ read: "ok", mode: "auto", phase: "unconfirmed" });
  check("a readback that never arrived says so",
    flat(box).includes("could not confirm"));
  check("and the control comes back", button(box).disabled === false);
}

{
  const box = draw({ read: "ok", mode: "auto", phase: "idle" });
  check("a settled row makes no claim about a readback",
    !flat(box).includes("awaiting") && !flat(box).includes("could not confirm"));
}

done();
