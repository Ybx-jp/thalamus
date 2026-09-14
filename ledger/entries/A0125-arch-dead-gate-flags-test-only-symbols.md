---
id: A0125-arch-dead-gate-flags-test-only-symbols
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: e9e39e15b5b874f96da37fca45718454c14015e1d1cbcf9d434c8da9bb6bd9c6
---

## Assertion

The dead-ends gate reports a source definition whose only references outside its own file sit under the test roots, rather than every unreferenced definition.

## Scope

metric: which unused definitions the dead-ends gate reports by default
cohort: the dead-ends census's declared policy
condition: not the census's mechanics for resolving a reference (AST walk, embedded-script handling), only which population of definitions the policy reports

## Grounds

- code: src/thalamus/arch/deadends.py § "DeadEndPolicy" =sha256:5d012e80db8ed7093175b1d55d7b07e9aee6daeeff9c3715bc2f29353a726eb9

## Warrant

`DeadEndPolicy` declares `source_roots` and `test_roots` and documents the test-only set as the default report, distinct from the broader never-referenced set behind `report_unreferenced`, which defaults off; the policy is where this choice of what counts as the finding is made.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
