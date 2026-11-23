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

- 2026-11-23T11:03:32-08:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/consultation.py § "refuse_reason" =sha256:1faaf60d17576f64c6485c59044290c7145b19ccd9d2fce5da33f50ae112a81a
  artifact: sha256:ee69a272305486281a62332bf69d3f7a7262d28bc88acccb1159ed8c2e2d6f14
  note: propagated from a moved ground
- 2026-11-23T11:03:32-08:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/consultation.py § "refuse_reason" =sha256:ee69a272305486281a62332bf69d3f7a7262d28bc88acccb1159ed8c2e2d6f14
  note: a comment in refuse_reason was corrected to say a call does not name which agent made it; the self-consultation rule and its checks are unchanged, so the assertion is unaffected

## References

- docs/concepts.md · standing · cites-as-live
