---
id: A0130-discrimination-lives-in-per-case-verdict
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 74507f163d181c4b615498274cd3581e2d2bb706ffe19b7e5888f77a7331af06
---

## Assertion

Which specific cases are newly red, as opposed to merely that the run is red, is only recoverable from the per-case verdicts the runner records, not from its single exit code.

## Scope

metric: where a reader finds out which case caused a red run
cohort: the reconciled verdict recorded per case
condition: not the exit code, which the same claim explicitly excludes as a source of that information

## Grounds

- code: tests/qe/expectations.py § "reconcile" =sha256:550671f7da04980ee86bba00ee247ed642443dd3a96c966a64957ee0d1a4300f

## Warrant

`reconcile` computes a distinct verdict string per case (`NEW_FAILURE`, `DRIFTED`, `FIXED`, and so on) that the runner prints and ledgers alongside that case's name, while the process exit code is a single collapsed value over the whole run; the per-case detail exists only at the point `reconcile` produces it.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
