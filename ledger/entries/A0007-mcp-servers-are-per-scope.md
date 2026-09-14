---
id: A0007-mcp-servers-are-per-scope
kind: claim
stated: 2026-09-13T20:05:35-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: f61bccd65a41bd9aee05c92681880b8b37a83790888c376b68e31ebaada3adc0
---

## Assertion

A scope can declare MCP servers of its own in `config/mcp/<scope>.json`, giving it tools that are reachable from that scope alone.

## Scope

metric: where a scope's own MCP configuration is read from
cohort: every scope with a config/mcp/<scope>.json file
condition: the per-scope config file resolution only

## Grounds

- code: src/thalamus/harness/pin.py § "scope_mcp_config" =sha256:6eb2907b01d7f82e3cd8780e6ff898406b85debb2acf7c48fea031ea49618600

## Warrant

scope_mcp_config is the function that resolves a scope's own MCP config path, so its existence is what makes a scope-specific tool set possible at all.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
