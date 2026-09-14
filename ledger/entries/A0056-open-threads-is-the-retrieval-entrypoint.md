---
id: A0056-open-threads-is-the-retrieval-entrypoint
kind: claim
stated: 2026-09-13T20:54:18-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 16c8e198eaa19571645b0baaae17ecc6de0d1234e537629c12433c52e84f939d
---

## Assertion

`memory_open_threads` is the entrypoint to the whole retrieval surface — the call a new session opens with.

## Scope

metric: which served tool is the one named for a session's first retrieval call
cohort: every new pinned session
condition: the tool's existence and role as the open-threads surface; enforcement of a harness actually calling it at session start is a separate, harness-specific claim

## Grounds

- code: src/thalamus/harness/mcp_server.py § "memory_open_threads" =sha256:54610625bb0bea0530f1e0a6d3429e714f41f4b342ca9d6a5f82a18bd69b40f0

## Warrant

memory_open_threads is the MCP tool named for exactly this retrieval surface, so its signature and docstring are what the entrypoint claim rests on.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
