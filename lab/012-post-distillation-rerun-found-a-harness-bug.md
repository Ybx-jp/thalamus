# 012 — The post-distillation re-run, an OAuth outage, and a session-start scoping bug that voided both

**Date:** 2026-07-20 (first attempt) / 2026-07-26 (completion + fix) · **Component:**
eval loop layer 2 (`thalamus eval run`, `src/thalamus/harness/hooks/*/session-start.sh`) ·
**Status:** campaign complete, 4/4 runs recorded; both headline numbers below are
invalidated by a harness bug, not superseded by it — read the finding before the table.
The bug is fixed (below); no campaign run before the fix should be cited as a
memory-utility result.

## The setup

Same two seed tasks as [lab/011](011-first-counterfactual-campaign.md), re-authored to
the graph-only-token probe rule, run as the pre-registered post-distillation follow-up:
the authoring session (`accfe19d`) had distilled by the time this ran, so — unlike
lab/011 — the memorization stratum's memo genuinely existed in the graph to be found.
Balanced order, `--full-auto`, sonnet, 40-turn cap.

## Incident: an OAuth token expired mid-campaign

Both `thalamus eval run` invocations were launched together. Around the 3-minute mark,
the headless `claude -p` OAuth token expired and could not silently refresh. Effect,
read from `~/.thalamus/counterfactuals/runs.jsonl` and the raw transcripts:

- The **first** arm in each task (`reader-case-insensitive-recall · memory-on`,
  session `a1c88911`; `consultation-empty-brief-refusal · memory-off`, session
  `b109c2fd`) did real work — 33 and 26 turns, $0.91 and $0.95 — and were mid-verification
  when the token died on their closing turn (confirmed from the raw transcript: the last
  assistant turn in `a1c88911` is the string `"Failed to authenticate: OAuth session
  expired and could not be refreshed"`, immediately after a tool result showing all
  three case-sensitivity fixtures passing). The worktree state at that point is real; the
  acceptance oracles run against it are trustworthy. What's missing is only the model's
  own closing summary.
- The **second** arm in each task (`reader · memory-off`, session `eb4b3543`;
  `consultation · memory-on`, session `f1e60bac`) started after the token was already
  dead: 1 turn, $0.00, ~90–130ms — no candidate work happened at all. These two records
  are void and were excluded.

Fix: confirmed headless auth was healthy (`claude -p "say ok"` → `Ok.`), then re-ran
only the two void arms. They landed six days later (2026-07-26) because of an
unrelated session gap, but each worktree is pinned to the task's git ref, so the code
state each arm starts from is identical to its pair-mate's regardless of the calendar
gap — the pairing is still valid on the axis that matters (git ref), just not on
wall-clock proximity the way lab/011's pairs were.

**Process note for the runner:** `thalamus eval run` should treat a mid-session
`is_error` + `Failed to authenticate` result as a hard stop and refuse to record the
downstream arm rather than silently emitting a 1-turn/$0 record indistinguishable at a
glance from a genuine 1-turn success. Filed as a runner hardening item, not fixed here.

## The sharper finding: memory-on never actually got memory

Both real memory-on transcripts (`a1c88911`, `f1ec39df`) made exactly two thalamus
calls each — the `SessionStart` hook's own prescribed pattern — and neither made any
further recall attempt afterward:

```
mcp__thalamus__memory_open_threads   {"project": "reader-case-insensitive-recall--memory-on--20260720T122137Z"}
mcp__thalamus__memory_recall_by_project {"project": "reader-case-insensitive-recall--memory-on--20260720T122137Z"}
→ {"result":"No open threads found."}
→ {"result":"No matching memories found."}
```

(`f1ec39df`, the consultation memory-on re-run, shows the identical pattern with its
own worktree's directory name as `project`.)

Root cause: `src/thalamus/harness/hooks/claude-code/session-start.sh:47` —
`project=$(basename "$cwd")`. In a normal dev session `cwd` is the repo root, so
`basename` yields `thalamus` and matches the project tag every session distills under.
Inside the arm runner, `arms.py` runs the headless session with
`cwd=worktree` (`src/thalamus/eval/arms.py:204`), and the worktree is named
`<task-id>--<arm>--<timestamp>` (`arms.py:304`) — so `basename "$cwd"` is never
`thalamus`, and the session-start recall is scoped to a project that has no sessions
under it. Both `memory_open_threads` and `memory_recall_by_project` correctly report
nothing, because there genuinely is nothing filed under that literal string.

Consequence: neither memory-on arm in this campaign — nor, by the same mechanism,
either memory-on arm in **lab/011's original campaign** — ever received real memory
content. Lab/011 read this as "ambient project memory, not solution memos"; the
transcripts show it was actually a silent no-op. The two campaigns' memory-on arms
differed from memory-off only in: the SessionStart/UserPromptSubmit hooks stayed
installed (two wasted tool calls, plus whatever the `conditioning`/`pin-engaged`
UserPromptSubmit hooks inject) and the live MCP server stayed reachable for ad-hoc
calls the candidate chose not to make. Every acceptance and cost delta measured across
both campaigns to date is a comparison between memory-off and *memory-hook-present-but-
inert*, not between memory-off and memory-on.

## The numbers, reported for completeness, not for a memory-utility claim

| task · arm | accepted | cost | wall | turns | note |
|---|---|---|---|---|---|
| reader · memory-on | yes | $0.91 | 197s | 33 | closing turn lost to OAuth |
| reader · memory-off | **NO** (oracle: capitalized-term recall still returns nothing) | $1.24 | 234s | 41 (capped) | |
| consultation · memory-off | **NO** (2 pytest failures) | $0.95 | 189s | 26 | closing turn lost to OAuth |
| consultation · memory-on | yes | $1.41 | 224s | 37 | clean completion |

Acceptance flipped from lab/011 (memory-off 2/2, memory-on 1/2) to memory-on 2/2,
memory-off 0/2 here. Cost direction, consistent in one direction in lab/011
(memory-on costlier on both tasks), is mixed here (cheaper on reader, costlier on
consultation). Given the root cause above, none of this is evidence about memory
utility — it is noise from a small, cap-influenced, OAuth-interrupted sample where the
manipulated variable (recall content) didn't actually vary between arms.

**Probes:** both `memo-surfaced` and `fix-name-convergence` missed in all four arms.
Expected and correct, not a design failure this time — with the recall pull returning
nothing, there was no memo available to surface or converge on. Unlike lab/011 (every
probe hit everywhere — competence echo), a clean 0/4 here is exactly what the graph-only-
token design predicts *given* the scoping bug; it doesn't yet tell us whether the probes
would fire once memory-on genuinely has the memo in context.

## What this buys the design

1. **Fixed, same day.** `run_agent` (`src/thalamus/eval/arms.py`) now takes a
   `project` argument and sets `THALAMUS_PROJECT` in the subprocess env; `run_arm`
   passes the checkout's own name (`repo.name`, e.g. `thalamus`). Both
   `session-start.sh` variants (`claude-code/`, `cursor/`) prefer
   `THALAMUS_PROJECT` over `basename "$cwd"`/`basename "$workspace_root"`, falling
   back to the old behavior when unset — real (non-worktree) sessions are
   unaffected. Covered by `tests/test_eval_arms.py`
   (`test_run_arm_passes_repos_name_as_project`,
   `test_run_agent_threads_scope_and_project_into_the_subprocess_env`) and
   live-checked against the actual hook script both with and without the
   override. Full suite green (197 passed).
2. **Lab/011's numbers should be read as memory-hook-present-vs-absent, not
   memory-on-vs-off.** No retraction needed — the lab entry's own hedges ("ambient
   surface," "no cross-arm claim beyond this paragraph") already scoped it narrowly
   enough to survive this correction — but the *reason given* for the ambient-only
   result was wrong and is superseded here.
3. **Re-run again now that the scoping fix has landed.** This was the second
   campaign whose memory-on arm was accidentally memory-off in disguise; the actual
   post-distillation test the design has been waiting for still hasn't run under
   working memory access. That re-run is lab/013, not yet run.
4. **Runner hardening, still open:** stamp `auth_failed` (distinct from
   `turn_capped`) on records where `is_error` and the result string starts with
   `Failed to authenticate`, and stop the campaign rather than launching the next
   arm against dead credentials.
