---
id: A0051-trust-is-the-floor-over-derivation-chain
kind: claim
stated: 2026-09-13T20:49:43-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 5a7e59ac4ae3499967f79eb3d9be73f196c024a822f0ef055da8756140923834
---

## Assertion

Trust is not a label a writer chooses; it is the floor over a node's whole derivation chain, computed across its `DERIVED_FROM` edges.

## Scope

metric: how a node's effective trust is computed from its derivation
cohort: every node reachable by a DERIVED_FROM chain
condition: the definition only; the write-time code that actually walks the chain is a separate claim

## Grounds

- code: src/thalamus/substrate/schema.py § "Tier" =sha256:62a9c4d6ae8987d951aafd9282240463db421101fd11dfd8b42acb8f118e1573

## Warrant

Tier's own docstring states that effective trust is the floor over a node's DERIVED_FROM closure, which is the rule this assertion states.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- README.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
