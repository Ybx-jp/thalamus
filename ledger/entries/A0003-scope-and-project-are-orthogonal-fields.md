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

## References

- docs/concepts.md · standing · cites-as-live
