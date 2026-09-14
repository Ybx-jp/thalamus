---
id: A0131-arch-dead-catches-python-symbol-half
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 47818e62f85f42676f4c879082262a6ec352d8e9c42a6f3b1e593f67b360a09c
---

## Assertion

The dead-ends gate's census is a walk over Python definitions and references, which is the mechanism that lets it report a symbol nothing outside the test roots calls.

## Scope

metric: what kind of reference the dead-ends census actually walks
cohort: the dead-ends census's declared source and reference roots
condition: not the cross-surface half of the same defect class (an undeclared ontology term, a flag with no parser), which this entry does not claim the census covers

## Grounds

- code: src/thalamus/arch/deadends.py § "DeadEndPolicy" =sha256:5d012e80db8ed7093175b1d55d7b07e9aee6daeeff9c3715bc2f29353a726eb9

## Warrant

`DeadEndPolicy.source_roots` is `src` and its `kinds` are function, method and class — Python-symbol definitions — with `reference_extensions` added only to fold in the Python embedded in hook scripts; the policy's own scope is symbols and their references, not a cross-file naming convention.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
