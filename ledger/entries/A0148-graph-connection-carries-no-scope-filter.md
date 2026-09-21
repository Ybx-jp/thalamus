---
id: A0148-graph-connection-carries-no-scope-filter
kind: claim
stated: 2026-09-14T10:18:13-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 26ac3985064e06ded838d8802dab8cf55c4e55a5efa5855f4562838315c7da27
---

## Assertion

`connect()` hands back a traversal source over the whole graph, so scope confinement on a read is applied by the MCP tools above it rather than by the client any caller holds.

## Scope

metric: what a traversal source from connect can reach, and where confinement is applied instead
cohort: every caller that opens a graph connection
condition: the source connect returns; which tools above it confine a read, and how, are separate claims

## Grounds

- code: src/thalamus/substrate/writer.py § "connect" =sha256:d548f05b359efc17a85663eef589308e78deb34eaf2bd85a3d277fad4c486e08

## Warrant

connect probes the endpoint, wraps a DriverRemoteConnection for timing and returns the traversal source built on it; every step it takes is about reachability and instrumentation, so the source it returns is bounded by the graph and not by a caller's scope.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-20T20:37:07-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/substrate/writer.py § "connect" =sha256:d548f05b359efc17a85663eef589308e78deb34eaf2bd85a3d277fad4c486e08
  artifact: sha256:d90f6abc1f9e91af6c2c387e7dd8f030b7c16572b8c9319584d0b9e3fb9bc6fd
  note: propagated from a moved ground

- 2026-09-20T20:37:29-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/substrate/writer.py § "connect" =sha256:d90f6abc1f9e91af6c2c387e7dd8f030b7c16572b8c9319584d0b9e3fb9bc6fd
  note: the citation marker inside this section now names the entry by id alone, under the `citation-slug` rule `claims-ledger.toml` sets for source files, and the docstring was rewrapped. The assertion is unaffected.

## References

- README.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
- src/thalamus/substrate/writer.py · standing · cites-as-live
- src/thalamus/harness/skills/gremlin-python/SKILL.md · standing · cites-as-live
- src/thalamus/harness/hooks/claude-code/graph-guard.sh · standing · cites-as-live
