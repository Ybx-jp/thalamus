---
id: A0029-audit-direction-ontology-against-writers
kind: claim
stated: 2026-09-13T20:27:09-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 4c56c04dbbed6a198f0d309f6a484e2e58519b942c1bf9a0b9936c2eb41e9aac
---

## Assertion

A second audit direction checks the ontology against what writers actually produce, which catches a declaration with nothing behind it -- a node type, kind, edge type or edge property no code writes.

## Scope

metric: which check catches an ontology entry no writer ever produces
cohort: every declared node type, kind, edge type and edge property
condition: this one direction only

## Grounds

- code: src/thalamus/contract/conformance.py § "audit_declarations" =sha256:c72492a246a98d7f5c28a426a9808e3e78e864458b7e5a19930e8e94084c8ad8

## Warrant

audit_declarations is the function comparing declarations against what was actually written, so it is the code that would surface a declaration nothing backs.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
