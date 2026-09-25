#!/bin/bash
# Thalamus PostToolUse / PostToolUseFailure hook — memory reflex carrier and
# pointer-file tap (Claude Code).
#
# Two jobs on every tool call, each behind a test that costs no process when it fails.
#
# The carrier. A reflex firing assigned the agentic plan is not served from the hook
# that fired it: a local model's loop runs in a detached worker (harness/reflex_worker.py)
# and leaves its digest in `~/.thalamus/reflex/queue/<session>/<agent>/ready/`. On the
# agent's next tool call this hook delivers it as `additionalContext` through
# `thalamus reflex --deliver`, which charges the session's budget and writes the trace
# line with the depth at delivery. A synchronous hook's output reaches the subagent
# whose call ran it (docs/14 §4, measured on 2.1.281), so the key carries the agent.
# The test before any `uv run` is a glob over the session's ready directories.
#
# The tap. The reflex hands the agent a digest and keeps the records it indexes,
# verbatim, in a pointer file (`~/.thalamus/reflex/pointers/<session>/R<n>.md`). Any
# tool call whose input names a pointer file writes one trace line per file into the
# same monthly JSONL the memory tap writes, under tool_name "reflex_pointer_open", with
# the file's records as the response — so `eval sync` prices the read and attributes
# the nodes it put into context like any other retrieval, and `eval reflex` reads
# opens per firing beside the arms. An open is a secondary use signal: it says the
# agent looked, not that the record changed what it did, and an open event carries
# the position bias of whatever listing prompted it.
#
# Matched on every tool, because a file is read through `Read`, `Grep` and `Bash`
# (`cat`, `sed`, `head`) alike, and wired on both events a call can end on, so a digest
# waiting for the agent does not wait longer because its next call failed. Both events
# carry `tool_input` and accept `additionalContext`; the script reads `hook_event_name`
# and answers under whichever event ran it.
#
# Install (project .claude/settings.json), the same group under each event:
#   {"hooks": {"PostToolUse": [{"hooks": [{"type": "command",
#     "command": "$CLAUDE_PROJECT_DIR/src/thalamus/harness/hooks/claude-code/reflex-pointer-tap.sh"}]}],
#     "PostToolUseFailure": [ …the same group… ]}}

set -euo pipefail

input=$(</dev/stdin)

# Everything before the two tests below is bash builtins: most calls end here, and a
# call that ends here has run no process.
#
# `session_id` is the payload's first field; a later match inside a tool's input or
# output is escaped and does not match this pattern.
session=""
if [[ $input =~ \"session_id\"[[:space:]]*:[[:space:]]*\"([A-Za-z0-9._-]+)\" ]]; then
  session="${BASH_REMATCH[1]}"
fi

ready=0
if [ -n "$session" ]; then
  for f in "$HOME/.thalamus/reflex/queue/$session"/*/ready/*.json; do
    [ -e "$f" ] && ready=1
    break
  done
fi

case "$input" in
  *.thalamus/reflex/pointers/*) pointer_named=1 ;;
  *) pointer_named=0 ;;
esac

[ "$ready" = 1 ] || [ "$pointer_named" = 1 ] || exit 0

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_require_binaries jq || exit 0

session=$(printf '%s' "$input" | jq -r '.session_id // empty')
[ -n "$session" ] || exit 0

if [ "$pointer_named" = 1 ]; then
  # Only the call's own input counts: a pointer path that shows up in a tool's
  # *output* (a directory listing) is not the agent opening it.
  paths=$(printf '%s' "$input" | jq -r '.tool_input | tostring' \
    | grep -oE '\.thalamus/reflex/pointers/[A-Za-z0-9._-]+/R[0-9]+\.md' | sort -u) || paths=""
  if [ -n "$paths" ]; then
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
  fi
fi

[ "$ready" = 1 ] || exit 0
thalamus_require_binaries uv || exit 0

agent_id=$(printf '%s' "$input" | jq -r '.agent_id // ""')
key="${agent_id:-session}"
has_ready=0
for f in "$HOME/.thalamus/reflex/queue/$session/$key/ready"/*.json; do
  [ -e "$f" ] && has_ready=1
  break
done
[ "$has_ready" = 1 ] || exit 0

event=$(printf '%s' "$input" | jq -r '.hook_event_name // "PostToolUse"')
log_dir="$HOME/.thalamus/logs"
mkdir -p "$log_dir"
context=$(uv run --project "$(thalamus_repo_root)" thalamus reflex --deliver \
  --session-id "$session" --agent-id "$agent_id" --event "$event" \
  2>>"$log_dir/reflex.log") || context=""

[ -n "$context" ] || exit 0

jq -cn --arg event "$event" --arg ctx "$context" \
  '{hookSpecificOutput:{hookEventName:$event, additionalContext:$ctx}}'

exit 0
