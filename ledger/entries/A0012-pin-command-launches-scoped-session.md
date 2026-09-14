---
id: A0012-pin-command-launches-scoped-session
kind: claim
stated: 2026-09-13T20:10:10-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 4212fa89f8fdf13fd992e26bae2391bf060f3a7073d0c20c9ca0ffdf492b9d4e
---

## Assertion

`thalamus pin <scope>` launches an agent session whose environment names that scope.

## Scope

metric: what the pin command does to start a session
cohort: every harness launch reachable through thalamus pin
condition: the launch call only; how each harness carries the scope onward afterward is a separate, per-component claim

## Grounds

- code: src/thalamus/harness/pin.py § "launch" =sha256:ce099670146c8d118e1423896cc58b595adca156fc1f3af3982c168eff1fcef7

## Warrant

launch is the function thalamus pin calls, and it is what sets the scope into the child process's environment before starting it.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
