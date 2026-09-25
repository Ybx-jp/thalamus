---
id: A0180-reflex-plans-are-assigned-in-balanced-blocks-of-three
kind: claim
stated: 2026-09-24T20:35:40-07:00
author: main
grade: measured
supersedes: A0176-reflex-plans-are-assigned-in-balanced-blocks
verbatim_change: the plan set grew from word match and propagation to add the agentic plan, so the cohort names sessions assigned under three plans and the condition records that a session spanning the change is not recomputable across it
verbatim_sha: ede4b43dbeb5ac22d75bd9341db3265aeb0ffcbf335ba98560067b29f0fde7fe
---

## Assertion

A memory reflex firing whose caller leaves the plan unset takes the next slot in its session's sequence of blocks, where each block holds word match, propagation and the agentic plan once each in an order drawn from the session id and the block's index, so the plans a session's firings were assigned differ in count by at most one and each assignment can be recomputed from the reflex ledger. Only ledger rows that carry a plan and ended served, empty, refused or queued advance the sequence.

## Scope

metric: which plan a reflex firing runs, and how the plans are balanced within a session
cohort: firings of thalamus reflex that pass every check needing no graph, with no plan fixed by the caller, in sessions whose firings were all assigned under the three-plan set
condition: two firings of one session at the same instant can read the same count and take the same slot, unbalancing that block by one; a session whose earlier firings were assigned under the two-plan set continues its count under three plans, so its blocks are not recomputable across the change

## Grounds

- code: src/thalamus/harness/reflex.py § "PLANS" =sha256:b4cf29d99104d2a403f256a6a5c5dbfa3cb9c90f1335009f6ac75d52114c325f
- code: src/thalamus/harness/reflex.py § "assign_plan" =sha256:e49247251370b2f26e7b8567829aa332adc6f549be8340e8c5095d560818e5ba
- code: src/thalamus/harness/reflex.py § "_ASSIGNED_OUTCOMES" =sha256:0b272149f49bd66110a807a870d42915b5e95782a846067419557cb7a3571151

## Warrant

PLANS names the three arms and _ASSIGNED_OUTCOMES the outcomes that count as assigned, queued among them for an agentic firing handed to the worker. assign_plan counts the session's ledger rows whose arm is one of PLANS and whose outcome is one of those, splits the count into a block index and a slot, and returns the slot's entry of PLANS shuffled by a random generator seeded with the session id and the block index; the seed makes the order a function of those two values alone, and a block of len(PLANS) consecutive slots is one permutation of PLANS.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/harness/reflex.py · standing · cites-as-live
