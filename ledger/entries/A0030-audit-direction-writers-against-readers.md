---
id: A0030-audit-direction-writers-against-readers
kind: claim
stated: 2026-09-13T20:28:16-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 968b282af94c5d3fdffe97d747fad3aec75c19629658860b7f9d47a34fa8d82a
---

## Assertion

A third audit direction checks what writers produce against what readers project, which catches the opposite gap -- a field written onto every vertex of its label that no read path ever names.

## Scope

metric: which check catches a written field no reader ever queries
cohort: every property written onto a labeled vertex
condition: this one direction only

## Grounds

- code: src/thalamus/contract/conformance.py § "audit_reader_projection" =sha256:1ec6e8c78f087c68948944bf9373cd6a910759e3788619c5f8cfb7b5692b2638

## Warrant

audit_reader_projection is the function comparing writer output against reader projections, so it is the code that would surface a persisted, unreadable field.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
