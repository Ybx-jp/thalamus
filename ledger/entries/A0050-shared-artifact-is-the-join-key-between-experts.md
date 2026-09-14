---
id: A0050-shared-artifact-is-the-join-key-between-experts
kind: claim
stated: 2026-09-13T20:48:36-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: bc40a14624edfaa16cdc4b11f3e802c3e2f5b2166a85719a47e4db8496e57bcd
---

## Assertion

A file touched by two different experts is one `Artifact` node, which makes it the join key between their subgraphs.

## Scope

metric: whether two experts touching the same file produce one node or two
cohort: every artifact any session touches
condition: the upsert function only

## Grounds

- code: src/thalamus/substrate/writer.py § "_upsert_artifacts" =sha256:c6f8d9fba882eb59218af1624a31d87b83143297a093d9b892451e03ea4a10b3

## Warrant

_upsert_artifacts is what resolves a touched file to a vertex, and doing so by upsert rather than insert is what collapses two experts' touches onto the same node.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
