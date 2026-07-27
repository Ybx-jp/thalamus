# 018 — The first graded campaign: does the ladder's interior actually get used?

**Date:** 2026-07-27 · **Component:** eval loop layer 2 (`thalamus eval run`) ·
**Status:** pre-registered, unrun at time of writing. Everything below the
horizontal rule was committed **before** the first arm launched.

## The question

lab/017 established that the graded ladder discriminates *when handed candidates
built to land on specific rungs* — five pre-registered mutants plus two anchors,
7/7. That is a property of the instrument measured against authored inputs. It
does not establish that real candidates, working the task unaided, ever land
anywhere except the two ends the binary oracle already distinguished.

If every real arm scores 0 or 5, the ladder is a more expensive spelling of
`accepted` on this task and the interior rungs are decoration.

## Design

| | |
|---|---|
| task | `reader-case-insensitive-recall` — the only battery task carrying L3–L5 |
| model | sonnet |
| arms | `memory-on`, `memory-off` |
| replicates | 3 (6 arms total) |
| endpoint | `rung` ∈ 0–5, **not** `accepted` |

`consultation-empty-brief-refusal` is deliberately excluded: it stops at L2, so
it cannot de-saturate and would buy nothing but cost. Replicates are spent on
reps rather than on the model dimension because lab/016 showed the model×task
recall pattern was stochastic at n=1 — buying a third model before buying a
second replicate repeats that mistake.

Void and interrupted arms (`SessionFault`) are excluded from every criterion
below rather than counted as failures — the lab/016 correction.

---

## Pre-registered criteria

**C1 — de-saturation (primary).** The ladder's interior is *used* iff at least
one valid arm scores a rung in {1, 2, 3, 4}. If all six land at 0 or 5, the
graded endpoint carries no information the binary did not, on this task, at this
model, and the honest write-up says the ladder is unexercised outside its mutant
set.

**C2 — within-arm dispersion.** Rung spread across the three replicates of the
*same* cell. If any cell spreads ≥2 levels, per-cell n=1 graded campaigns are
uninterpretable and the next campaign must buy replicates before it buys models
or tasks.

**C3 — the arm comparison is recorded, not concluded.** memory-on vs memory-off
mean rung is logged for the record. n=3 per cell powers nothing, and it is
written down here, in advance, that **no claim about the effect of memory on
task quality will be made from this run.** This entry measures the instrument.
If C2 comes back tight, the arm comparison becomes worth powering; if it comes
back wide, the number in this run's table is noise and will be labelled as such.

Secondary observables logged without criteria attached: `recall_calls`, cost,
turns, `turn_capped`, `attributable`.
