---
id: A0033-claim-is-one-label-with-subtypes
kind: claim
stated: 2026-09-13T20:31:37-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: c38ed4de9f3b139a4d2fe28483115e8026960932489cee30949c739bb49b1415
---

## Assertion

`Claim` is one graph label discriminated by `kind`; `Decision`, `Problem` and `Solution` are subtypes of it in the type system rather than separate sibling labels.

## Scope

metric: whether Decision, Problem and Solution are distinct graph labels or subtypes of Claim
cohort: every decision, problem and solution a session extracts
condition: the class hierarchy only

## Grounds

- code: src/thalamus/substrate/schema.py § "Decision" =sha256:93aeef084350bba12930b1b6054fc3ea4a4af087be95cdff907aa7aa00ca013a
- code: src/thalamus/substrate/schema.py § "Problem" =sha256:9d188a943da4ce0361c811ca9ea6afae4d581a4b365725f28eeec104550548fd
- code: src/thalamus/substrate/schema.py § "Solution" =sha256:4ac143529613b74e7dbb5ca0fee9e03efa17dad2a27d86d2372a2129cd937738

## Warrant

Decision, Problem and Solution are each declared as a Python subclass of Claim, so the type system itself makes them subtypes rather than sibling labels.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
