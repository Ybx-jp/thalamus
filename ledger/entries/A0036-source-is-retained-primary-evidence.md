---
id: A0036-source-is-retained-primary-evidence
kind: claim
stated: 2026-09-13T20:34:58-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 998e152e04d7a48b8deda4d7ff1ef196eca1295c68724700872a7fecb3e6d71d
---

## Assertion

`Source` is retained primary evidence -- a transcript or an ingested paper -- the same node type at a different trust tier depending on which.

## Scope

metric: what a Source node represents, and how a transcript and a paper differ as Sources
cohort: every Source node
condition: the node type only

## Grounds

- code: src/thalamus/substrate/schema.py § "Source" =sha256:46e5814d5548cf7d282afb0d4e58fca25ca3bdbb04caa82f4be71a28057f9dd8

## Warrant

Source is one class used for both a session transcript and an ingested document, distinguished only by the provenance tier stamped on the instance, which is exactly same node type, different tier.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
