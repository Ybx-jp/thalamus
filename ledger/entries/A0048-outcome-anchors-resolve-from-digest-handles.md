---
id: A0048-outcome-anchors-resolve-from-digest-handles
kind: claim
stated: 2026-09-13T20:46:22-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: ed41fcf890debae85a39f4b486ba6bb20593cfd3b11b9b984576d9f3007dbafa
---

## Assertion

Both a decision's and a solution's outcome carry `anchors`, message UUIDs resolved from the handles the digest exposed.

## Scope

metric: how an outcome's anchor UUIDs are derived
cohort: every decision or solution outcome an extraction names
condition: the resolution function only

## Grounds

- code: src/thalamus/harness/extraction.py § "resolve_anchors" =sha256:1bcbdeba17f4b8b36b43219a19959b7406c14aa1e660947712720924b8fe7d52

## Warrant

resolve_anchors is what turns a handle back into the message UUID it names, so it is the code producing exactly the anchors this claim describes.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
