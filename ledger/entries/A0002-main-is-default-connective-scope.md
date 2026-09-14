---
id: A0002-main-is-default-connective-scope
kind: claim
stated: 2026-09-13T20:00:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 7e7becea2d61507875bab15311b95f825520a3f95f4f68969485c53565c05f05
---

## Assertion

`main` is the default scope, the connective plane where ordinary work lands when a session names no other scope.

## Scope

metric: which scope name is the fallback when no other scope is declared
cohort: every node and session that does not declare another scope
condition: only the constant's value; what makes a session actually adopt it is `resolve_pin`'s own claim, not this one

## Grounds

- code: src/thalamus/contract/ontology.py § "MAIN_SCOPE" =sha256:d7c365a6dc3312b9503a861d9c5455a24f1ef9b6557d0517f8b07d2458152baa

## Warrant

MAIN_SCOPE is the single literal the rest of the ontology and every scope-defaulting parameter reads for "no scope declared", so the module's own binding is what main being the default reduces to in code.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
