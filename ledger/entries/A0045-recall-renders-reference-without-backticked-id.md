---
id: A0045-recall-renders-reference-without-backticked-id
kind: claim
stated: 2026-09-13T20:43:01-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: bfb2ee97e14518c9337a6086bb692ced18cf7285f0183d3474e6621ca3d09386
---

## Assertion

Recall renders each `USES` reference as one plain line under the claim, without a backticked vertex ID.

## Scope

metric: whether a rendered reference line carries the target's raw vertex id
cohort: every claim recall renders with references
condition: the rendering function only

## Grounds

- code: src/thalamus/substrate/reader.py § "_attach_uses" =sha256:c90ce6a7efdacaaa9b6d693f1ab12e7dbe950a922f7a2d88bc34afe79fc55ee1

## Warrant

_attach_uses is what formats a claim's USES references for recall output, so its formatting choice is what settles whether an id appears in the rendered line.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
