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

## References

- README.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
