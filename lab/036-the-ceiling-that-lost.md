# 036 — The ceiling arm lost every pair, and the endpoint it was measured on read null

**Date:** 2026-07-30 · **Component:** eval layer 2 (`eval/arms.py` `ceiling`) · **Status:** measured. Cancels the queued layer-2 campaign work. Full write-up: `experiments/004-the-ceiling/`.

## The question

Every memory-on/off campaign so far asked whether *retrieval* helps. None
established that the battery could register the help of memory at all. So: hand a
candidate exactly the right memory, with no retrieval to get wrong, and see whether it
beats a candidate with none. If a perfect memory does not separate, no ranking change,
no dial and no better instrument can move this battery.

`ceiling` is memory-off's stripped harness — no MCP, memory hooks removed — plus the
task's `under_specification.fact` injected into the prompt, framed as recall rather
than as instruction. A task with nothing withheld is refused: there the ceiling is
memory-off wearing another name.

## Result — 12 arms, $28.84, sandboxed with the store isolated

| | rungs | L≥4 (primary) | L≥3 (exploratory) | turn-capped |
|---|---|---|---|---|
| ceiling | 1,1,1,1,1,1 | **0/6** | 0/6 | 4/6 |
| memory-off | 3,3,3,3,0,3 | **0/6** | 5/6 | 1/6 |

**The pre-registered falsifier fires.** Rung 4 is the task's own memory-attributable
outcome, fixed in its YAML before any campaign. Neither arm reached it. A perfect
memory cannot clear this task's gate, so the battery is the binding constraint, and
the container campaign and consequence-probe work queued behind it are cancelled
rather than rescheduled.

The direction at rung 3 runs against the ceiling, and the statistics are modest and
reported as such: paired sign test **p = 0.219** (1 win, 5 losses — six pairs cannot
beat 0.031 even with a clean sweep), rank statistic 0.167 as recorded and 0.000
excluding censored arms. The confidence sequence reached its horizon without firing,
which at this n it was always going to.

## Two mechanisms, and this design cannot separate them

The ladder is strictly implying. L2 is *stop on the death the operator described*,
reachable from the prompt alone; L4 is *a death after real work leaves an attempt of
unknown completeness, so it must not be graded*. The injected memory is **L4/L5
content**, and every ceiling arm failed **L2**.

1. **A conclusion without its path.** A distilled memory records the endpoint of a
   design discussion. Handed to an agent that has not walked that path, it may
   substitute for the earlier steps instead of adding to them — the candidate builds
   the refinement and never builds what it refines. All four ceiling arms with the
   field recorded visibly acted on the memo (term ratios 0.41–0.54), so this is not
   the memo being ignored.
2. **Scope expansion.** Ceiling arms hit the 40-turn cap 4 times in 6 against
   memory-off's 1 in 6. The memo may simply have prompted a change too large for the
   budget, and the floor score is censoring rather than misdirection.

Raising the turn cap discriminates. Run afterwards as one exploratory arm, outside
the registered design, and it settles the question.

## The follow-up: 80 turns, worktree kept

One ceiling arm at double the turn budget, retained for inspection. It finished in
**36 of 80 turns** — not censored, L1 green, nothing broken — and scored rung 1 again.
So the budget was never the constraint, and scope expansion is out.

What it passed is the finding. The ladder came back:

| L1 no-regression | L2 behavioral | L3 relation-r1 | L4 relation-r2 | L5 relation-r3 |
|---|---|---|---|---|
| PASS | **FAIL** | FAIL | FAIL | **PASS** |

**Correction, and it narrows the claim.** An earlier reading of this table said the arm
"passed the rung the memo describes". That is misleading: memory-off arms pass L5 as
well — every arm in the campaign did. L5 is an *absence* check (having refused to grade,
also refuse to classify by turn count), so any candidate that never writes a turn-count
heuristic passes it for free. It discriminates nothing.

What discriminates is the other end. Every ceiling arm failed **L2** and **L3**;
every memory-off arm passed both:

| | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|
| ceiling (4 of 4 recorded) | PASS | **FAIL** | **FAIL** | FAIL | PASS |
| memory-off | PASS | **PASS** | **PASS** | FAIL | PASS |

L2 is *stop on the death the operator actually described* — reachable from the prompt
alone, and the thing the memo says nothing about. The conclusion memo cost the
foundation rungs, and it cost them in all four recorded arms while the arms with no
memory at all cleared them.

The retained diff says the same thing in the candidate's own words. It wrote
"distinguish the two credential-death shapes lab/012 first saw — both ungraded", "both
shapes stop the campaign and leave their record void", "completeness unknown", and
reasoned explicitly against a turn-count heuristic. That is the memo's conclusion,
implemented faithfully, on top of a base behaviour that was never built.

**A conclusion handed over without its path replaced the path.** The candidate did not
ignore the memory and did not misunderstand it — memo-echo ratio 0.784, the highest of
any arm. It built what the memory described and never built what the memory presupposed.

This is a claim about *what distillation extracts*. `thalamus extract` writes decisions
and solutions — the endpoints of sessions — and this is one measured case where an
endpoint, delivered to an agent that had not walked the path to it, cost that agent the
step it was already capable of taking on its own.

## Two corrections made mid-campaign

**The void detector was wrong.** It counted every entry in `recall_calls`, so an arm
with `thalamus: 0, tool_search: 1` — one that loaded tool schemas and reached no memory
tool — was flagged as memory reached inside a no-memory arm. That is confinement
*working*. Voiding a campaign for succeeding is worse than the failure the check exists
for.

**Three identical 41-turn arms were read as diligence.** They were the 40-turn cap. A
capped arm is censored and its rung is a lower bound, and the write-up's "worked
longer" line was removed.

The pre-registration was **silent on censoring**, so both readings are reported and
neither is called primary. The censored arm favours the ceiling, so dropping it quietly
would have strengthened the story the campaign had been accumulating.

## Two things confirmed that were not the point

**Confinement works, live.** Four arms loaded tool schemas and reached no memory tool.
Three ran `git log --all` inside their worktree — lab/022's channel — and none was
stamped contaminated, because `prepare_worktree` gives each arm a one-commit repo, so
the reach returns nothing. Until this campaign confinement had only been verified by
direct probe (`scope:eval-methodology:thread:arm-confinement-unverified-live`).

**The battery had been unrunnable for a day** — see lab/035. Found only because this
campaign tried to run it.

## The mechanism did not survive its own test

experiments/005 put "a conclusion replaced the path" to a pre-registered test: the same
knowledge, framed as the situation and the evidence, with the prescription withheld. If
the framing were the variable, the problem framing should not have cost L2.

It cost it anyway — 1 of 5 problem-framed arms passed L2 against 0 of 5 conclusion-framed,
one discordant pair, exact p = 1.000. **The hypothesis is falsified as operationalised.**

What replaces it is blunter and worse for the premise. Pooling both framings, **1 of 10**
arms handed a memory passed the foundation rung, against **5 of 6** handed nothing. The
cost belongs to *injection*, not to how the memory was written — and rewriting what
`thalamus extract` stores would not have avoided it, because the problem framing is such
a rewrite and it changed nothing measurable.

**Ends in:** measurements (null on the primary endpoint) + a cancelled programme + a
falsified mechanism.
