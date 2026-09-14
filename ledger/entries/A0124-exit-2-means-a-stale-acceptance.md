---
id: A0124-exit-2-means-a-stale-acceptance
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: b1417980f4dede9fcd0b68f5119c5f874291c09b45c10061a6fa7664cb15182b
---

## Assertion

The architecture rules gate's exit code distinguishes a newly forbidden dependency from an accepted exception that no longer occurs in the measured graph, exiting 2 only for the latter.

## Scope

metric: what the rules gate's exit code distinguishes
cohort: the gate's own result type
condition: not the CLI command that prints or returns this code, only the value the gate computes

## Grounds

- code: src/thalamus/arch/model.py § "GateResult" =sha256:b02041ea2570d788fa107cd7bbefdd97a2bbba42753140421dec065f6f4b0c3e

## Warrant

`GateResult.exit_code` returns 1 when new violations or newly unplaced modules were measured and 2 only when nothing new was found but some previously accepted exception no longer fired; the property is the single place this distinction is computed, so reading it settles what each exit code means.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
