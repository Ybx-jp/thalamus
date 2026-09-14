---
id: A0039-attribution-edges-are-scope-closed
kind: claim
stated: 2026-09-13T20:37:19-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: b4f4aa2398963c6d5be32006b6099372da1907b97a916a5af72b1a3f18ac623e
---

## Assertion

A `USES` edge reaches the claim's own scope or session-less knowledge in any scope, but never another scope's episodic memory; the write path drops a target that would cross that boundary.

## Scope

metric: which targets a USES edge is allowed to reach, and what happens when a target would cross scope
cohort: every USES edge a session write attempts
condition: this boundary rule only; the eval-verified stamp later applied to a surviving edge is a separate, later-arriving fact

## Grounds

- code: src/thalamus/contract/conformance.py § "audit_attribution" =sha256:c2d15ef4a05d6b4e3b54d4877993aed35eede816bce81a44d424a56664d1614b

## Warrant

audit_attribution is the check that classifies a USES edge crossing into another scope's episodic memory as a violation, which is the scope-closure rule the assertion states.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
