---
id: A0003-scope-and-project-are-orthogonal-fields
kind: claim
stated: 2026-09-13T20:01:07-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 38ed5f5fe38a8d5edd77142b43c5164574197ec46b37b8f5e9c2d5f8904e7b10
---

## Assertion

Scope and project are two independent fields on a session record -- which expert a session is pinned to, and which repository it ran in -- and a session carries both at once.

## Scope

metric: whether scope and project are the same field or two independent ones
cohort: every SessionGraph a session extracts to
condition: the field declarations only; how project is derived from repo_root is a separate claim this one does not cover

## Grounds

- code: src/thalamus/substrate/schema.py § "SessionGraph" =sha256:2f55fe7cdcb01048203b89a126d756807bb5ef3d6bc7d516358c20d7a3b54e7e

## Warrant

SessionGraph declares scope and project as two separate fields, and the project field's own description states it is orthogonal to scope, which is exactly the independence the assertion states.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-24T01:14:53-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/substrate/schema.py § "SessionGraph" =sha256:2f55fe7cdcb01048203b89a126d756807bb5ef3d6bc7d516358c20d7a3b54e7e
  artifact: sha256:39816ac9843eb35e21714e6f0c9cc24dd9302e5d43a567e5a8e0c4d7bb3a7ea9
  note: propagated from a moved ground
- 2026-09-24T01:16:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/substrate/schema.py § "SessionGraph" =sha256:39816ac9843eb35e21714e6f0c9cc24dd9302e5d43a567e5a8e0c4d7bb3a7ea9
  note: The docstring of a removed conformance wrapper moved onto SessionGraph.referenced_artifact_ids; the scope and project field declarations are unchanged, so the assertion is unaffected.

## References

- docs/concepts.md · standing · cites-as-live
