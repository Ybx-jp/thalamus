---
id: A0001-pinned-scope-is-resolved-once-at-process-start
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 3a1818e15d9f9e83aecf110ef2237ec6d6cc8012bd92b0aafbc24206c194e817
---

## Assertion

The MCP server resolves the scope it serves once, at import time, from its own environment, so a session's pin is fixed for the life of the process.

## Scope

metric: where and how often the served scope is determined
cohort: the MCP server process a pinned session talks to
condition: the module-level binding only; what the individual tools then do with that scope is each tool's own claim

## Grounds

- code: src/thalamus/harness/mcp_server.py § "SCOPE" =sha256:73c525c221ca6e6b0c1dedf6f6e5bd7601dd1018ab7f47d1b126c2f6d2e90b70

## Warrant

The scope is a module-level binding evaluated when the module is imported, which happens once per process, and its only input is the process environment read by resolve_pin. A module-level name evaluated once cannot be re-evaluated later in the same process, so nothing after startup can move it.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CONTRIBUTING.md · standing · cites-as-live
- README.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
