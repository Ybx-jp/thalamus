## CLI flags

| Flag | Description | Example |
| :- | :- | :- |
| `--no-session-persistence` | Disable session persistence so sessions are not saved to disk and cannot be resumed. Print mode only. The [`CLAUDE_CODE_SKIP_PROMPT_HISTORY`](/docs/en/env-vars) environment variable does the same in any mode | `claude -p --no-session-persistence "query"` |
