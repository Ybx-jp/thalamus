# 035 — The battery had been unrunnable for a day, and validation said OK

**Date:** 2026-07-30 · **Component:** eval layer 2 (`eval/tasks.py`, `config/tasks/*.yaml`) · **Status:** fixed. Found by trying to run an arm, not by any check.

## What broke

The first `ceiling` arm died before its session started:

```
git rev-parse 1fc6aef failed: fatal: ambiguous argument '1fc6aef':
unknown revision or path not in the working tree.
```

Every one of the six refs across all three battery tasks — three `source.ref`, three
`source.fix_ref` — named an object that no longer existed. The counterfactual battery
had been unrunnable since 2026-07-29 and nothing had said so.

## Why

A `git-filter-repo` pass that day scrubbed a licence phrase from 41 commit messages,
which rewrites every commit from the first changed one forward. 128 commits got new
SHAs. The task YAMLs pin their worktree ref and their oracle's positive anchor by
short SHA, and both died.

The rewrite was a deliberate, correct operation. What made it a silent failure is that
nothing downstream of it was checked against it.

## The wall, and it is a validator wall

`thalamus eval tasks` reported **"Battery OK — every task carries its oracle before any
arm runs"** for the whole period. That sentence was true and useless. It verified that
each task *carried* an oracle — acceptance commands, probes, mutants, rungs — and never
that the oracle could be *reached*. A ref is the one part of a task that points outside
the file, and it was the one part validation did not follow.

The failure could therefore only surface at worktree-checkout time, inside a paid
campaign, which is the last place anyone wants to learn it. This is the same shape as
the latent configuration errors docs/07 is built around: set at one time, exercised
much later, symptom far from cause.

## The fix

`.git/filter-repo/commit-map` survives the rewrite and maps old SHA to new. All six
remapped, each verified to resolve and to carry the subject its task describes —
`4432703` → `71ae0df` is still "lab/016: replication kills the hypothesis; SessionFault
matches the class", which is exactly the fix that task replays.

Old SHAs are kept beside the new ones in each YAML. The content of every commit is
unchanged, so what the task files' own git history attests — the pre-registration — is
intact, and the annotation keeps the chain checkable rather than asking a reader to
trust the swap.

`load_battery` now checks ref resolvability, reported as an issue rather than raised:
a dead ref is a repairable provenance fault, and a validator that refused to load the
battery would make the repair harder than the break. Scoped to the real battery, since
a task loaded from a caller's directory makes no claim about this repository's history.

## What it cost, and what it says about the corpus

Nothing was lost — no campaign ran against a dead ref, because a dead ref cannot run.
But the window is worth naming: between the rewrite and this fix, any campaign would
have failed at arm 1, and the last campaign before it (lab/023) is the most recent
layer-2 evidence in the project.

Before spending the ceiling campaign's budget, the ladder was re-validated against the
remapped refs: negative anchor L1, positive anchor L5, both as pre-registered. The
oracle survived the rewrite. Had it not, every arm would have scored the floor and the
campaign would have measured the repair rather than the candidate.

**Ends in:** fix.
