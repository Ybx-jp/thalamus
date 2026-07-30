#!/bin/bash
# Thalamus sessionEnd hook — Cursor.
#
# Cursor's contract: stdin {session_id, reason, duration_ms, is_background_agent,
# final_status, ...} + common fields (transcript_path, workspace_roots).
# Fire-and-forget; no output is honored.
#
# ⚠️ This hook records the session's end — it does NOT distill. Distillation
# (`thalamus extract`) parses Claude Code's JSONL transcript format
# (harness/transcripts.py); Cursor transcripts are a different format, and no
# adapter exists yet (lab/010 — a wall, not an oversight). Until one does, a
# Cursor session's episodic memory is NOT captured. This hook logs the ended
# session with its transcript_path and pinned scope so the evidence pointer
# survives and a future adapter can backfill from Cursor's own storage.
#
# Install (project <root>/.cursor/hooks.json):
#   {"version": 1, "hooks": {"sessionEnd": [{"command":
#     "./src/thalamus/harness/hooks/cursor/session-end.sh"}]}}
# Not supported in Cursor cloud agents.

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"
. "$here/resolve-scope.sh"
thalamus_sandbox_guard
. "$here/spool.sh"

input=$(cat)

session_id=$(printf '%s' "$input" | jq -r '.session_id // .conversation_id // empty')
[ -n "$session_id" ] || exit 0

# Undelivered injection dies with the session: a turn that ended without a tool
# call left its spool behind, and delivering it into some later session would be
# both stale and misattributed.
rm -f "$(thalamus_spool_file "$session_id")" "$(thalamus_spool_file "$session_id")".draining.* 2>/dev/null || true

transcript_path=$(printf '%s' "$input" | jq -r '.transcript_path // empty')
reason=$(printf '%s' "$input" | jq -r '.reason // empty')

# Ledger-first scope, env fallback — same rule as the Claude Code session-end.
env_scope="$(thalamus_resolve_scope)"
ledger="$HOME/.thalamus/pins/pins.jsonl"
ledger_scope=""
if [ -f "$ledger" ]; then
  ledger_scope=$(jq -r --arg sid "$session_id" \
    'select(.session_id == $sid) | .scope' "$ledger" 2>/dev/null | tail -1)
fi
scope="${ledger_scope:-$env_scope}"

log_dir="$HOME/.thalamus/logs"
mkdir -p "$log_dir"
jq -cn --arg sid "$session_id" --arg scope "$scope" --arg tp "$transcript_path" \
  --arg reason "$reason" --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{ts: $ts, harness: "cursor", session_id: $sid, scope: $scope,
    transcript_path: $tp, reason: $reason,
    distilled: false, note: "no Cursor transcript adapter (lab/010)"}' \
  >> "$log_dir/cursor-session-end.jsonl"

exit 0
