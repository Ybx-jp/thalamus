#!/bin/bash
# Thalamus afterMCPExecution hook — retrieval trace tap (Cursor).
#
# Thin adapter over ../claude-code/post-tool-use.sh, the eval loop's layer-1
# feed. Cursor reports MCP tools by BARE name (no mcp__<server>__ prefix), so
# the adapter gates on the thalamus tool roster and restores the
# `mcp__thalamus__` prefix before writing — trace records stay uniform across
# harnesses and `eval sync` needs no harness awareness.
#
# Cursor's contract: stdin {tool_name, tool_input, result_json, duration} +
# common fields. No output honored — fire-and-forget. Not supported in Cursor
# cloud agents (beforeMCPExecution/afterMCPExecution don't load there).
#
# Install (project <root>/.cursor/hooks.json):
#   {"version": 1, "hooks": {"afterMCPExecution": [{"command":
#     "./src/thalamus/harness/hooks/cursor/mcp-tap.sh"}]}}

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"
. "$here/resolve-scope.sh"
thalamus_sandbox_guard

input=$(cat)

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')
bare="${tool_name#mcp__thalamus__}"

# The thalamus MCP tool roster (harness/mcp_server.py) — anything else on this
# machine's MCP surface is not ours to trace.
case "$bare" in
  memory_recall|memory_recall_by_artifact|memory_recall_by_project|\
  memory_recall_recent|memory_open_threads|memory_open_problems|\
  memory_thread|memory_query|\
  memory_exchanges|memory_consultations|\
  consult_request|consult_answer|memory_visualize) ;;
  *) exit 0 ;;
esac

printf '%s' "$input" | jq -c --arg name "mcp__thalamus__${bare}" \
  '{tool_name: $name,
    tool_input: (.tool_input // {}),
    tool_response: (.result_json // ""),
    session_id: (.session_id // .conversation_id // ""),
    cwd: (.cwd // .workspace_roots[0] // "")}' \
  | "$here/../claude-code/post-tool-use.sh"
