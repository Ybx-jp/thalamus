---
id: A0028-audit-direction-vertices-against-ontology
kind: claim
stated: 2026-09-13T20:26:02-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: b4442d4637c7d24e334847499208d73d03b253f46a015b79d5c9e7823925ed19
---

## Assertion

One audit direction checks written nodes against the ontology, which is what catches a bad write.

## Scope

metric: which check catches a node that violates the declared ontology
cohort: every audited vertex
condition: this one direction only

## Grounds

- code: src/thalamus/contract/conformance.py § "audit_vertices" =sha256:44c13881a3ea1fa81114577b5c83cbc34cd8ca0f23692099eeccb68fbecbeb7f

## Warrant

audit_vertices is the function that walks written vertices against the declared ontology, so it is the code performing exactly this direction of the audit.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
