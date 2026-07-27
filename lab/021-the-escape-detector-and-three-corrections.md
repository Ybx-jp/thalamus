# 021 — The escape detector, and three corrections from the eval-methodology scope

**Date:** 2026-07-27 · **Component:** eval loop layer 2 (`thalamus eval run`) ·
**Status:** detector built and validated against lab/020's own arms — it
reproduces the leak found by hand and finds one more; three methodology
corrections filed, two of them changing numbers already published.

## What was attempted

A review of lab/018–020 from the `eval-methodology` pin rather than from `main`.
The campaigns are sound and the pre-registration discipline held throughout; what
follows is what a scope whose whole domain is measurement validity found when it
read them.

## Correction 1: the answer-key leak is now measured, and it was undercounted

lab/020 caught two memory-off arms reading the operator's live task file by
absolute path, and named confinement as the first thing that must happen before
the next gated campaign. Confinement is still unbuilt. **Detection is cheap and
was not**, so it is built here: `detect_worktree_escape` reads each arm's own
transcript for tool inputs naming the operator's checkout, and stamps `escapes`
and `contaminated` on the record.

The discipline is the one the infra classifier already follows (docs/11 §2a,
arXiv 2111.03382, 2605.05564): **flag, never exclude.** The rung stands exactly
as measured.

**The validation found a defect in the first version.** Run against lab/020's 27
arm-runner-session records, the first cut reproduced both hand-found arms
(rungs 3 and 5) with no false positives — and filed a third under the weaker
`operator_repo` class. That arm had run the live `src/thalamus/eval/arms.py`,
which at HEAD already carries the fix the task asks the candidate to write. A
fixed directory list cannot see that, because **which files give the answer away
is a property of the task**. `fix_touched_paths` now derives the set from
`source.ref..fix_ref`, and the arm reclassifies to `answer_key`.

Re-derived over lab/020: **3 of 24 valid arms were contaminated, not 2.** The
correction does not move the pre-registered result — the newly flagged arm scored
rung 1, so the intention-to-treat comparison (3/12 vs 2/12) is untouched, and the
exploratory leak-excluded number moves from 10% to 11%. It moves the *rate*,
which is the thing the next campaign has to budget against.

`contaminated` is deliberately **not** `attributable`. An infra fault means the
verdict is not about the candidate at all; contamination means it is about the
candidate but not about an *unaided* one. The first invalidates a measurement,
the second re-labels it.

## Correction 2: `mean rung` has no measurement-scale warrant

lab/020 reports mean rung 2.25 vs 2.33 and lab/019 computes power from a pooled
sd of 1.63 rungs. Both treat an ordinal ladder as interval-scaled — they assert
that L1→L2 is the same distance as L4→L5. docs/04 already refuses that assumption
**for the score**, citing the cardinality bias a weighted sum imports (arXiv
2601.03525); the analysis layer then reimports it. Same shape as lab/017's own
generalization: an instrument assembled from parts built for another purpose
inherits their assumptions silently.

It is not academic on this data:

| endpoint | memory-on | memory-off | direction |
|---|---|---|---|
| share rung ≥ 4 (**pre-registered primary**) | 3/12 | 2/12 | memory-on |
| mean rung (reported secondary) | 2.25 | 2.33 | **memory-off** |
| rank sum (Mann-Whitney) | 147.0 | 153.0 | memory-off |

The published secondary points the opposite way from the campaign's own primary
endpoint. Every one of these is noise at n=12 against 4 rungs of dispersion, and
that is the point: a number with no scale warrant was printed beside the endpoint
that has one, pointing the other way, inviting exactly the misreading the ordinal
design was chosen to prevent. The remedy is to **report the rung distribution and
the pre-registered threshold, and drop the mean** — not to swap in a rank test,
which agrees with the mean here anyway.

lab/019's power arithmetic inherits the same defect and is the more expensive
one, since it is what a ~43-arms/side budget decision rests on.

## Correction 3: the worktree runs the MCP server from pinned source

`.mcp.json` is `uv run thalamus-mcp` with cwd set to the worktree, so **the memory
surface an arm gets is whatever the memory system was at the task's ref.**

For `reader-case-insensitive-recall` the ref `9f28895` predates `8b70330`, the
commit that made keyword matching case-insensitive. A memory-on arm on that task
calls `memory_recall` through the very bug it is being asked to fix: distinctive
capitalized terms — the query shape the `recall-strategy` discipline
prescribes — silently return nothing.

lab/018's follow-up verified harness fidelity and concluded the worktree-pinning
hazard "did not bite". That is correct for lab/018 and does not cover this path:
it bit nothing there because **zero arms called any thalamus tool**, and the
checks run were settings.json wiring and schema loading, neither of which
exercises the matcher. `memory_open_threads` and `memory_recall_by_project` do no
keyword matching and are unaffected, which is why the one successful recall in
lab/014 worked.

Two reasons it matters more than a stale dependency normally would:

1. **The bias is asymmetric and runs against memory-on** — toward making the
   project's headline claim look false. A confound that flatters a null result is
   still a confound.
2. **In the general case it is self-referential.** For any task whose fix touches
   the memory read path, the candidate's own edits mutate its own memory tool
   mid-session.

Unfixed here deliberately: the obvious repair — sync the memory system into the
worktree the way `sync_runner_hooks` syncs hooks — is wrong for exactly the task
that exposed it, since `reader.py` *is* the code under test. Naming the hazard and
recording which ref served the memory surface is the honest first step; confining
the arm is the same unbuilt work as Correction 1.

## Correction 4: an expert has no route back to `main`

`memory_query` refuses a pinned session with "Ask through a consultation ticket
instead (`consult_request`)". `consult_request(expert="main")` refuses with "no
expert manifest for `main`". There is no manifest because `main` is the anchor
scope, not a roster expert.

So the refusal points at a door that does not exist, and the consultation
protocol is **one-directional by construction**: `main` consults experts, experts
cannot consult `main` or reach the master plane. An expert's findings reach `main`
only through docs, the lab notebook, and tier-2 claims surfaced by recall — which
is why this entry exists and why its findings are also written to the scope.

Not obviously a defect — the trust model has reasons for the master plane being
main-only (docs/05). The defect is the error message, which prescribes a
route that cannot be taken.

## Grounding

Two consultations with the technical-literature expert, exchanges
`scope:main:exchange:ccbee4b6098b4295` → `scope:main:exchange:1273642c41064119`.

- arXiv 2111.03382, 2605.05564 — classify validity from the run's own record and
  keep it in the denominator; post-hoc exclusion criteria over-fire (371 confirmed
  of 10,316 potentially unrelated). The warrant for flag-never-exclude and for
  leak-exclusion being exploratory rather than primary.
- arXiv 2601.03525 — cardinality bias: weighted-sum analysis of partial success
  disproportionately favors gains on easy items over frontier progress. The held
  objection to `mean rung`, by consequence rather than by name.
- arXiv 2505.15055 (PSN-IRT) — item difficulty and discrimination on a latent
  continuous scale, the mature alternative to averaging ordinal scores; and
  smaller benchmarks with stronger alignment via information-weighted item
  selection, which is the held argument that lab/019's one-good-task strategy
  buys more than replicates would.
- arXiv 2601.19935 (Mem2ActBench) — memory frameworks are inadequate at *applying*
  memory rather than retrieving it. `fix-name-convergence` at 0/24 is a local
  replication of a published field-level negative result, not a harness defect,
  and should be written up as one.

**Named gaps, confirmed by scope census rather than by recall miss** (27
documents, 174 claims in `literature`; cross-checked against `eval-methodology`,
which holds MQuAKE and the oracle-adequacy set): ordinal-as-interval by name,
ITT/per-protocol, ordinal power, gold-context upper-bound arms, survival analysis
for censored trajectories, rediscovery cost. Ranked procurement candidates, all
demand-driven against open threads per docs/06:

1. **Liddell & Kruschke (2018), "Analyzing ordinal data with metric models"** —
   load-bearing *today*: metric models on ordinal data produce inflated and
   sign-reversed effects. Corrections 2's citation by name.
2. **Hernán & Robins (2017), per-protocol analyses / ICH E9(R1) estimands** —
   lab/020 shipped an ITT/per-protocol split citing nothing.
3. **Whitehead (1993), sample size for ordered categorical data** — replaces
   lab/019's "pooled sd in rungs".
4. **CONSORT 2010** — primary-vs-exploratory labelling and exclusion reporting.

Deferred as supply-driven: survival analysis and rediscovery cost, neither
load-bearing in shipped design. **Do not re-ingest IRT** (already held) or the CI
pair (already held, docs/11 §2a) — the first consultation's MQuAKE report was a
scope-locality artifact that would have caused a duplicate, and a title check
inside one scope is what nearly allowed it.
