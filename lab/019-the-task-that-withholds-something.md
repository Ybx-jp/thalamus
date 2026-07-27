# 019 — The task that withholds something, and the three facts that couldn't gate it

**Date:** 2026-07-27 · **Component:** eval loop layer 2 (`config/tasks/`,
`thalamus eval oracle`) · **Status:** the task is authored and its gate passes
**6/6** at zero model cost, with every rung witnessed. Unrun against arms.

## Why

lab/018 established that the battery, not the runner, was the binding
constraint: memory-on arms call a thalamus tool at 2/21 while real interactive
sessions in this repo call it at 20/31, and a controlled probe holding the
harness completely fixed showed the gap is carried entirely by the prompt. Both
existing tasks hand the candidate symptom, counterexample and constraint. Nothing
is unreachable, so declining to recall is correct behavior, and the contrast has
nowhere to appear.

This entry builds the first task that withholds something.

## The obstacle: this repo documents itself out of gateable facts

Three candidate graph-only facts were rejected before one survived, all for the
same reason. The `at_close` reasoning is in `lab/016` **and** in an `arms.py`
docstring. The reader task's match-floor constraint is in a `reader.py` comment.
The lab/018 turn-cap hazard is in lab/018.

CLAUDE.md requires docs to describe current state only, with history in git and
the graph — but the **lab notebook lives in the repo**, and the code is
commented at essay density. Between them, almost every decision is recoverable
from the worktree, and a fact recoverable from the worktree gates nothing.

The consequence is a method, not a complaint: **fact selection has to be
mechanical.** The task now carries an `absence_check` — a command that proves the
tree at `source.ref` cannot answer the question — and the first version of that
check *failed*, catching `rate limit` in `docs/06-ingestion.md`. That hit is
about the arXiv ingest API and cannot inform how an arm classifies a dead
session, so the check was narrowed to the runner's surface **and the exclusion
written into the file** rather than silently dropped.

## The task

`arm-runner-session-death-classification` — replayed, ref `1fc6aef`, fix_ref
`4432703`. The prompt names no marker, no shape and no turn count:

> A counterfactual campaign kept running after my account died partway through a
> matrix, and the arms it recorded afterwards look like ordinary candidate
> failures in the run records. Make the runner notice and stop. Don't change what
> a healthy arm records.

What makes it gate: at `1fc6aef` the runner not only matches one vendor string,
it **implements and unit-tests an `auth_failed_at_close` shape that grades a
late-dying arm**. The inherited suite actively rewards the wrong answer — which
is what makes the fact-blind path *realistic* rather than unfair. A passing test
is the strongest reason a competent agent preserves a behavior.

The ladder, ceiling-gated and floor-preserved:

| rung | check | reachable from the prompt? |
|---|---|---|
| L1 | pinned suite, minus a pre-registered obsolete set | yes |
| L2 | the described death stops the campaign | yes |
| L3 (R1) | the whole failure class, not one more literal | partly |
| L4 (R2) | a death after real work is **not graded at all** | **no — gated** |
| L5 (R3) | classification is invariant to turn count | weakly gated |

## What the expert changed

Two rounds with eval-methodology (`scope:main:exchange:5c5c57142ffc43ef`,
`scope:main:exchange:1ef0d3649b5b495f`). Three corrections, each of which the
first draft would have shipped broken:

**The design was ungradeable.** L1 pins `tests/` at `source.ref`, and the correct
fix legitimately retires three of those tests — so *no candidate, including the
fix itself, could exceed rung 3*. Reproduced before believing it: the fix fails
exactly 3 pinned tests. Two of the three are pure name-coupling
(`classify_auth_fault` → `classify_session_fault`), the imitation hazard
`pin_pre_existing_suite`'s own docstring warns about; only the third is a genuine
design contradiction. The proposed fix — deselect the whole module — was rejected
on the grounds that the module also holds the tests guarding *"don't change what a
healthy arm records"*, the prompt's own second requirement. What shipped instead
is an exemption at **test-node granularity**, pre-registered in the task file,
with the retired assertion **relocated to L4 with the opposite sign**. The gate is
not hollowed because nothing is dropped.

**L5 had no witness.** The fact-blind candidate fails R2 *and* R3, so nothing
separated them and the entire designed gap sat on R2. Fixed by the **rung-witness
rule**: every rung needs a candidate scoring exactly it. `m3-turn-keyed-label` —
refuses to grade, but still labels by how late the death was — is that witness.

**L2 and R1 were the same rung.** At `1fc6aef` an auth-string death *is* already
caught, so L2 could only fail there if its witness were non-auth, which is R1.
Redrawn: L2 is one exemplar, L3 is generalization across the class, and
`m1-second-literal-marker` witnesses the split.

## The gate

```
candidate                kind             expect   got   verdict
negative-anchor          anchor-negative      L1    L1   ok
positive-anchor          anchor-positive      L5    L5   ok
m1-second-literal-marker mutant               L2    L2   ok
m2-at-close-preserved    mutant               L3    L3   ok
m3-turn-keyed-label      mutant               L4    L4   ok
m4-equivalent-renamed    mutant               L5    L5   ok
PASSED — the ladder reproduced every pre-registered rung
```

Every rung 1–5 has a witness, and `m4` confirms the rungs stayed behavioral: a
correct fix that renames the exception class, the classifier and both shapes
still scores full marks. `m2` is the load-bearing one — it is the **pre-registered
memory-off ceiling**, and `fix_ref` cannot stand in for it, because the fix says
where a *correct* candidate lands and says nothing about where an unaided one
should.

## What is disclosed rather than hidden

**R3 is derivable in principle.** The pinned suite at `ref` carries a 33-turn
`at_close` fixture, so a candidate could reason its way to turn-invariance
without recall. Judged unlikely but unmeasurable, so it is recorded as
`gates_rungs_weak: [5]`, both routes are listed, and the pre-registered
memory-attributable endpoint is **rung ≥ 4**, not 5. Nesting is what makes this
safe: a memory-off arm that derives turn-invariance still fails R2 and cannot
reach 5 anyway.

**Under-specification and memorization are confounded.** This is a `replayed`
task whose fixing session distills into the graph, so a memory-on arm can reach
the marker class by recalling the answer rather than by reasoning about failure
classes. The stratum is tagged `memorization` honestly, and an unscored
`literal-convergence` probe flags the confound without pretending to resolve it.

**The obsolete set's equality check is manual.** The rule is that the declared
set must equal *exactly* the pinned tests `fix_ref` fails; it was verified by
hand this session (3 for 3) but is not yet automated, because doing so needs a
worktree and a pytest run rather than a schema check.

## Power

Not yet run against arms, and the expert was explicit that its scope holds no
claims on power — the numbers are arithmetic on lab/018's dispersion (pooled sd
≈ 1.63 rungs): Δ=1 needs 43 arms/side, Δ=1.5 needs 19, Δ=2 needs 11 (~$26–35).
The anchor ceiling gap was therefore *designed* to be Δ=2 — memory-off ceiling
at rung 3, correct answer at 5. The plan is 15/arm, analysed at ≥12.

## Grounding

- arXiv 2601.19935 (Mem2ActBench) — existing memory benchmarks test passive
  retrieval of isolated facts in response to explicit questions rather than
  active application of memory to execute a task. This entry's whole premise:
  the old prompts asked explicitly, so nothing had to be retrieved.
- arXiv 2305.14795 (MQuAKE) — recall of a stored fact and action on its entailed
  consequences are different measurements. Why the probes stay unscored and the
  rungs assert consequences.
- arXiv 2412.20692 — metamorphic test adequacy is measured over relations **and
  source inputs**; the warrant for putting the necessity in the prompt rather
  than in a relation's predicate.
- arXiv 2103.07189, 2512.16741 — mutant realism and coupling; why the fact-blind
  anchor must be the plausible failure rather than the catchable one.
