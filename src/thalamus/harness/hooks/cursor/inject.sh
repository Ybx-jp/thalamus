#!/bin/bash
# Thalamus postToolUse hook — deferred injection, delivery side (Cursor).
#
# `postToolUse` is one of exactly two Cursor events that can inject context
# (`additional_context`; the other is sessionStart, already used for priming).
# It fires for every tool type, so this hook is the delivery half of the spool
# written by timestamp.sh and conditioning.sh on beforeSubmitPrompt.
#
# It deliberately does NOT tap. The retrieval traces stay on the specialized
# events (afterMCPExecution -> mcp-tap.sh, afterShellExecution ->
# gremlin-tap.sh) because Cursor's docs do not state whether a tool call fires
# both the generic and the specialized hook; if it does, a tap here would
# double-count every retrieval in `eval sync`. Injection has no such hazard —
# the spool is drained exactly once whoever delivers it.
#
# Cadence: the spool holds at most one turn's worth, so this injects roughly
# once per prompt rather than once per tool call. Indiscriminate per-call
# injection is what the conditioning tier is grounded against (selective beats
# always-on injection — arXiv 2607.08716; the local ignored share is real at
# the measured magnitude), and every injected token rides every later call.
#
# The clock is rendered HERE, from the shared Claude Code script, not at spool
# time: delivery is when the agent reads it, and a timestamp computed a tool
# call earlier is exactly the drift the tier exists to prevent.
#
# Fire-and-forget on failure: an empty object is a valid no-op response, so a
# missing spool, a truncated line or an unreadable directory costs the turn its
# injection and nothing else.
#
# Install (user ~/.cursor/hooks.json, written by `thalamus init`):
#   {"version": 1, "hooks": {"postToolUse": [{"command":
#     "<checkout>/src/thalamus/harness/hooks/cursor/inject.sh"}]}}

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"
. "$here/resolve-scope.sh"
thalamus_sandbox_guard
. "$here/spool.sh"

input=$(cat)
session=$(printf '%s' "$input" | jq -r '.session_id // .conversation_id // empty')

if [ -z "$session" ]; then
  printf '{}\n'
  exit 0
fi

spool="$(thalamus_spool_file "$session")"
if [ ! -s "$spool" ]; then
  printf '{}\n'
  exit 0
fi

# Drain atomically: rename first, then read. Two concurrent postToolUse hooks
# for one session would otherwise both deliver the same items, and a rename is
# the cheapest way to make exactly one of them the winner.
claimed="${spool}.draining.$$"
if ! mv "$spool" "$claimed" 2>/dev/null; then
  printf '{}\n'
  exit 0
fi

parts=()

if jq -e -s 'any(.[]; .kind == "clock")' "$claimed" >/dev/null 2>&1; then
  clock=$("$here/../claude-code/timestamp.sh" 2>/dev/null \
    | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null || true)
  [ -n "$clock" ] && parts+=("$clock")
fi

while IFS= read -r line; do
  [ -n "$line" ] && parts+=("$line")
done < <(jq -r 'select(.kind == "conditioning") | .text | select(length > 0)' \
  "$claimed" 2>/dev/null || true)

rm -f "$claimed"

if [ "${#parts[@]}" -eq 0 ]; then
  printf '{}\n'
  exit 0
fi

printf '%s\n' "${parts[@]}" | jq -Rs '{additional_context: (. | rtrimstr("\n"))}'
