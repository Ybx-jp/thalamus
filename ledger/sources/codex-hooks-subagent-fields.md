## Common input fields

Every command hook receives one JSON object on `stdin`.

These are the shared fields you will usually use:

| Field             | Type             | Meaning                                                             |
| ----------------- | ---------------- | ------------------------------------------------------------------- |
| `session_id`      | `string`         | Current Codex session id. Subagent hooks use the parent session id. |
| `transcript_path` | `string \| null` | Path to the session transcript file, if any                         |
| `cwd`             | `string`         | Working directory for the session                                   |
| `hook_event_name` | `string`         | Current hook event name                                             |
| `model`           | `string`         | Codex-specific extension. Active model slug                         |

Turn-scoped hooks list `turn_id` as a Codex-specific extension in their
event-specific tables.


### SubagentStart

`matcher` is applied to `agent_type` for this event.

Fields in addition to [Common input fields](#common-input-fields):

| Field             | Type     | Meaning                                        |
| ----------------- | -------- | ---------------------------------------------- |
| `turn_id`         | `string` | Codex-specific extension. Active Codex turn id |
| `agent_id`        | `string` | Identifier for the subagent                    |
| `agent_type`      | `string` | Subagent type or profile                       |
| `permission_mode` | `string` | Current permission mode                        |

Plain text on `stdout` is added as extra developer context for the subagent.

### PreToolUse

`PreToolUse` can intercept Bash, file edits performed through `apply_patch`,
MCP tool calls, and other local function tools. See [Tool
coverage](#tool-coverage) for the supported paths and exceptions.

`matcher` is applied to `tool_name` and matcher aliases. For file edits through
`apply_patch`, `matcher` values can use `apply_patch`, `Edit`, or `Write`; hook input
still reports `tool_name: "apply_patch"`.

Fields in addition to [Common input fields](#common-input-fields):

| Field         | Type         | Meaning                                                                                                                          |
| ------------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| `turn_id`     | `string`     | Codex-specific extension. Active Codex turn id                                                                                   |
| `tool_name`   | `string`     | Canonical hook tool name, such as `Bash`, `apply_patch`, or an MCP name like `mcp__fs__read`                                     |
| `tool_use_id` | `string`     | Tool-call id for this invocation                                                                                                 |
| `tool_input`  | `JSON value` | Tool-specific input. `Bash` and `apply_patch` use `tool_input.command`. MCP and other local function tools send their arguments. |

Plain text on `stdout` is ignored.
