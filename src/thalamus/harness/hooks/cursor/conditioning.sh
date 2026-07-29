#!/bin/bash
# Thalamus beforeSubmitPrompt hook — conditioning tier, prompt side (Cursor).
#
# Thin adapter over ../claude-code/conditioning.sh: one set of lexical intent
# classes, one throttle, one telemetry log. The Claude Code script is run
# unchanged against a reshaped UserPromptSubmit payload, so its per-class
# once-per-session throttle and its `~/.thalamus/conditioning/` firing log —
# the join `thalamus eval conditioning` reads — work identically on Cursor.
# Duplicating the classifier here would fork the detection logic and silently
# desynchronise the two harnesses' telemetry.
#
# The split: Cursor's `beforeSubmitPrompt` sees the prompt but cannot inject
# (lab/010 wall 1), so the emitted context is spooled and `inject.sh` delivers
# it on the next postToolUse. The firing is logged at *classification* time,
# which is what the rescue-rate join wants — it measures whether behavior
# followed the reminder, and the reminder's own delivery lag is a property of
# the harness, recorded in docs/07 rather than hidden by re-timing the log.
#
# TaskCreate (the milestone class) has no Cursor carrier: it is Claude Code
# task-list UI, and Cursor's generic `Task` tool type is subagent spawning, a
# different event. The milestone tier is Claude-Code-only; the two lexical
# classes on the prompt are the load-bearing ones and both cross.
#
# Install (user ~/.cursor/hooks.json, written by `thalamus init`):
#   {"version": 1, "hooks": {"beforeSubmitPrompt": [{"command":
#     "<checkout>/src/thalamus/harness/hooks/cursor/conditioning.sh"}]}}

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"
. "$here/spool.sh"

input=$(cat)

session=$(printf '%s' "$input" | jq -r '.session_id // .conversation_id // empty')
prompt=$(printf '%s' "$input" | jq -r '.prompt // empty')

if [ -z "$session" ] || [ -z "$prompt" ]; then
  printf '{"continue": true}\n'
  exit 0
fi

# A new prompt invalidates any classification still undelivered from the last
# one: it was matched against different text, and delivering it here would
# advise design work over whatever the user actually just asked. This hook runs
# on every prompt and is the only writer of conditioning entries, so pruning
# here is what makes "the spool holds at most one turn's worth" true rather
# than assumed. The clock needs no equivalent — it carries no rendered value
# and regenerates at drain.
thalamus_spool_prune "$session" conditioning

claude_payload=$(jq -cn --arg s "$session" --arg p "$prompt" \
  '{hook_event_name: "UserPromptSubmit", session_id: $s, prompt: $p}')

# The real classifier. It writes its own firing log and returns Claude Code's
# injection envelope on stdout, or nothing when no class fires or the class is
# already throttled for this session.
set +e
emitted=$(printf '%s' "$claude_payload" \
  | THALAMUS_HARNESS=cursor "$here/../claude-code/conditioning.sh" 2>/dev/null)
set -e

context=$(printf '%s' "$emitted" \
  | jq -r 'try .hookSpecificOutput.additionalContext catch empty // empty' 2>/dev/null || true)

if [ -n "$context" ]; then
  thalamus_spool_append "$session" conditioning "$context"
fi

printf '{"continue": true}\n'
