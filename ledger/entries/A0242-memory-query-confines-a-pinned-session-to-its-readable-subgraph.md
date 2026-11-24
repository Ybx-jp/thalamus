---
id: A0242-memory-query-confines-a-pinned-session-to-its-readable-subgraph
kind: claim
stated: 2026-11-04T16:14:57-08:00
author: main
grade: argued
supersedes: A0149-memory-query-refuses-a-pinned-session
verbatim_change: the predecessor said memory_query refuses every pin but main because a free-form traversal cannot be confined; it now serves every pin, confining a non-main pin's traversal source with a SubgraphStrategy, so the cohort is unchanged and the condition names the confinement and the manifests it reads
verbatim_sha: 10eaa326aa20e62dbd7376ba09fe7f37326d734c2661d85323267a0198075df4
---

## Assertion

`memory_query` serves every pin. A session pinned to `main` traverses the whole graph; a session pinned to any other scope traverses a source whose SubgraphStrategy admits only the vertices that scope may read: every node in the scope itself, the global Artifact and Agent nodes, and from each other expert scope its knowledge subgraph, meaning a Claim no Session contains, a Chunk, an Entity or an article Source. Which pin a call is confined by comes from the server's own pin and manifests, never from the caller.

## Scope

metric: which vertices, and so which edges and aggregates, a memory_query traversal can reach for a given pin
cohort: every memory_query call, from any scope
condition: the knowledge scopes are the manifests on disk at call time, less the pinned scope; the confinement holds only while the source is not replaced or removed, which entry A0243 is about

## Grounds

- code: src/thalamus/harness/mcp_server.py § "memory_query" =sha256:cb05eb04f9774e105acdf043a1a2232dafd868cfec19a1c1a4741e2c70e890a2
- code: src/thalamus/substrate/query.py § "readable_subgraph" =sha256:88d58a66e2b9d05642b2a2baa8a994b1ec39be699f65172f04bbd1880b6cc781
- code: src/thalamus/substrate/query.py § "traversal_source" =sha256:0f2711fee2044f15d7c052b86c4f3ab2f4dc81f85a25dbaa610d3c4df9d2f03c
- code: src/thalamus/substrate/query.py § "sourced" =sha256:9db1015db0be79ab6d795809b80fba1fb765725d167fba23150c65b88ffd4c7c

## Warrant

memory_query passes no confinement when the process scope is main and otherwise passes the process scope with knowledge_scopes(); traversal_source turns a confinement into a SubgraphStrategy whose vertex criterion is readable_subgraph, which admits the scope, the global labels, and in the other scopes only the four knowledge shapes; sourced puts that source in place of the query's leading g. TinkerPop applies a SubgraphStrategy's vertex criterion to every vertex step and drops edges whose endpoints fail it, which a disposable 3.7.3 server seeded with episodic and knowledge nodes in two scopes showed for V(), E(), a walk through an Artifact, a direct V(id) and a mid-traversal V(). The operator decided on 2026-11-04 that the main-only refusal this entry supersedes is lifted, with recall's scope line as the confinement.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/harness/hooks/claude-code/graph-guard.sh · standing · cites-as-live
- src/thalamus/harness/mcp_server.py · standing · cites-as-live
- src/thalamus/harness/skills/gremlin-python/SKILL.md · standing · cites-as-live
- src/thalamus/substrate/query.py · standing · cites-as-live
