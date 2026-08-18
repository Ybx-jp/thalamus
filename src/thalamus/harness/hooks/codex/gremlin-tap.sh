#!/bin/bash
# Thalamus PostToolUse hook — ad-hoc gremlin Bash tap (codex).
#
# One reshaping step, and it is the only place codex's payload is not literally
# Claude Code's. Measured 2026-08-17: codex reports a shell result as a **single
# string** —
#
#   {"tool_name": "Bash", "tool_input": {"command": "cat note.txt"},
#    "tool_response": "hello\n"}
#
# — where Claude Code sends `{stdout, stderr, …}`. The real tap reads
# `.tool_response.stdout`, so an unreshaped codex payload would record every ad-hoc
# gremlin query with an empty response: the query would be priced at zero injected
# chars and read as a traversal that returned nothing, which is exactly the failure
# the gremlin skill is about. The combined string goes on the stdout leg, the same
# mapping ../cursor/gremlin-tap.sh makes for `afterShellExecution`'s `output`.
#
# Guarded on `tool_name == "Bash"` rather than applied to every string: the MCP taps
# on this event carry an object response, and rewriting one would corrupt a record
# that is already correct.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

printf '%s' "$(cat)" | jq -c '
  if .tool_name == "Bash" and (.tool_response | type) == "string"
  then .tool_response = {stdout: .tool_response, stderr: ""}
  else . end' \
  | thalamus_codex_delegate gremlin-tap.sh
