---
id: A0016-pin-is-checked-per-component-not-as-one-property
kind: claim
stated: 2026-09-13T20:14:38-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: b7dee252a9de18cdf3c30bc4385d739233764a5e5c15829e4932c0c635cbf1dc
---

## Assertion

A pin is not one property every harness carries equally; routing and the write/capability boundary bind on all of them, but the charter and per-scope MCP arming do not.

## Scope

metric: which pin properties each harness actually carries, and which it does not
cohort: the harnesses contract/pinning.py records
condition: the recorded properties only

## Grounds

- code: src/thalamus/contract/pinning.py § "PIN_ROWS" =sha256:201cf8dcec4edeb0fcca06cb9d070ecdd058a54243eb96c8067deb66d6a8d164

## Warrant

PIN_ROWS is the table stating, per component and per harness, which of these properties actually holds, so it is the ground for any claim about which bind everywhere and which do not.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
