#!/bin/bash
# Thalamus beforeShellExecution hook — room boundary on the command channel (Cursor).
#
# The adapter half. One boundary (../claude-code/room-command-guard.sh), two harness
# contracts: this reshapes Cursor's stdin onto Claude Code's payload and maps the
# exit-code/stderr protocol onto Cursor's permission JSON, exactly as write-guard.sh
# does for its boundary.
#
# This is the *only* shape the room boundary can take on Cursor. `room-guard.sh`
# matches the `SendMessage` tool name and Cursor has no such tool, so peer traffic is
# a shell command or it is nothing — which is why the row in contract/boundaries.py
# read ABSENT while an addressable member existed.
#
# Measured 2026-08-13 (lab/065): `beforeShellExecution` fires *before* Cursor's own
# approval modal — a probe hook logged at 11:01:15 with the modal still unanswered at
# 11:01:20. So a denial here lands before the operator is asked to approve anything,
# rather than racing it.
#
# Cursor's contract (docs.cursor.com):
#   stdin:  {command, cwd, session_id/conversation_id, workspace_roots, ...}
#   stdout: {"permission": "allow"|"deny"|"ask", "agent_message": ..., "user_message": ...}

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"
. "$here/resolve-scope.sh"
thalamus_sandbox_guard

input=$(cat)

command=$(printf '%s' "$input" | jq -r '.command // empty')
if [ -z "$command" ]; then
  printf '{"permission": "allow"}\n'
  exit 0
fi

# `cwd` arrives as an empty string rather than null on Cursor's shell payloads, and
# jq's `//` does not fall through on an empty string — the defect that once wrote
# empty cwds into three ledgers from three adapters.
claude_payload=$(printf '%s' "$input" | jq -c \
  '{tool_name: "Bash",
    tool_input: {command: (.command // "")},
    session_id: (.session_id // .conversation_id // ""),
    cwd: (if (.cwd // "") != "" then .cwd else (.workspace_roots[0] // "") end)}')

set +e
stderr_msg=$(printf '%s' "$claude_payload" | "$here/../claude-code/room-command-guard.sh" 2>&1 >/dev/null)
rc=$?
set -e

if [ "$rc" -eq 2 ]; then
  # Both channels: on cursor/2026.08.11-e8db854 the denial's tool result carries
  # `user_message` and no occurrence of `agent_message`, so a guard explaining itself
  # only through the documented agent channel blocks in silence — and a block with no
  # reason is a stall.
  jq -n --arg msg "$stderr_msg" \
    '{permission: "deny",
      agent_message: $msg,
      user_message: $msg}'
else
  printf '{"permission": "allow"}\n'
fi
