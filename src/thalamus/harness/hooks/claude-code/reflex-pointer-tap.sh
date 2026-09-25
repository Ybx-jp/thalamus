#!/bin/bash
# Thalamus PostToolUse hook — memory reflex pointer-file tap (Claude Code).
#
# The reflex hands the agent a digest and keeps the records it indexes, verbatim, in
# a pointer file (`~/.thalamus/reflex/pointers/<session>/R<n>.md`). This tap records
# the agent opening one: any tool call whose input names a pointer file writes one
# trace line per file into the same monthly JSONL the memory tap writes, under
# tool_name "reflex_pointer_open", with the file's records as the response — so
# `eval sync` prices the read and attributes the nodes it put into context like any
# other retrieval, and `eval reflex` reads opens per firing beside the arms.
#
# An open is a secondary use signal: it says the agent looked, not that the record
# changed what it did, and an open event carries the position bias of whatever
# listing prompted it.
#
# Matched on every tool, because a file is read through `Read`, `Grep` and `Bash`
# (`cat`, `sed`, `head`) alike. A call whose raw payload never names the pointer
# directory exits on a string test before running anything else.
#
# Install (project .claude/settings.json):
#   {"hooks": {"PostToolUse": [{"hooks": [{"type": "command",
#     "command": "$CLAUDE_PROJECT_DIR/src/thalamus/harness/hooks/claude-code/reflex-pointer-tap.sh"}]}]}}

set -euo pipefail

input=$(</dev/stdin)

case "$input" in
  *.thalamus/reflex/pointers/*) ;;
  *) exit 0 ;;
esac

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_require_binaries jq || exit 0

session=$(printf '%s' "$input" | jq -r '.session_id // empty')
[ -n "$session" ] || exit 0

# Only the call's own input counts: a pointer path that shows up in a tool's *output*
# (a directory listing) is not the agent opening it.
paths=$(printf '%s' "$input" | jq -r '.tool_input | tostring' \
  | grep -oE '\.thalamus/reflex/pointers/[A-Za-z0-9._-]+/R[0-9]+\.md' | sort -u) || exit 0
[ -n "$paths" ] || exit 0

trace_dir="$HOME/.thalamus/traces"
mkdir -p "$trace_dir"
trace_file="$trace_dir/$(date -u +%Y-%m).jsonl"
scope="$(thalamus_scope_from_payload "$input")"
stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

while IFS= read -r rel; do
  pointer="$HOME/$rel"
  [ -f "$pointer" ] || continue
  firing=$(basename "$pointer" .md)
  printf '%s' "$input" | jq -c \
    --arg ts "$stamp" \
    --arg scope "$scope" \
    --arg pointer "$pointer" \
    --arg firing "$firing" \
    --rawfile records "$pointer" \
    '{ts: $ts,
      session_id: (.session_id // ""),
      scope: $scope,
      cwd: (.cwd // ""),
      tool_name: "reflex_pointer_open",
      tool_input: {firing_id: $firing, pointer: $pointer, via: (.tool_name // "")},
      tool_response: $records,
      agent_id: (.agent_id // ""),
      agent_type: (.agent_type // "")}' \
    >> "$trace_file"
done <<< "$paths"

exit 0
