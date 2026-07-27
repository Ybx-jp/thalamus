# 018 — The first graded campaign: does the ladder's interior actually get used?

**Date:** 2026-07-27 · **Component:** eval loop layer 2 (`thalamus eval run`) ·
**Status:** run. **C1 passes — the interior is real.** C2 fails: both cells
spread three rungs, so n=1 graded cells are uninterpretable. C3 is void for a
harder reason than n=3 — **no memory-on arm ever called a thalamus tool**, so
the two arms were never two conditions. Pre-registration committed in `fa38dc6`,
before the first arm launched.

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

---

## Result

Six arms, all valid — no void, no `SessionFault`, `attributable: true`
throughout. $8.57, 32 minutes wall.

| rep | arm | rung | first failure | turns |
|---|---|---|---|---|
| 1 | memory-on | **2** | L3 — `recall('A-Trak') != recall('a-trak')` | 27 |
| 1 | memory-off | 5 | — | 27 |
| 2 | memory-on | 5 | — | 33 |
| 2 | memory-off | **4** | L5 — `recall_by_project('CODE')` matched; project matching must stay verbatim | 41 · capped |
| 3 | memory-on | 5 | — | 41 · capped |
| 3 | memory-off | **2** | L3 — `recall('ALSA-emulation-over-Pulse') != recall('alsa-…-pulse')` | 36 |

### C1 — passes, and the interior is occupied for two different reasons

Three of six arms land at 2 or 4. The ladder's interior is reachable by
candidates working unaided, not only by mutants authored to reach it — which is
the thing lab/017's 7/7 could not establish about itself.

The two interior classes are distinct and both invisible to the binary oracle:

- **Under-fix at L3 (reps 1 and 3).** Both arms fixed the reported symptom and
  passed the behavioral oracle, then failed on *hyphenated* capitalized terms.
  These are candidates that fixed the case they were shown rather than the path,
  and L3 is precisely the diagnosed-vs-patched cut lab/017 predicted `m1` probed.
  The binary oracle scores them identically to a candidate that did nothing.
- **Over-fix at L5 (rep 2).** The arm loosened project matching to
  case-insensitive as well, which the relation forbids. Collateral damage, the
  `m3` class — a candidate that did *more* than the fix and is worse for it.
  Note this failure is legible in the diff rather than an absence of work, so
  the turn cap below does not confound it.

Under-fix and over-fix landing on opposite ends of the interior is the ordering
claim doing visible work: a weighted sum would have let them cancel.

### C2 — fails; buy replicates before models or tasks

memory-on {2, 5, 5} · memory-off {5, 4, 2}. **Both cells spread three rungs.**
The pre-registered consequence stands: per-cell n=1 graded campaigns are
uninterpretable, and the next campaign spends on replicates first. lab/015's
mistake — reading structure off one observation per cell — would have been
available here in a new form, and the criterion written down in advance is what
forecloses it.

The useful number: **three rungs of spread under fixed model, task, and arm** is
the noise floor. Any future memory effect on rung has to clear that, and nothing
about this run suggests it is small.

### C3 — void, and not merely underpowered

memory-on mean 4.0 vs memory-off 3.67 — reported per pre-registration, claimed
nothing from, and now known to be worse than noise. **`recall_calls.thalamus`
is 0 in all three memory-on arms.** The arms differed in hooks and MCP wiring;
they never differed in behavior. This is six samples of one condition, and the
0.33 gap is the same stochasticity C2 measured.

## The recall gap moved, it did not close

The `toolsearch-deferred-recall-gap` fix (session `623f0ced`) targeted agents
not knowing the deferred schemas needed loading. Measured here, **it works at
the layer it targeted and the blocker is now one step later**:

| | memory-on arms |
|---|---|
| SessionStart hook text present | 3/3 |
| called `ToolSearch` | 1/3 |
| loaded the thalamus schemas successfully | 1/1 of those |
| called any `mcp__thalamus__*` tool | **0/3** |

Rep 2 is the sharp case. It issued
`select:mcp__thalamus__memory_open_threads,mcp__thalamus__memory_recall_by_project`
verbatim, got both tool references back with no error — and then went straight
to `Read` on `reader.py` and never touched either tool again. Discovery is
fixed. **Use is not.** The remaining gap is not a harness defect at all but a
judgment the agent makes: with a concrete bug report in hand, reading the source
looks cheaper than querying memory. Any fix aimed at discovery will now miss.

This also extends lab/016's sturdiest result cleanly: `memo-surfaced` fired iff
the arm called a thalamus tool, and with 0 calls there are 0 hits, 0 mismatches.
24 arms, no exceptions. `fix-name-convergence` remains **0/24**.

## A grading hazard this run exposed but did not suffer

Two arms hit the 40-turn cap and were graded anyway (`num_turns: 41`,
`is_error: true`, empty result tail). Here it was harmless — the capped
memory-on arm scored 5, and the capped memory-off arm's L5 failure is an
overshoot *present in the diff* rather than work left undone. But the general
case is not harmless: an arm cut off mid-work scores the rung it happened to
reach, and "could not" is then indistinguishable from "ran out of budget."

This is lab/016's `interrupted` reasoning arriving at a second door. A
`SessionFault` arm is excluded from grading; a turn-capped arm is not, and the
argument for excluding it is the same argument. Left as a named hazard rather
than patched blind — the fix wants a campaign where it actually bites, and
raising the cap is the cheaper first probe.

## What this unblocks, and what it does not

The graded endpoint carries information the binary did not, on real candidates,
at a measured 3/6 interior occupancy. Layer 2 can now report *how* a candidate
failed. What it still cannot do is compare arms: until a memory-on arm calls a
memory tool, the counterfactual has no contrast to measure, and every campaign
run before that is an expensive way to sample candidate variance. **The recall
gap, not the oracle, is now the binding constraint on the eval loop.**

## Grounding

Instrument design and its citations are lab/017 and docs/04 §"Anchors and
mutants"; nothing new was ingested for this entry. The pre-registration
discipline followed here — falsification criterion committed before the run —
is the lab/016 protocol, applied to the instrument instead of the hypothesis.
