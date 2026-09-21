---
id: A0149-memory-query-refuses-a-pinned-session
kind: claim
stated: 2026-09-14T10:18:18-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 304fa391cc2fec0a1fa42c1d199130fe09b26352bd89d758321a55498d73cd65
---

## Assertion

`memory_query` answers a session pinned to any scope other than `main` with a refusal that redirects to a consultation ticket, on the stated ground that a free-form traversal cannot be confined to a scope.

## Scope

metric: which sessions memory_query serves and what a refused one is told
cohort: every memory_query call, from any scope
condition: this tool's own gate; the confinement the other recall tools apply is a separate mechanism

## Grounds

- code: src/thalamus/harness/mcp_server.py § "memory_query" =sha256:8f8a438ce029247cc5d956008335391abba6a730d33fa43f996bc35dbbbacf35

## Warrant

memory_query's first statement compares the process scope against the main scope and returns the refusal text before reaching run_query, so the gate and the redirect it names are both read directly off the tool body.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-20T20:37:07-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/mcp_server.py § "memory_query" =sha256:8f8a438ce029247cc5d956008335391abba6a730d33fa43f996bc35dbbbacf35
  artifact: sha256:2efd48e89d4df4d442710611f4c3c4360c279b7716ca05a2f34d275db5a0e275
  note: propagated from a moved ground

- 2026-09-20T20:37:29-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/mcp_server.py § "memory_query" =sha256:2efd48e89d4df4d442710611f4c3c4360c279b7716ca05a2f34d275db5a0e275
  note: the citation marker inside this section now names the entry by id alone, under the `citation-slug` rule `claims-ledger.toml` sets for source files. The assertion is unaffected.

## References

- src/thalamus/harness/skills/gremlin-python/SKILL.md · standing · cites-as-live
- src/thalamus/harness/mcp_server.py · standing · cites-as-live
- src/thalamus/harness/hooks/claude-code/graph-guard.sh · standing · cites-as-live
