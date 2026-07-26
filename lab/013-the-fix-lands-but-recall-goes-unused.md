# 013 — The scoping fix validated live; neither memory-on arm called recall anyway; a third bug found under questioning

**Date:** 2026-07-26 · **Component:** eval loop layer 2 (`thalamus eval run`,
`src/thalamus/eval/arms.py`) · **Status:** campaign complete, 4/4 runs recorded
under the lab/012 fix; the fix is confirmed working, the campaign surfaces two
findings, and a third infra bug — initially misdiagnosed as "root cause not
pinned down" — was fully root-caused and fixed after the operator pushed back
on that hedge. Read all three sections before the table.

## Setup, and a second harness gap found before this could even run

Same two seed tasks as lab/011/012, same design: balanced order, `--full-auto`,
sonnet, 40-turn cap. Two attempts preceded the one reported here:

1. Launched immediately after lab/012's `THALAMUS_PROJECT` fix landed
   (uncommitted, in the working tree). Both campaigns ran to completion but their
   memory-on arms still showed the pre-fix symptom — `project=` still resolved
   to the worktree's own name. Cause: `thalamus eval run` checks out a worktree
   at the **task's pinned ref** (`9f28895`, `a7fc38e` — both from 2026-07-19,
   before the fix existed), and that checkout carries its own frozen copy of
   `session-start.sh`. A runner-side fix landing in the repo does not reach a
   worktree pinned to a pre-fix ref — the fix was real but had nowhere to run.
   Both attempts discarded, not reported below.
2. Fixed by adding `sync_runner_hooks` (`src/thalamus/eval/arms.py:120`, wired
   into `prepare_worktree` at line 117): after checkout, overwrite the
   worktree's `src/thalamus/harness/hooks/` tree with the current repo's.
   `.claude/settings.json` (which hook files are wired up) stays pinned to the
   task's ref — only the *content* of already-wired scripts refreshes, so this
   can't accidentally arm a hook the task's ref never declared. Verified before
   re-running: a fresh worktree's `session-start.sh` already carried the
   `THALAMUS_PROJECT` line straight after checkout. Tests:
   `tests/test_eval_arms.py::test_prepare_worktree_syncs_current_hooks_over_the_pinned_refs`
   (commits an old hook at a pinned ref, changes it uncommitted, asserts the
   worktree gets the new content).

The run reported below is the first one launched after both fixes were in place.

## Finding 1 (confirmed): the scoping fix works

Both memory-on transcripts show the `SessionStart` hook firing with the
correct project this time:

```
'content': ['You have access to the Thalamus graph-memory MCP server. At the
start of this session, call mcp__thalamus__memory_open_threads with
project="thalamus" to see active continuation points...
```

— reader/memory-on session `3f38f7eb`, line 3; consultation/memory-on session
`aa1ab21c`, line 3. `project="thalamus"`, not the worktree's timestamped name.
The fix does what lab/012 designed it to do.

## Finding 2 (new): neither memory-on arm called recall at all

Grepping both memory-on transcripts for any `mcp__thalamus__*` tool use finds
**zero calls** in either session — not "recall returned nothing" (that was
lab/012's bug), but the candidate never asked. 46 tool-use blocks in
`3f38f7eb` (reader), none of them thalamus tools; same in `aa1ab21c`
(consultation). Both sessions went straight to reading/grepping source instead
of following the hook's injected instruction. This is a different failure mode
than lab/012's: the infrastructure is now correct — project resolves right,
the MCP server is reachable (`mcp_removed=False` in both arm applications) —
and the model still didn't use it. Advisory context (docs/07's own framing:
"the context injection stays advisory") does not guarantee the agent acts on
it, and this campaign is the first direct evidence of that gap actually
occurring, not just being possible in principle.

Consequence: **no campaign to date — lab/011, lab/012, or this one — has yet
produced an arm where the model actually recalled real memory content.**
Lab/011 and lab/012 couldn't, because the infrastructure was broken. This one
could have, and the model chose not to try. The probe design (graph-only
tokens) is still only negatively validated — it correctly stays silent when
nothing memory-related happened — never positively validated, because no run
has yet put a real memo in front of a memory-on arm that used it. (Ruled out
as the explanation for this specific gap: the MCP server itself, launched via
`uv run thalamus-mcp` per `.mcp.json`, depends only on the *base* dependency
list — unaffected by Finding 3 below — and both transcripts show all 11
`mcp__thalamus__*` tools genuinely registered as deferred-available. The tools
were real and reachable; the model just never called `ToolSearch` to load
their schemas, and nothing in either transcript explains that mechanism to
it.)

## Finding 3: reported as "not fully pinned down," actually fully explained

First pass at this lab entry called the reader collection failure an
unexplained infra confound and moved on. That was the wrong place to stop —
called out directly: *"they don't have gremlin_python? are the arms somehow
not inheriting the venv and mcp? [...] this is pretty sus, i don't think
'better prompting' is the right move here."* Re-investigated from scratch,
ruling candidates out one at a time in a scratch worktree at the same ref:

1. Leaked `VIRTUAL_ENV`/`UV_RUN_RECURSION_DEPTH` from the operator's own shell
   (`run_agent`'s `env = dict(os.environ)` inherits everything) — stripped
   both, failure persisted. Not it.
2. Ref-specific dependency drift — checked `pyproject.toml`/`uv.lock` at both
   task refs and HEAD: `gremlinpython>=3.7,<3.8` declared identically at all
   three. Not it.
3. `uv run` resolving to the *operator's own* `.venv` instead of the
   worktree's (`uv python find` inside the worktree printed
   `/home/ybx/code/thalamus/.venv/bin/python3`) — real, but a red herring for
   the actual failure: forcing `UV_PROJECT_ENVIRONMENT` to the worktree's own
   `.venv` didn't fix it either.
4. `uv run -v` traced far enough to show the real answer:
   `pytest` is declared under `[project.optional-dependencies] dev`
   (`pyproject.toml:15-20`), not the base `dependencies` list
   (`pyproject.toml:6-13`). `uv run pytest` in a worktree whose `.venv` has
   only ever had the base set auto-synced can't find a `pytest` binary in
   `.venv/bin/` — confirmed absent (`ls .venv/bin/pytest` → not found) — so it
   silently falls through to `$PATH` and runs Debian's unrelated
   `python3-pytest` package (`/usr/bin/pytest`, confirmed via `which -a
   pytest` and the traceback path
   `/usr/lib/python3/dist-packages/_pytest/config/__init__.py`), which
   naturally can't see anything installed in the worktree's isolated venv.
   `uv sync --extra dev` in the same worktree fixed it outright: 180 passed.
   The operator's own checkout only ever "worked" because it was synced with
   `--extra dev` at some past setup step no worktree ever repeats.

**Fixed:** `sync_worktree_env` (`src/thalamus/eval/arms.py`, called from
`prepare_worktree`) runs `uv sync --extra dev` in every worktree right after
checkout, before any session or oracle runs — raising `ArmError` if it fails,
rather than letting a broken sync surface three steps later as a mysterious
test failure. Verified live end-to-end: a fresh `prepare_worktree` call at
the reader task's ref now leaves `.venv/bin/pytest` present and `uv run
pytest -q` at 180 passed. Unit-tested with a mocked subprocess
(`tests/test_eval_arms.py::test_sync_worktree_env_installs_the_dev_extra`,
`::test_sync_worktree_env_raises_on_failure`); the three existing tests that
call `prepare_worktree`/`run_arm` against the bare-fixture repo (no real
`pyproject.toml`) now stub `sync_worktree_env` to a no-op, since a live `uv
sync` isn't something the fast unit suite should be doing.

This bug predates lab/013 — it would have hit *any* prior campaign's
candidate the moment it or the acceptance oracle ran `uv run pytest`, memory-on
or memory-off alike, indistinguishable from a genuine regression. lab/011 and
lab/012's accepted verdicts happened not to trip it (apparently coincidental,
not because anything protected against it); the reader pair here is the first
confirmed case, and the fix is now unconditional for every future run.

## The numbers

| task · arm | accepted | cost | wall | turns | probes |
|---|---|---|---|---|---|
| reader · memory-on | **NO*** | $1.27 | 216s | 41 (capped) | both miss |
| reader · memory-off | **NO*** | $1.36 | 256s | 41 (capped) | both miss |
| consultation · memory-off | yes | $1.17 | 177s | 29 | memo-surfaced miss, fix-name-convergence **hit** |
| consultation · memory-on | yes | $1.57 | 245s | 41 (capped) | both miss |

\* **Infra-confounded, not a fix-quality signal — and fully root-caused, below.**
Both reader arms failed `uv run pytest -q` identically — `ModuleNotFoundError:
No module named 'gremlin_python'`, "22 errors during collection" — while each
arm's direct behavioral oracle (`uv run python -c ...`) **passed** in both.
Reported first-pass as "root cause not fully pinned down"; that was wrong to
settle for, and the operator said so ("this is pretty sus, I don't think
'better prompting' is the right move here") — see "Finding 3" below for the
actual chain, now fixed. Because it hit both arms identically, it didn't bias
the memory-on/off contrast, only reader's acceptance column. Consultation's
pair ran clean (both `uv run pytest -q` passed 180/180) and is the trustworthy
half of this specific campaign.

**The one probe hit:** `fix-name-convergence` on consultation/memory-off —
the candidate, with no memory access, independently wrote a helper named
`_scope_holds_memory`, matching the memorized fix's name exactly. Read as the
task's own rubric warns: "a candidate could coin the same natural name" —
suggestive of nothing on its own, and expected precisely because memory-off
had no memo to converge *from*.

## What this buys the design

1. **Three fixes are now validated, not just tested:** `THALAMUS_PROJECT`
   scoping (lab/012), `sync_runner_hooks` (this entry), and `sync_worktree_env`
   (this entry, Finding 3). Every worktree now gets a working recall path *and*
   a working test suite before anything runs in it — neither was true for any
   campaign before today.
2. **Finding 2 (recall available but unused) is not explained by Finding 3.**
   Checked directly, not assumed: the MCP server's own dependencies are all in
   the base list, unaffected by the missing `dev` extra, and both transcripts
   show the tools genuinely registered. The two findings are independent —
   fixing one doesn't touch the other.
3. **Finding 2's fix is still open, and "better prompting" is the wrong frame
   for it too** — the same objection that was right about Finding 3 applies
   here on reflection. The one concrete, mechanical gap actually observed: an
   earlier (lab/012) memory-on session called `ToolSearch` before calling a
   deferred `mcp__thalamus__*` tool and it worked; both of this campaign's
   memory-on sessions never called `ToolSearch` at all, and neither transcript
   contains any explanation of that mechanism — `SessionStart`'s injected text
   says "call mcp__thalamus__memory_open_threads" as if it's directly
   callable, never mentioning the deferred-tool discovery step. That's a
   testable, fixable claim about the injected instruction being factually
   incomplete about the calling convention — not "try harder" — and is the
   next thing to try before concluding anything about whether recall itself is
   useful. **Applied 2026-07-26** (same day, after this entry's first draft):
   `claude-code/session-start.sh`'s injected text now names one `ToolSearch
   select:mcp__thalamus__memory_open_threads,mcp__thalamus__memory_recall_by_project`
   ahead of the call instructions, conditionally phrased ("may be deferred")
   because whether they are is a per-session harness fact the hook can't
   observe; the Cursor variant deliberately doesn't carry it. Both texts are
   now contract-tested (`tests/test_claude_code_hooks.py` — the first test
   coverage the Claude Code hooks have had — and an added assertion in
   `tests/test_cursor_hooks.py`). Its *effect* is unmeasured: that is what the
   fourth campaign in item 5 tests.
4. **Runner hardening, still open (carried from lab/012):** collection/sync
   failures should be caught and reported distinctly from a genuine test
   failure — right now both would render identically as "pytest FAIL" in the
   record, burying an infra fault inside what looks like a candidate defect.
   Same category as `auth_failed` deserving its own stamp.
5. **A fourth campaign, run under all three fixes, is the first one whose
   reader numbers (not just consultation's) can be trusted** — and whether
   Finding 2 recurs under a corrected `SessionStart` instruction is the
   question it should answer.
