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

---

## Result

24 valid arms, 12 replicates, $55.58, no session faults, 3/24 turn-capped at 60.

| | memory-on | memory-off |
|---|---|---|
| **C1 — reached rung ≥ 4** | **3/12 (25%)** | **2/12 (17%)** |
| rungs | 1,1,1,1,1,1,2,2,2,5,5,5 | 1,1,1,1,1,1,3,3,3,3,5,5 |
| mean rung | 2.25 | 2.33 |
| **C2 — arms calling a thalamus tool** | **5/12 (42%)** | **0/12 (0%)** |
| `memo-surfaced` | 4/12 | 2/12 |
| `literal-convergence` | 6/12 | 9/12 |

### C2 passes, and it is the result worth keeping

**42% against lab/018's 9.5%** (2/21 across every memory-on arm on the old
self-contained tasks), with the memory-off control clean at 0/12. The prediction
was written down before the run. **An under-specified prompt induces recall; a
self-contained one does not.** That is the mechanism lab/018 inferred from a
two-session probe, now measured across 12 replicates.

### C1 fails — no outcome effect

3/12 vs 2/12 is a one-arm difference on n=12, and the *mean* rung is marginally
worse for memory-on. Nothing here supports a memory effect on quality.

The pre-registered falsification said that if memory-off reaches rung ≥ 4 at a
comparable rate, the fact was derivable from the tree. It does, so **the gating
claim does not hold as stated** — with the caveat below about how two of those
arms got there.

### The contamination: arms read their own answer key

Two memory-off arms ran `ls config/tasks/` and then read
`/home/ybx/code/thalamus/config/tasks/arm-runner-session-death-classification.yaml`
— **the operator's live repo, by absolute path, outside the worktree**. That file
is the answer key: `under_specification.fact` states the withheld constraint in
prose, and the acceptance block contains every relation with its exact marker
strings and turn counts.

The worktree is checked out at `1fc6aef`, where the task file does not exist —
the leak is that an arm runs with `--dangerously-skip-permissions` and nothing
stops it reading the operator's checkout. Scoped, but real:

| | n | rungs | ≥ 4 |
|---|---|---|---|
| memory-on (none leaked) | 12 | 1,1,1,1,1,1,2,2,2,5,5,5 | 3 (25%) |
| memory-off, clean | 10 | 1,1,1,1,1,1,3,3,3,5 | 1 (10%) |
| memory-off, leaked | 2 | 3,5 | 1 |

Excluding the two leaked arms moves the comparison to 25% vs 10% — still not an
effect at these counts, and **post-hoc, so it is exploratory and not the
pre-registered answer**. The pre-registered C1 is the intention-to-treat 3/12 vs
2/12, and it is null.

One clean memory-off arm did reach rung 5 without memory or the answer key. The
`alternative_routes` disclosure in lab/019 earned its place.

### C3 — `memo-surfaced` is not a memory signal any more

lab/016's sturdiest result was that `memo-surfaced` fires **iff** the arm called
a thalamus tool, 0 mismatches across 24 arms. It is now falsified, and precisely:
both memory-off firings are the two leaked arms, because the probe's pattern is a
session UUID **printed in the task file they read**. Among clean memory-on arms it
still behaves — 4 hits against 5 callers, no false positives.

So the probe is sound and its *environment* is not. A probe searching for a token
that appears in a file the candidate can open measures reading, not recall.

`literal-convergence` fired 9/12 in memory-off, which cannot involve recall at
all. As a confound flag it is uninformative: the marker vocabulary is reachable
by reading `arms.py`, which is the point of the task.

### C4 — dispersion widened

Spread of **4 rungs in both cells** (1→5), against lab/018's 3. Per-cell n=1 is
hopeless and n=12 is marginal; a real Δ=1 effect would need the ~43/side the
power arithmetic called for, at ~$2.30/arm.

### The unbudgeted finding: half the arms barely tried

**12 of 24 arms scored rung 1**, failing the L2 behavioral oracle. Six of them
concluded in 12–20 turns at $0.45–0.70, against $2.89 for the rest. Under-
specification cuts both ways: it makes an arm reach for memory (C2), and it also
lets an arm decide it is finished before it has done the work. The prompt says
"make the runner notice and stop" and never says what counts as noticing.

That is a task-design finding, not a memory finding, and it dominates the
variance in this campaign.

## Verdict

The task did what lab/019 built it to do at the *mechanism* level and not at the
*outcome* level. The honest summary: withholding the constraint changes retrieval
behavior four-fold and does not — at n=12, against 4 rungs of noise, with half
the arms under-attempting — change the score.

No claim about memory's value follows. This is one task in the memorization
stratum with a leaking harness and a floor problem.

## What has to happen before the next gated campaign

1. **Close the answer-key leak.** An arm must not be able to read the operator's
   checkout. Until then every gated task is one `ls config/tasks/` from being
   solved, and `memo-surfaced` cannot be trusted.
2. **Raise the floor.** Half the arms stopped before the behavioral oracle. The
   prompt needs enough specification to make "done" legible without restoring
   the constraint that does the gating — the exact line lab/019's `floor_rung`
   names but does not enforce behaviorally.
3. **Then power it.** Δ=1 at 4 rungs of dispersion is ~43/side. That is a real
   budget decision, not an incidental one.
