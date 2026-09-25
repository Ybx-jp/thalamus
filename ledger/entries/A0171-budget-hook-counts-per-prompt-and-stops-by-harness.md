---
id: A0171-budget-hook-counts-per-prompt-and-stops-by-harness
kind: claim
stated: 2026-09-24T02:17:06-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 21633201b320a0bdc7b68357f34545da125aa1f1f1a23d2011753d0a2065740e
---

## Assertion

budget.sh counts a scope's tool calls on PreToolUse and its tool-using turns on Claude Code's PostToolBatch, per prompt and per agent, and its tokens per session; past a cap it denies the call and stops the prompt on Claude Code, and on codex, which has no batch event and no stop from PreToolUse, it denies each further call and does not count turns.

## Scope

metric: what the budget guard counts, where, and what it returns past a cap on each harness
cohort: sessions whose resolved scope selects a budget preset, or that carry a THALAMUS_MAX_* override
condition: measured 2026-09-24 on Claude Code 2.1.281 in print mode with the hook wired by a settings overlay: a two-call cap stopped a four-call prompt after two calls, a two-turn cap after two turns, a one-token cap at the first batch; a resumed session's next prompt ran; a subagent capped at two calls stopped while its launcher went on. An interactive session stopped by a hook accepted the next prompt (operator-run probe). Cursor sessions carry no prompt id and are not counted.

## Grounds

- code: src/thalamus/harness/budget.py § "decide" =sha256:37113b8deb7cbd73f942247bae58f5c1e3134781e2d83a46d3959164ac4e8916
- code: src/thalamus/harness/install.py § "HOOK_WIRING" =sha256:d96c8cf3a9dcb537fecdcf0e63d1ee1a6f91006a65ed8cde66386bab5d0a5909
- code: src/thalamus/harness/install.py § "CODEX_HOOK_WIRING" =sha256:3d68726f767fa30fd31e21a2997285a9e7ac48534577f444b4c388a8c3a1c601
- entry: A0168-claude-code-hook-stop-and-prompt-id · cites-as-live
- entry: A0169-codex-pretooluse-denies-but-cannot-stop · cites-as-live

## Warrant

decide keys its counters on the prompt id or turn id and the agent id, counts tool calls on PreToolUse and turns on PostToolBatch, reads tokens for the main session, and past a cap returns a deny that carries continue false everywhere but codex, or continue false alone from PostToolBatch. HOOK_WIRING wires the script on PreToolUse and PostToolBatch, CODEX_HOOK_WIRING on PreToolUse only. Claude Code stops the loop on continue false and names the prompt (A0168); codex denies on the deny shape and fails a hook that asks it to stop (A0169).

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-24T18:04:05-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/budget.py § "decide" =sha256:37113b8deb7cbd73f942247bae58f5c1e3134781e2d83a46d3959164ac4e8916
  artifact: sha256:1a19031c5a6c63837c4c2ca7a75101f1a6e2c88741961067a8acb44ed1323957
  note: propagated from a moved ground
- 2026-09-24T18:06:00-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/budget.py § "decide" =sha256:1a19031c5a6c63837c4c2ca7a75101f1a6e2c88741961067a8acb44ed1323957
  note: decide now also reads a Claude Code subagent's tokens, from the subagent's own transcript, on the subagent's own count (A0175); what it counts for the main session and each prompt, and what it returns past a cap on each harness, is unchanged

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/harness/budget.py · standing · cites-as-live
- src/thalamus/harness/hooks/codex/budget.sh · standing · cites-as-live
- src/thalamus/harness/install.py · standing · cites-as-live
