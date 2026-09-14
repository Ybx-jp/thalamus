---
id: A0006-capability-boundary-scopes-tools-and-skills
kind: claim
stated: 2026-09-13T20:04:28-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 5c3a6f542d433fd750884f8b63d8f2b4dc39f5bf81bff24caa1bc1568c067b9e
---

## Assertion

A manifest's `capability_boundary` field is what limits which skills and tools a scope may reach.

## Scope

metric: what capability_boundary governs
cohort: every scope that declares one
condition: the declared shape only; the roster-wide default a scope falls back to when it declares none is a separate mechanism

## Grounds

- code: src/thalamus/contract/manifest.py § "CapabilityBoundary" =sha256:5997af161249eb0766f8cb796bb0744329d36051964436ee2fc26b578af2e651

## Warrant

CapabilityBoundary is the model the manifest's capability_boundary field is typed as, so reading the class is reading exactly what the field can restrict.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
