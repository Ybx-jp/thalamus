---
id: A0194-codex-subagent-hooks-inherit-env-and-carry-agent-id
kind: claim
stated: 2026-09-25T00:39:55-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 45d20dbc7f0be74a39de1e492c688ca03582b13c3bb33edd086d30851dab1bd9
---

## Assertion

In codex, a hook fired inside a subagent runs with the parent session's environment and under the parent's session id; its SubagentStart input carries the subagent's agent_id and agent_type, and on codex-cli 0.154.0 so does its PreToolUse input, where the parent session's own PreToolUse input has no agent_id.

## Scope

metric: what lets a codex hook tell a subagent's tool call from the session's own, and which environment it runs with
cohort: codex's hooks documentation as retrieved on 2026-09-25, for codex-cli 0.154.0
condition: the PreToolUse half is undocumented and was measured, not read: codex exec with the multi_agent feature, one subagent spawned through spawn_agent to run one Bash command, probe hooks inline by -c: with `env PROBE_TEMPLATE=<arm>` in front, the subagent's PreToolUse, SubagentStart and SubagentStop hooks all saw the variable (absent in the control); the subagent's PreToolUse payload carried its agent_id, agent_type default, the parent's session_id and a transcript_path naming the subagent's own rollout, and the session's PreToolUse payloads for spawn_agent, wait_agent and Bash carried no agent_id.

## Grounds

- source: codex-hooks-subagent-fields · §Common input fields
- source: codex-hooks-subagent-fields · §SubagentStart
- source: codex-hooks-subagent-fields · §PreToolUse

## Warrant

The common input fields say subagent hooks use the parent session id, so the session id cannot tell a subagent's call apart; the SubagentStart section lists agent_id and agent_type as its additional fields; the PreToolUse section's table does not list them, which is why the PreToolUse half rests on the measurement and on this version.

## Backing

- source: codex-hooks-subagent-fields · §Common input fields
  speaker: OpenAI
  quote: […] "Subagent hooks use the parent session id." […]
- source: codex-hooks-subagent-fields · §SubagentStart
  speaker: OpenAI
  quote: […] "| `agent_id`        | `string` | Identifier for the subagent                    |" […]

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
