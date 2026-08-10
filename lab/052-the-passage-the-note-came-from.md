# 052 — The passage the note came from

**Status: design, to build.** Continues
[051](051-the-representation-we-never-measured.md), whose coverage endpoint falsified
the hope that a claim's verbatim `citation` already occupies the intermediate
representation — it does not; it is the artifact pole with a provenance anchor. Grounded
through `scope:main:exchange:d0060228a7454be0` (literature, 54 citations), following
`7848872f9deb464c` (38) and `6557ba9dbe024210` (41).

## The design

For **every ingested document, in every expert scope**:

- **Chunk vertices** over the retained source text, fixed width.
- **Chunks join the first-pass retrieval pool**, ranked against claims and summaries.
  This is co-indexing, and it is the configuration the evidence supports.
- **A `citation` → chunk anchor edge**, so a note reaches the passage it came from, and
  a chunk carries **its location in the source** (character offset and ordinal).
- **`ADJACENT_IN_TEXT`** edges in document order, so a retrieved chunk can be expanded
  to its neighbours.
- **`MENTIONS`** edges on shared entities, under a degree bound (below).
- **The full original text stays retained as the floor**, as now.

Claims, citations and extraction are unchanged. Nothing about the episodic corpus
changes.

**The boundary is `ingest` versus `extract`, not one scope versus another.** An earlier
draft of this entry said "literature corpus only", which was the corpus that had been
measured rather than a rule the design needs. Every expert that ingests documents gets
chunks — measured 2026-08-10 across seven scopes, 187 article Sources, 4,309,673 chars,
**3,292 chunk vertices**. Session transcripts get none, because they arrive through
`extract`, which never touches this path. That is where the 2026-07-14 node-explosion
estimate remains correct and binding: transcripts are 98% of the archive.

### One correction to an earlier draft of this entry

A previous version framed co-indexing and citation-anchored traversal as rival arms and
gated the work on a three-arm comparison. That rivalry was an error introduced in the
consultation ticket, not in the design: co-indexing is *how a chunk is found*, and the
anchor edge is *what a chunk is attached to*. They compose. The gate is dropped with it.

## Why co-indexing, specifically

**It is the one configuration measured to recover the gap.** A union store indexing
artifacts alongside verbatim chunks scores 42.5% against 43.9% chunks-alone and 28.0%
artifacts-alone (`scope:literature:claim:00aeb8542b0e3f30`) — ~14.5 of the 15.9pp
recovered, and artifacts are accuracy-*neutral* beside chunks rather than harmful. The
ranking-interference fear that would argue for keeping chunks out of the pool measured
**1.4pp**, which is not clearly distinguishable from noise.

**Expansion alone would not have carried it.** The identical 1-hop expansion applied
over verbatim chunks is a no-op (43.1% vs 43.9%,
`scope:literature:claim:e9cfc1dac2ed55d7`), and expansion's large retrieval-recall gain
(25.8%→71.8%, `scope:literature:claim:f2cb29a74cbb943d`) **did not convert** to answer
quality (`scope:literature:claim:e490d8900938402e`). So adjacency edges are a
**secondary** affordance here, not the mechanism the design rests on — which is the
right weight for them, and not the weight an earlier draft gave them.

**The architecture is on the safe side of the corpus's own account.** Annotating
verbatim text is safe; replacing it, however gently, costs accuracy
(`scope:literature:claim:e7205d68dd06fa17`). Zep is the worked instance, retaining raw
episodes beneath its entity and community tiers
(`scope:literature:claim:ec4af50636456ddb`).

## Fixed width, not "one complete idea"

Semantic segmentation is dropped. An extra full-corpus LLM pass has a measured record of
not paying — GraphRAG's gleaning pass moved accuracy 2.1pp, within noise,
"its measured contribution is negligible" (`scope:literature:claim:39e72cc13213881a`) —
and finer units at *constant fidelity* cost accuracy, with sentence-granularity verbatim
giving up 3.7 of 16.3pp and fidelity, not granularity, load-bearing
(`scope:literature:claim:af0c3da6c8456689`). Zero-overlap controls reproduce the gap
(`scope:literature:claim:abd3a5d4c382f26d`), so overlap is not load-bearing either.

Fixed width at ~1,500 chars with a small overlap, reusing `chunk_text`. If a later
measurement shows boundary policy matters, semantic segmentation is a one-pass re-run
against retained bytes — extraction is disposable by design (docs/10).

## Cost, measured

The 2026-07-14 decision rejected `Chunk` nodes on a ~100× node-explosion estimate. That
estimate is right about the archive — 275.7M chars over 419 documents, ~183,800 chunks
against 9,636 vertices — and does not reach this design, because **the literature corpus
is 2.1% of the archive**: 154 sources, 5,685,696 chars, **~3,790 chunks, 0.4× graph
growth**. The scoping is structural rather than imposed: only literature claims carry a
`citation`, so the anchor edge is papers-only by construction. Measured 2026-08-10.

## Build-time constraints that are not optional

**Tier and provenance.** Co-indexed chunks arrive in recall automatically, which is
ambient injection of third-party text. A chunk is tier 2 and renders like a knowledge
claim — quoted, cited to its Source, informs-never-instructs (docs/05). Agents treat
retrieved memories as ground truth absent provenance checks
(`scope:literature:claim:ba6b62409b3d8b95`), and no provenance-free retrieval-time
filter achieves a non-trivial worst-case certificate against an adaptive adversary
(`scope:literature:claim:b2dc45c539882811`) — the anchor edge is what makes this
retrieval provenance-mediated rather than provenance-free. A chunk is ~1,500 chars of
unfiltered source text against a `citation`'s ~109, so the attacker-controllable budget
per result rises by roughly an order of magnitude. This ties the work to the open
`transcript-mediated-laundering-gap` thread.

**Injection budget.** lab/006 measured 33.8% of injected retrieval tokens judged unused.
Chunks are an order of magnitude larger than claims, so the pool needs a chunk cap and
chunks must compete for slots rather than being appended — otherwise the change is a
token-waste regression wearing a fidelity story. Performance also degrades when relevant
material sits mid-context (`scope:literature:claim:2268d735ff10a67e`) and pruning
irrelevant context improves responses (`scope:literature:claim:6843553dde27884a`).

**`MENTIONS` degree bound.** Chunk count is linear in corpus; shared-entity edges are
quadratic in entity cliques. A common name would connect a large fraction of 3,790
chunks, and uncontrolled connectivity has a measured harm signature — dense connections
incur redundant token overhead and let task-irrelevant noise distract agents
(`scope:literature:claim:9db15d4954c4958f`; conditions differ, multi-agent topology
rather than document graphs). A maximum degree and an entity-specificity floor are
written before the edge is, not after.

## Prior art, labelled

- **Anchor edge (typed node → text chunk): has prior art, asserted not measured.** An
  Applied Knowledge Graph links ClauseVersion nodes to text chunks, prioritizing
  decision-readiness over semantic storage (`scope:literature:claim:2fd0cfa3ca7f01b8`) —
  a practitioner essay with a Cypher sketch and no evaluation. **Not novel.**
- **Co-indexing:** measured, and the measurement is someone else's
  (`scope:literature:claim:00aeb8542b0e3f30`). We are instantiating it, not inventing it.
- **Document-order adjacency between passages as a retrieval mechanism:** not found in
  the 2026 scan (see docs/11 §4).
- **Shared-entity chunk edges:** partially claimed, unmeasured — GraphRAG builds
  chunk→entity→chunk co-reachability (`scope:literature:claim:b79dbcb02f018a5e`) without
  evaluating it as a chunk-linking mechanism. Procure HippoRAG before claiming
  otherwise.
- **RAPTOR is not prior art and is structurally opposite** — its parents are generated
  summary text above the chunks (`scope:literature:claim:71f398594a2230db`), a lossy
  layer where this keeps a verbatim floor.

## What is deliberately not built

Chunks for the 98% of the archive that is session transcripts — the 2026-07-14 decision
stands everywhere outside the literature corpus. Semantic segmentation. Embeddings; the
reader stays lexical, and the gap survives lexical retrieval anyway (BM25, 14.7pp, the
largest of three retriever families). Any change to claim extraction or scoring.

## Open, and worth stating rather than gating on

Whether this helps *our* work is unmeasured, and per `6557ba9dbe024210` a downstream arm
campaign is unpowered at this scale — 24 arms could not resolve memory entirely-on
against entirely-off. So the honest position is that this instantiates a configuration
measured elsewhere, on a corpus where the effect is untested (all four benchmark corpora
are conversational; ours are static technical documents), for a retrieval surface the
paper's authors flag as untested (proactive injection rather than QA). What can be
watched cheaply once it ships: the used-vs-ignored share on chunk results versus claim
results, remembering that flag scores lexical overlap and will flatter long text
(lab/051), so it is a monitor, not a verdict.

## Ends in

**design** — co-indexing plus a provenance anchor, built on someone else's measurement,
with the three constraints that make it safe written down before the code.
