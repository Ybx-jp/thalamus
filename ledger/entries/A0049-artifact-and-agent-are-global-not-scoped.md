---
id: A0049-artifact-and-agent-are-global-not-scoped
kind: claim
stated: 2026-09-13T20:47:29-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 858e573c8f6beaf2af7dbb69291fa01f1323d5ff8342e1e36add0af3424e303b
---

## Assertion

Every node carries a scope except `Artifact` and `Agent`, which are deliberately global -- one vertex per identifier, shared by every scope.

## Scope

metric: which node labels are exempt from carrying a scope
cohort: every node type in the core ontology
condition: the exemption set only

## Grounds

- code: src/thalamus/contract/ontology.py § "GLOBAL_LABELS" =sha256:4b25dd23ba044b98de0d007a965f00b2fdcfdcf97ef2b9381836f2b565978945

## Warrant

GLOBAL_LABELS is computed directly from which CORE_NODES entries are marked unscoped, so it is exactly the set this claim names.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
