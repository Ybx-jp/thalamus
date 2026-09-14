---
id: A0129-regression-and-self-referential-red-both-exit-1
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 82e5284efa5d26fa8eda439228da4b9e1f98584b2a01db503a2513ec5766b64b
---

## Assertion

The adversarial suite's runner exits 1 when any case reconciles to a new or changed failure, without distinguishing a failure in `src/` from a failure in the suite's own additions.

## Scope

metric: which reconciled verdicts make the suite runner exit 1
cohort: the runner's top-level exit-code decision
condition: not the exit codes for a broken check or a fixed defect, which are separate branches of the same decision

## Grounds

- code: tests/qe/run.py § "main" =sha256:f0b3925c86452f11f5fa5bf133e684c5530900255b559c774f2a182c46155ff6

## Warrant

`main` collects every case's verdict and returns 1 when `NEW_FAILURE` or `DRIFTED` appears among them, with no branch that reads which case produced it; the same exit code follows from either kind of untriaged red because the function never asks the question that would separate them.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
