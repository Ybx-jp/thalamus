---
id: A0176-budget-session-total-and-subagent-token-caps
kind: claim
stated: 2026-09-24T18:57:25-07:00
author: main
grade: argued
supersedes: A0175-budget-hook-reads-a-subagents-own-transcript
verbatim_change: max_tokens widened from each agent's own spend to the session's total with every subagent added, and a subagent's own run moved to its own key, max_subagent_tokens
verbatim_sha: e743b1ae5216896c1d95ca981e613eb59480a6018c333d16732697138e393c1c
---

## Assertion

budget.sh counts max_tokens as the session's total, the session's own transcript plus every subagent transcript in the subagents folder beside it, and max_subagent_tokens as one subagent's own transcript alone; the session's cap, once its own hook has read it, is recorded and binds every subagent in the session whatever its scope's preset. On codex the total is read from the session's own rollout, and max_subagent_tokens is checked on Claude Code subagents.

## Scope

metric: which transcripts the budget guard sums for each token cap, per harness
cohort: sessions whose resolved scope selects a budget preset with max_tokens or max_subagent_tokens, or that carry THALAMUS_MAX_TOKENS or THALAMUS_MAX_SUBAGENT_TOKENS
condition: the path shape rests on A0174; summation over several subagents and the recorded cap binding an uncapped scope are tested against constructed transcripts; a live Claude Code 2.1.282 run with THALAMUS_MAX_SUBAGENT_TOKENS=1 denied the subagent's first call on its own count while the launcher's calls went through

## Grounds

- code: src/thalamus/harness/budget.py § "_claude_session_tokens" =sha256:8a166464871463df8e5b31d200c2dc5e9bd3dea41d9d4f003e7c9f579f8e8d8c
- code: src/thalamus/harness/budget.py § "_spent" =sha256:5ceeab571a78c7fc9fb8770afdccc196bc646f450f7ab9794cee7fa677103af5
- entry: A0174-claude-code-subagent-hooks-name-the-launchers-transcript · cites-as-live

## Warrant

_claude_session_tokens sums the session transcript and every agent-*.jsonl under its subagents folder; _spent records the session cap from the main agent's caps, checks the lower of it and the event's own max_tokens against that total (codex: its own rollout), and checks max_subagent_tokens against the subagent's own file on Claude Code only. A0174 is what makes those files the subagents' spend.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/harness/budget.py · standing · cites-as-live
