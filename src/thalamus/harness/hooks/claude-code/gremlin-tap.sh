#!/bin/bash
# Thalamus PostToolUse hook — ad-hoc gremlin Bash tap (Claude Code).
#
# Ad-hoc gremlin-python run through Bash was the eval loop's dark surface: it
# queried the same graph as `memory_query` but left no trace, so its cost and
# utility were unmeasurable. This tap closes that gap by recording executed
# gremlin-marker Bash commands into the same monthly trace JSONL the memory
# tap writes, under tool_name "bash_gremlin", in the same record shape — so
# `eval sync` prices them exactly like memory_query traces (stdout chars are
# the injected_chars analog; used-vs-ignored attribution is unchanged). One
# priced surface, not a parallel metric.
#
# Same marker heuristic as gremlin-guard.sh: only commands whose text inlines
# gremlin-python are gremlin events. Script files are invisible here, as they
# are to the guard — a known, named residual.
#
# Install (project .claude/settings.json):
#   {"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
#     "command": "$CLAUDE_PROJECT_DIR/src/thalamus/harness/hooks/claude-code/gremlin-tap.sh"}]}]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

input=$(cat)

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')
[ "$tool_name" = "Bash" ] || exit 0

command=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
[ -n "$command" ] || exit 0

printf '%s' "$command" | grep -qE \
  'gremlin_python|with_remote\(|DriverRemoteConnection|substrate\.writer import|from thalamus\.substrate' \
  || exit 0

trace_dir="$HOME/.thalamus/traces"
mkdir -p "$trace_dir"
trace_file="$trace_dir/$(date -u +%Y-%m).jsonl"

# tool_response: stdout then stderr, as the model saw them. The trace parser
# backticks bare vertex IDs at read time so RETURNS extraction works on raw
# gremlin output too.
printf '%s' "$input" | jq -c \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg scope "$(thalamus_scope_from_payload "$input")" \
  '{ts: $ts,
    session_id: (.session_id // ""),
    scope: $scope,
    cwd: (.cwd // ""),
    tool_name: "bash_gremlin",
    tool_input: {command: (.tool_input.command // "")},
    tool_response: (((.tool_response.stdout // "") + (if (.tool_response.stderr // "") != "" then "\n" + .tool_response.stderr else "" end)))}' \
  >> "$trace_file"

exit 0
