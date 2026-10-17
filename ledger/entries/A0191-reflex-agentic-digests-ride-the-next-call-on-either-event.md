---
id: A0191-reflex-agentic-digests-ride-the-next-call-on-either-event
kind: claim
stated: 2026-09-24T23:06:26-07:00
author: main
grade: measured
supersedes: A0181-reflex-agentic-digests-are-delivered-and-traced-on-a-later-call
verbatim_change: the carrier is wired on PostToolUseFailure as well as PostToolUse, so the cohort covers delivery on either event and a failed next call no longer holds a digest back
verbatim_sha: 4bea258c68671fbffcafc92e42dcb4f04c5397943fef9d005770ea7ff51a12e0
---

## Assertion

A memory reflex firing on the agentic plan is not served by the hook that fired it: it is appended to its agent's pending job, and the digest the worker leaves ready is delivered as additionalContext by the carrier hook on a later tool call of the same session and agent, whether that call succeeded or failed. The delivery writes that firing's trace line, with its timestamp at the time of delivery, tool_name reflex_agentic, the pointer file as its response and the number of tool calls the transcript records after the triggering call as its depth, and charges the session's budget with the digest's characters, dropping whole a result that would cross it.

## Scope

metric: when and on which surface an agentic firing's digest reaches the agent, and what its trace line records
cohort: firings of thalamus reflex assigned the agentic plan, delivered through reflex-pointer-tap.sh on PostToolUse or PostToolUseFailure
condition: a digest whose agent makes no further tool call before its session ends is not delivered; depth is none when the hook payload carried no transcript or call id, or the transcript does not hold the triggering call

## Grounds

- code: src/thalamus/harness/reflex.py § "fire" =sha256:031232e668301a6cd9d47a992888bbbe633a568074e272b3920d5a212d60daa8
- code: src/thalamus/harness/reflex_worker.py § "deliver" =sha256:c2c0b7f978e3343c50ec47e695c8592c6b7ee13f41392842b410f2f641ee22b3
- code: src/thalamus/harness/hooks/claude-code/reflex-pointer-tap.sh § "context" =sha256:c108b12e3e4cdb154d6a9e1f58c3423d838ce6fdd7b02517e45016f0925ab1ed
- code: src/thalamus/harness/install.py § "HOOK_WIRING" =sha256:55e36f47f67e88eeedc9235d80601a79a2c9f128e744eaeb4c87b16e0194b106

## Warrant

fire returns an empty digest for an agentic firing after reflex_queue.enqueue appends it to the key directory named by its session and agent. HOOK_WIRING runs reflex-pointer-tap.sh with no matcher on both PostToolUse and PostToolUseFailure. The carrier's context assignment runs thalamus reflex --deliver for the payload's session and agent only when that key's ready directory holds a result, and prints its output as additionalContext under the payload's hook_event_name. deliver takes the key's lock, sums the session's firing and delivery characters against ReflexBudget, records a result that does not fit as budget without a trace, and otherwise appends a trace line whose ts is the delivery time, whose tool_name is ARM_AGENTIC, whose tool_response is the pointer file and whose tool_input carries depth from tool_calls_after, then appends the digest's characters to the session's deliveries ledger, which fire and deliver both charge.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts
- 2026-09-28T17:12:02-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/reflex_worker.py § "deliver" =sha256:20634ac43b350b4afc0c6ae0327fd0c43771b5573cbdf9c5700f5880762e61b8
  note: deliver now also copies listwise, verdicts and admit_ms into the trace's tool_input; the trace's ts, tool_name, response and depth and the budget charge are unchanged, so the assertion is unaffected
- 2026-10-08T00:17:08-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/reflex.py § "fire" =sha256:031232e668301a6cd9d47a992888bbbe633a568074e272b3920d5a212d60daa8
  artifact: sha256:861aa97e16791bb83e7d98d65334302056c2d753016b4dfeb7821cbc1ff99746
  note: propagated from a moved ground

- 2026-10-08T00:17:08-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/reflex_worker.py § "deliver" =sha256:20634ac43b350b4afc0c6ae0327fd0c43771b5573cbdf9c5700f5880762e61b8
  artifact: sha256:446ba82234f6e8bdc594bb5d62c71519472c090a4970842166606bbe43ee67a5
  note: propagated from a moved ground

- 2026-10-08T00:20:00-07:00 · corroborated · grade: argued · author: main
  evidence: code: src/thalamus/harness/reflex.py § "fire" =sha256:861aa97e16791bb83e7d98d65334302056c2d753016b4dfeb7821cbc1ff99746
  note: Read at the current revision. The agentic firing is still appended to its agent's pending job and the hook returns; only the spawn_worker call gained the concurrent flag — the assertion is unaffected.

- 2026-10-08T00:20:00-07:00 · corroborated · grade: argued · author: main
  evidence: code: src/thalamus/harness/reflex_worker.py § "deliver" =sha256:446ba82234f6e8bdc594bb5d62c71519472c090a4970842166606bbe43ee67a5
  note: Read at the current revision. deliver copies the job's channel, model and channel_run figures into the outcome row and the trace's tool_input; the delivery-time trace, depth and budget charge are unchanged — the assertion is unaffected.
- 2026-10-16T21:58:03-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/hooks/claude-code/reflex-pointer-tap.sh § "context" =sha256:c108b12e3e4cdb154d6a9e1f58c3423d838ce6fdd7b02517e45016f0925ab1ed
  artifact: sha256:3470b84f12164ccfdd489a9fa6c6003269a5f5af5e35ebd752a17db9c16abc8c
  note: propagated from a moved ground
- 2026-10-16T22:10:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/harness/hooks/claude-code/reflex-pointer-tap.sh § "context" =sha256:3470b84f12164ccfdd489a9fa6c6003269a5f5af5e35ebd752a17db9c16abc8c
  note: reflex-pointer-tap.sh runs the carrier through thalamus_cli_argv instead of `uv run --project`; delivery is unchanged. #35 makes an installed wheel resolve its own files and run itself (contract/paths.py). The assertion is unaffected.

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/harness/reflex.py · standing · cites-as-live
