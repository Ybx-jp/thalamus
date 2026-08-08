#!/bin/bash
# Thalamus PreToolUse hook — room boundary on SendMessage (Claude Code).
#
# A room is a bounded set of pinned sessions that may talk freely among
# themselves under the cheap unprovenanced quick protocol, and reach anything
# outside only through a ticketed consultation. That boundary is what makes the
# cheap tier defensible, so it needs enforcement rather than convention.
#
# Structural isolation would be better and is not available: cross-session
# messaging discovers peers through the socket registry at
# `$XDG_RUNTIME_DIR/cc-socks`, and overriding that variable does not relocate
# the registry — it stops the session binding a socket at all (lab/044, clean
# A/B). Relocating it needs a bind mount in a mount namespace, and unprivileged
# ones are refused on this box. So the boundary is policy here, at the sender,
# until a privileged bind mount or a container per room exists.
#
# What this guard is honest about: it governs **outbound only**. An outsider can
# still message a room member, because nothing at the sender's end of that
# exchange is ours to gate. Closing inbound needs `crossSessionInbound` on the
# members, which cannot discriminate by sender. A room enforced this way is a
# room whose members will not talk out, not one nobody can talk into.
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

input=$(cat)

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
    --arg scope "$(thalamus_resolve_scope)" \
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
# over it — so anything that is not unambiguously a peer session passes. lab/008's
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
that never agreed to it — the laundering channel docs/05 tracks, with the room's
own bound removed.

Reach outside the room the way every cross-scope exchange is reached: mint a
consultation ticket (\`consult_request\`), which opens the exchange record and
returns an answer whose citations are validated. If the target really is a room
member, it was launched without the \`${room}-\` name prefix that makes
membership legible — relaunch it named \`${room}-<scope>\`.
EOF
exit 2
