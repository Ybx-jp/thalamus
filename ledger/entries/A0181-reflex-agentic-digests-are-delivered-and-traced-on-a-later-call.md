---
id: A0181-reflex-agentic-digests-are-delivered-and-traced-on-a-later-call
kind: claim
stated: 2026-09-24T20:35:41-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: ee96f2f4456f511410e1a3fea7dd396e123ab89048a972920181c8c1554401e8
---

## Assertion

A memory reflex firing on the agentic plan is not served by the hook that fired it: it is appended to its agent's pending job, and the digest the worker leaves ready is delivered as additionalContext by the carrier hook on a later tool call of the same session and agent. The delivery writes that firing's trace line, with its timestamp at the time of delivery, tool_name reflex_agentic, the pointer file as its response and the number of tool calls the transcript records after the triggering call as its depth, and charges the session's budget with the digest's characters, dropping whole a result that would cross it.

## Scope

metric: when and on which surface an agentic firing's digest reaches the agent, and what its trace line records
cohort: firings of thalamus reflex assigned the agentic plan, delivered through reflex-pointer-tap.sh on PostToolUse
condition: a digest whose agent makes no further successful tool call before its session ends is not delivered; depth is none when the hook payload carried no transcript or call id, or the transcript does not hold the triggering call

## Grounds

- code: src/thalamus/harness/reflex.py § "fire" =sha256:031232e668301a6cd9d47a992888bbbe633a568074e272b3920d5a212d60daa8
- code: src/thalamus/harness/reflex_worker.py § "deliver" =sha256:79995a9ad820d2ba7e4defc60408ddae05b1e634012ad54ea1a6621a970a64de
- code: src/thalamus/harness/hooks/claude-code/reflex-pointer-tap.sh § "context" =sha256:c108b12e3e4cdb154d6a9e1f58c3423d838ce6fdd7b02517e45016f0925ab1ed

## Warrant

fire returns an empty digest for an agentic firing after reflex_queue.enqueue appends it to the key directory named by its session and agent. The carrier's context assignment runs thalamus reflex --deliver for the payload's session and agent only when that key's ready directory holds a result, and prints its output as additionalContext. deliver takes the key's lock, sums the session's firing and delivery characters against ReflexBudget, records a result that does not fit as budget without a trace, and otherwise appends a trace line whose ts is the delivery time, whose tool_name is ARM_AGENTIC, whose tool_response is the pointer file and whose tool_input carries depth from tool_calls_after, then appends the digest's characters to the session's deliveries ledger, which fire and deliver both charge.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-24T23:02:47-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/reflex_worker.py § "deliver" =sha256:79995a9ad820d2ba7e4defc60408ddae05b1e634012ad54ea1a6621a970a64de
  artifact: sha256:c2c0b7f978e3343c50ec47e695c8592c6b7ee13f41392842b410f2f641ee22b3
  note: propagated from a moved ground
- 2026-09-24T23:02:59-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/reflex_worker.py § "deliver" =sha256:c2c0b7f978e3343c50ec47e695c8592c6b7ee13f41392842b410f2f641ee22b3
  note: deliver now copies the note, its check, its arm and its cited handles into the trace's tool_input and the outcome row; the trace's ts, tool_name, response and depth and the budget charge are unchanged, so the assertion is unaffected


## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/harness/reflex.py · standing · cites-as-live
