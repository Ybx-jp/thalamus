# Pre-registration — experiment 002

Committed **2026-07-30**, before the estimator was run against the snapshot.

## Question

What interval does Thalamus's token-waste figure carry once the clustering of
verdicts inside sessions is respected, and what does that figure become after
correcting for the judge's chance level?

## Hypotheses

H1. The published point estimate is materially less precise than a verdict-level
interval would suggest, because verdicts inside a session share a window, a topic
and an operator.

H2. The chance correction changes the headline more than the interval does — i.e.
the dominant uncertainty is what "used" means, not how many sessions were observed.

## Endpoint

R̂ = Σ wasted tokens / Σ injected tokens, sessions as primary sampling units,
delete-one-session jackknife for the SE, normal 95% interval.

Per-node price is `injected_chars / returned_count`, which is what the graph
records. The chance-corrected share is 1 − κ on the **token-weighted** rate against
the **token-weighted** permuted null, because a token-weighted estimand corrected by
a node-weighted null mixes two denominators.

## Falsifiers

- **H1 is false** if the session-clustered interval is no wider than the
  verdict-level binomial interval. Clustering would then be immaterial and the
  simpler estimator stands.
- **H2 is false** if the chance correction moves the headline by less than the
  interval's own half-width.

## Stopping rule

Census at the pinned snapshot — every attributed `RETURNS` edge in scope `main`.
There is no sampling decision to stop. 200 rotations for the null, fixed in advance.

## Declared in advance as uninterpretable

- If the naive verdict-level SE comes out **wider** than the clustered one, the
  clustering calculation is broken rather than the data being surprising, and the
  number must not be published until it is fixed.
- The chance-corrected share is reported **without an interval**. Its uncertainty is
  that of a difference between two rates on the same verdicts, which needs the
  paired estimator extended to token weights. A placeholder interval would be worse
  than none.

## Known bias, declared before the run

The per-node price is uniform within a retrieval, so a short node and a long node in
the same render are charged identically. The direction of that bias depends on
whether long nodes are used more often than short ones, which this experiment does
not measure.

## Seed and data

Seed `20260730`. Snapshot `post-sandbox-purge-20260730` (`experiments/snapshots.jsonl`).
