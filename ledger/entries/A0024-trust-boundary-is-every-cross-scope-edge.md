---
id: A0024-trust-boundary-is-every-cross-scope-edge
kind: claim
stated: 2026-09-13T20:22:34-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 5fa2529356d97e0edee17a2a401762b5d70b8a87b0c9517c076b31233a946567
---

## Assertion

Every edge that crosses between two scopes crosses the federation contract's trust boundary.

## Scope

metric: which edges are subject to the trust boundary
cohort: every edge in the graph
condition: the crossing test only

## Grounds

- code: src/thalamus/contract/ontology.py § "edge_crosses_scope" =sha256:1db04b44268a415af02d3104ade97328133601a73720e78339ead4f4e975ca1d

## Warrant

edge_crosses_scope is the predicate deciding whether an edge counts as crossing, so it is what the every-crossing-edge claim reduces to in code.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-14T10:30:34-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/contract/ontology.py § "edge_crosses_scope" =sha256:1db04b44268a415af02d3104ade97328133601a73720e78339ead4f4e975ca1d
  artifact: sha256:ebc48f3b625be9c68a6b135bc5aeda68c77abfcb9aad4f513aebe3dcf37c728a
  note: propagated from a moved ground
- 2026-09-14T10:30:53-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/contract/ontology.py § "edge_crosses_scope" =sha256:ebc48f3b625be9c68a6b135bc5aeda68c77abfcb9aad4f513aebe3dcf37c728a
  note: Read at the current revision. edge_crosses_scope was the last definition in the module, so the exchange-record protocol appended below it by the write-gate change (7de0d95) fell inside its section and moved the digest; the predicate's own body is untouched and the crossing test it decides is unchanged.

## References

- docs/concepts.md · standing · cites-as-live
