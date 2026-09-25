---
id: A0179-every-budget-cap-forces-an-answer
kind: claim
stated: 2026-09-24T19:12:16-07:00
author: main
grade: measured
supersedes: A0187-budget-hook-counts-stops-and-forces-an-answer
verbatim_sha: 12d8512770975dd02b6f2183b42619472f0d02c4017f5df88f943a9ded5370f8
verbatim_change: a spent cap now asks the model for an answer, denying every further call in the prompt and stopping it only after three further denials, where the turn and tool-call caps had stopped it at once
---

## Assertion

budget.sh counts a scope's tool calls on PreToolUse and its tool-using turns on Claude Code's PostToolBatch, per prompt and per agent, and its tokens at PreToolUse. Past the turn cap it returns additionalContext from PostToolBatch asking the model to answer now; past a tool-call or token cap it denies the call, saying it was not run and asking for an answer; either way every further call in the prompt is denied, and on Claude Code the prompt is stopped after three further denials. On codex, which has no batch event and no stop from PreToolUse, it denies each further call and does not count turns.

## Scope

metric: what the budget guard counts, where, and what it returns past each cap on each harness
cohort: sessions whose resolved scope selects a budget preset, or that carry a THALAMUS_MAX_* override
condition: Measured 2026-09-24 on Claude Code 2.1.282 in print mode on haiku, the real hook wired by a settings overlay, three sequential echo calls against a control without the cap: THALAMUS_MAX_TOKENS=1 let the first call through (transcript lag) and denied the second, and the session ended end_turn with an answer naming what ran and what did not; THALAMUS_MAX_SUBAGENT_TOKENS=1 denied the subagent's first call and its answer reached the launcher. Told only to answer, one subagent reported output for the denied call; with the reason saying the call was not run, two further runs did not. THALAMUS_MAX_TURNS=1 injected the request at the first batch and the model answered with no further tool call; THALAMUS_MAX_TOOL_CALLS=1 denied the subagent's second call and its answer reached the launcher. Cursor sessions carry no prompt id and are not counted.

## Grounds

- code: src/thalamus/harness/budget.py § "decide" =sha256:5c80dc5bc1e55ba92863b0bd52c6df88edad53404a8a81198343bc355fb07964
- code: src/thalamus/harness/install.py § "HOOK_WIRING" =sha256:2240b5ea6b948770b72f725456548972aa00dc990a8e81fa8352d257e360ce2d
- code: src/thalamus/harness/install.py § "CODEX_HOOK_WIRING" =sha256:33201860cffc691d5af35d46ef7dd6da5014d1bcda2e966106d336c6726b351d
- entry: A0168-claude-code-hook-stop-and-prompt-id · cites-as-live
- entry: A0169-codex-pretooluse-denies-but-cannot-stop · cites-as-live
- entry: A0188-claude-code-posttoolbatch-context-reaches-the-next-request · cites-as-live

## Warrant

decide keys its counters on the prompt id or turn id and the agent id, counts tool calls on PreToolUse and turns on PostToolBatch, and checks tokens only at PreToolUse; the turn cap reached at PostToolBatch returns additionalContext asking for an answer (A0188), and a tool-call or token cap returns the deny alone with that request; the spent cap is kept on the agent's count, so every further PreToolUse in the prompt is denied, with continue false added once the denials pass FORCED_ANSWER_DENIALS, everywhere but codex. HOOK_WIRING wires the script on PreToolUse and PostToolBatch, CODEX_HOOK_WIRING on PreToolUse only. Claude Code stops the loop on continue false and names the prompt (A0168); codex denies on the deny shape and fails a hook that asks it to stop (A0169).

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-24T22:19:50-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/install.py § "HOOK_WIRING" =sha256:2240b5ea6b948770b72f725456548972aa00dc990a8e81fa8352d257e360ce2d
  artifact: sha256:55e36f47f67e88eeedc9235d80601a79a2c9f128e744eaeb4c87b16e0194b106
  note: propagated from a moved ground
- 2026-09-24T22:25:00-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/install.py § "HOOK_WIRING" =sha256:55e36f47f67e88eeedc9235d80601a79a2c9f128e744eaeb4c87b16e0194b106
  note: HOOK_WIRING gained a PostToolUseFailure row for reflex-pointer-tap.sh from the reflex qe branch's merge; budget.sh's rows on PreToolUse and PostToolBatch are unchanged, so the assertion is unaffected

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/harness/budget.py · standing · cites-as-live
- src/thalamus/harness/hooks/codex/budget.sh · standing · cites-as-live
- src/thalamus/harness/install.py · standing · cites-as-live
