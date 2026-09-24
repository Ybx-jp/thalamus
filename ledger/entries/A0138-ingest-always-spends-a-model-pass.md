---
id: A0138-ingest-always-spends-a-model-pass
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 73dfde1c79527eb6bfddd1aa87b1ac18df119088901dc6132abf5096c9759947
---

## Assertion

Every call to the ingest function performs a model-extraction pass over the fetched text, whether or not the caller goes on to persist the result to the graph.

## Scope

metric: whether an ingest call's model spend depends on the caller persisting its result
cohort: the ingest function's own control flow from preflight through extraction
condition: not the contract check or graph write, which the function's own documentation assigns to its caller and which this entry does not claim happens inside it

## Grounds

- code: src/thalamus/harness/ingest.py § "ingest" =sha256:0f4103b5dfc79231f5ac10a5394d329fd8e0f636dae749c2f7f62e82a5e5079f

## Warrant

`ingest` calls `preflight` and then unconditionally runs an extraction pass — one pass over the whole text, or one per chunk — with no parameter that skips it; its own docstring assigns the graph write to the caller, so a call whose result the caller discards still pays the same extraction cost as one that gets written.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-24T01:14:53-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/ingest.py § "ingest" =sha256:0f4103b5dfc79231f5ac10a5394d329fd8e0f636dae749c2f7f62e82a5e5079f
  artifact: sha256:0cd38c5a1abe29a5d5b4e56ae067ebd54f3f140abc2cba44854cd623b3f8697c
  note: propagated from a moved ground
- 2026-09-24T01:16:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/harness/ingest.py § "ingest" =sha256:0cd38c5a1abe29a5d5b4e56ae067ebd54f3f140abc2cba44854cd623b3f8697c
  note: Only the arguments to build_chunks and anchor_citations changed; preflight and the unconditional extraction pass are untouched, so the assertion is unaffected.

## References

- CLAUDE.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
