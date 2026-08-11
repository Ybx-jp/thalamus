# 053 — The night the corpus tripled

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

`_article_heads` looks for prior heads by **exact `origin` string within a scope**, and
`/html/…` ≠ `/abs/…`, so no head is found and no edge is written: **all 67 re-ingested
papers now hold two Sources**, the abstract-derived one and the full-text one. Both
fetches really happened and the abstract claims are not false, so this is defensible.

The hedge that identical descriptions would converge and near-identical ones would not
is now measured, and it lands almost entirely on the second branch. The abstract side of
those 67 pairs is **436 Claims, of which 5 converge** onto the full-text side — **62 of
67 papers share nothing at all**. Convergence is content-addressed on the claim
description, and a claim written from the whole paper is not the string the abstract
produced, even when it says the same thing.

Supersession tracks the address, not the work.

The obvious next sentence — *431 thin claims now compete with the full-text claims at
equal weight, and the thin one can win* — was written here and does not survive the
literature scope. Both tiers in one flat pool is what RAPTOR **chooses**, selecting
across layers by the granularity a question needs
(`scope:literature:claim:b035e16d6aa3af7e`), and our own *Fidelity Before Structure*
isolates fidelity, not granularity, as the load-bearing variable — granularity is 3.7 of
16.3pp (`scope:literature:claim:af0c3da6c8456689`), the paper [051](051-the-representation-we-never-measured.md)
already turns on. Whether the abstract tier hurts retrieval here is **unmeasured**: not
supported, not refuted, and no measurement in scope names it.

What the duplication actually destroyed is the **layer label**. RAPTOR can report which
layer a retrieved node came from because its nodes carry that relation; ours were minted
by a hash that keys on the URL, so nothing distinguishes an abstract-derived claim from a
full-text one. The falsifier — retrieval quality with the abstract-side claims present
versus absent, over one query set — cannot be run today for want of the label, not for
want of a corpus.

The `/abs/`↔`/html/` pairs are the tidy part of a wider surface: **72 arXiv ids hold more
than one Source origin**, 3 of them three or more, and 39 article Sources have non-URL
origins (hand-fed files) that no URL rule reaches at all. The standing thread
`same-paper-multiple-sources-dedup-still-open` has 2606.04329 behind **four** — abstract,
full text, and two section excerpts fed deliberately, which is a *proper part* of the
work and must never supersede the whole. One edge cannot mean both "richer rendering of"
and "excerpt from".

Two findings from the architect scope make the bookkeeping fix less attractive than it
looks. First, **writing `SUPERSEDES` would change retrieval by exactly zero**: the edge
appears nowhere in `reader.py`, and Sources are loaded only to render provenance *after*
candidates are selected, never to rank them. The harm, if any, is at retrieval; the fix
under discussion is bookkeeping. Second, **the lineage key is itself mutable** —
`write_knowledge` hands one property dict to both `Merge.on_create` and `Merge.on_match`,
`origin` included, so a byte-identical re-ingest rewrites the very field `_article_heads`
searches by. There is no `text_digest` on an article Source to detect it with: all 251
carry neither `written_at` nor `text_digest`, because `write_knowledge` never calls
`_text_stamp` (and that helper digests the *title* regardless).

Left as-is deliberately rather than resolved with an ad-hoc write path at 2am, and the
ticketed channel has now reframed it — from a dedup question to a labelling one, on a key
that is not yet stable.

## The duplicate generator was never the URL

Auditing the four papers bought for that consultation turned up the finding the whole
line had been looking past. MMR came in as 10 claims, and **four of them are two
near-duplicate pairs** — from one document, one ingest, two extraction passes, no
re-fetch anywhere near it:

> MMR is asserted to be especially useful for extracting passages from multiple documents
> on the same topic, since news stories in particular contain…
>
> MMR is extremely useful for extraction of passages from multiple documents about the
> same topics, such as news stories that repeat background information…

Measured across the scope at word-level Jaccard ≥ 0.6: **89 near-duplicate pairs sitting
inside a single Source, across 25 of 199 sources — 13%.** The worst holds 7 pairs among
16 claims.

[06](../docs/06-ingestion.md) already records the mechanism as a deliberate choice —
claims are *retained, never merged* across passes, and entities dedup on exact name only.
That two passes over adjacent text would restate one point twice is the obvious
consequence, and is an inference here rather than a traced one; what is measured is the
89 pairs.

This reverses the direction of the whole investigation. The `/abs/`↔`/html/` duplication
is larger in volume (431 claims) but it was a **one-time artifact of one migration**. The
extractor's is **structural and recurs on every multi-pass ingest**, which is every
ingest of a real paper. A dedup keyed on document identity would not have touched it: both
claims in every one of those 89 pairs already share a Source, an origin, and a content
hash.

The paper about eliminating redundancy was ingested redundantly, and it took reading its
own claims to notice.

The same nondeterminism has a second edge worth stating, found re-feeding Broder's §2–§3
to recover two sentences the full-text pass had lost. **The dry run and the write are two
separate extractions, and they do not produce the same claims.** The dry run returned both
target sentences; the write returned the containment definition and dropped the caveat
that containment estimation is error-prone for a very short document inside a much larger
one — which is precisely the abstract-inside-full-text case it was fetched for.

[06](../docs/06-ingestion.md)'s dry-run rule is sound for what it claims: it catches a
mis-resolved *reference*, and the title is stable across passes. It is not a preview of
the content, and reading it as one is a mistake this entry made. Re-running to fish for
the missing claim was declined on the spot — the same bytes re-extracted would land under
the same content hash and simply add another near-duplicate to the pile above.

## Ends in

**measurements + fixes.** The corpus co-indexing was built for now actually contains the
documents it claims to. What remains is a dated discontinuity, 45 papers held at abstract
depth with a publication-date bias that runs against importance, and an open question
about whether a second fetch of the same paper should supersede the first — reframed by
the literature scope from a dedup question into a **labelling** one, since the harm the
duplication was assumed to cause is unmeasured and cannot be measured while the two tiers
are indistinguishable.
