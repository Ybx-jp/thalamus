#!/bin/bash
# Thalamus beforeShellExecution / beforeMCPExecution hook — open the readiness bracket.
#
# The opening half of the first-party readiness descriptor (harness/readiness.py). A
# member is about to make a call that may raise an approval modal, so it stops being
# addressable until the paired after-event closes the bracket.
#
# Measured 2026-08-13 (lab/065 §5): `beforeShellExecution` fires *before* Cursor's own
# approval modal — a probe hook logged at 11:01:15 with the modal still unanswered at
# 11:01:20. That ordering is the whole mechanism. If this event fired after the modal,
# `pending` would be written only once the operator had already been asked, and a
# dispatch racing the modal would still land in it.
#
# Cursor's contract: stdin {command, cwd, session_id/conversation_id, ...} for the
# shell event and {tool_name, ...} for the MCP one. This hook reads neither — the
# bracket is about the *interval*, not about what is running in it — so one script
# serves both events and neither payload shape can break it.
#
# Roomless sessions write nothing: readiness is a room's question, and a solo session
# has no dispatcher asking it.

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"
. "$here/resolve-scope.sh"
thalamus_sandbox_guard

input=$(cat)

room="${THALAMUS_ROOM:-}"
scope="$(thalamus_resolve_scope)"
if [ -z "$room" ] || [ -z "$scope" ]; then
  printf '{"permission": "allow"}\n'
  exit 0
fi

session_id=$(printf '%s' "$input" | jq -r '.session_id // .conversation_id // empty')

dir="$HOME/.thalamus/readiness/$room"
mkdir -p "$dir"
# Written through a temp file and moved into place: a dispatch pre-flight reading this
# path mid-write would parse a truncated object, and `read_descriptor` turns that into
# a refusal — safe, but it would refuse a member that is merely being written about.
jq -cn --arg phase "pending" --arg room "$room" --arg scope "$scope" \
  --arg sid "$session_id" --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{phase: $phase, room: $room, scope: $scope, session_id: $sid, ts: $ts}' \
  > "$dir/$scope.json.tmp"
mv -f "$dir/$scope.json.tmp" "$dir/$scope.json"

# This hook decides nothing about the command. `allow` here is not a permission grant
# — `room-command-guard.sh` and `write-guard.sh` are the deciders on this event, and a
# hook that abstains has to say so in the vendor's vocabulary.
printf '{"permission": "allow"}\n'
