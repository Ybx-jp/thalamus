---
name: track-open-work
description: File unfinished work as a GitHub issue instead of writing a Thread mid-session — the boundary a session may not cross, what belongs in the tracker versus the graph, and the register an issue body must be written in. Use when work is found that this session will not finish, when a defect is measured but out of scope, and before reaching for any graph write to record it.
argument-hint: "What should be tracked?"
---

# Track Open Work — the tracker is the entrypoint, not the graph

## The boundary

**A session does not write its own memory.** Episodic writes happen *after* a session
ends, by `thalamus extract` over the retained transcript. `thalamus write` and
`thalamus extract --force --write` survive as operator actions **from outside a
session**, and `write-guard.sh` blocks both from inside one.

Reading `thalamus write` as a general permission is the specific mistake this exists
to stop. The rationale prices it: distillation writes the session regardless, so a live
write is a *second* pass over the same session — claims are content-addressed on (kind,
normalized description) so a re-phrased one mints a new node instead of converging, and
**threads get fresh ids, so both stay open in `memory_open_threads`, the surface the
next session reads first.** A synthetic Session written mid-flight corrupts that same
entrypoint, which is why it was rejected as an alternative.

The one write verb a session does hold is **closing** a thread, and only through
approval: `thalamus thread propose` writes a ledger row and nothing to the graph, then
the operator approves. Report the title, a 1–2 sentence description, **and** the
proposal id — all three, every time. The operator approves remotely and cannot read
the ledger to find out what they are approving.

## Where a thing goes

| It is… | Where |
|---|---|
| Work a future session should pick up | **A GitHub issue** — file it |
| Something this session learned or decided | Say it plainly in the final message; distillation writes it once, properly |
| A thread that is now finished | `thalamus thread propose` → operator approves |
| A design decision that is settled | The project's decision log, in the same change |
| A measured finding | The project's findings record, and the graph via `thalamus ingest` if it is literature |

The split is about *audience*. The graph is what an agent recalls; the tracker is what
the operator reads to decide what a session should do next. An open thread is served
into briefs and recall whether or not anyone intends to act on it — which is why 402
open threads against 97 closed became unworkable, and why the tracker exists as
something the operator can see and order.

## Filing

GitHub Issues on `Ybx-jp/thalamus` is the tracker. One command, from anywhere in the
checkout:

```bash
gh issue create --title "<descriptive title>" --body-file /tmp/issue.md \
  --label type:bug --label area:harness
```

- **Write the body to a file first** and pass `--body-file`. A body passed inline
  through `--body` goes through shell quoting, and backticks, `$`, and newlines in a
  multi-paragraph body are exactly what that mangles.
- `gh issue create` fails outright on a label the repo does not carry. If it errors on
  a label, re-run without `--label` and say which labels you would have applied.
- Check `gh issue list --search "<a distinctive term>"` before filing. A duplicate
  issue costs the next session the same triage.

**Labels** — one `type:` and one `area:`:

- `type:bug`, `type:feature`, `type:docs`, `type:chore`
- `area:` one of `substrate`, `harness`, `console`, `eval`, `contract`, `ingestion`

## The register — this is the part that goes wrong

An issue is a technical record read by someone who was not in your session. Write the
**problem, what it affects, and what a reader has to do differently.** Nothing else.

- **No verdict framing.** "the case was unbeaten", "this cuts against the proposal",
  "reads backwards", "ships flagged" — cut every one.
- **No session narrative.** Who proposed what, which argument won, how many rounds it
  took, what you tried first. None of it is actionable.
- **No grading anyone's decisions**, the operator's least of all.
- **Constraints, counter-evidence and known gaps stay in**, stated as facts with their
  numbers. "The write-back is not built, so the measured result is conditional on it"
  belongs in the issue; a paragraph about whose objection that was does not.

**Titles are descriptive, not literary.**

- Good: `Attribution judge tokenizes node terms and the output window differently`
- Bad: `The judge that could not tell defense from refusal`

The good title names the component and the defect, so a reader scanning a list knows
whether it is theirs. The bad one is a story title: it names nothing searchable and
tells the reader only that something was wrong somewhere.

## A defect that can be reproduced is filed with its reproduction

Before you file a `type:bug`, ask which qe harness can reach it:

| The defect shows up… | Reproduction goes in |
|---|---|
| During the documented install sequence — sync, `docker compose up`, `init --check`, `init`, re-init, uninstall — on a box a config can shape (a binary removed, an env var unset, the checkout moved, a wheel installed) | `tests/qe/install/` — a `Check` with `issue=<n>` and no `fixed` |
| By driving a surface directly — a hook script, the CLI, an MCP tool, a console route | `tests/qe/cases/` — a case module |

File both in the same change. The issue then records a defect that is **confirmed**
rather than asserted, and the matrix keeps a live positive control on itself: a run
in which nothing is tagged says only that nothing new broke, never that the instrument
can still see.

**Say so when it does not qualify**, in the issue, rather than filing untagged and
silent. Three shapes genuinely do not:

- Evidence that is one long-lived machine's state. A fresh cell builds the thing
  correctly, so the check passes and reproduces nothing.
- A question that still needs a measurement designed. Undetermined is not known-wrong.
- A gap in coverage. Writing the check *closes* that issue; it does not reproduce it.

**Never tag what you have not watched reproduce.** A tagged check that unexpectedly
passes fails the run (`drive.py` exit 2), which is the mechanism working — but a tag
placed on a guess spends someone else's CI to find that out.

`tests/qe/` is owned by scope `qe` (`contract/ownership.PATH_OWNERSHIP`) and
`role-guard.sh` enforces it. From any other scope, hand the reproduction to a
`qe`-pinned session; do not route around the guard.

When the defect is fixed, the same check gains `fixed=True` and its control and stays
as the regression guard — a red there afterwards means the repair came undone.

## Issue template

Follow this. Drop a section only when it genuinely has no content — do not pad it.

```markdown
## What

The defect or gap, stated as a claim about the system. Name the file, function or
surface. Not "look into X".

## Evidence

How it was measured, with the numbers and the corpus: `999 cases / 8,446 verdicts`,
not "seems biased". If it was not measured, say what was observed and how often.

## Impact

What this affects, and what a reader has to do differently while it stands. Include
any workaround that currently works.

## Already decided

Constraints that are settled and must not be re-litigated, and where that decision is
recorded. This is the section that stops the next session redoing the argument.

## Deliberately not to be done

Approaches ruled out, and the reason each was ruled out. The most expensive thing to
rediscover.

## Open decision

What is still undecided and whose call it is. If it is the operator's, say so — the
issue is then open on the decision, not on the work.
```

## Before you file

Check the graph first — `memory_exchanges(query=...)` for a question an expert has
already settled, `memory_open_threads(topic=...)` for work already tracked. A tracker
entry that duplicates a settled consultation costs the next session the same rounds
over again.
