---
id: A0089-check-stops-before-the-model-call
kind: claim
stated: 2026-09-13T20:14:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 4c3c5162affbb388c83c585c1ed5543339b3c2eb32daf1092bf0aade247a13c6
---

## Assertion

`--check` runs the identical code path a full ingest runs, up to but not including the model call, so the two cannot disagree about what a source is.

## Scope

metric: how much of the ingest path --check exercises before stopping
cohort: every ingest invocation, --check and the full run alike
condition: does not cover what --write does with the confirmed bytes afterward, only the portion of the path both runs share

## Grounds

- code: src/thalamus/harness/ingest.py § "preflight" =sha256:844f1bc61b4b2ba00cfe6b7f76f8babbc8e51a1b1514e1442a609b8e1872c1d1

## Warrant

preflight's own docstring states it is every step of ingest() that precedes the model call and that --check runs it on its own, and ingest() itself calls preflight as its first step, so the section is literally the shared code both paths execute.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- README.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
