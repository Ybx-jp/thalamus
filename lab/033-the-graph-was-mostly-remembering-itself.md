# 033 — 69% of the graph was memory about the act of remembering

**Date:** 2026-07-29 · **Component:** harness distillation (`harness/extraction.py`, the hook suite) · **Status:** fixed + purged. Recalibrates every per-Session count taken before this date.

## What broke

`thalamus extract` distills a session by shelling out to a headless `claude -p`
in a throwaway `/tmp/thalamus-extract-*` cwd. That subprocess is a **full session
to its own harness**: Claude Code gives it a session id, writes its transcript
under `~/.claude/projects/-tmp-thalamus-extract-*/`, and fires SessionEnd — where
the hook suite, installed at *user* scope since `thalamus init`, was armed and
waiting. So distillation distilled itself, and the recursion had no floor: the
self-distillation spawned another headless run, which distilled in turn.

The graph on 2026-07-29, before the purge:

| | count |
|---|---|
| Session vertices | 445 |
| …whose cwd was an extraction sandbox | **307 (69%)** |
| Claims held only by those sessions | 143 |
| Threads spawned by them, all `open` | 54 |
| sandbox project dirs in `~/.claude/projects/` | 696 |

The content is the tell. A sandbox's prompt is the digest of a *real* session, so
the model wrote a summary of that session's work — a second-hand paraphrase,
attributed to a session that was never lived, evidenced by a transcript of a
distillation. Repeated `--force` re-extraction of one session minted a fresh
paraphrase every time: 16 sandbox claims mentioning `scope-resolution` against
one real one.

This was not inert. Retrieval traces recorded 37 `RETURNS` edges onto sandbox
nodes, most stamped `used: true` — `memory_open_threads` served nine junk threads
in one call — and a consultation Exchange served four sandbox Sessions into the
eval-methodology expert's brief.

## Why it went unnoticed

Partial failure looked like no failure. The hook computes the project dir with
`tr '/' '-'`, but Claude Code also rewrites `_` → `-`, so any sandbox whose random
suffix contained an underscore distilled to `Unknown project dir(s)` in
`~/.thalamus/logs/` and vanished. Roughly half the runs failed loudly enough to
look like the whole story, and the sandbox transcript's own cleanup (the temp dir
is gone before the detached extract runs) reinforced it.

## The fix — three refusals, because one is not enough

The live loop and a retroactive sweep see different evidence: a transcript on
disk carries no environment.

1. **The subprocess runs marked.** `agents.sandbox_env()` sets `THALAMUS_SANDBOX`;
   `thalamus_sandbox_guard` in both `resolve-scope.sh` mirrors exits every hook
   that sees it. Uniform across the suite, so a new hook inherits the rule.
2. **The reader refuses by name.** `transcripts.discover()` withholds project dirs
   carrying `agents.SANDBOX_TMP_PREFIX`, so `thalamus bootstrap` never lists one
   and an explicit `extract -- <sandbox-dir>` is an unknown project.
3. **Extraction re-checks the cwd** each transcript recorded, for a sandbox
   transcript reached any other way.

Verified live: a real `run_extraction` call now completes with no session-end log,
no ledger row, and no new Session vertex.

## The purge

Dropped 307 Sessions, their 307 sandbox Sources, 143 exclusively-held Claims, 54
Threads, and 44 Artifacts the drop stranded. One claim was **kept**: it was also
`CONTAINS`ed by a real session, which is content-addressed convergence working as
designed — only the sandbox's edge went. `thalamus contract check` passes on
5,585 vertices / 13,710 edges; a pre-purge snapshot is on the graph server as
`pre-sandbox-purge-20260729.kryo`.

## What it costs elsewhere

Any per-Session figure computed before this date counted sandboxes: session
totals, claims-per-session, and the `RETURNS`-derived used-rates for the 37 edges
that landed on sandbox nodes. lab/032's attribution numbers are unaffected in
kind — the swap control it rests on is a within-trace permutation — but its
absolute denominators came from the polluted graph.

**Ends in:** fix.
