---
id: A0171-vocabulary-rows-are-confined-to-the-readable-scope
kind: claim
stated: 2026-09-24T02:00:40-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 6639e5c5f01fa44f798366519b6142ccab57c017aa89c8807475a6961f2be502
---

## Assertion

Every retrieval-vocabulary primitive returns only nodes the calling scope may read, whatever its walk passed through: a Session, a Thread or a session-contained Claim only from the scope itself, a Claim contained by no Session or a Chunk only from the scope or a granted knowledge scope, and no Artifact, Entity or other node as a result; resolve renders nothing for a node outside that set.

## Scope

metric: which vertices appear in the rows or the rendering a vocabulary primitive returns for a given scope and knowledge-scope grant
cohort: calls to lexical_by_kind, expand_one_hop, session_claims, chunks_near_source, by_path, threads_by_topic and resolve, from the reflex compiler and from the MCP wrappers
condition: the scope and the knowledge scopes are the caller's grant; the claim is about what the primitive returns given them, not about how the grant is decided

## Grounds

- code: src/thalamus/substrate/vocabulary.py § "_row" =sha256:17a4ecc4b35de0e52fe418a594bb2f410f17812da233ba3b060f5850265424df
- code: src/thalamus/substrate/vocabulary.py § "rows_for" =sha256:5c29770871243cf34e8d0f06f7e69aa0b0f8b5822cc7d10718adb1fc7d92b7fb
- code: src/thalamus/substrate/vocabulary.py § "lexical_by_kind" =sha256:5ba2e41761ea4b7715e7b2297990def537c5c64d955de765fab3a6d259de61f7
- code: src/thalamus/substrate/vocabulary.py § "expand_one_hop" =sha256:d3f1beb692d91cdbfaa0302a4fe99b6cab66975bb1aaeb208784f463c56a664a
- code: src/thalamus/substrate/vocabulary.py § "session_claims" =sha256:c7804aa04d19f1556b85968eaaa27db9f8ea684db75ed63e48ae2c69f9bf8c0c
- code: src/thalamus/substrate/vocabulary.py § "chunks_near_source" =sha256:3fc48989ac800b5a106ca14c7ab50bc56f4b9fa5006d6cf7965420dfeab05984
- code: src/thalamus/substrate/vocabulary.py § "by_path" =sha256:5f5a719d8d0b8ea9c0145519b2f0d5b0e3de0060908107ccfbbeaecfa31350b6
- code: src/thalamus/substrate/vocabulary.py § "threads_by_topic" =sha256:5f2777e9d1a18ba606c1c2d84cc4864caf7579f53526e0cc364121a914c69452
- code: src/thalamus/substrate/vocabulary.py § "resolve" =sha256:1de7f448944e5ef9c28601a9635ce539ea97c4097597fba921b9cd62f784b0c7

## Warrant

_row returns None for a Session, Thread or session-contained Claim whose id carries another scope, for a knowledge Claim or Chunk whose scope is neither the caller's nor granted, and for every other label; rows_for keeps only what _row returns. Each primitive returns the output of rows_for over its candidates and nothing else, and those that walk from a node first require that node to pass rows_for. resolve calls rows_for on the requested node and returns None before loading anything when it does not pass.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/harness/mcp_server.py · standing · cites-as-live
- src/thalamus/substrate/vocabulary.py · standing · cites-as-live
