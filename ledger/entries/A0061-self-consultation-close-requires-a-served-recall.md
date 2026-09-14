---
id: A0061-self-consultation-close-requires-a-served-recall
kind: claim
stated: 2026-09-13T20:59:53-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: f4cececde0152227cb8a8716f598b6d80bddb7882dd5e9e02d2f74a67e5faba5
---

## Assertion

A self-consultation's close is refused unless the server actually served a recall under that ticket.

## Scope

metric: whether a self-consultation can close without any ticketed read
cohort: self-consultations only
condition: this one gate; a cross-expert consultation's close is explicitly exempt from it

## Grounds

- code: src/thalamus/harness/consultation.py § "consult_answer" =sha256:cbdf5f0ea8341003e30f2439b10cc5c9b06d86b8aa401841cb19d53a03e185c7

## Warrant

consult_answer checks ticketed_recalls equal to zero together with expert equal to from_scope before rejecting, which is exactly the served-recall gate stated.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
