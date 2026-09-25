---
id: A0175-budget-hook-reads-a-subagents-own-transcript
kind: claim
stated: 2026-09-24T18:02:16-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: ae92fe8086af9d78d8c812cc6da809d6b034f8280d461ee74fda280dbd1116eb
---

## Assertion

On Claude Code, budget.sh counts a subagent's tokens from the subagent's own transcript, derived from the payload's transcript_path and agent_id, on a count separate from the session's; on codex it counts tokens for the main session only.

## Scope

metric: which transcript the budget guard reads a token count from, per agent and per harness
cohort: sessions whose resolved scope selects a budget preset with max_tokens, or that carry THALAMUS_MAX_TOKENS
condition: the path shape rests on A0174; tested against constructed transcripts, not yet against a live subagent run past a token cap

## Grounds

- code: src/thalamus/harness/budget.py § "_token_transcript" =sha256:d1c191139b2bdf4f8f0ed4f7b7b917ff5c0daa1bf8cbcf039e6b8ea5cd276fec
- entry: A0174-claude-code-subagent-hooks-name-the-launchers-transcript · cites-as-live

## Warrant

_token_transcript returns the payload's transcript for the main session, the sibling subagents/agent-<agent_id>.jsonl file for a Claude Code subagent, and nothing for a codex subagent; decide keys the token reading on the agent, so a subagent's count does not add to the session's. A0174 is what makes the derived path the subagent's.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/harness/budget.py · standing · cites-as-live
