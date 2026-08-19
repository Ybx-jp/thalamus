#!/bin/bash
# Thalamus PostToolUse hook — stage validated graph queries for RECIPES.md (codex).
#
# The gremlin-python skill's rule 5 ("check RECIPES.md before writing, add to it
# after validating") binds whoever is querying the graph, so the staging half is
# wired on every harness that can reach it. The skill ships at user scope and arms
# for codex sessions like any other.
#
# Same one reshaping step as ../codex/gremlin-tap.sh, for the same measured reason:
# codex sends a shell result as a single string and the real script reads
# `.tool_response.stdout` on the `Bash` surface. Without it every ad-hoc gremlin
# query would look like a traversal that answered nothing — the admission threshold
# is "it RAN and RETURNED something", so an unreshaped payload silently stages
# nothing at all.
#
# The `mcp__thalamus__memory_query` surface needs no reshaping: codex's MCP response
# is Claude Code's `{"content": [{"type": "text", …}]}` envelope, which the real
# script already reads.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

printf '%s' "$(cat)" | jq -c '
  if .tool_name == "Bash" and (.tool_response | type) == "string"
  then .tool_response = {stdout: .tool_response, stderr: ""}
  else . end' \
  | thalamus_codex_delegate recipe-stage.sh
