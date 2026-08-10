# 053 — The night the corpus doubled

**Status: measurements + two fixes.** The follow-through on
[052](052-the-passage-the-note-came-from.md): co-indexing shipped, and the corpus it
indexes turned out to be mostly abstracts. Re-ingesting the abstracts as full text moved
every count in the graph on one night, which is the discontinuity this entry exists to
date.

## What broke

Nothing broke at 2am. What broke was earlier and had been invisible for weeks: **the
`literature` scope was largely built from arXiv `/abs/` pages.** The ingestion guidance
had advised `/abs/` over `/html/`, PDFs are refused by design, and a `/abs/` fetch
succeeds loudly — it returns a real document, extracts real claims, and reports a clean
write. Nothing anywhere said "these claims are abstract-level."

Two defects compounded it, both fixed earlier the same session: the PDF refusal message
recommended the abstract page, and a document over the 24,000-char digest budget was
silently truncated to its opening. A corpus can be built entirely out of successful
operations and still be wrong.

## The shape of the correction

74 `/abs/`-derived Sources with a post-2312 arXiv id (the HTML era) were re-fetched as
`/html/` and re-extracted at full length, each preserving its original scope and feed.
**67 of the 74 landed** — 36 in batch 1, 30 in the batch-2 retry, and the last once the
entity fix below was in place. The 7 that did not are the 404s in Wall 2.

| | before | after batch 1 | after batch 2 |
|---|---|---|---|
| vertices | 13,005 | 16,849 | 20,503 |
| edges | 39,808 | 54,222 | 65,827 |
| Source | 398 | 431 | 464 |
| Claim | 4,438 | 6,091 | 7,445 |
| Chunk | 3,292 | 4,925 | 6,664 |
| Entity | 874 | 1,317 | 1,704 |
| `literature` claims | 1,250 | 2,798 | 3,745 |

`literature` claims **tripled off 67 papers** — already more than doubled off the first
36. That ratio *is* the measurement: what a full paper says beyond its own abstract is
several times over what the abstract said, and none of it was reachable before.

The Claim column is a whole-graph census, so it is not all re-ingest: `literature` gained
2,495 and `eval-methodology` 401, while `main` and `teacher` drifted +111 between the two
readings from ordinary session distillation running alongside the batch.

## Wall 1 — the batch died at the usage window, not at the papers

Batch 1 ran 36 papers cleanly and then failed 30 consecutive times with
`claude -p --model sonnet exited 1` and an **empty stderr**. Not paper-specific: a hard
cutoff at 05:15, which is the 5-hour subscription window closing mid-run. The window
reset at 07:50 and the same 30 papers ran fine.

The lesson is about the failure's shape rather than its cause. A resource exhaustion
arrives through the subprocess boundary as an ordinary non-zero exit with nothing on
stderr, so it is indistinguishable at the call site from "this document could not be
extracted." The batch script's skip-rather-than-retry policy was right — it kept going
and lost nothing recoverable — but the log needed reading by cause, not by count. **38
failures were three unrelated things**, and treating them as one number would have sent
30 re-runnable papers to the hand-feed pile.

Batch length should be sized against the window, or the runner should recognise the
signature and pause rather than burn through the queue marking everything failed.

## Fix — one stray name should not cost seventeen passes

Two documents failed conformance on a real defect, and it is the one worth keeping:

```
Claim references undeclared entity: 'Spearman's rank correlation'
Orphan entity: 'SWE-RAG+GPT-3.5' — no claim is about it
```

Extraction emits `claims` and `entities` as two independent lists and does not keep them
in step. Both directions violate `check_knowledge`, and **the contract judges a batch
whole** — so a 17-pass document was rejected in full over a single edge, discarding ~$2
of extraction and every claim in the paper.

The fix does not loosen the contract; it makes the producer conform.
`reconcile_entity_references` drops the unresolvable reference from the claim that made
it, then drops any entity left unreachable. Both operations **narrow**. Nothing is
invented — no placeholder description, no synthesised entity — which is the property
that keeps it on the safe side of [docs/05](../docs/05-trust-model.md): the write path
may discard what it cannot verify, and never manufacture what the model did not assert.
Backfilling a *known* entity from the graph stays as it was, because that needs no model
judgement; an unknown name can only be closed by inventing a description, so it loses its
edge instead.

A claim stripped to zero entities survives. `about` is a retrieval affordance, not a
claim's identity, and dropping the claim would discard verified content to tidy an index.
`prune_orphan_artifacts` had already made this trade for sessions.

Narrowing is **reported**, never silent — `DigestReport` carries the dropped names and
the run prints them. That is the same defect this session opened with, and the reason it
is worth stating twice: a write path that quietly discards is how the `/abs/` corpus was
built in the first place.

Re-run under the fix, the `Spearman's rank correlation` document lands whole: **63 claims
and 93 chunks for $2.15**, against the zero it had produced twice. One dangling name was
costing the largest single paper in the queue.

## Wall 2 — 45 papers cannot be reached this way at all

`/abs/`-only Sources that no full-text ingest replaced:

- **38 pre-2312** — arXiv never rendered HTML for them. No fetch fixes this; hand-feeding
  a PDF is the only route.
- **7 post-2312 that 404 anyway** — an HTML id is not a guarantee of an HTML rendering,
  so the "≥ 2312 means full text exists" filter is a heuristic and not a rule.

The stuck 38 are the *older* end of the corpus, which is to say the foundational end:
*Doubly Robust Policy Evaluation*, *Understanding Black-box Predictions via Influence
Functions*, *Unbiased Learning-to-Rank with Biased Feedback*, *Deep Knowledge Tracing*,
*Design and Analysis of Switchback Experiments*. The off-policy-evaluation and
experiment-design spine of `eval-methodology` is held at abstract depth while the recent
agent-memory literature is held in full.

**That is a bias with a direction, and it is the opposite of the one to want.** Anything
that reads relative claim counts as evidence of where the literature is dense will read
this artifact of arXiv's rendering history instead. Depth in this corpus tracks
publication date, not importance.

## The discontinuity, stated so it is not rediscovered

Anything comparing retrieval or eval numbers across **2026-08-10** is comparing two
different corpora. Three things moved the same night:

1. `literature` claim count tripled, and Chunk vertices went from 0 to ~6,700.
2. `RANKER_VERSION` moved `1` → `2` when chunks joined the first-pass pool.
3. Entity count rose ~50%, changing the shared-entity topology every 2-hop traversal
   walks.

[038](038-the-corpus-that-moved-under-its-own-numbers.md) is the standing precedent, and
the mitigation is the same: the comparison is across corpora unless it is run against a
pinned snapshot.

One inhomogeneity inside the run itself: the entity-reconciliation fix landed mid-batch,
so papers ingested before ~10:05 ran under reject-whole-document and after under
narrow-and-report. Only ever converts a total loss to a near-complete one, but the run is
not uniform.

## Re-ingest does not replace, it accumulates

`SUPERSEDES` keys on matching origin, and `/html/…` ≠ `/abs/…`, so **each re-ingested
paper now has two Sources** — the abstract-derived one and the full-text one. Both
fetches really happened and the abstract claims are not false, so this is defensible;
identical claim descriptions converge by content hash, near-identical ones do not.

Left as-is deliberately rather than resolved with an ad-hoc write path at 2am. It is a
real question — whether a richer re-fetch of the same document should supersede its
predecessor across a URL change — and it wants the ticketed channel, not a script.

## Ends in

**measurements + fixes.** The corpus co-indexing was built for now actually contains the
documents it claims to. What remains is a dated discontinuity, 45 papers held at abstract
depth with a publication-date bias that runs against importance, and an open question
about whether a second fetch of the same paper should supersede the first.
