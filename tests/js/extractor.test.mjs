// The extraction card's pure helpers: how the extractor in force is put into words,
// and which model chips a harness offers. One renderer serves both passes, so these are
// exercised against both payloads — the difference between them is exactly what the
// summary has to carry.
import { extractFunction, evaluate, suite, check, done } from "./harness.mjs";

const src = ["extractorSummary", "extractorModelOptions"]
  .map((n) => extractFunction(n)).join("\n");
const { extractorSummary, extractorModelOptions } =
  evaluate(src, ["extractorSummary", "extractorModelOptions"]);

// The server's payload shape, abbreviated to the fields these two read.
const OPTIONS = [
  { value: "claude", label: "claude", models: ["sonnet", "opus"], default_model: "sonnet" },
  { value: "codex", label: "codex", models: ["gpt-5.6-terra", "gpt-5.4-mini"],
    default_model: "gpt-5.6-terra" },
];
const DISTILL = {
  pass: "distill",
  label: "distillation",
  value: { harness: "codex", model: "" },
  resolved: {},
  options: [{ value: "", label: "follow the session", models: [], default_model: "" },
            ...OPTIONS],
};
const INGEST = {
  pass: "ingest",
  label: "ingestion",
  value: { harness: "", model: "" },
  resolved: { harness: "codex", model: "gpt-5.4-mini" },
  options: [{ value: "", label: "follow distillation", models: [], default_model: "" },
            ...OPTIONS],
};
const withValue = (state, harness, model) => ({ ...state, value: { harness, model } });

suite("extractorSummary");

// Deferring is a choice with a meaning, not an empty field. Spelling it "" or "none"
// would make "every session distills through whatever wrote it" and "nothing is
// configured" the same line, and only one of those is true.
check("distillation with no harness reads as following the session",
      extractorSummary(withValue(DISTILL, "", "")) === "follow the session");
// A blank model is the CLI's own default, so the summary has to name the slug that
// will actually run — an operator cannot weigh "codex" against his allowance.
check("a blank model shows the slug the CLI will use",
      extractorSummary(withValue(DISTILL, "codex", "")) === "codex · gpt-5.6-terra");
check("a chosen model is the one shown",
      extractorSummary(withValue(DISTILL, "codex", "gpt-5.4-mini")) === "codex · gpt-5.4-mini");
check("a harness the payload does not describe still names itself",
      extractorSummary(withValue(DISTILL, "cursor", "")) === "cursor");
check("an empty payload says nothing", extractorSummary(null) === "");

// The two passes defer to different things, and the words come off the payload rather
// than out of this function — a client that spelled them itself would name the wrong
// one the moment a third pass existed.
check("ingestion says what it defers to, and what that resolves to",
      extractorSummary(INGEST) === "follow distillation → codex · gpt-5.4-mini");
// Distillation is the case where there is genuinely no answer yet: no session has
// ended. Inventing one would assert a fact about a run that has not happened.
check("a pass with nothing to resolve to shows the rule alone",
      extractorSummary({ ...INGEST, resolved: {} }) === "follow distillation");
// An explicit selection is the whole answer; the fall-through is no longer in play and
// showing it would read as two settings fighting.
check("an explicit selection outranks the resolved fall-through",
      extractorSummary(withValue(INGEST, "claude", "opus")) === "claude · opus");

suite("extractorModelOptions");

const codex = extractorModelOptions(withValue(DISTILL, "codex", ""), "codex");
check("the harness's declared slugs are the whole list",
      codex.map((m) => m.value).join(",") === "gpt-5.6-terra,gpt-5.4-mini");
// With nothing chosen, the chip that lights up must be the one that will run. A card
// showing no selection would imply the pass has no model.
check("a blank selection lights the CLI's default",
      codex[0].on === true && codex[1].on === false);

const chosen = extractorModelOptions(withValue(DISTILL, "codex", "gpt-5.4-mini"), "codex");
check("an explicit selection lights that chip instead",
      chosen[0].on === false && chosen[1].on === true);
// The default stays marked even when it is not the selection, so stepping back to it
// is a labelled act rather than a guess.
check("the default stays identifiable when something else is chosen",
      chosen[0].isDefault === true && chosen[1].isDefault === false);

check("a deferring pass offers no models",
      extractorModelOptions(withValue(INGEST, "", ""), "").length === 0);
check("an empty payload offers no models",
      extractorModelOptions(null, "codex").length === 0);

done();
