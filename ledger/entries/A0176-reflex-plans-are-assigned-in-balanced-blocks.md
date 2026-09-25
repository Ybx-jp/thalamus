---
id: A0176-reflex-plans-are-assigned-in-balanced-blocks
kind: claim
stated: 2026-09-24T18:02:47-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: d75102384aee95da33d926398c943c8bed6ff71b4ed926039436134f5fbb4648
---

## Assertion

A memory reflex firing whose caller leaves the plan unset takes the next slot in its session's sequence of blocks, where each block holds word match and propagation once each in an order drawn from the session id and the block's index, so the plans a session's firings were assigned differ in count by at most one and each assignment can be recomputed from the reflex ledger. Only ledger rows that carry a plan and ended served, empty or refused advance the sequence.

## Scope

metric: which plan a reflex firing runs, and how the plans are balanced within a session
cohort: firings of thalamus reflex that pass every check needing no graph, with no plan fixed by the caller
condition: two firings of one session at the same instant can read the same count and take the same slot, unbalancing that block by one

## Grounds

- code: src/thalamus/harness/reflex.py § "PLANS" =sha256:637c8afa57319b80578fa9228ae31197ea651b5a32e7543635fddbc4fe572249
- code: src/thalamus/harness/reflex.py § "assign_plan" =sha256:e49247251370b2f26e7b8567829aa332adc6f549be8340e8c5095d560818e5ba
- code: src/thalamus/harness/reflex.py § "_ASSIGNED_OUTCOMES" =sha256:bf579da76a06ec4a4f5fb305f2445f50f3f0a7cdcc05357b8a0c1fbaa9589c3b

## Warrant

PLANS names the two arms and _ASSIGNED_OUTCOMES the outcomes that count as assigned. assign_plan counts the session's ledger rows whose arm is one of PLANS and whose outcome is one of those, splits the count into a block index and a slot, and returns the slot's entry of PLANS shuffled by a random generator seeded with the session id and the block index; the seed makes the order a function of those two values alone, and a block of len(PLANS) consecutive slots is one permutation of PLANS.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-24T20:35:18-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/reflex.py § "PLANS" =sha256:637c8afa57319b80578fa9228ae31197ea651b5a32e7543635fddbc4fe572249
  artifact: sha256:b4cf29d99104d2a403f256a6a5c5dbfa3cb9c90f1335009f6ac75d52114c325f
  note: propagated from a moved ground

- 2026-09-24T20:35:18-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/reflex.py § "_ASSIGNED_OUTCOMES" =sha256:bf579da76a06ec4a4f5fb305f2445f50f3f0a7cdcc05357b8a0c1fbaa9589c3b
  artifact: sha256:0b272149f49bd66110a807a870d42915b5e95782a846067419557cb7a3571151
  note: propagated from a moved ground
- 2026-09-24T20:37:18-07:00 · superseded · grade: measured · author: main
  evidence: entry: A0180-reflex-plans-are-assigned-in-balanced-blocks-of-three · supersedes
  note: PLANS gained the agentic plan and _ASSIGNED_OUTCOMES gained queued; the block mechanism is unchanged and now permutes three plans


## References

