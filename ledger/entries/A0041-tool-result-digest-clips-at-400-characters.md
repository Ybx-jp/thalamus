---
id: A0041-tool-result-digest-clips-at-400-characters
kind: claim
stated: 2026-09-13T20:39:33-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 701cb68146a600027236481c49d9f9e37b39905196029aa62fd04b6f4fd1999c
---

## Assertion

The digest served into a session clips a tool result at 400 characters, which is why a vertex ID rendered inside a recall bundle is usually cut off.

## Scope

metric: the character limit applied to a tool result inside the digest
cohort: every tool result the digest renders
condition: the constant only

## Grounds

- code: src/thalamus/harness/extraction.py § "_TOOL_RESULT_CAP" =sha256:06bf5be00fcd2e8d21686b633c5e9c286618c272a812b1f7a836e1502620c178

## Warrant

_TOOL_RESULT_CAP is the literal cap the digest applies to a tool result, so its value is exactly the number that decides whether a full vertex id survives.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
