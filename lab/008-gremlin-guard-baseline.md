# 008 — Gremlin guard baseline: the archive convicted the guard, not the queries

**Date:** 2026-07-17 · **Component:** gremlin fluency layer (guard hook, taps, recipe store) · **Status:** guard amended, instrumentation live, prospective numbers pending

## Why measured

The fluency layer (gremlin-python skill, RECIPES.md, terminal-step guard,
memory_query dialect guard) shipped on an operator observation: a session's
ad-hoc gremlin-python queries never invoked the iterator, and lazy traversals
fail *silently*. The eval-methodology consultation (exchange
`scope:main:exchange:918ddb8ddf094a29`) ordered the measurements: block counts
are activity, not effectiveness — the metrics are rescue rate,
doomed-execution rate against a pre-ship baseline, and a false-positive audit,
with pre-ship retained transcripts as a free control arm.

## The retrospective (pre-ship arm)

Scanned every retained transcript in the archive for inline Bash commands
matching the guard's gremlin markers, deduplicated across snapshots, cut at
the ship commit (2026-07-17):

- **48** pre-ship inline gremlin commands.
- **8** lacked a terminal-step token — the guard v1 would have blocked them.
- Manual classification of all 8: **3** text-manipulation commands (sed /
  `re.sub` / file-rewrite heredocs that merely *mention* marker strings while
  refactoring code), **5** house-wrapper calls (`recall(...)`,
  `run_query(...)`) that iterate internally.
- **Genuinely doomed in the archive: 0. False positives under guard v1: 8/8.**

The operator-observed doomed queries are not refuted — they sit in sessions
not yet distilled into the archive (the tap lists them as pending), outside
this scan's reach. But the scan's verdict on the *guard* is unambiguous: as
shipped, its first eight historical firings would all have been wrong, and the
consultation named exactly this failure mode — false positives teach agents to
route around a guard and silently destroy its rescue metric.

## Action taken

Guard v2 treats house wrappers (`recall(`, `run_query(`) and text-manipulation
markers (`re.sub(`, `read_text(`, `write_text(`, leading `sed`) as
satisfaction, verified against the three archive false-positive classes plus a
genuinely doomed command (still blocks). This is the false-positive audit run
*before* the guard's first real firing rather than after.

## Instrumentation now live (prospective arm)

- Guard events: every gremlin-marker command logs block/pass to
  `~/.thalamus/guards/` — rescue rate and friction read from there.
- `bash_gremlin` trace tap: executed ad-hoc gremlin lands in the same monthly
  JSONL as memory tools; `eval sync` prices it like any recall (stdout chars =
  injected_chars; attribution unchanged). memory_query itself was found
  **absent from `RETRIEVAL_TOOLS`** — recorded by the tap but never landed as
  Trace nodes, contradicting query.py's own pricing claim. Fixed; rejections
  are their own event class, not "legacy".
- `thalamus eval gremlin`: rescue rate, rejection classes (dialect / mutation /
  server-failed), recipe-derived vs from-scratch by traversal-shape
  fingerprint, first-shot success per arm.
- `thalamus eval recipes`: read-only smoke run of every stored recipe —
  rolling freshness instead of a one-shot "Validated" date; a recipe carrying
  a mutating step fails lexically before execution.

## On record

- First honest report: 0 blocks, 9 memory_query calls (7 data, 1 empty,
  1 server-failed — the lab/006 arrow interpolation), all pre-store queries
  tagged from-scratch. The interrupted-time-series comparison (doomed rate
  pre vs post) starts accumulating now; the bundle caveat stands — skill,
  recipes, and guards shipped together, so the ITS grades the bundle, and
  component attribution needs an ablation arm (skill-on/guard-off) if the
  bundle number ever needs decomposing.
- Residual: script files (`python lab/x.py`) are invisible to both guard and
  tap — the marker heuristic reads command text only. Named, not hidden.
