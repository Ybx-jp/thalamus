# 041 — Three proposals, and the audit nobody ran

**Ends in: build nothing. One proposal falsified, one blocked on an hour of unlabelled
work, one deferred for want of an instrument — and a defect in the tool shipped
alongside them.**

Four structural gaps were named against the live graph (7,251 vertices / 18,378 edges),
three of them as proposals:

1. a typed `Claim→Thread` edge — none exists in either direction;
2. more `Claim→Claim` edge types, so a belief can be revised rather than overwritten;
3. similarity-based claim convergence, replacing exact-hash identity;
4. no retrieval surface for open problems — shipped as `memory_open_problems`
   (`2166e7a`), out of scope for the rest of this entry.

Both experts were consulted in parallel and deliberately given different jobs:
literature (`ee3dd5908a994139`, 25 citations) on the external field, eval-methodology
(`99068bee1ef649a5`, 13 citations) on our own measurements. They agree on the outcome
and disagree about the reasons, which is the useful part.

## Proposal 3 — falsified

The falsifier was cheap enough to just run: all 307,720 problem-claim pairs, token
Jaccard. **14 pairs score ≥ 0.4.** Four are Jaccard 1.00 and are identity-migration
ghosts — byte-identical `description`/`kind`/`category`/`source`/`ingested_at` under two
different SHA-256 ids, one minted under the retired identity function. Strip those and
**10 genuine near-duplicates remain, maximum similarity 0.67**, with distinct files,
distinct sessions and distinct `SOLVED_BY` targets.

There is no threshold that works: above 0.67 there is nothing but ghosts, below it you
merge distinct instances. A *perfect* matcher would move Problem convergence from 1.5%
to 2.8%.

The literature closes the same door from the other side. Cosine separates contradictions
from duplicates at **AUROC 0.59** — near chance — and contradictions are *more*
embedding-similar (0.812) than genuine duplicates (0.800), capping precision at 0.667.
The ordering is inverted, so a merge rule preferentially merges contradictions.

**Which produces the cross-cutting finding: proposals 2 and 3 are in direct conflict.**
Belief revision needs contradictory claims to stay distinct; similarity merging deletes
exactly those pairs first. Building 3 would silently destroy the input to 2.

Neither expert accepted 0.9% convergence as evidence of failure: the prior identity
converged *zero* times across 1,089 claims, so 0.9% is the fix working off a floor.

## Proposal 1 — blocked on an hour of work

`~/.thalamus/rake-audit/025-queue-precision.md` was drawn 2026-07-28: 50 items, 40
candidates and 10 decoys, over a stratum of **278** pairs (not the 263 the thread text
says — the stratum moved). **All 50 label lines are empty.** Ten days, zero labels, on a
worksheet its own header prices at roughly an hour. Its sibling thread
`rake-stage2-adjudicator-design-needs-labels` is blocked on the same labels.

That audit *is* proposal 1's premise measurement: it asks whether the artifact-`TOUCHES`
join key is strong enough to build on. Proposing a second derived-linkage mechanism while
the audit of the first sits unread is the [lab/033](033-the-graph-was-mostly-remembering-itself.md)
shape.

Two further findings kill the case for building now:

- **lab/029's ranking unit is the parent Session**, so a `Claim→Thread` edge is *inert*
  until the ranker grows an independent claim track. Proposal 1 is two changes, not one.
- **[lab/030](030-the-miss-rate-was-the-consultation.md) is the governing prior on what
  moves retrieval**: query shape cuts fan-out 28%, detail cap 8%, match floor −1%. No
  schema addition has ever been measured to move retrieval here, and the one thing that
  did was not in the schema.

### The census argument was wrong, both times

The proposal claimed `TOUCHES` dominates the edge census (6,487) *because* artifacts
carry connective load nothing else can — offered as evidence for the missing edge. That
inference is unsound: adding `Claim→Thread` removes zero `TOUCHES` edges.

The literature expert's substitute explanation — sessions touch many files — is also
incomplete. Measured, `TOUCHES` splits **Session 2,691 / Claim 3,159 / Thread 637**, so
sessions are under half of it. Neither account was right.

What the graph does say, measured over 699 `main` Problems: **43% (299) reach no Thread
at all** through a shared artifact; among the 400 that do, the fan-out is **median 3,
mean 6.6, max 34**, and only **119** land on exactly one thread. So the proxy fails
outright four times in ten and is ambiguous in most of the rest — a fact about our graph,
not a mandate, since the edge still has to be written by something.

`SUPERSEDES` sitting at **5 edges** is the standing proof that an edge type does not
populate itself.

## Proposal 2 — best supported, still deferred

Both experts converge on a smaller shape than proposed: extend the **existing**
`SUPERSEDES` edge to `Claim→Claim`, deterministically, rather than minting a
`CONTRADICTS`/`INVALIDATES`/`INFLUENCES` family. No influence edge at all — unfalsifiable
and with zero measured support.

The field converged on *invalidate-and-retain*, not retraction. Graphiti uses
LLM-detected edge invalidation; MemStrata reaches the same result with a deterministic
supersession rule, **no similarity threshold and no LLM call**, and the LLM route is
priced at ~8× retrieval latency for no temporal benefit. Leaving it to the model fails
outright: BeliefShift leaves **up to 42% of cross-session contradictions unresolved**.
Toki names our exact failure as its *audit erasure* anomaly. No measured evidence
supports a JTMS/ATMS-style truth-maintenance system — an absence that is itself
informative, since three systems had the option and all declined.

The reframe matters more than the mechanism: Thalamus is already append-only and
content-hashed, so it **never actually overwrites**. Both claims are in the graph. What
is missing is an *ordering signal at read time* — a read-time validity filter, not a
belief-revision subsystem.

It is deferred anyway, because **the benefit is invisible to our instrument by
construction**: a superseded claim that gets echoed still scores `used: true`. And the
power is not there. Live `RETURNS` census: Claim 1720/1061, **Thread 436/133 (76.6%, the
best class)**, Session 287/161 — 2463/1368 overall, 64.29%. Perfect Thread precision is
worth **+2.31pp** against an **MDE of 13.4pp** (SE 3.39pp clustered, ICC 0.229, deff
2.52, 29 session PSUs). Detecting it needs **≈980 sessions against 29**, and reaching the
MDE would require Δκ = 0.314 — 2.24× the shipped judge's measured discrimination
(κ = 0.140 [0.028, 0.272]), above its own CI ceiling.

The instrument needed is a stale-service audit keyed on a revision marker, not something
inferred from timestamps.

## The tool shipped alongside this had the same disease

`memory_open_problems` (`2166e7a`) ranked by recurrence, and its docstring called that
"the strongest signal the episodic record carries." Measured: `times_seen` is **1 for 77
of 82** open problems and 0 for 3. It separated two rows and left the tail sorted
alphabetically by description — [lab/031](031-the-dial-that-had-nothing-to-tune.md) on a
live retrieval surface, shipped the same hour the design pass was rejecting the same
mistake elsewhere. Fixed in `7ca9211`: recency orders the list (29 distinct dates),
recurrence only lifts the rare case, and the docstring states the firing rate.

## Open, and cheap

- **The 50 labels.** ~1 hour, zero code. Either outcome constrains proposal 1's design.
- **8 ghost `Claim` vertices** — tier-1, parentless, all 8 served through `RETURNS`, so
  they perturb every RETURNS-derived rate. Of 877 parentless Claims, 869 are tier-2 by
  design and exactly these 8 are tier-1. Needs a normalizer fix and a drop; dropping
  nodes is outside the sanctioned write paths ([docs/05](../docs/05-trust-model.md)), so
  it waits on an operator decision.
- **Proposal 2's falsifier**: count `RETURNS`/`REFERENCES{role:citation}` landing on
  withdrawn-figure claims *after* their withdrawal date (~30 min). Near-zero kills it;
  material gives the pre-registered baseline.

Numbers here were derived against the live graph on 2026-08-07 at 7,251/18,378 and are
**not snapshot-pinned** — re-derivable, not citable as constants.
