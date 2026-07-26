# 014 — The first clean campaign: recall finally happened, in one arm of two

**Date:** 2026-07-26 · **Component:** eval loop layer 2 (`thalamus eval run`,
`src/thalamus/harness/hooks/claude-code/session-start.sh`) · **Status:**
campaign complete, 4/4 runs recorded, **zero infra faults** — the first
campaign whose numbers are not confounded by the harness. The headline is a
split verdict, not a win: the corrected `SessionStart` instruction was followed
exactly by one memory-on arm and ignored entirely by the other.

## Setup

Same two seed tasks, same design as lab/011–013 (balanced order, `--full-auto`,
sonnet, 40-turn cap), run under all four fixes: `THALAMUS_PROJECT` (lab/012),
`sync_runner_hooks`, `sync_worktree_env` (lab/013), and the `ToolSearch`
instruction fix this entry tests. Headless auth was confirmed healthy first
(`claude -p "say ok"` → `ok`), and the runner would now halt the campaign
itself on a credential death rather than recording void arms.

## Finding 1: the infra fixes hold under a real campaign

`uv run pytest -q` **passed in all four arms**. In lab/013 this same reader
pair failed it identically in both arms (`ModuleNotFoundError: No module named
'gremlin_python'`, 22 collection errors) and cost a day to root-cause.
`sync_worktree_env` is confirmed in production, not just unit-tested. Every
record carries `attributable: true` and `infra_faults: []`.

Honest caveat: precisely *because* the campaign was clean, the new
infra-fault classification never fired against a real fault here. It is
validated by its unit suite and two in-process CLI smokes, not by this
campaign.

## Finding 2 (the headline): the instruction fix works — in one arm of two

The corrected injection reached both memory-on sessions verbatim (confirmed at
line 3 of each transcript, including the
`` ToolSearch with query `select:mcp__thalamus__memory_open_threads,...` ``
sentence). What the two arms did with it diverged completely:

| memory-on arm | ToolSearch | thalamus calls | tool blocks |
|---|---|---|---|
| consultation (`55ae8c78`) | **1** — the prescribed query, verbatim | **1** (`memory_open_threads`) | 41 |
| reader (`e698f245`) | 0 | 0 | 40 |

The consultation arm followed the new instruction *exactly as written*: one
`ToolSearch` with `select:mcp__thalamus__memory_open_threads,mcp__thalamus__memory_recall_by_project`,
then `memory_open_threads(project="thalamus")`, which returned real open
threads (line 18). **This is the first arm in any campaign to actually recall
real memory content** — the milestone lab/013 recorded as never yet reached.

The reader arm, given the identical instruction, went straight to `Bash`×31 and
never called anything. So lab/013's Finding 2 is *half* closed. The mechanical
gap named there was real — naming `ToolSearch` was necessary, and one arm
proves it is sufficient to be followable. It is not sufficient to be
*followed*. n=1 vs n=1; this distinguishes nothing statistically and is
reported as a mechanism observation, not a rate.

## Finding 3: the first positive probe firing, read narrowly

`memo-surfaced` **hit** on consultation/memory-on — the first probe hit in any
campaign that isn't competence echo (lab/011) or absence (lab/012–013). It is
genuine by its own definition: `accfe19d` appears in the `tool_result` of
`memory_open_threads`, i.e. rendered into context by recall, and that UUID
exists nowhere in the worktree at this ref nor in the prompt.

**But read what actually surfaced.** The UUID appeared as the `Opened in:`
provenance line of a *different* thread (`m4-turn-cap-censoring`) — not as the
memorized diagnosis being recalled. The probe detects "the authoring session's
node was rendered into context," which is exactly what happened and exactly
what its `meaning` claims, no more. The memo's *content* did not reach context;
`fix-name-convergence` missed, consistent with that. The probe design is now
positively validated as a **surfacing** detector. Nothing here validates it as
a use signal, and the acceptance column (below) cannot help.

## Finding 4: acceptance had no variance to explain

All four arms were **accepted**. With 4/4 passing, the acceptance oracle
discriminates nothing this campaign — no memory-on/memory-off contrast can be
read from it in either direction. Combined with the turn cap binding in 3/4
arms (only consultation/memory-off finished, at 22 turns), the battery as
currently tuned is measuring "can sonnet solve this in 40 turns" (yes, always)
rather than anything about memory. This is a battery-design finding, not a
memory finding, and it is the main obstacle to the next campaign saying
anything.

## The numbers

| task · arm | accepted | cost | wall | turns | probes | recall calls |
|---|---|---|---|---|---|---|
| reader · memory-on | yes | $1.16 | 199s | 41 (capped) | both miss | **0** |
| reader · memory-off | yes | $1.29 | 277s | 41 (capped) | both miss | n/a |
| consultation · memory-off | yes | $1.32 | 263s | 22 | both miss | n/a |
| consultation · memory-on | yes | $1.49 | 231s | 41 (capped) | memo-surfaced **hit** | **2** |

Cost direction is mixed again (memory-on cheaper on reader, costlier on
consultation) and, with acceptance saturated and n=1 per cell, carries no
signal. Reported for completeness.

## What this buys the design

1. **The harness is finally out of the way.** Four fixes across three campaigns
   (`THALAMUS_PROJECT`, `sync_runner_hooks`, `sync_worktree_env`, the
   `ToolSearch` instruction), and this is the first campaign where no arm's
   result is explained by a runner bug. That is the precondition for every
   number the eval loop will ever produce.
2. **"Advisory context doesn't compel use" is now measured, not assumed** — and
   it survives the instruction being *complete*. lab/013 could not separate
   "the instruction was impossible to follow" from "the model chose not to";
   this campaign separates them, and both effects are real: one arm followed a
   followable instruction, one ignored it. Enforcement stays off the table for
   the reason docs/07 gives, so the design question is what makes recall
   *worth* calling, not what makes it callable.
3. **The battery is the bottleneck now, not the runner.** Acceptance saturated
   at 4/4 with the cap binding in 3/4. Before a fifth campaign, either the
   tasks need to be hard enough to fail sometimes, or acceptance needs a graded
   oracle rather than pass/fail — otherwise a memory effect has nowhere to show
   up. This supersedes "run a fourth campaign" as the next M4 step.
4. **Still open, unchanged:** the turn cap censors 3/4 arms
   (`m4-turn-cap-censoring`), and no campaign has yet produced an arm where
   recalled memory content demonstrably *changed the work* — surfacing is now
   proven, use is not.
