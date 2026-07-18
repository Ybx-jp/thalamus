#!/bin/bash
# Thalamus PostToolUse hook — retrieval traces (Claude Code).
#
# The eval loop's layer-1 feed (docs/04): every call to a thalamus memory tool is
# recorded verbatim — what was asked, what came back, in which session. Used-vs-ignored
# attribution later matches these retrievals against the session's outputs (the retained
# transcript), so the trace must capture the full response, not a summary of it.
#
# Traces are append-only JSONL under ~/.thalamus/traces/, one file per month. This hook
# does no analysis — it is a tap, not a judge. M2 reads the tap.
#
# Install with a matcher so it only fires for thalamus tools (project .claude/settings.json):
#   {"hooks": {"PostToolUse": [{"matcher": "mcp__thalamus__.*", "hooks": [{"type": "command",
#     "command": "$CLAUDE_PROJECT_DIR/src/thalamus/harness/hooks/claude-code/post-tool-use.sh"}]}]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"

input=$(cat)

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')

# Belt and braces: the matcher should already scope us, but a misconfigured matcher
# must not turn this into a firehose of every tool call on the machine.
case "$tool_name" in
  mcp__thalamus__*) ;;
  *) exit 0 ;;
esac

trace_dir="$HOME/.thalamus/traces"
mkdir -p "$trace_dir"
trace_file="$trace_dir/$(date -u +%Y-%m).jsonl"

# scope: the pin, from the same env the MCP server read at process startup. The tap
# records it verbatim and judges nothing — eval sync validates it like any hint.
printf '%s' "$input" | jq -c \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg scope "$(thalamus_resolve_scope)" \
  '{ts: $ts,
    session_id: (.session_id // ""),
    scope: $scope,
    cwd: (.cwd // ""),
    tool_name: (.tool_name // ""),
    tool_input: (.tool_input // {}),
    tool_response: (.tool_response // "")}' >> "$trace_file"

exit 0
