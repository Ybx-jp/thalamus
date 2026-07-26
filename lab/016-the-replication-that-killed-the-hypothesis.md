# 016 — The replication that killed the hypothesis, and the guard that was too specific

**Date:** 2026-07-26 · **Component:** eval loop layer 2 (`thalamus eval run`) ·
**Status:** matrix aborted ~40% in by a session limit; **the valid half
falsifies lab/015's headline hypothesis**; the runner guard that should have
caught the abort was keyed too narrowly and is fixed.

## What was attempted

Replicates 2 and 3 of lab/015's full matrix (3 models × 2 tasks × 2 arms),
design held identical, to test whether the model×task recall pattern was real
and whether the under-specification hypothesis was worth pursuing. The
falsification criterion was written down **before** the run: if the reader cells
flip across replicates, recall-calling is substantially stochastic and the n=1
pattern was noise.

## Incident: a session limit, and a guard that missed it

A usage limit landed at 22:44Z, mid-matrix. The runner did not stop:

| segment | arms | state |
|---|---|---|
| rep2 sonnet | 4 | valid |
| rep2 fable | 2 | valid |
| rep2 fable | 2 | killed at turns 11 and 18 of 40 |
| rep2 opus → rep3 all | 16 | void — 1 turn, $0.00 |

**Root cause: the lab/012 hardening matched one vendor string.**
`AUTH_FAULT_MARKER = "Failed to authenticate"` was taken from the single
incident lab/012 observed, so `You've hit your session limit · resets 3:50pm`
walked straight past it. Four further waves ran against a dead account,
recording 16 arms as `accepted: false` — not merely useless but *actively
misleading*, since a $0.00 1-turn arm reads as a candidate that failed
instantly. Worse, the two arms killed mid-work were stamped
`attributable: true, accepted: false`: a trustworthy-looking candidate defect
that was nothing of the kind — exactly the error class the classifier was built
to prevent, reintroduced by matching phrasing instead of failure class.

**Fixed.** `AuthFault` → `SessionFault`, matching a class of markers
(authentication, session/usage/rate limit, quota). Two shapes, both stopping
the campaign and **neither graded**:

- `void` — 1 turn, $0.00, nothing happened.
- `interrupted` — real work, then death at unknown completeness.

There is deliberately **no `at_close` shape**. lab/012 did establish that one
arm's token died only after its fixtures were already passing, making its
oracles trustworthy — but that was established by reading the raw transcript,
at 33 turns of a 40-turn budget, which no cheap signal distinguishes from this
entry's arms cut off at 11 and 18 of the same budget. A first attempt at this
fix did guess, via `num_turns < max_turns`; the test suite caught it
immediately by replaying lab/012's own 33-turn shape. When an interrupted arm
matters, read its transcript and say so by hand.

## The finding: recall-calling is stochastic, not a task property

Valid arms only (18 of 36), memory-on cells:

| model · task | r1 | r2 | verdict |
|---|---|---|---|
| sonnet · reader | 0 | **1** | **inverted** |
| sonnet · consultation | 1 | **0** | **inverted** |
| fable · reader | 0 | 0 | consistent |

Sonnet did the exact opposite in replicate 2 — both cells flipped. lab/015's
under-specification hypothesis (the consultation task's open-ended design
judgment invites recall; the reader task's fully specified mechanical fix does
not) predicted consultation > reader *within* a model. Across two replicates
sonnet is 1–1. That is a coin flip, and it is the pre-registered falsification
condition, met exactly.

**lab/015 §2 is superseded.** The "model×task interaction" it reported was a
single draw from what now looks like a substantially random process, and the
under-specification story was an explanation fitted to n=1 per cell. The
hypothesis is dropped, not weakened — no task-authoring work should be built on
it. What survives from lab/015 §2 is narrower and still true: *when* a call
happens it follows the injected pattern exactly, and the arm-order confound is
still broken.

This is also the second time in two entries that a clean-looking pattern across
a handful of cells dissolved under one more observation (lab/015 read a
two-model agreement as a task effect; opus falsified it — then opus's own
pattern falsified here). The operating lesson is specific: with one observation
per cell, *any* 2×3 pattern will look structured, and this battery's per-cell
variance is large enough to manufacture one.

## What survives, and is now better supported

| claim | evidence | n |
|---|---|---|
| Acceptance is saturated — a battery ceiling, not a model ceiling | **18/18 accepted** across three models and two replicates | 18 |
| The memory-off control is clean | 9 control arms, **0** recall calls | 9 |
| `memo-surfaced` fires iff the arm called a thalamus tool | **0 mismatches** | 18 |
| Memo *use* is unevidenced | `fix-name-convergence` **0/18** | 18 |

The probe-validity result is now the sturdiest thing the eval has produced:
perfect correspondence at n=18, no false positives, control arms silent.

## What this buys the design

1. **Do not pursue the under-specification hypothesis.** It was refuted by the
   cheapest possible test, before any task-authoring effort was spent on it.
   That is the replication doing exactly its job.
2. **Recall-calling needs a base rate before it can be a dependent variable.**
   It varies run-to-run within a fixed (model, task, arm) cell, so any single
   campaign's recall column is one sample of an unknown distribution. Estimating
   that rate is many replicates of an already-saturated battery — expensive, and
   it yields no utility signal while acceptance cannot discriminate.
3. **The battery ceiling is now the only sensible next move.** 18/18 acceptance
   means neither recall-calling nor memory content has anywhere to show an
   effect. Harder tasks or a graded oracle must come before any further
   campaign spend.
4. **Guard rule, generalized:** infrastructure guards must match the *class* of
   failure, never the phrasing of the one incident that motivated them. Both
   times this runner lost a campaign to infrastructure, the loss came from a
   guard that was correct about the case in front of it and blind one step to
   the side.
