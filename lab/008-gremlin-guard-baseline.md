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

The scan's verdict on the *guard* is unambiguous: as shipped, its first eight
historical firings would all have been wrong, and the consultation named
exactly this failure mode — false positives teach agents to route around a
guard and silently destroy its rescue metric.

## The completed baseline (undistilled sessions included)

The verification consultation (exchange
`scope:main:exchange:8f6ad2d6f4024b2c`) demoted the archive scan to an
FP-calibration instrument (a zero-numerator baseline detects harm, never
benefit) and named extending it over the undistilled sessions as the
highest-value next measurement. Done — scanning the raw session transcripts
directly:

- **50** further inline gremlin commands in undistilled sessions; flagged
  candidates classified by hand: two more false-positive classes (`thalamus.eval`
  helper imports that iterate internally; `grep`/`rg` commands mentioning
  markers inside their search patterns) and one scanner artifact (Python `re`
  without MULTILINE misreads the guard's line-based `^sed` — the live guard
  passes it).
- **Doomed inline commands across both arms: 0/98.**
- **The flagged script-file hit was a scan artifact too.** Session 5f8ad588's
  `prune_migration_orphans.py` showed a "bare"
  `g.V().has_label("Claim").not_(T.both_e())` line — which on reading the
  file is the opening of a *multi-line parenthesized expression* ending in
  `.to_list()`. Line-level grep cannot see statement structure; only AST
  inspection can. The script itself executed correctly (its dry run found
  1,114 migration orphans; the `--write` was blocked by the harness
  permission classifier and the cleanup completed later — live orphan count
  is now 0).
- **Net: no doomed query has been located in any retained or undistilled
  transcript.** The operator's observation stands as real but unlocated
  (plausibly another project's session, or code read outside these
  transcripts). The measured claim is narrow and honest: the inline-Bash
  channel this guard covers has a doomed rate of 0/98, and every scan-flagged
  candidate — inline or file — was a false positive of lexical, line-level
  matching. A statement-level AST check on written `.py` content is the only
  instrument that could measure the file channel; open design item, to be
  grounded before building.

## Action taken

Guard v4 satisfaction branches, each logged per event: `terminal` (real
iterator invocation), `wrapper` (`recall(`, `run_query(`, `from thalamus.eval`
— house code that iterates internally), `textedit` (`re.sub(`, `read_text(`,
`write_text(`, leading `sed`/`grep`/`rg` — code manipulation and search that
merely mention marker strings). Verified against all archive false-positive
classes plus a genuinely doomed command (still blocks). This is the
false-positive audit run *before* the guard's first real firing rather than
after.

## Metric validity fixes from the verification audit

All seven findings of exchange `8f6ad2d6f4024b2c` addressed in code:

1. **Rescue join on intent, not any pass** — guard events now carry the
   command's step fingerprint, the satisfaction branch, and `guard_version`; a
   rescue is a later *terminal-branch* pass sharing the blocked fingerprint;
   friction is the *same* command re-blocked. Wrapper/textedit passes are
   ineligible (they fire constantly and would saturate the metric).
2. **Tap over-inclusion** — bash_gremlin events must carry a
   connection/wrapper call token (`connect(`, `run_query(`…) to count as
   retrieval events; marker-mentioning text edits are filtered read-side (the
   tap stays dumb).
3. **Temporal reuse tagging** — a trace is recipe-derived only if it postdates
   the recipe's Validated date; anything earlier was the recipe's *source*
   (selection-on-success leakage).
4. **Miss ≠ failure** — an empty memory_query result counts as executed in the
   arm stats; emptiness is often the right answer to an existence question.
5. **Smoke deny list unified** — underscore-folded, covering both dialects and
   the writer's entry points by name; still lexical, and `exec()` of store
   content remains a declared hazard (subprocess isolation is the open fix).
6. **FN measurability** — the logged branch makes v4's false-negative exposure
   auditable per class.
7. **Version stamping** — `guard_version` in every event.

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
- Residual: script files stay invisible to both guard and tap, and lexical
  line-level scanning demonstrably cannot classify them (the one flagged file
  was a false positive on AST-level reading). The guard's covered channel is
  measured clean; its benefit case is currently the operator's unlocated
  observation plus the prospective ITS, nothing stronger — say so. The
  candidate instrument for the file channel is a statement-level AST check on
  written `.py` content (a bare traversal expression never consumed), to be
  grounded before building.
- Not implemented, tracked open: reuse weighted by displaced from-scratch
  cost (injected_chars exists to build it), the demand-miss admission signal
  ("consulted the store, found nothing"), within-session paired arm
  comparison, an eviction ledger, subprocess isolation for the smoke run.
