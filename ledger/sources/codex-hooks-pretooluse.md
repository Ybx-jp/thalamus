### PreToolUse

| `turn_id` | `string` | Codex-specific extension. Active Codex turn id |

JSON on `stdout` can use `systemMessage`. To deny a supported tool call, return this hook-specific shape:

`permissionDecision: "ask"`, legacy `decision: "approve"`, `continue: false`, `stopReason`, and `suppressOutput` are parsed but not supported yet. Codex marks the hook run as failed, reports the error, and continues the tool call.
