---
id: A0243-memory-query-runs-as-gremlin-lang-on-a-read-only-source
kind: claim
stated: 2026-11-04T16:15:01-08:00
author: main
grade: argued
supersedes: none
verbatim_sha: d9f88c756611ee9e041e3b2bbdc5891938eeb9b1d60cdd58615ed5bf594663d9
---

## Assertion

`memory_query` submits every traversal with the gremlin-lang script engine named, on a source carrying ReadOnlyStrategy, and refuses before submission any text that would replace that source or run a second traversal: a withStrategies, withoutStrategies or withComputer step, a second `g` root, a statement separator, or a closure brace outside a string literal.

## Scope

metric: what the server is asked to evaluate for a memory_query call, and which query text never reaches it
cohort: every memory_query call, from any scope, and the profiles thalamus-measure runs through the same source
condition: the graph server is a Gremlin Server that honours the request's language argument; the 3.7.3 image this package ships does

## Grounds

- code: src/thalamus/substrate/query.py § "LANGUAGE" =sha256:174a00356319a4defd7372db4cbb48e1b980aa6e328bb67c816b3c9bc93d98d0
- code: src/thalamus/substrate/query.py § "_SOURCE_STEPS" =sha256:aa3545760ad3f453f0e138528c32cc9fdb94b87ead3a19f594ab3722a321269b
- code: src/thalamus/substrate/query.py § "_lexical_floor" =sha256:22a0f6b98c23c4c1c17c1f755b8de6c3c46007ddec37ddd8eefc07410af3bfbd
- code: src/thalamus/substrate/query.py § "validate_query" =sha256:650f467be9ef764458778fd522479b0812c1b299e680843592623536a693dcc1
- code: src/thalamus/substrate/query.py § "traversal_source" =sha256:0f2711fee2044f15d7c052b86c4f3ab2f4dc81f85a25dbaa610d3c4df9d2f03c
- code: src/thalamus/substrate/query.py § "run_query" =sha256:4bc93d3868207aba5974290cbbb4a71db8bf69e2569a20658d0b26cc4a1feb29
- entry: A0242-memory-query-confines-a-pinned-session-to-its-readable-subgraph · distinguishes

## Warrant

run_query returns validate_query's rejection before opening a client, and otherwise submits the sourced text with request option language set to LANGUAGE; traversal_source always begins withStrategies(ReadOnlyStrategy; validate_query refuses every _SOURCE_STEPS token in its compact view, and _lexical_floor refuses a semicolon, a brace and a bare g after position zero outside a string literal. Without the language argument the server's default engine is gremlin-groovy, where a closure and a statement after a semicolon both ran against the live server; with it, both failed at parse time, and a mutating step on the read-only source failed in the engine. The second root and the source steps are refused because the server ran every root it was sent and returned the last, and a later SubgraphStrategy replaced the confining one.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/substrate/query.py · standing · cites-as-live
