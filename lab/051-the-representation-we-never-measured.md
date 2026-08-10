# 051 — The representation we never measured

**Status: pre-registration. Nothing here has been run.** Written before the first
measurement deliberately, so the endpoints, the margin and the stop conditions are on
the record ahead of any number. The two consultations behind it are
`scope:main:exchange:7848872f9deb464c` (literature, 38 citations) and
`scope:main:exchange:6557ba9dbe024210` (eval-methodology, 41 citations).

## What broke

Nothing broke. This entry exists because a readiness brief flagged a paper that argues
against a shipped design, and the ticket-back did not dissolve.

Thalamus retrieval returns LLM-extracted typed claims and session summaries. The
archive retains every fetched and transcribed byte, and `Source` vertices resolve to
them, but **no retrieval path reaches that text**. `_load_knowledge_result`
(`substrate/reader.py:931`) walks `DERIVED_FROM` to the Source and reads `title` and
`origin` — never the archive `uri`, never the bytes.

*Fidelity Before Structure* (arXiv 2601.00821, now in `literature` in full at 91
claims) measures verbatim chunks beating LLM-extracted typed artifacts by 15.9 points
on LoCoMo and 22.0 on LongMemEval-S, in a fixed retrieve-rerank-reason pipeline
varying only the stored representation, with six confound controls
(`scope:literature:claim:0a5efda94cf2d814`, `8c5b0141f8db68d2`). Accuracy tracks how
much source text survives in the store (`scope:literature:claim:8328d2e1c7a732e3`).

## Why the obvious dismissals fail

**"Our reader is lexical, so this is about embeddings."** Measured shut. The paper's
retriever-family ablation reports the gap under BM25 sparse lexical retrieval at
14.7pp — the *largest* of three families. The 2026-07-14 decision against `Chunk`
nodes rests on them earning their keep only under per-chunk retrieval *or* embeddings;
the embeddings half of that disjunction is not a precondition. Per-chunk retrieval
still is.

**"We can just drill down from a claim to its source."** The measured augmenting
configuration is co-indexing — artifacts and verbatim chunks in one first-pass
candidate pool, ranked against each other (union 42.5%, chunks-alone 43.9%,
artifacts-alone 28.0%), so artifacts are accuracy-*neutral* there and the chunks carry
the gain. Drill-down was never measured. And 69% of the diagnosable gap is **write-time
loss** — facts the extractor never wrote down — which a drill-down keyed on an artifact
structurally cannot reach. Its ceiling is the other 31%.

## What is already true here, and was not obvious

Two findings from reading our own code, both of which reshape the question.

**The two halves of the graph sit at different poles.** `LiteratureClaim` carries
`citation` — a short verbatim quote — plus `locator` (`substrate/schema.py:230`). That
is the near-verbatim, provenance-preserving shape the paper measures as landing
*between* the poles. The episodic claims — `Decision`, `Problem`, `Solution`
(`schema.py:203-219`) — carry **no verbatim field at all**; `rationale`, `approach` and
`outcome` are model-authored prose. So the literature scope is plausibly already at the
intermediate position and the episodic scope is at the artifact pole. The paper's four
corpora are all conversational, which maps to the episodic side — the side with no
verbatim anchor. The condition assumed least met is met exactly where the evidence is
strongest.

**The alternative the closed decision promised was never built.** The 2026-07-14 entry
rejects `Chunk` nodes in favour of "anchors on the edge (message UUIDs)". No edge
carries one: `_ensure_edge` writes no properties and the ontology declares none. So
there is no path from an episodic claim to the span it came from — not chunks, and not
the locators that were supposed to make chunks unnecessary.

## The measurement, pre-registered

Eval-methodology's verdict is that a downstream counterfactual campaign **must not be
run** for this change. At 24 arms we could not resolve memory entirely-on versus
entirely-off (P(on>off)=0.667, p=0.0849, `scope:eval-methodology:claim:a91fd45f4edf5d46`);
this is a representation refinement *inside* the memory-on condition and is necessarily
a smaller effect. Detecting ~0.60 would need on the order of 280 arms, and arms cluster
by task, so effective N is below nominal (`scope:eval-methodology:claim:f4f201d024fa3248`:
rho of 0.017 across 4 clusters dropped realized power from 80% to 61%).

What replaces it is offline, arm-free and compute-bound, so N is effectively unlimited.

### Endpoint disqualified in advance

**Used-vs-ignored trace attribution may not be the endpoint.** The `used` flag is a
lexical-overlap test against a node's own distinctive terms, so the bar scales with
text length and with vocabulary shared with the source. Verbatim spans are longer and
share strictly more surface vocabulary with the documents they came from, so a verbatim
arm would score higher close to mechanically. It would measure the representation's
lexical similarity to itself. Compounding it: a node never returned has no `RETURNS`
edge, so harm from failing to retrieve is invisible by construction — and that is
where 69% of the phenomenon lives.

### The assay

For N archive items where a `Source` resolves to retained bytes and claims were
extracted from it, build three representations of the **same span**:

| arm | content | role |
|---|---|---|
| **A** | claim `description` only, `citation` stripped | artifact pole (control floor) |
| **B** | claim `description` + verbatim `citation` | unit under test — as shipped |
| **C** | the raw archive span | verbatim pole (control ceiling) |

Two mechanical endpoints, no judge: rank-of-correct-item and recall@k under both our
own `recall()` ranker and a BM25 arm (the paper's highest-prior transfer condition and
the closest to what we run); and literal coverage — versions, flags, paths, thresholds,
identifiers, which is where extractor loss lands in technical documents.

**This is an equivalence question, not a superiority one.** "B > A" is trivially true
and uninteresting. The quantity is where B sits on the A–C interval:
`(score_B − score_A) / (score_C − score_A)`, with a non-inferiority margin fixed
*before* looking at our data, derived from the paper's own intermediate-vs-pole gaps
(fixed-margin method, `scope:eval-methodology:claim:217c8acabf8e8c33`). 57.9% of
published non-inferiority margins never report how they were defined
(`scope:eval-methodology:claim:b44e14bee800c5ff`); ours is defined here. The ratio's
denominator is unstable and the scope holds no anchor for a ratio-of-differences
estimator, so the three raw scores are reported alongside it always.

### Separating "more text helped" from "verbatim text helped"

Without this the measurement is uninterpretable. Four contrasts at matched token
budget *T*:

- **V** — verbatim span.
- **A+** — extracted claims padded to *T* with lower-ranked claims. V vs A+ isolates
  representation at fixed budget.
- **V-shuf** — the same verbatim tokens, sentences reordered. If V ≈ V-shuf, the effect
  is lexical mass, not fidelity.
- **V-para** — the span paraphrased at equal length. If V ≈ V-para, the exact bytes buy
  nothing over better extraction, and the archive story is not what is working.

These are metamorphic relations (`scope:eval-methodology:claim:3ade7ca7aeeaeca2`) and
carry that family's weakness: they are degradation-direction relations, not equality
relations, and a uniformly bad system satisfies them.

**Cheapest control of all, which may end the inquiry outright:** a budget-only
ablation with no representation change — same injected tokens, just more existing
claims. If that moves the endpoint as much as verbatim does, build nothing.

## Stop conditions, stated before any number exists

1. **Run the C-vs-A pole check first.** If `score_C ≈ score_A` on our corpus, the
   verbatim pole buys nothing here, the paper's effect does not transfer to static
   technical documents, and the inquiry ends — no arms, no build. Denominator
   degeneracy is not a nuisance case; it is the primary result and the cheapest
   possible answer.
2. **Condition (d) supported** if B closes at least the pre-registered fraction of the
   A→C gap with the interval excluding the margin. Then no problem exists to architect
   around: we are already at the intermediate position, and the correct output is a
   recorded negative.
3. **Condition (d) falsified** if B lands indistinguishably from A on a majority of
   items with the interval excluding the margin. This is the *only* outcome that
   licenses further design work.
4. **Write-time-loss coverage runs in parallel**, measured against retained bytes via
   `DERIVED_FROM`. If our loss is concentrated at write time, the correct change is to
   the extractor and no retrieval architecture addresses it.

## Blockers that bind before anything is scored

**The ordinal thread blocks any rung-based campaign.** On lab/020's real data,
mean-of-rungs, the pre-registered threshold metric and rank-based analysis disagreed
**in direction** (`scope:eval-methodology:claim:f45bf431de59f220`), and the sign-reversal
warning for metric models over ordinal data is live. Any new campaign reporting a
rung-based primary statistic before `ordinal-metric-sign-reversal-open` closes produces
a number whose *sign* is a function of an unmade decision. The assay above largely
sidesteps this — its endpoints are continuous rank and coverage, not ordinal rungs.

**Archive reach is an unwatched leak channel, and it biases toward the treatment.**
Nine of 88 arms once reached their answer key through the git object store, undetected
by the filesystem-only detector and found post-hoc
(`scope:eval-methodology:claim:30663540dd870284`). Making retained bytes retrievable
opens a read path neither `detect_worktree_escape()` nor `detect_history_reach()`
watches. A positive result is exactly what such a leak would produce — the worst
possible orientation for a confound. If arms are ever run here, three things are
mandatory first: a pre-registered archive-reach detector, an as-of-T archive cut
filtered to bytes retained before the arm's pinned ref, and a defense-off condition
proving the detector fires (`scope:eval-methodology:claim:86155d50448b73b6`).

**A cost none of the accuracy papers price.** Retrieval that surfaces retained bytes
widens the poisoning surface: retrieval carries no provenance check and agents treat
retrieved memories as ground truth (`scope:literature:claim:ba6b62409b3d8b95`,
`ae6c87c8e28712b8`). Today's retrieval surface is claims that passed a write path; the
archive passed none. This ties the inquiry to the open `transcript-mediated-laundering-gap`
thread rather than leaving it a pure accuracy question.

## The falsifier for this plan itself, unchecked

If the offline assay's ranking endpoints turn out to be uncorrelated with downstream
rung outcomes on the lab/023 arms already on disk, then the assay measures something
that does not matter, and only an arm campaign would do — in which case the honest
output is still "this cannot be answered at our scale", not a cheaper substitute. That
correlation is checkable against `~/.thalamus/counterfactuals/runs.jsonl` for no cost,
and it should be checked before any assay result is believed.

## What this entry does not license

No architecture. Co-indexing is not designed here, `Chunk` nodes are not reinstated,
and the 2026-07-14 decision stands until a measurement moves it. Condition (b) —
proactive, non-QA recall, our dominant retrieval surface — is flagged untested by the
paper's own authors and stays unmet after every measurement proposed above. That is an
honest gap, not something the assay closes.

## Ends in

**pre-registration** — endpoints, margin, stop conditions and blockers recorded before
the first run, which is the whole point of writing it now rather than after.
