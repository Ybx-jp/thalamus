#!/bin/bash
# Thalamus sessionStart / afterShellExecution / afterMCPExecution hook — close the
# readiness bracket.
#
# The closing half of the first-party readiness descriptor (harness/readiness.py).
# `ready` is the resting state: written once when a member's session starts, so a
# freshly-launched member is addressable at all, and again each time a bracketed call
# completes.
#
# **A `ready` never clears a `pending` left by a different session.** A headless
# `agent -p` spawned from a member's own shell inherits `THALAMUS_ROOM` and
# `THALAMUS_SCOPE`, fires its own `sessionStart`, and would otherwise report the parent
# ready at the exact moment the parent is sitting at the modal that shell call raised —
# the one interval this whole mechanism exists to catch, cleared by its own side effect.
#
# Cursor's contract: no output is honored on the after-events; `sessionStart` accepts
# `{additional_context, env}` and gets `{}` here, because priming is session-start.sh's
# job and two hooks writing context on one event is how a duplicate arrives.
#
# Roomless sessions write nothing — see readiness-pending.sh.

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"
. "$here/resolve-scope.sh"
thalamus_sandbox_guard

input=$(cat)

room="${THALAMUS_ROOM:-}"
scope="$(thalamus_resolve_scope)"
if [ -z "$room" ] || [ -z "$scope" ]; then
  printf '{}\n'
  exit 0
fi

# Background agents are spawned for specific tasks and are not room members — the same
# exclusion session-start.sh makes, for the same reason.
is_background=$(printf '%s' "$input" | jq -r '.is_background_agent // false')
if [ "$is_background" = "true" ]; then
  printf '{}\n'
  exit 0
fi

session_id=$(printf '%s' "$input" | jq -r '.session_id // .conversation_id // empty')

dir="$HOME/.thalamus/readiness/$room"
descriptor="$dir/$scope.json"

if [ -f "$descriptor" ]; then
  standing_phase=$(jq -r '.phase // empty' "$descriptor" 2>/dev/null || true)
  standing_session=$(jq -r '.session_id // empty' "$descriptor" 2>/dev/null || true)
  if [ "$standing_phase" = "pending" ] && [ "$standing_session" != "$session_id" ]; then
    printf '{}\n'
    exit 0
  fi
fi

mkdir -p "$dir"
jq -cn --arg phase "ready" --arg room "$room" --arg scope "$scope" \
  --arg sid "$session_id" --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{phase: $phase, room: $room, scope: $scope, session_id: $sid, ts: $ts}' \
  > "$descriptor.tmp"
mv -f "$descriptor.tmp" "$descriptor"

printf '{}\n'
