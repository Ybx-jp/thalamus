---
id: A0177-budget-hook-counts-stops-and-forces-an-answer
kind: claim
stated: 2026-09-24T18:57:25-07:00
author: main
grade: measured
supersedes: A0171-budget-hook-counts-per-prompt-and-stops-by-harness
verbatim_change: a spent token cap now denies the call and asks the model for an answer, stopping the prompt only after three further denials, where it had stopped the prompt at once; tokens are counted at PreToolUse only
verbatim_sha: 777ed4df6b68611a6caa1917abb6be5ca2d3e0545a9cbfad01c27582c142b6a1
---

## Assertion

budget.sh counts a scope's tool calls on PreToolUse and its tool-using turns on Claude Code's PostToolBatch, per prompt and per agent, and its tokens at PreToolUse; past a turn or tool-call cap it denies the call and stops the prompt on Claude Code, and past a token cap it denies the call and tells the model the call was not run and to answer now, stopping the prompt only after three further denials. On codex, which has no batch event and no stop from PreToolUse, it denies each further call and does not count turns.

## Scope

metric: what the budget guard counts, where, and what it returns past each cap on each harness
cohort: sessions whose resolved scope selects a budget preset, or that carry a THALAMUS_MAX_* override
condition: count caps as measured for A0171 on Claude Code 2.1.281. Token caps measured 2026-09-24 on Claude Code 2.1.282 in print mode on haiku, the real hook wired by a settings overlay, three sequential echo calls against a control without the cap: THALAMUS_MAX_TOKENS=1 let the first call through (transcript lag) and denied the second, and the session ended end_turn with an answer naming what ran and what did not; THALAMUS_MAX_SUBAGENT_TOKENS=1 denied the subagent's first call and its answer reached the launcher. Told only to answer, one subagent reported output for the denied call; with the reason saying the call was not run, two further runs did not. Cursor sessions carry no prompt id and are not counted.

## Grounds

- code: src/thalamus/harness/budget.py § "decide" =sha256:6d0b84cee8fb5f7134e584e324019836012ac6a35e5929333ea3c51ac770d36b
- code: src/thalamus/harness/install.py § "HOOK_WIRING" =sha256:b48f40f7442f0c734bb61a2cf21b1ee786ffaad2520924ac28b9751cd87b4689
- code: src/thalamus/harness/install.py § "CODEX_HOOK_WIRING" =sha256:f3fd9b66bd9b8643479ba2f3a66ac42235920dee5bd14eb831286cc9eb6a3122
- entry: A0168-claude-code-hook-stop-and-prompt-id · cites-as-live
- entry: A0169-codex-pretooluse-denies-but-cannot-stop · cites-as-live

## Warrant

decide keys its counters on the prompt id or turn id and the agent id, counts tool calls on PreToolUse and turns on PostToolBatch, and checks tokens only at PreToolUse; past a count cap it returns a deny carrying continue false everywhere but codex, or continue false alone from PostToolBatch; past a token cap it returns the deny alone with a reason asking for an answer, adding continue false once the agent's denials in the prompt pass FORCED_ANSWER_DENIALS. HOOK_WIRING wires the script on PreToolUse and PostToolBatch, CODEX_HOOK_WIRING on PreToolUse only. Claude Code stops the loop on continue false and names the prompt (A0168); codex denies on the deny shape and fails a hook that asks it to stop (A0169).

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/harness/budget.py · standing · cites-as-live
- src/thalamus/harness/hooks/codex/budget.sh · standing · cites-as-live
- src/thalamus/harness/install.py · standing · cites-as-live
