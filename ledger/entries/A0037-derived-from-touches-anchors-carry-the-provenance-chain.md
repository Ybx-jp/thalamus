---
id: A0037-derived-from-touches-anchors-carry-the-provenance-chain
kind: claim
stated: 2026-09-13T20:35:05-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 3104c347bd4d65f286d79ab21b168075d40266a62e4657c154493a3635c19971
---

## Assertion

`DERIVED_FROM` lands a belief on the evidence it came from, `TOUCHES` carries the `anchors` naming the exact messages, and `ANCHORS` puts a literature claim on the passage it quotes.

## Scope

metric: which write function lands each of the three provenance-chain edges
cohort: every session or ingested document written to the graph
condition: the three named functions only

## Grounds

- code: src/thalamus/substrate/writer.py § "_write_sources" =sha256:f1c7f354759c6e259913a097ab9fbdf6dbae1a5c3f39b16102a9da2f7b35f355
- code: src/thalamus/substrate/writer.py § "_write_touches" =sha256:c0e15eae932105d327e2886143a3f5d87a522b5ea4a7d69d67c154334b500527
- code: src/thalamus/harness/ingest.py § "anchor_citations" =sha256:250a85e5aab835c3113d5b9fcbfe4089f1d5f3ef369f105740995f9482b27498

## Warrant

Each function is the code that actually writes the named edge -- _write_sources writes DERIVED_FROM to a session's sources, _write_touches writes TOUCHES with its anchors, and anchor_citations resolves the ANCHORS targets -- so together they are the whole of what forms this chain.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
