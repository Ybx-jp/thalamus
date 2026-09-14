---
id: A0064-fork-distills-only-its-own-delta
kind: claim
stated: 2026-09-13T20:02:14-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 83c7d533f88b8e40c201ebde5046b96babcd15206d442f7fc14aa1d15bb5f6fc
---

## Assertion

A fork distills only its own delta, never the parent session's transcript.

## Scope

metric: what a fork's distillation pass reads -- the whole parent transcript or only what the fork added
cohort: every forked quick-ask session
condition: the delta computation only

## Grounds

- code: src/thalamus/harness/quick.py § "delta_records" =sha256:86c1facec1781096ecfe73d498c29c9bd5100687cf50dd86512321149041d958

## Warrant

delta_records is what computes exactly the fork's own additions relative to the parent, so it is the code that keeps distillation scoped to the delta.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
