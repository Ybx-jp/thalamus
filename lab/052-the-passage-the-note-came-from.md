# 052 — The passage the note came from

**Status: design + pre-registered gate. Nothing here is built.** Continues
[051](051-the-representation-we-never-measured.md), whose coverage endpoint falsified
the hope that a claim's verbatim `citation` already occupies the intermediate
representation. Grounded through `scope:main:exchange:d0060228a7454be0` (literature, 54
citations), which follows `7848872f9deb464c` (38) and `6557ba9dbe024210` (41).

## The proposal

Operator's design, stated as given. Nothing about today's claims changes.

- **Chunk vertices for the literature corpus only**, at "one complete idea"
  granularity rather than fixed width.
- **A citation → chunk edge**, so an agent holding a note can reach the passage it came
  from.
- **Chunk → chunk edges**: `ADJACENT_IN_TEXT` (document order) and `MENTIONS` (shared
  entity or reference).
- **The full original text stays retained as the floor**, as now.
- **Retrieval is unchanged.** Claims and session summaries remain the first-pass pool.
  Chunks are reached by deliberate agent traversal, never injected ambiently.

## Why the cost objection does not apply here

The 2026-07-14 decision rejected `Chunk` nodes on a ~100× node-explosion estimate. That
estimate is correct for the archive as a whole — 275.7M chars across 419 documents,
~183,800 chunks at 1,500 chars, against a graph of 9,636 vertices.

It does not apply to this proposal, because **the literature corpus is 2.1% of the
archive**: 154 sources, 5,685,696 chars. At ~1,500 chars that is **~3,790 chunk
vertices — 0.4× graph growth**, from 9,636 to roughly 13,400. The remaining 98% is
session transcripts, and the design excludes them by construction: only literature
claims carry a `citation`, so "traverse from a citation" is papers-only without anyone
having to impose it.

Measured 2026-08-10. The old estimate was not wrong; it was answering a different
question.

## What the evidence says

### For

**Annotating is the safe side of the only mechanistic account the corpus offers.**
Annotating verbatim text is safe; replacing it, however gently, costs accuracy
(`scope:literature:claim:e7205d68dd06fa17`). This design annotates and keeps the floor.
Zep is the worked instance: its lowest tier retains raw interaction data beneath the
entity and community layers, instantiating structure-annotating-text rather than
structure-replacing-text (`scope:literature:claim:ec4af50636456ddb`).

**Making verbatim text reachable recovers nearly the whole gap.** A union store
indexing artifacts alongside verbatim chunks scores 42.5% against 43.9% chunks-alone
and 28.0% artifacts-alone (`scope:literature:claim:00aeb8542b0e3f30`) — ~14.5 of the
15.9pp recovered. Strongest evidence in the corpus that the direction is right.

**Expansion does reach material the representation omitted.** Retrieval-only scoring —
does the retrieved context contain the ground-truth keywords — rises from 25.8% to
71.8% under graph expansion (`scope:literature:claim:f2cb29a74cbb943d`). That is
exactly the hoped-for mechanism.

**The existing verbatim `citation` is already doing fidelity work.** The artifact
pipeline's verbatim quote field carried an exact date through to retrieval where
community summarization generalized "8 May 2022" into "last year"
(`scope:literature:claim:636af19a1d14aa63`). Keeping citations unchanged is supported.

### Against — and the first one is the strongest objection on the table

**1. The design declines the only configuration measured to work, in favour of one
measured to be a no-op.** The union store recovered ~14.5pp
(`scope:literature:claim:00aeb8542b0e3f30`). The identical 1-hop expansion applied over
*verbatim chunks* rather than artifacts is a no-op — 43.1% vs 43.9% — indicating
expansion only helps within the lossy artifact representation
(`scope:literature:claim:e9cfc1dac2ed55d7`). This proposal takes the second shape and
rejects the first, to avoid a ranking harm that measured **1.4pp**, barely
distinguishable from noise.

*Conditions not met, and they matter:* in that no-op arm the verbatim chunks were
**already the first-pass pool**, so a neighbouring chunk was directly retrievable
without any edge — there was no write-time loss for expansion to escape, which is this
design's entire premise. Expansion was also automatic and pre-rerank under a fixed
budget, over conversational turns rather than argumentative prose. So it is not
"demonstrated not to work". It is the null this design has to beat, and it is
pre-registered as such below.

**2. The +45.9pp did not convert.** Keyword-recall gains are not a proxy for answer
quality: the verbatim store scores *lower* on keyword recall yet 15.9 points higher on
final accuracy (`scope:literature:claim:e490d8900938402e`). The available reason is
that the expanded neighbours were still artifacts, still lossy, and accuracy tracks how
far the stored representation departs from source text
(`scope:literature:claim:f885759edc61f7d0`) — under this design the expansion *target*
is verbatim text, so that specific failure reason is absent by construction. **That is
an argument, not a measurement**, and it is the design's central bet.

**3. "One complete idea" chunking probably does not pay.** An extra full-corpus LLM
pass has a measured track record of not paying: GraphRAG's gleaning pass changed
accuracy by 2.1pp, within conversation-level noise, "its measured contribution is
negligible" (`scope:literature:claim:39e72cc13213881a`). And finer units at *constant
fidelity* cost accuracy — sentence-granularity verbatim gives up 3.7 of 16.3pp, with
fidelity, not granularity, the load-bearing variable
(`scope:literature:claim:af0c3da6c8456689`). Zero-overlap controls reproduce the gap
(`scope:literature:claim:abd3a5d4c382f26d`), so overlap is not load-bearing either.
The standing prior should be that **fixed-width 1,500-char chunking ties an
LLM-segmented corpus at a fraction of the cost**, and that prior is currently
unfalsified in scope.

**4. `MENTIONS` is the volume risk, not the chunks.** Chunk count is linear in corpus;
shared-entity edges are quadratic in entity cliques. A common name like "GraphRAG"
would connect a large fraction of 3,790 chunks. Uncontrolled connectivity has a
measured harm signature — dense unconstrained connections incur redundant token
overhead and let task-irrelevant noise distract agents
(`scope:literature:claim:9db15d4954c4958f`, conditions differ: multi-agent topology,
not document graphs). Any `MENTIONS` edge needs a **degree bound and an
entity-specificity floor written before the edge is**, not after.

**5. What happens once a chunk lands in context.** Performance degrades when relevant
information sits mid-context, even in long-context models
(`scope:literature:claim:2268d735ff10a67e`), and pruning irrelevant context *improves*
responses (`scope:literature:claim:6843553dde27884a`). Against our own measured 33.8%
of injected retrieval tokens judged unused (lab/006), a mechanism whose success mode is
"fetch more text" needs a stopping rule from day one.

**6. The poisoning surface grows by roughly the chunk-size factor.** A `citation` is a
short bounded quote; a chunk is ~1,500 chars of unfiltered third-party text reaching
context on demand. Agents treat retrieved memories as ground truth absent provenance
checks (`scope:literature:claim:ba6b62409b3d8b95`); weak-signal payloads carry no
syntactic anomaly (`scope:literature:claim:73b19e8595b5031d`); and no provenance-free
retrieval-time filter achieves a non-trivial worst-case certificate against an adaptive
adversary (`scope:literature:claim:b2dc45c539882811`). Two things cut for the design:
the traversal is **provenance-mediated by construction** — citation → chunk is a
provenance edge, which is what that last result says a filter needs — and randomised
memory ablation with verdict aggregation cut authenticated ASR from 93–100% to 8.0%
(`scope:literature:claim:f344d4496545632a`), a defence shape that composes with a chunk
tier. This ties the design to the open `transcript-mediated-laundering-gap` thread.

**7. Agents may not traverse when they should.** The design's safety argument is that
traversal is deliberate. Confirmed gap: agent-initiated versus pipeline-injected
expansion, mechanism held constant, is **not found in the 2026 scan (see docs/11 §4)**.
Self-RAG is the nearest system, but its decision is a trained LM emitting reflection
tokens inside the generation loop, not an agent choosing a tool
(`scope:literature:claim:07bbc814f5c3edc0`), and it is compared against non-adaptive
RAG rather than against automatic injection of the same expansion. The sharp worry: the
retrieval literature's premise is that automatic retrieval exists *because* models
under-retrieve when left to decide.

## Prior art, labelled honestly

- **citation → chunk anchor edge — has prior art, asserted not measured.** An Applied
  Knowledge Graph versions contract/clause/party entities and links ClauseVersion nodes
  to text chunks, prioritizing decision-readiness over semantic storage
  (`scope:literature:claim:2fd0cfa3ca7f01b8`). A practitioner essay with a Cypher
  sketch and no evaluation. **This edge may not be called novel.**
- **chunk → chunk document-order adjacency as a retrieval mechanism** — not found in
  the 2026 scan (see docs/11 §4). Nothing in scope builds it or measures it.
- **chunk → chunk shared-entity edges** — partially claimed, unmeasured. GraphRAG
  builds chunk → entity → chunk co-reachability
  (`scope:literature:claim:b79dbcb02f018a5e`) but never evaluates it as a chunk-linking
  mechanism. HippoRAG should be procured before this is written up as unclaimed.
- **RAPTOR is not prior art here** and is structurally opposite: its parents are newly
  generated *summary* text above the chunks (`scope:literature:claim:71f398594a2230db`)
  — a lossy layer, where this design keeps a verbatim floor.

## The gate — a three-arm comparison, pre-registered

Nothing is built until this runs. Three arms at **fixed token budget**:

| arm | first-pass pool | expansion |
|---|---|---|
| **1 — claims only** | claims + summaries | none (today's system; the ~31% ceiling) |
| **2 — traversal** | claims + summaries | citation → chunk → adjacent, agent-initiated |
| **3 — co-index** | claims + summaries **+ chunks** | none (the measured winner) |

Arm 3 is included **because the design rejects it and the evidence favours it**. If
arm 3 wins, the design was wrong and no edges get built. If arm 2 matches or beats it,
that is a first-party result on our own corpus stronger than anything the corpus
currently holds.

**Questions are written before the edges exist.** The one setting where artifacts beat
verbatim storage was a synthetic probe where every planted fact was pre-shaped into
exactly one artifact (`scope:literature:claim:bfcba12e80f373aa`); a question set written
after the edges would reproduce that trap by construction.

**Pre-registered nulls:** arm 2 ≈ arm 1 is the outcome predicted by
`scope:literature:claim:e9cfc1dac2ed55d7`. Fixed-width ≈ semantic chunking is the
outcome predicted by `39e72cc13213881a` and `af0c3da6c8456689`, so **the segmentation
strategy is itself an arm dimension, not a settled choice** — build fixed-width first
and make semantic segmentation earn its LLM pass.

**Not a counterfactual campaign.** Per `6557ba9dbe024210` a downstream arm campaign is
unpowered at this scale; this gate is offline and retrieval-scored, and the
`ordinal-metric-sign-reversal-open` thread blocks any rung-based statistic regardless.

## Deliberately not built

`Chunk` nodes for the 98% of the archive that is session transcripts. Automatic
injection of chunk text into recall. Any change to how claims are extracted or scored.
The 2026-07-14 decision stands for everything outside the literature corpus.

## Gaps this adds to the standing list

G1 boundary policy isolated from representation; G2 cost and quality of a segmentation
pass; G3 expansion from a lossy index *into verbatim text* scored at answer level; **G4
whether traversal reachability substitutes for first-pass-pool reachability — the hinge
of this design, unmeasured**; G5 document-order adjacency as a retrieval mechanism; G6
shared-entity chunk edges evaluated as such; G7 passage-level reference links; G8
agent-initiated vs automatic expansion with mechanism held constant; G9 any measured
case of a memory graph degrading when chunk structure was added above retained text
(none found — the corpus supports "costs more than it returns" far better than "makes
things worse"); G10 late chunking / parent-document / sentence-window retrieval, scope
holds nothing; G11 re-segmentation and edge staleness under document revision; G12
poisoning surface as a function of retrieved-passage size.

**Procurement queue**, demand-driven against those: (1) the semantic-chunking
cost/benefit comparison — closes G1+G2, highest-value single ingest; (2) HippoRAG —
decides G6; (3) Dense X Retrieval / proposition indexing — G1; (4) Late Chunking and a
parent-document reference — G10; (5) LumberChunker — G2.

## Ends in

**design + gate** — the design is written, its strongest objection is recorded rather
than answered, and the arm that would refute it is in the experiment.
