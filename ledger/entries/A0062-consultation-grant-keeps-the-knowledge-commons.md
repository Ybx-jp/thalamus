---
id: A0062-consultation-grant-keeps-the-knowledge-commons
kind: claim
stated: 2026-09-13T20:00:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 69724c30ae235b2e50f22ff06dc599c5f49888b42666c836ae5081276a41aab3
---

## Assertion

A consultation ticket's grant keeps the knowledge commons available, so a ticketed read is never poorer than an ambient one.

## Scope

metric: whether a ticketed recall can see less than an unticketed recall in the same scope
cohort: every recall made under a consultation ticket
condition: the scope-granting function only

## Grounds

- code: src/thalamus/harness/mcp_server.py § "_granted_scope" =sha256:52b991f1ce66224882d4419f1cdab022c51a7db2ec7dbf55e6dc425d8a755ea0

## Warrant

_granted_scope is what computes what a ticketed recall may read, and it adds to the session's own ambient scope rather than substituting a narrower one for it.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
