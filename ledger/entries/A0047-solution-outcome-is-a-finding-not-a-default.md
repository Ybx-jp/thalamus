---
id: A0047-solution-outcome-is-a-finding-not-a-default
kind: claim
stated: 2026-09-13T20:45:15-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: d566241a831372dab9d8aee3c56c1a8e2f84d8e7630da8780ebfefbf14c9b45c
---

## Assertion

A solution's `worked` flag is a finding rather than a default, and its `outcome_kind` (`unresolved`, `reversed`, `rejected`, `residual`) tells a fix that never held apart from one that was undone or refused.

## Scope

metric: whether a solution's outcome defaults to worked, and what distinguishes its failure modes
cohort: every solution a session extracts
condition: the two class declarations only

## Grounds

- code: src/thalamus/substrate/schema.py § "Solution" =sha256:4ac143529613b74e7dbb5ca0fee9e03efa17dad2a27d86d2372a2129cd937738
- code: src/thalamus/substrate/schema.py § "OutcomeKind" =sha256:6c44521d91bc8e4b1c66889d1fa52167f8a439b2a05a3dcef8806cb440cc4912

## Warrant

Solution's worked field and the OutcomeKind enum are what the extraction schema actually offers, so what they declare is what the outcome semantics this assertion describes rest on.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
