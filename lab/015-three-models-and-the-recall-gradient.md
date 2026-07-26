# 015 — Three models, twelve arms: recall is a model×task effect, and a metric was lying

**Date:** 2026-07-26 · **Component:** eval loop layer 2 (`thalamus eval run`) ·
**Status:** 12/12 arms recorded, all attributable, zero infra faults. Two
results the single-model campaign could not have produced, one probe-validity
win, and one eval-metric defect found and fixed.

## Setup

lab/014's campaign re-run across three models — **sonnet**, **fable**, **opus**
— same two seed tasks, same balanced order, `--full-auto`, 40-turn cap. Two
campaigns concurrent at a time throughout, matching lab/014's shape so
wall-clock stays comparable. Motivated by lab/014 §4: acceptance had saturated
at 4/4 and the open question was whether that was a sonnet ceiling or a battery
ceiling.

## Finding 1: acceptance is a battery ceiling, not a model ceiling

**12/12 arms accepted.** Every arm of every model solved both tasks. Fable
never even hit the turn cap. The acceptance oracle discriminates *nothing* at
any capability level tested, which upgrades lab/014 §4 from a suspicion about
one model to a measured property of the battery. No memory contrast can be
read from the acceptance column until the tasks can fail.

## Finding 2: recall-calling is a model×task interaction

The corrected `SessionStart` instruction (lab/014) reached every memory-on arm
identically. What each did with it:

| memory-on arm | sonnet | fable | opus |
|---|---|---|---|
| reader (order 0) | 0 calls | 0 calls | **1 call** |
| consultation (order 1) | **1 call** | **1 call** | **1 call** |

Every call that happened followed the injected pattern exactly: one
`ToolSearch` with the prescribed `select:` query, then one
`memory_open_threads(project="thalamus")`.

Two independent effects, neither visible at n=1 model:

- **Task**: the consultation task elicited recall from *all three* models; the
  reader task from only one. The consultation prompt asks for a design
  judgment ("make the refusal honest — the two failures should be
  distinguishable, each naming its own remedy"), which is under-specified in a
  way that invites looking for prior intent. The reader prompt is a fully
  specified mechanical fix ("without loosening the match floor or changing what
  counts as a keyword") where reading the source is self-evidently sufficient.
- **Model**: opus reached for memory on the task the other two skipped.

An intermediate reading of this campaign — after sonnet and fable agreed and
before opus ran — was that the split was purely by task. Opus's reader arm
falsified it. Two models agreeing was not evidence enough; recorded here
because the same trap will recur every time a two-cell pattern looks clean.

**The order confound this dissolves.** The balanced design pairs
reader→(on, off) and consultation→(off, on), so across lab/011–014 memory-on
had *only ever* run first on reader and second on consultation — task and
arm-order were perfectly confounded. Opus's reader/memory-on hit is at order 0,
and sonnet/fable's consultation hits are at order 1, so no ordering rule
explains the pattern. The confound is broken by data rather than by argument,
and no control campaign is needed.

## Finding 3: the probes are validated as surfacing detectors

Across all 12 arms, `memo-surfaced` fired **exactly** when the arm called a
thalamus tool and never otherwise:

- 4 hits, all in arms with ≥1 `mcp__thalamus__*` call
- 0 hits across all 6 memory-off arms (the surface was removed — correct silence)
- 0 hits in the 2 memory-on arms that never called (correct: nothing surfaced)

Perfect correspondence, no false positives at n=12. lab/014 could claim this
from one hit; it is now a real validity property. The probe is a faithful
**surfacing** detector.

**And `fix-name-convergence` fired 0/12** — including in all four arms where
the memo demonstrably reached context. Surfacing is now well-measured; *use* is
still not evidenced anywhere. That gap is the whole remaining question.

## Finding 4 (defect): `turn_capped` was marking completed runs as censored

`record["turn_capped"] = agent.num_turns > max_turns` is wrong, and opus
exposed it. Measured shapes:

| model | num_turns | max_turns | is_error | result |
|---|---|---|---|---|
| sonnet (capped) | 41 | 40 | **True** | *empty* |
| opus | 46–53 | 40 | **False** | a real closing summary |

Opus reports 46–53 turns against `--max-turns 40` while terminating
*normally* — the reported turn count and the cap are not on the same scale, so
the naive comparison flagged three concluded opus runs as censored. The genuine
cap signature is the one every truly capped run carries: errored, with an empty
`result` because the model never got to conclude.

Fixed to `num_turns >= max_turns and is_error and not result.strip()`.
Re-derived over the 12 records, this changes **only opus's three**; the corrected
cap rate is sonnet 3/4, fable 0/4, opus 0/4. lab/014's "cap bound in 3/4"
described sonnet and **stands unretracted** — the defect was latent until a
model outran the cap.

## Finding 5: `recall_calls` now lives in the record

Whether an arm reached for memory is the primary outcome of the whole
memory-on/off contrast, and it existed only inside transcripts — this entry had
to re-derive it by hand for twelve arms. `count_recall_calls` now records
`{thalamus, tool_search}` per run, `render_run` prints it, and `tool_search` is
kept separate on purpose: it is what distinguishes "never tried" from "tried
and could not load the schema" (lab/013's failure mode).

## The numbers

| model | task · arm | accepted | cost | turns | capped | recall | probes |
|---|---|---|---|---|---|---|---|
| sonnet | reader · on | yes | $1.16 | 41 | yes | 0 | both miss |
| sonnet | reader · off | yes | $1.29 | 41 | yes | — | both miss |
| sonnet | consult · off | yes | $1.32 | 22 | no | — | both miss |
| sonnet | consult · on | yes | $1.49 | 41 | yes | 1 | surfaced **hit** |
| fable | reader · on | yes | $3.65 | 35 | no | 0 | both miss |
| fable | reader · off | yes | $3.09 | 35 | no | — | both miss |
| fable | consult · off | yes | $2.99 | 29 | no | — | both miss |
| fable | consult · on | yes | $3.07 | 31 | no | 1 | surfaced **hit** |
| opus | reader · on | yes | $2.19 | 49 | no | 1 | surfaced **hit** |
| opus | reader · off | yes | $2.12 | 53 | no | — | both miss |
| opus | consult · off | yes | $2.79 | 39 | no | — | both miss |
| opus | consult · on | yes | $2.71 | 46 | no | 1 | surfaced **hit** |

**Cost, counterintuitively: fable ($2.99–3.65) > opus ($2.12–2.79) > sonnet
($1.16–1.49)** on these tasks. Memory-on vs memory-off cost deltas stay small
and mixed in sign within every model, and with acceptance saturated they carry
no utility signal. Reported, not interpreted.

## What this buys the design

1. **The battery is now unambiguously the blocker.** 12/12 acceptance across
   three capability tiers. Harder tasks or a graded oracle must precede any
   further campaign; running a fourth model would buy nothing.
2. **"Does the agent call recall?" is a real, structured outcome** — it varies
   by task and by model in a legible way, and it is now recorded per run rather
   than reconstructed. That makes it usable as a dependent variable in its own
   right, which matters because acceptance currently cannot be one.
3. **Design implication, stated as hypothesis not finding:** the task that
   invited recall was the under-specified one. If that holds up, memory's
   measurable value lives in tasks where intent is under-determined by the
   prompt — which is an argument about *which tasks the battery should contain*,
   and the most concrete lead this campaign produced.
4. **Still open:** no arm anywhere has yet shown recalled content *changing the
   work* (`fix-name-convergence` 0/12). Surfacing is solved; use is unmeasured.
