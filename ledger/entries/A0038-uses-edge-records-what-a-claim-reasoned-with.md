---
id: A0038-uses-edge-records-what-a-claim-reasoned-with
kind: claim
stated: 2026-09-13T20:36:12-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 972b0597cfb9e73cf8ec4b4186a6c33d756d587141cbfaf1252b32f29f3139fd
---

## Assertion

A decision or solution that used something recalled as grounds carries a `USES` edge to it, with a `role` property saying how.

## Scope

metric: which edge type and property record what a claim used as grounds, and how
cohort: every decision or solution with a references list
condition: the write function only

## Grounds

- code: src/thalamus/substrate/writer.py § "_write_references" =sha256:56537f121ab92fd0f70df6e607609ea8c3371c7906ac3471b4961a64fa6e6aad

## Warrant

_write_references is the function that turns a claim's references into USES edges carrying a role property, so it is the code this assertion describes.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
