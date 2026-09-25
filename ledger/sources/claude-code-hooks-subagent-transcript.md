### Hooks in subagents

Hooks from settings files, managed policy settings, and plugins also run inside [subagents](/docs/en/sub-agents). When a subagent calls a tool, tool events such as `PreToolUse` and `PostToolUse` fire the same configured hooks as in the main conversation, and the input carries the `agent_id` and `agent_type` [common input fields](#common-input-fields) that identify the subagent.

### SubagentStop input

In addition to the [common input fields](#common-input-fields), SubagentStop hooks receive `stop_hook_active`, `agent_id`, `agent_type`, `agent_transcript_path`, and `last_assistant_message`. The `agent_type` field is the value used for matcher filtering. The `transcript_path` is the main session's transcript, while `agent_transcript_path` is the subagent's own transcript stored in a nested `subagents/` folder. The `last_assistant_message` field contains the text content of the subagent's final response, so hooks can access it without parsing the transcript file.

"agent_transcript_path": "~/.claude/projects/.../abc123/subagents/agent-def456.jsonl",
