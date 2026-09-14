---
id: A0144-scope-narrows-subgraph-root-not-target
kind: claim
stated: 2026-09-14T10:14:01-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 43c68207cd4f2d98e0987429e0a1ff62edd867c4b3dc683563aee8c649677660
---

## Assertion

`thalamus eval uses --scope` narrows the root of an attribution subgraph and never its target: an edge survives the filter when the citing claim's own scope matches, whatever scope the cited node belongs to.

## Scope

metric: which end of a USES edge the report's scope filter tests
cohort: every USES edge the report reads
condition: the report's own filter only; which targets the write path allows an edge to reach is a separate rule

## Grounds

- code: src/thalamus/eval/uses.py § "_edge_rows" =sha256:077625f454cb5ee81c7178ef6e49d9a7c9cb957a49cca402782f644d08e7ce93

## Warrant

_edge_rows projects root_scope and target_scope as separate keys and its only filter compares root_scope against the requested scope, so no value of the target's scope can exclude an edge the root's scope admits.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/eval/uses.py · standing · cites-as-live
