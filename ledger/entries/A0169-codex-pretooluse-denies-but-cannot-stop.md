---
id: A0169-codex-pretooluse-denies-but-cannot-stop
kind: claim
stated: 2026-09-24T02:17:05-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: ed56c1fbf8e506b104aa49f1917f0a48a2660c513afd965faad35289e9cce270
---

## Assertion

In codex, a PreToolUse hook denies a tool call by returning permissionDecision deny, and its input carries a turn_id naming the active turn; a PreToolUse hook that returns continue false or stopReason is marked failed and the tool call goes ahead.

## Scope

metric: what a codex PreToolUse hook can do to a tool call and to the turn it belongs to
cohort: codex's hooks documentation as retrieved on 2026-09-24, for codex-cli 0.154.0
condition: PreToolUse only; PostToolUse and the compaction events have their own stop semantics

## Grounds

- source: codex-hooks-pretooluse · §PreToolUse

## Warrant

The PreToolUse section lists turn_id among its input fields, gives the deny shape as the way to deny a supported call, and lists continue false and stopReason among the outputs that are parsed but not supported, with the consequence that the run is marked failed and the call continues.

## Backing

- source: codex-hooks-pretooluse · §PreToolUse
  speaker: OpenAI
  quote: […] "To deny a supported tool call, return this hook-specific shape:"
- source: codex-hooks-pretooluse · §PreToolUse
  speaker: OpenAI
  quote: […] "are parsed but not supported yet. Codex marks the hook run as failed, reports the error, and continues the tool call."

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
