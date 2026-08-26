#!/bin/bash
# Thalamus beforeShellExecution hook — a session does not write its own memory (Cursor).
#
# Thin adapter over ../claude-code/write-guard.sh: one detection logic, one event log
# (~/.thalamus/guards/), two harness contracts. The adapter reshapes Cursor's stdin
# into the Claude Code PreToolUse shape, runs the real guard, and maps its exit-2 +
# stderr protocol onto Cursor's permission JSON.
#
# The boundary is a decision about the graph (decided 2026-08-03), and the graph
# does not care which harness ran the command — so this is wired rather than left as a
# Claude-only gap, following `gremlin-guard.sh`, the other PreToolUse-on-Bash guard.
#
# Cursor's contract: stdin {command, cwd, sandbox} + common fields (conversation_id,
# ...); stdout {"permission": "allow"|"deny"|"ask", "agent_message": ...,
# "user_message": ...}.
#
# Install (project <root>/.cursor/hooks.json):
#   {"version": 1, "hooks": {"beforeShellExecution": [{"command":
#     "./src/thalamus/harness/hooks/cursor/write-guard.sh"}]}}

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"
. "$here/resolve-scope.sh"
thalamus_sandbox_guard

thalamus_read_guard_input write-guard.sh
input="$thalamus_guard_input"

# Called for the refusal, not the value: the reshaping below reads `.command`
# out of the payload itself. What this asks is whether there is one to read.
thalamus_read_guard_command write-guard.sh

claude_payload=$(printf '%s' "$input" | jq -c \
  '{tool_name: "Bash",
    tool_input: {command: (.command // "")},
    session_id: (.session_id // .conversation_id // ""),
    cwd: (if (.cwd // "") != "" then .cwd else (.workspace_roots[0] // "") end)}')

set +e
stderr_msg=$(printf '%s' "$claude_payload" | "$here/../claude-code/write-guard.sh" 2>&1 >/dev/null)
rc=$?
set -e

if [ "$rc" -eq 2 ]; then
  # Both channels, for the reason gremlin-guard's adapter measured: on
  # `cursor/2026.08.11-e8db854` the denial's tool result carries `user_message` and no
  # occurrence of `agent_message`, so a guard explaining itself only through the
  # documented agent channel blocks in silence — and a block with no reason is a stall.
  jq -n --arg msg "$stderr_msg" \
    '{permission: "deny",
      agent_message: $msg,
      user_message: $msg}'
else
  printf '{"permission": "allow"}\n'
fi
