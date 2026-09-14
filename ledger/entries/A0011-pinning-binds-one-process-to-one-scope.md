---
id: A0011-pinning-binds-one-process-to-one-scope
kind: claim
stated: 2026-09-13T20:09:03-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 75b3f6327ff0888d6e24a111fa9639bd97b9b83b911a7f437001e47e33cfdb82
---

## Assertion

Routing between experts is not done by a classifier; it is done by pinning, so one OS process is bound to exactly one immutable scope for its whole life.

## Scope

metric: how a process's scope is decided, and how many times over its life
cohort: every process that reads its scope through resolve_pin
condition: the resolution mechanism only, not the per-harness carrier that makes the binding stick across tools

## Grounds

- code: src/thalamus/harness/pin.py § "resolve_pin" =sha256:b1133eb7a69ea289bc74e3627e9ef74dff013341ff3e7c9f1ee37b7390167a8f

## Warrant

resolve_pin is the one function that decides a process's scope from its environment, read once by the MCP server at import time, which is what makes the binding a per-process, immutable one rather than a routed decision.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
