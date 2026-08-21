#!/bin/bash
# Thalamus PreToolUse hook — room boundary on SendMessage (Claude Code).
#
# A room is a bounded set of pinned sessions that may talk freely among
# themselves under the cheap unprovenanced quick protocol, and reach anything
# outside only through a ticketed consultation. That boundary is what makes the
# cheap tier defensible, so it needs enforcement rather than convention.
#
# This is defence-in-depth, not the boundary itself. The boundary is structural
# and it is the **config dir**: peer discovery scans no socket directory, it
# enumerates `$CLAUDE_CONFIG_DIR/sessions/<pid>.json` and reads each session's
# `messagingSocketPath` from the descriptor. A per-room CLAUDE_CONFIG_DIR with a
# private `sessions/` therefore partitions the roster; a per-room
# XDG_RUNTIME_DIR only moves the socket and hides nothing. Structure
# governs discovery — a non-member is never listed — and this guard governs
# intent, catching a member that means to reach out however it learned the name.
#
# It governs **outbound only**. An outsider can still message a room member,
# because nothing at that sender's end is ours to gate, and `crossSessionInbound`
# cannot discriminate by sender. That asymmetry is survivable exactly because the
# structural boundary is doing the real work.
#
# Membership is carried by name. Room members launch as `<room>-<scope>`
# (`--name`), which is the address SendMessage routes on, so a target is a
# room-mate exactly when its name is prefixed with this session's room.
#
# Scope: fires only when THALAMUS_ROOM is set. A session outside a room is
# untouched, so arming this changes nothing for every session that exists today.
#
# Install (user or project settings.json):
#   {"hooks": {"PreToolUse": [{"matcher": "SendMessage", "hooks": [{"type":
#     "command", "command": ".../hooks/claude-code/room-guard.sh"}]}]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

thalamus_read_guard_input room-guard.sh
input="$thalamus_guard_input"

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')
[ "$tool_name" = "SendMessage" ] || exit 0

room="$(thalamus_resolve_room)"
# Not in a room: nothing to bound. This is the common case and stays a no-op.
[ -n "$room" ] || exit 0

target=$(printf '%s' "$input" | jq -r '.tool_input.to // empty')
[ -n "$target" ] || exit 0

log_event() {
  local verdict="$1" branch="$2"
  local guard_dir="$HOME/.thalamus/guards"
  mkdir -p "$guard_dir"
  printf '%s' "$input" | jq -c \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg scope "$(thalamus_scope_from_payload "$input")" \
    --arg room "$room" \
    --arg verdict "$verdict" \
    --arg branch "$branch" \
    --arg target "$target" \
    '{ts: $ts,
      session_id: (.session_id // ""),
      scope: $scope,
      room: $room,
      cwd: (.cwd // ""),
      guard: "room-boundary",
      guard_version: 1,
      verdict: $verdict,
      branch: $branch,
      target: $target}' >> "$guard_dir/$(date -u +%Y-%m).jsonl" || true
}

# Satisfaction branches, and they are deliberately generous. SendMessage serves
# in-process subagents as well as peer sessions — the consultation protocol runs
# over it — so anything that is not unambiguously a peer session passes. The
# standing trade applies with full force: a false positive teaches route-around,
# and route-around costs more than a miss. The gap is named rather than closed:
# a room member messaging an outside session under a bare name it happens to
# share with no room prefix is not caught.

# The parent conversation — a background subagent reporting home, never a peer.
if [ "$target" = "main" ]; then
  log_event pass parent
  exit 0
fi

# A raw agentId (the spawn result's `a<hex>` form) is an in-process subagent.
if printf '%s' "$target" | grep -qE '^a[0-9a-f]{8,}$'; then
  log_event pass subagent-id
  exit 0
fi

# A room-mate: `<room>-<scope>`, or the room's own anchor. The optional
# " [ref]" disambiguator SendMessage appends is tolerated.
if printf '%s' "$target" | grep -qE "^${room}(-[^ ]+)?( \[[0-9a-f]+\])?$"; then
  log_event pass roommate
  exit 0
fi

log_event block outside-room

cat >&2 <<EOF
Blocked: this session is in room \`${room}\`, and \`${target}\` is not a member.

A room's cheap quick protocol is only defensible because it cannot leave the
room. Messaging outward would carry unprovenanced, uncited content into a scope
that never agreed to it — the laundering channel the trust model tracks, with the
room's own bound removed.

Reach outside the room the way every cross-scope exchange is reached: mint a
consultation ticket (\`consult_request\`), which opens the exchange record and
returns an answer whose citations are validated. If the target really is a room
member, it was launched without the \`${room}-\` name prefix that makes
membership legible — relaunch it named \`${room}-<scope>\`.
EOF
exit 2
