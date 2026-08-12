#!/bin/bash
# Thalamus afterShellExecution hook — ad-hoc gremlin Bash tap (Cursor).
#
# Thin adapter over ../claude-code/gremlin-tap.sh: reshapes Cursor's stdin
# into the Claude Code PostToolUse shape so ad-hoc gremlin run from Cursor
# lands in the same monthly trace JSONL, as the same `bash_gremlin` records,
# priced by `eval sync` identically. Cursor's afterShellExecution carries one
# combined `output` string; it maps to the stdout leg of the trace record.
#
# Cursor's contract: stdin {command, output, duration, sandbox} + common
# fields. No output honored — fire-and-forget.
#
# Install (project <root>/.cursor/hooks.json):
#   {"version": 1, "hooks": {"afterShellExecution": [{"command":
#     "./src/thalamus/harness/hooks/cursor/gremlin-tap.sh"}]}}

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"
. "$here/resolve-scope.sh"
thalamus_sandbox_guard

printf '%s' "$(cat)" | jq -c \
  '{tool_name: "Bash",
    tool_input: {command: (.command // "")},
    tool_response: {stdout: (.output // ""), stderr: ""},
    session_id: (.session_id // .conversation_id // ""),
    cwd: (if (.cwd // "") != "" then .cwd else (.workspace_roots[0] // "") end)}' \
  | "$here/../claude-code/gremlin-tap.sh"
