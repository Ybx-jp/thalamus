---
id: A0022-ten-node-types-five-episodic
kind: claim
stated: 2026-09-13T20:20:20-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 380f482153a2516faaa8a061a94115495540ae560a60ce5616bfc0c3317265d6
---

## Assertion

The ontology declares ten node types, of which five are episodic -- `Session`, `Claim`, `Thread`, `Source` and `Artifact` -- joined by seventeen edge types.

## Scope

metric: how many node types and edge types the core ontology declares
cohort: the whole core ontology
condition: the declared tuples only; an expert manifest's own claim kinds are a separate, narrower declaration

## Grounds

- code: src/thalamus/contract/ontology.py § "CORE_NODES" =sha256:1e97534dc11a36702e206b1c7ed6b130893cec62239e379b1c87f8b6e81166ce
- code: src/thalamus/contract/ontology.py § "CORE_EDGES" =sha256:260d1ddb4d8430d74f1a1358eac836e58405ddea4676eee4a40e2b43f13c833d

## Warrant

CORE_NODES and CORE_EDGES are the literal tuples the ontology is built from, ten and seventeen entries respectively, and the five named node types are each a distinct entry in CORE_NODES, so counting settles the assertion directly.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
