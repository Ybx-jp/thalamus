---
id: A0057-threads-are-minted-only-by-distillation
kind: claim
stated: 2026-09-13T20:55:25-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 96f9620d86ed40b37ae886ee772c7ec55aa44047a04802a37bc0f0971cf364d6
---

## Assertion

A thread is minted only by distillation from a session that actually happened; an agent cannot open one directly, and its reach is limited to proposing a close, which the operator approves.

## Scope

metric: what can create a new Thread node, and what an agent can do toward closing one
cohort: every Thread node in the graph
condition: minting and the propose half of closing; approve is the operator's own action and not itself evidence of an agent's reach

## Grounds

- code: src/thalamus/substrate/writer.py § "_write_threads" =sha256:e7934b94b6af0e2b72bcf002ecdf55492b76151a621ad3a2290b199ae57e01ef
- code: src/thalamus/harness/closes.py § "propose" =sha256:292ebd6bb030e76cc0cd25912602dcdfa3f91a83ebd8f6c0d3b11bfc41e260ef

## Warrant

_write_threads is the only writer of Thread vertices and it runs inside distillation, not inside any live-session tool; propose is the one closing action exposed to an agent and writes only a ledger row, never the graph, which together is the boundary the assertion states.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
