# 029 — The bleed that was not a leak: project-blind recall, and two consultations that inverted each other

**Date:** 2026-07-29 · **Component:** retrieval (`substrate/reader.py` `recall()`), eval attribution · **Status:** measured; no dial turned. Supersedes the 13% ceiling in exchange `scope:main:exchange:46f20d96fa084a3c`.

## The false alarm that started it

A main-scope session working the Cursor-port question wrote "this repo is now a
public job-search artifact," and it read as cross-scope contamination — resume
material bleeding into a thalamus session.

It was not. That session (`b54485f7`) called `ToolSearch`, `Bash`,
`memory_open_threads`, `Bash`, `Bash` — **no `memory_recall`, no `memory_query`,
nothing lexical**. Both halves were correctly sourced: `gh repo view --json
visibility` returned `PUBLIC` live, and `memory_open_threads(project="thalamus")`
returned `thalamus-9-month-career-strategy-reassessment` ("Decide on
open-sourcing / business path / job-search framing for Thalamus") and
`thalamus-work-machine-migration-gates`, whose Tier 4 is public. Both are
`scope:main`, `project:thalamus`, operator-opened. Claude Code's own auto-memory
was not in that session's context either (zero hits for its filenames).

Worth keeping because the reflex was wrong in an instructive direction: the
scoping suspicion was aimed at the federation axis, where enforcement is
server-side and worked exactly as designed. The real defect was one axis over,
in a surface nobody suspected because it has no enforcement at all.

## The real defect

`recall()` filters on `scope` and nothing else — `reader.py:206` and `:219`.
`project` is never a predicate. Every other project-aware surface takes project
as a **model-supplied parameter** (`recall_by_project`, `recall_open_threads`),
injected by prose from the SessionStart hook; the MCP server resolves `scope`
from the pin at startup and has no project analog. So scope is enforced and
project is advisory, which is the documented design (`docs/index.md:81`,
2026-07-14) — but it means lexical recall draws from the whole main plane.

The main plane holds 262 sessions: 141 `thalamus-extract-*` eval-worktree
artifacts, leaving **121 real ones — 63 stepmania-chart-generator, 47 thalamus**,
7 ybx, 4 singletons. A thalamus session's lexical recall draws from a pool where
thalamus is the minority.

## What the returns actually look like

Calling session `project=thalamus`, RETURNS edges by the returned node's project
(claims attributed to their **parent** session, since claims carry no `project`
property at all — 1597/1597 returned claims are bare):

| parent project | Session vertices | Claim vertices |
|---|---|---|
| thalamus | 167 used / 17 ignored · **91% used** | 519 used / 99 ignored · **84% used** |
| stepmania-chart-generator | 28 used / 85 ignored · **25% used** | 317 used / 475 ignored · **40% used** |
| ybx | 0 / 2 | 0 / 10 |
| resume-workbench | 0 / 1 | 3 / 1 |

Off-project material carries **83% of all wasted claim volume** (486/585) and
**38% of all delivered claim value** (320/839).

## The 2×2 settles a disagreement the first pass could not

Measured against session summaries alone, off-project returns are 75% ignored
against 9% on-project, and that framing motivated a project-boost design. Two
consultations were minted against it (`837783bc60cb467b` literature,
`46f20d96fa084a3c` eval-methodology). Both answered against the design; then the
claim-level numbers above inverted a load-bearing argument in each.

**Eval-methodology filed a 13% ceiling** — "73% of returns carry no project
property, so a perfect boost removes at most 105/808 of ignored volume." The
schema fact is right and the conclusion does not follow: `recall()` has no
independent ranking track for contained claims. `matched_session_ids` is the
ranking unit, a contained-claim hit adds +1.0 to its **parent session's** score,
and `_load_session_result` renders the survivors. Demote the parent and its
claims never render. Addressable volume is **486/585 ≈ 83%, not 13%.** The
residual genuinely out of reach is the `matched_knowledge_vids` track — claims
with no parent session (`.not_(__.in_e("CONTAINS"))`), holding up to half the
window via `_mixed_window` — which is tier-2 expert knowledge served into main
and which a project prior must not touch at all.

**Literature filed a saturation objection** — a prior on for most of the pool is
a constant offset, non-discriminative. Refuted by the split: off-project is 57%
of returned volume, so the feature is near-balanced, which is the good case for
a binary feature, not the degenerate one. At 84% vs 40% the odds ratio is ~8.
Project is a *strong* discriminator.

**And the "kind, not project" reading is refuted too.** Both consultations
converged on a tempting alternative: summaries are noise, the claims underneath
them are not, so the discriminating variable is node kind. Eval-methodology
named a mechanism that would manufacture it — `MIN_MATCHED_RATIO = 0.3` in
`attribution.py` is a fraction of the node's *own* distinctive terms, so the bar
scales with text length and multi-topic session summaries are structurally
harder to score used than one-sentence claims.

That mechanism predicts summaries score worse than claims **in every cell**. The
2×2 says otherwise: it holds for stepmania (25% < 40%) and **reverses for
thalamus (91% > 84%)**. A length artifact cannot reverse sign by project. The
kind effect has no consistent main effect; the project effect is large in both
kinds. So the 75% figure is not an instrument artifact — off-project summaries
really are being ignored.

## Why no dial was turned anyway

The surviving objection is the one neither correction touched, and it is
structural rather than quantitative: **the intervention's granularity does not
match the granularity at which utility varies.** Within a single stepmania parent
session, claims run 40/60 used-to-ignored. A session-level prior assigns one
score to that whole block. Perfect exclusion of off-project parents is −475
ignored **and −317 used** — roughly two used claims destroyed per three ignored
ones saved, and no choice of weight changes that exchange rate, because the
weight has no information about which side of the block an item is on.

Two cheaper dials dominate it on the same arithmetic, and neither has been
measured:

- **Within-session claim selection.** Perfect selection is −574 ignored, −0 used.
  `reader.py` already does a crude version — details render only claims the
  query's terms touch, capped at 8 — and [lab/007](007-query-shape-refinement.md)
  called that cap arbitrary in its own dials section. It has never been tuned.
- **Summary suppression as a stub.** Render the matched session's summary as a
  no-vertex-ID stub and measure whether *claim* used% falls. Unchanged → the
  summary was injection cost at no utility. Falls → it was an orienting mediator
  and the waste number was lying. Precedent exists in lab/007's elision stub.

The decisive unmeasured number for the boost itself is **off-project used% as a
function of lexical rank within the trace.** A boost cuts at the margin, not at
the base rate; if off-project used% falls steeply with rank the boost is cheap,
if flat it cuts at 40% and is expensive. Rank is not currently on the RETURNS
edge.

## Standing prerequisites, in order

1. **Audit lab/007's outstanding prediction.** It added the ≥2-distinct-keyword
   floor for a *fan-out* symptom, validated on a single replayed query, and
   predicted fan-out ≤~15 nodes/trace with wasted share falling 50% → ≤30% over
   the next ten synced sessions. Twenty-two entries later that has never been
   checked; the ≤30% band survives only as a rendered target
   (`docs/03-master-plane.md:133-135`). `Trace` carries `ts` and `scope_report`
   already computes all three numbers — it needs a `--since/--until` window, and
   that audit *is* any future dial's baseline.
2. **Record `ranker_config` on `Trace`.** The properties dict in `eval/sync.py`
   carries query, tool, ts, session_id, scope, returned_count, injected_chars —
   nothing about the ranker that produced the row. Without it, a second dial on
   this path converts lab/007's "unverified" into "unauditable."
3. **The rank curve and the claim-kind breakdown**, before choosing a dial.

## The citation hazard this exchange created

Both tickets are burned, and `scope:main:exchange:46f20d96fa084a3c` holds the
13% ceiling **with a server-validated citation stamp on it**. Citation validation
checks that cited vertices resolve in the consulted scope; it cannot check that
the reasoning over them is sound. A future session recalling that exchange gets a
wrong number wearing the same badge as a right one. This entry is the durable
supersession — the corrected figures are here, and the exchange should be read
against them.

Generalizable, and it is the entry's main finding beyond the numbers: the
MEASURED / INFERENCE / ARGUMENT labels the grounding discipline mandates guard
against overclaiming *confidence*. They do not guard against a wrong model of the
system underneath correctly-labeled arithmetic. Both experts labeled their work
honestly and both were wrong about the mechanism. What caught it in each case was
one more query against the live graph — establishing the ranking **unit** before
reasoning about what a ranking change can reach.

## Grounding

Consultations `scope:main:exchange:837783bc60cb467b` (literature) and
`scope:main:exchange:46f20d96fa084a3c` (eval-methodology), both 2026-07-29, read
against the corrections above. Two anchors procured under feed `recall-ranking`:
*Unbiased Learning-to-Rank with Biased Feedback* (arXiv 1608.04468) — why a
ranker cannot be fit to logs it generated itself, which rules out tuning a weight
on used/ignored; and *Degenerate Feedback Loops in Recommender Systems* (arXiv
1902.10730) — echo-chamber vs filter-bubble degeneration, the hazard for a
single-operator system with no control population. Classical IR ranking is
otherwise a structural absence in the scan; see
[docs/11 §4](../docs/11-related-work.md).
