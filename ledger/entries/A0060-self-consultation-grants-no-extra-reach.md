---
id: A0060-self-consultation-grants-no-extra-reach
kind: claim
stated: 2026-09-13T20:58:46-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: a5ebdb07621ef43246dd48ba2314f064c71a6d1ea0e340783ccc69119a818651
---

## Assertion

A scope may consult itself, but that ticket grants only the reach the session already had, and its answer corroborates nothing.

## Scope

metric: whether a self-consultation is allowed, and what it is worth if it proceeds
cohort: every consultation whose expert and from_scope are the same
condition: the refusal-decision function only

## Grounds

- code: src/thalamus/harness/consultation.py § "refuse_reason" =sha256:1faaf60d17576f64c6485c59044290c7145b19ccd9d2fce5da33f50ae112a81a

## Warrant

refuse_reason is what decides whether a self-consultation is allowed to proceed at all, so the constraints it enforces are the boundary this claim describes.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
