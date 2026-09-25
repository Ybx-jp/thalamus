---
id: A0174-claude-code-subagent-hooks-name-the-launchers-transcript
kind: claim
stated: 2026-09-24T18:02:16-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 4dd77e54dcefd9b2eeb8109652aeaa0ae11808afabe5492414bc4426d76cb5fd
---

## Assertion

In Claude Code, a tool event fired inside a subagent carries the subagent's agent_id beside the session's transcript_path, which names the main session's transcript; the subagent's own transcript is a separate file in a subagents folder nested under the session, named for the agent id.

## Scope

metric: which transcript a Claude Code hook fired inside a subagent is pointed at, and where the subagent's own transcript is
cohort: Claude Code's hooks reference as retrieved on 2026-09-24
condition: the reference states transcript_path against agent_transcript_path for SubagentStop; for PreToolUse it was measured on Claude Code 2.1.282 (operator-run probe, one Bash call inside one general-purpose subagent): the payload carried agent_id a0ee019c92efe4044 and the session's transcript_path, and the subagent's model requests' usage was only in <session>/subagents/agent-a0ee019c92efe4044.jsonl

## Grounds

- source: claude-code-hooks-subagent-transcript · §Hooks in subagents
- source: claude-code-hooks-subagent-transcript · §SubagentStop input

## Warrant

The hooks-in-subagents paragraph says a subagent's tool events fire the configured hooks with agent_id and agent_type in the common fields; the SubagentStop input section says transcript_path is the main session's and agent_transcript_path is the subagent's own, nested in a subagents folder, and its example shows the path shape.

## Backing

- source: claude-code-hooks-subagent-transcript · §Hooks in subagents
  speaker: Anthropic
  quote: […] "the input carries the `agent_id` and `agent_type` [common input fields](#common-input-fields) that identify the subagent." […]
- source: claude-code-hooks-subagent-transcript · §SubagentStop input
  speaker: Anthropic
  quote: […] "The `transcript_path` is the main session's transcript, while `agent_transcript_path` is the subagent's own transcript stored in a nested `subagents/` folder." […]

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
