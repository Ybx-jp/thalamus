# 032 — The attribution instrument is a topic detector: 4pp of discrimination on a 59% floor

**Date:** 2026-07-29 · **Component:** eval layer 1 (`eval/attribution.py`) · **Status:** measured. Calibrates every used%/waste number the eval loop reports.

> **Erratum (2026-07-30).** Figures in this entry are withdrawn or bounded by [lab/034](034-the-corrections-the-instrument-forced.md); see its withdrawal list before citing anything here.

## The question

lab/031 could not tune the detail cap because used-rate was ~60% flat against
every property measured, and only 1.4% of detail verdicts came from the strong
citation path. That put the ceiling on the instrument rather than the analysis.
So: measure the instrument.

## The negative control

`attribute()` judges a returned node "used" if the agent's later output cites its
vertex ID, or echoes ≥2 of the node's distinctive terms at ≥30% of them. The test
is a permutation: judge each trace's returned nodes against **a different
session's** output window instead of its own. Real utility should survive the
swap; a vocabulary detector should not.

233 traces reconstructed from the tap, 2,367 node verdicts. Reconstruction
fidelity against what `eval sync` actually stored: **2367/2367, 100%** — this
replays the production path exactly, not an approximation of it.

| outputs the nodes were judged against | used% |
|---|---|
| **the retrieval's own real output window** | **62.9%** |
| another thalamus session (rotate 1 / 2 / 3) | 60.7 / 61.0 / 59.4% |
| another thalamus session (shuffled) | 58.2% |
| **a different project's session** | **5.0%** |

Restricted to the lexical-echo path alone (dropping vertex-ID citations): real
61.4% vs placebo 57.7%, **+3.7pp**.

## What this means

**The instrument works, at the wrong granularity.** Cross-project it is nearly
perfect: 63% vs 5%. It answers "is this node from the same body of work as this
output?" with high fidelity. Within a project — which is the only regime the eval
loop ever runs in — it answers "did this retrieval get used?" with **~4
percentage points of discrimination on a ~59% floor**. Signal to baseline is
roughly 1:14.

That is not "the metric is meaningless." It is: *the reported number is
approximately 59 points of vocabulary overlap plus 4 points of retrieval
utility*, and nothing in the pipeline separates them.

Two mechanisms, both structural:

- **Token-set membership with no proximity.** `matched = [t for t in terms if t
  in output_tokens]` asks only whether each term appears *anywhere* in the
  window. Long windows match more. Measured: used% 51.7% for 20–100k-char
  windows against **69.7% for 100k+**. So used% partly measures session length —
  and docs/04's standing finding is that session length already dominates token
  burn. Long sessions therefore look both expensive *and* high-utility, from the
  same cause.
- **Shared vocabulary within a project.** Two thalamus sessions six weeks apart
  discuss scopes, traces, pins and claims. Any node from either will echo in
  either's output.

The citation path is not immune. Under permutation it still fired on 54 nodes
(2.3%) against 90 (3.8%) real — agents cite the same vertex IDs across sessions,
so even the strong path has a false-positive floor.

## Where the floor lives: by node kind

Proposed mechanism (operator, same day): `memory_open_threads` fires at every
session start, sessions spawn far more threads than they close, and turn
completions reference open threads — so thread nodes would echo in *any*
session's output and inflate the floor.

The premise holds. **398 SPAWNS against 71 RESOLVES — 5.6 threads opened per one
closed — and 306 of 377 threads (81%) are open or in-progress.** Threads are
long-lived and shared across sessions by design.

The effect is real and is the largest of any node kind:

| node kind | n | real | placebo | discrimination |
|---|---|---|---|---|
| claim | 1756 | 60.1% | 56.0% | +4.1pp |
| **thread** | 323 | 77.7% | **70.0%** | +7.7pp |
| **session** | 285 | 63.2% | **62.8%** | **+0.4pp** |
| by tool: `memory_open_threads` | 319 | 77.4% | 69.6% | +7.8pp |
| by tool: `memory_recall` | 1972 | 60.0% | 56.3% | +3.7pp |

Threads do float free exactly as predicted — a 70% placebo rate is the highest
in the corpus, and `memory_open_threads` is the leakiest surface. **But it is not
the explanation for the floor.** Threads are 13.6% of verdicts; excluding them
entirely moves the floor 58.7% → **56.9%**, and the real-vs-placebo gap stays at
+3.7pp. The floor lives in Claims, which are 74% of all verdicts and sit at 56%
placebo on their own.

The channel is also not the one it looks like. `_judge` has a dedicated
thread-slug path, and it fires on only 26 of 323 thread verdicts (19 of those
also fire under permutation). The other 220 come through ordinary lexical echo:
thread *descriptions* are long topical prose about the project's live concerns,
which is the most echo-prone text in the graph. Slugs are a rounding error; the
description is the leak.

**The sharpest result here is the session row.** Session-summary verdicts carry
**+0.4pp** of discrimination — statistically nothing. Whatever a session
summary's used-flag means, it is not "this summary was used by this retrieval."
That bears directly on the open question in
[lab/030](030-the-miss-rate-was-the-consultation.md) about whether summaries are
noise or an unobservable mediator: as measured, the summary used-flag cannot
answer it either way, because it contains no retrieval-level signal to read.

## Consequences for numbers already on record

- **The `recall-strategy` skill told agents to target "used% above ~50."** The
  null baseline is ~59%. A session hitting that target is performing *below
  permuted chance*. Corrected in the skill.
- **lab/006's "waste ranking surfaces cross-project bleed" is close to
  circular.** A topic detector scores off-topic nodes ignored by construction, so
  a ranking by wasted tokens was always going to surface other projects' nodes.
  The observation is real; it is not independent evidence.
- **lab/029's off-project split (thalamus claims 84% used vs stepmania 40%)
  is substantially the same artifact.** Off-project material has off-project
  vocabulary, and this instrument scores that as ignored whether or not the agent
  ignored it. The direction survives; the magnitude does not, and the 83%
  addressable-waste figure should be read as an upper bound on what a
  project-aware ranker could reach *as measured*, not as utility recovered.
- **lab/031's null result stands, and is now better explained.** Used-rate was
  flat across position, length and keyword ranking because ~59 of those 60 points
  are a floor that no reordering of the same session's claims can move.
- **Any conclusion resting on session-summary used% is unreadable**, at +0.4pp.
  That includes the session-level half of lab/029's 2×2. Its internal argument
  survives — a *sign reversal* by project cannot be produced by a length artifact
  — but the 91%-vs-25% magnitudes are the topic detector detecting topic.

## What would change the conclusion

- **A stronger placebo.** The cross-project figure rests on one non-thalamus
  output pool. A proper permutation distribution over many pools would put an
  interval on the 5%.
- **Human labels on a sample.** ~100 hand-judged (retrieval, node) pairs would
  give the instrument a κ against ground truth instead of against a permutation,
  and would settle whether the 4pp is real signal or residual leakage.

## The designed, unbuilt response

**Report used% against its own permuted baseline** rather than raw. The
permutation is computable from data already retained — the tap holds every output
window, and this entry's script is the whole method. `eval report` would render
"used 63% vs 59% permuted (+4)" and the Pulse calibration plate would carry the
floor beside the rate, which is what the plate exists for (docs/03: floors and
gaps are rendered states, never zeros).

That is a change to a metric of record, so it goes through the grounding and
consultation gate before it is built, not after. Prior art to pull: permutation
testing for retrieval-utility baselines, and the NullMemory counterfactual
baseline already held at `scope:literature:claim:9fa544217395e928`.

Not built here. The measurement is the deliverable; the redesign is a decision.
