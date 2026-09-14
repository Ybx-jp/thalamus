---
id: A0097-every-memory-call-is-trace-tapped
kind: claim
stated: 2026-09-13T20:22:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: a6a2165306f60a34e0d1365d1f7fc1649a8629bb7a8659bd6a3361c2320e6941
---

## Assertion

A memory-tool call is recorded by the trace tap as one TraceEvent, carrying the pin, the agent context and the tool's own input and response.

## Scope

metric: what fields a recorded memory-tool call carries and where they come from
cohort: every memory-tool call the tap observes, from the main loop or a subagent
condition: does not cover how a recorded event is later judged used-vs-ignored or priced in tokens, only what the tap records at call time

## Grounds

- code: src/thalamus/eval/traces.py § "TraceEvent" =sha256:ac79ce0914dc51e3628f2a29d894c55d31106bf47f70e26a2350de65079105e3

## Warrant

TraceEvent's docstring states it is one memory-tool call as the tap recorded it, and its fields are exactly the scope, agent context and tool input/response the claim describes, so the section is the record structure the trace tap actually produces.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- README.md · standing · cites-as-live
