---
id: A0055-consultation-exchange-is-the-only-live-write
kind: claim
stated: 2026-09-13T20:53:11-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: e5d551ef1da5d1981ab3dbde9ef8a00c84b5448a361c898f3d7ab973a0c1bb7e
---

## Assertion

A session does not write its own memory; the only episodic write available inside a live session is the consultation exchange, which records a crossing between scopes rather than the session's own beliefs.

## Scope

metric: which MCP tool call actually writes a graph node during a live session
cohort: every tool a pinned session can call while live
condition: the write path only; distillation's own after-the-fact write is a separate mechanism this claim does not cover

## Grounds

- code: src/thalamus/harness/consultation.py § "open_exchange" =sha256:e66086788582ab08550041e1fbca8da0061ead40074451400128dff6f7be461f

## Warrant

open_exchange is the one function among the MCP server's tool implementations that writes a vertex, and its own docstring states the mint is the write, which is exactly the only-episodic-write claim this describes.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
