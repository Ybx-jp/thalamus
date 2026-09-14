---
id: A0134-propose-writes-only-a-ledger-row-close-needs-operator
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 521b84f3f51249dee031822f386bc759aab2a13063501b5124c95642df0e0f50
---

## Assertion

Proposing a thread close writes a row to a local ledger and nothing to the graph, and the edge that actually closes a thread is written by a separate function whose own documentation states it runs on an operator's authority with no session behind it.

## Scope

metric: what a proposed close writes, and what writes the close itself
cohort: the close ledger's propose step and the graph's close-writing function
condition: not the approve, reject, pending or audit CLI verbs individually, only the write surface of propose and of the function that records a close in the graph

## Grounds

- code: src/thalamus/harness/closes.py § "propose" =sha256:292ebd6bb030e76cc0cd25912602dcdfa3f91a83ebd8f6c0d3b11bfc41e260ef
- code: src/thalamus/substrate/writer.py § "write_thread_close" =sha256:ee7888cc5e3ac82a3feb716836d78de55c48d02e244dea288ceea4a9539cfc6b

## Warrant

`propose`'s own docstring states it writes a ledger row and nothing to the graph, and `write_thread_close`'s docstring states it closes a thread on an operator's authority with no session behind it; together the two functions are the whole of what proposing and closing actually do to the graph.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
