#!/bin/bash
# Thalamus UserPromptSubmit hook — mark this session engaged in the pin ledger.
#
# The session-start hook records every *spawn*; the tmux roster spawns every
# expert's pinned session at bring-up, so spawn records alone conflate
# infrastructure churn with operator routing decisions (the 2026-07-19
# "pinned, never retrieved" confound — 9 of 15 expert ledger entries were
# idle roster spawns). The first user prompt is the engagement boundary: from
# here on, a session with no retrievals is an *attribution gap*, not noise.
# Semantics vetted by the eval-methodology expert
# (scope:main:exchange:63b647977a624b85): engagement-gating restores the
# sampling frame to sessions with a measurement opportunity — same principle
# as the report's SIGNAL_FLOOR gate. First-prompt-as-engagement is a dial,
# not a truth (automated prompts count too); disclosed in docs/04.
#
# Append-only, idempotent per session: one {"event":"engaged"} line per
# session_id, alongside the spawn lines. load_pins skips event lines;
# load_engaged reads them.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"

input=$(cat)
session_id=$(printf '%s' "$input" | jq -r '.session_id // empty')

if [ -n "$session_id" ]; then
  ledger="$HOME/.thalamus/pins/pins.jsonl"
  mkdir -p "$(dirname "$ledger")"
  touch "$ledger"
  if ! grep -F "\"$session_id\"" "$ledger" | grep -qF '"event":"engaged"'; then
    jq -cn --arg sid "$session_id" --arg scope "$(thalamus_resolve_scope)" \
      --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      '{event: "engaged", session_id: $sid, scope: $scope, ts: $ts}' >> "$ledger"
  fi
fi

printf '{}\n'
