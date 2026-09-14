---
id: A0086-every-vertex-carries-provenance-and-scope
kind: claim
stated: 2026-09-13T20:11:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 6b4671a130322a396a907e78c04a776c2c84e13cae59cfb46ef2d5a2982806cc
---

## Assertion

Every vertex the contract accepts must carry a complete provenance envelope, and a scoped node type must declare a scope that agrees with the scope segment encoded in its own vertex ID.

## Scope

metric: what per-vertex obligations the contract audit checks before a vertex is accepted
cohort: every vertex label declared in the ontology
condition: does not cover edge-level obligations, which are audited by a separate function, and does not cover what happens to a vertex once the issue is reported

## Grounds

- code: src/thalamus/contract/conformance.py § "audit_vertices" =sha256:44c13881a3ea1fa81114577b5c83cbc34cd8ca0f23692099eeccb68fbecbeb7f

## Warrant

audit_vertices is the function that checks the provenance fields and the scope/ID agreement for every vertex passed to it, so its body is where these two obligations are actually enforced rather than merely documented.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- README.md · standing · cites-as-live
