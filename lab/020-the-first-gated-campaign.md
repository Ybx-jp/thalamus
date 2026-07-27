# 020 — The first gated campaign: does withholding the constraint change anything?

**Date:** 2026-07-27 · **Component:** eval loop layer 2 (`thalamus eval run`) ·
**Status:** pre-registered, unrun at time of writing. Everything below the
horizontal rule was committed **before** the first arm launched.

## The question

Every counterfactual campaign to date has measured candidate variance, because
the battery's prompts handed over everything the candidate needed (lab/018).
lab/019 built the first task that withholds: `arm-runner-session-death-classification`,
whose L4 asserts a property nothing in the tree at `source.ref` states and whose
inherited suite asserts the opposite.

Two things are being measured, and they are independent. The prompt could induce
recall without the recall helping, or help without being used.

## Design

| | |
|---|---|
| task | `arm-runner-session-death-classification` (lab/019, gate 6/6) |
| model | sonnet |
| arms | `memory-on`, `memory-off` |
| replicates | 15 planned, analysed at ≥12 |
| primary endpoint | share of arms reaching **rung ≥ 4** — the task's declared `attributable_outcome` |

Rung ≥ 4, not rung 5: R3 is only weakly gated (derivable in principle from a
33-turn fixture in the pinned suite), and lab/019 pre-registered that a weakly
gated rung cannot be evidence of memory use.

Δ=2 is the *designed* anchor gap — memory-off ceiling at rung 3
(`m2-at-close-preserved`), correct answer at 5. On lab/018's pooled dispersion
(sd ≈ 1.63 rungs) that needs ~11/side; 15 is the budget for attrition.

A `SessionFault` halts the campaign; void and interrupted arms are excluded from
every criterion rather than counted as failures (the lab/016 correction).

---

## Pre-registered criteria

**C1 — does the withheld constraint gate? (primary).** Compare the share of
valid arms scoring rung ≥ 4, memory-on vs memory-off. The gate is real iff
memory-on exceeds memory-off. **Falsification: if memory-off reaches rung ≥ 4 at
a comparable rate, the fact was derivable from the tree after all** and lab/019's
`absence_check` — which is a lexical check, not a semantic one — passed something
it should not have. That outcome retires the task rather than the hypothesis.

**C2 — does an under-specified prompt actually induce recall?** lab/018 measured
memory-on arms calling a thalamus tool at 2/21 (9.5%) against 20/31 (65%) for
real sessions, and attributed the gap entirely to prompt shape. This task's
prompt is the first written to withhold. **Prediction, recorded in advance: the
memory-on call rate on this task exceeds 9.5% by a wide margin.** If it does not,
the prompt-shape explanation is incomplete and C1 becomes uninterpretable — a
memory arm that never called memory cannot demonstrate a memory effect.

C2 is the *mechanism* check and C1 the *outcome* check. C2 failing while C1
passes would mean the rung difference came from somewhere other than recall, and
must be reported as such rather than as a memory win.

**C3 — the probes, read as designed and not as score.** `memo-surfaced` has read
0/24 across every campaign because it detects knowledge unreachable from the
prompt and nothing was unreachable. This is the first task where it *can* fire.
`literal-convergence` is a confound flag: this is a `memorization`-stratum
replayed task, so a memory-on arm can reach the marker class by recalling the
answer rather than by reasoning about failure classes. Both stay unscored.

**C4 — dispersion, carried forward.** lab/018 measured 3 rungs of spread under
fixed model/task/arm. Report the same for this task. If the spread is again ≥2
rungs, per-cell n=1 remains uninterpretable and the C1 comparison needs its full
replicate count rather than an early read.

**Stated in advance:** no claim about memory's value in general follows from one
task in the memorization stratum. What this campaign can establish is narrower —
whether a prompt that withholds changes recall behavior, and whether recall
changes the rung. Both are prerequisites to the broader claim, neither is it.
