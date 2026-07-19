#!/bin/bash
# Thalamus beforeShellExecution hook — gremlin terminal-step guard (Cursor).
#
# Thin adapter over ../claude-code/gremlin-guard.sh: one detection logic, one
# event log (~/.thalamus/guards/), two harness contracts. The adapter reshapes
# Cursor's stdin into the Claude Code PreToolUse shape, runs the real guard,
# and maps its exit-2 + stderr protocol onto Cursor's permission JSON.
#
# Cursor's contract: stdin {command, cwd, sandbox} + common fields
# (conversation_id, ...); stdout {"permission": "allow"|"deny"|"ask",
# "agent_message": ..., "user_message": ...}.
#
# Install (project <root>/.cursor/hooks.json):
#   {"version": 1, "hooks": {"beforeShellExecution": [{"command":
#     "./src/thalamus/harness/hooks/cursor/gremlin-guard.sh"}]}}

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"

input=$(cat)

command=$(printf '%s' "$input" | jq -r '.command // empty')
if [ -z "$command" ]; then
  printf '{"permission": "allow"}\n'
  exit 0
fi

claude_payload=$(printf '%s' "$input" | jq -c \
  '{tool_name: "Bash",
    tool_input: {command: (.command // "")},
    session_id: (.session_id // .conversation_id // ""),
    cwd: (.cwd // .workspace_roots[0] // "")}')

set +e
stderr_msg=$(printf '%s' "$claude_payload" | "$here/../claude-code/gremlin-guard.sh" 2>&1 >/dev/null)
rc=$?
set -e

if [ "$rc" -eq 2 ]; then
  jq -n --arg msg "$stderr_msg" \
    '{permission: "deny",
      agent_message: $msg,
      user_message: "Thalamus gremlin guard: blocked a lazy traversal with no terminal step"}'
else
  printf '{"permission": "allow"}\n'
fi
