---
id: A0035-every-node-carries-provenance
kind: claim
stated: 2026-09-13T20:33:51-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 09c222df300cc40e097311521415808d3b7a36923a6eb1160cdb92ebec57f2a3
---

## Assertion

Every node in the graph carries provenance -- a trust tier, a source, and an ingestion time.

## Scope

metric: which fields every node's provenance carries
cohort: every node in the graph
condition: the declared model only; whether a given writer always fills it in is the write-time contract's own enforcement, not this claim

## Grounds

- code: src/thalamus/substrate/schema.py § "Provenance" =sha256:6273dbd1cae739fd46457dabc7ba130bf76fdcbce7f8f266197ffdf4814cc68a

## Warrant

Provenance is the model every node's provenance is typed as, and its fields are exactly tier, source and ingested_at.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
