---
id: A0052-transcript-ingress-floor-down-tiers-fetched-content
kind: claim
stated: 2026-09-13T20:50:50-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 77d84d832519e075a66789f7e1cc89eaf148b4b2f0c843fbbdd6727f65fa17bc
---

## Assertion

A claim distilled from a session that read a fetched web page cannot come out trusted the way a claim the agent reasoned to itself does; the transcript ingress floor down-tiers it, so distillation does not launder external content into first-party trust.

## Scope

metric: whether external content distilled through a session keeps first-party trust
cohort: every claim distilled from a session that fetched external content
condition: the down-tiering mechanism only

## Grounds

- code: src/thalamus/harness/extraction.py § "apply_ingress_floor" =sha256:ba7eb912db22a33630a8205e96cf5cb67fff0bac1ec27ec0f1405aa8db33af9d

## Warrant

apply_ingress_floor is the function that down-tiers exactly this content at distillation time, and its own docstring names this the write-path half of the laundering defense.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-18T16:14:12-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/extraction.py § "apply_ingress_floor" =sha256:ba7eb912db22a33630a8205e96cf5cb67fff0bac1ec27ec0f1405aa8db33af9d
  artifact: sha256:d67842e1031c75f28b6fbbb1714c6177e1233d506cc9e88d4b0c0b7e8794c2a0
  note: propagated from a moved ground
- 2026-10-18T16:25:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/harness/extraction.py § "apply_ingress_floor" =sha256:d67842e1031c75f28b6fbbb1714c6177e1233d506cc9e88d4b0c0b7e8794c2a0
  note: the docstring names the tokenizer word_forms, its public name now that the reflex plugin imports it; the floor's logic is unchanged, so the assertion is unaffected

## References

- README.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
