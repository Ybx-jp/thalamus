#!/bin/bash
# Thalamus beforeSubmitPrompt hook — wall-clock tier, prompt side (Cursor).
#
# Counterpart of ../claude-code/timestamp.sh, split across two events because
# `beforeSubmitPrompt` cannot inject. This half only records
# that a turn began; `inject.sh` renders the clock at delivery time on the next
# postToolUse. The marker carries no timestamp deliberately — a clock rendered
# here and delivered later is a stale clock, which is the drift this tier
# exists to prevent.
#
# Kept separate from conditioning.sh for the same reason as on Claude Code:
# conditioning firings are measured for rescue rate (`thalamus eval
# conditioning`) and an unconditional per-turn clock must not pollute that
# telemetry.
#
# Install (user ~/.cursor/hooks.json, written by `thalamus init`):
#   {"version": 1, "hooks": {"beforeSubmitPrompt": [{"command":
#     "<checkout>/src/thalamus/harness/hooks/cursor/timestamp.sh"}]}}

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"
. "$here/resolve-scope.sh"
thalamus_sandbox_guard

. "$(dirname "${BASH_SOURCE[0]}")/spool.sh"

input=$(cat)
session=$(printf '%s' "$input" | jq -r '.session_id // .conversation_id // empty')

thalamus_spool_append "$session" clock ""

printf '{"continue": true}\n'
