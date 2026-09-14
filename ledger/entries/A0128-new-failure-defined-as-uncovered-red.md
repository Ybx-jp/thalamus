---
id: A0128-new-failure-defined-as-uncovered-red
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 186d5d82f644d56a9adf556e1507ab0b23a3d463d72763364051a49b1a080124
---

## Assertion

A failed adversarial case with no matching entry in the triage list is reported under one verdict, regardless of whether the failing code sits under `src/` or `tests/`.

## Scope

metric: what a failed case with no triage entry is reported as
cohort: the reconciliation of one case result against the expectations list
condition: not the other verdicts reconcile produces (fixed, drifted, malformed, skipped), only the untriaged-failure case

## Grounds

- code: tests/qe/expectations.py § "reconcile" =sha256:550671f7da04980ee86bba00ee247ed642443dd3a96c966a64957ee0d1a4300f

## Warrant

`reconcile` returns `NEW_FAILURE`, with an explanation naming the absent expectation, for any failed result absent from the expectations mapping, with no branch on which side of the tree the failure came from; the function's own logic is the definition, not a description of it.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
