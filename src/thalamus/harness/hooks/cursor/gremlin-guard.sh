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
. "$here/resolve-scope.sh"
thalamus_sandbox_guard

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
    cwd: (if (.cwd // "") != "" then .cwd else (.workspace_roots[0] // "") end)}')

set +e
stderr_msg=$(printf '%s' "$claude_payload" | "$here/../claude-code/gremlin-guard.sh" 2>&1 >/dev/null)
rc=$?
set -e

if [ "$rc" -eq 2 ]; then
  # The reason rides BOTH channels, and that is measured rather than belt-and-braces.
  # In `agent -p` on 2026.08.11, `agent_message` reaches nothing — the denial's tool
  # result in the chat store carries the `user_message` text and no occurrence of the
  # other, so a guard that explains itself only through `agent_message` blocks in
  # silence. `agent_message` is the field the vendor documents for the agent and is
  # unmeasured interactively, so it keeps the same text rather than a stub: a reason
  # delivered twice costs a few tokens, and a block with no reason costs a stall —
  # 24.6% of failed trajectories are tool errors *or* blocked commands not followed
  # by effective recovery (Harness-Bench, arXiv 2605.27922, Table 3; the symptom
  # categories are non-exclusive, so this is not a clean slice of either).
  jq -n --arg msg "$stderr_msg" \
    '{permission: "deny",
      agent_message: $msg,
      user_message: $msg}'
else
  printf '{"permission": "allow"}\n'
fi
