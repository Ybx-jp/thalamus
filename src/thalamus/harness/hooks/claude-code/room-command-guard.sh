#!/bin/bash
# Thalamus PreToolUse hook — room boundary on the *command* channel (Claude Code).
#
# `room-guard.sh` bounds `SendMessage`, which is a tool name, and that was the whole
# peer channel while peer messaging was a tool. It is not any more: `tmux send-keys`
# is a measured delivery path into any pane on the box, and `thalamus
# dispatch` addresses a room by name from a shell. Both are Bash. A boundary that
# matches a tool name cannot see either, and on Cursor there is no `SendMessage` at
# all, so this is the only shape the boundary can take there.
#
# This is defence-in-depth and it is deliberately the *second* line. The boundary is
# `dispatch.authenticate`, which establishes the sender from the calling process and
# refuses a room mismatch — a check inside the verb, on data the caller cannot author.
# A guard over command strings can always be evaded by a determined member (a variable,
# a here-doc, an alias), so it is not asked to be airtight. It is asked to make the
# ordinary reach-out fail loudly, in the ledger, at the moment it is attempted, and to
# cover the raw transport that never reaches the verb at all.
#
# Scope: fires only when THALAMUS_ROOM is set. A session outside a room is untouched.
#
# Install (user or project settings.json):
#   {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
#     "command": ".../hooks/claude-code/room-command-guard.sh"}]}]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

thalamus_read_guard_input room-command-guard.sh
input="$thalamus_guard_input"

room="$(thalamus_resolve_room)"
# Not in a room: nothing to bound. The common case, and a no-op. Asked before the
# command is read so that an unreadable payload outside a room stays the no-op it
# already was — there is no boundary here to fail closed around.
[ -n "$room" ] || exit 0

# Inside a room there is, and this hook is matched on `Bash`, where the command is
# the event. An absent one is a payload the guard cannot read, not an empty call.
thalamus_read_guard_command room-command-guard.sh
command="$thalamus_guard_command"

log_event() {
  local verdict="$1" branch="$2" target="$3"
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

# Does the command name this session's own room as a standalone word?
#
# This is the whole matching rule, and it is fail-closed on purpose. Extracting the
# room *positional* out of a shell string is not reliably possible — `thalamus
# dispatch --to qe alpha "msg"` puts it after a flag that takes a value — so instead
# of parsing an argument the guard asks whether the command names the room it is
# allowed to name. A dispatch whose target cannot be confirmed as this room is
# refused rather than assumed to be local.
names_own_room() {
  printf '%s' "$command" | grep -qE "(^|[^A-Za-z0-9_-])${room}([^A-Za-z0-9_-]|$)"
}

# 1. The raw transport. `tmux send-keys` is how dispatch itself delivers, so a member
#    with a shell can reach any pane on the box — including a non-member's, and
#    including one in another room — with nothing in any ledger to show for it. There
#    is no "to my own room" form of this worth allowing: the sanctioned channel writes
#    a row and this does not, and that difference is the point.
# Matched on the *verb*, not on `tmux`: the binary can be spelled `/usr/bin/tmux`,
# `$TMUX_BIN`, or reached through an alias, and unlike the addressing rules below
# there is no second line behind this one — a raw send never reaches `dispatch`, so
# nothing else can refuse it. `paste-buffer` is the same capability by another route.
if printf '%s' "$command" | grep -qE '(^|[^A-Za-z0-9_-])(send-keys|paste-buffer)([^A-Za-z0-9_-]|$)'; then
  log_event block raw-transport "tmux send-keys"
  cat >&2 <<EOF
Blocked: this session is in room \`${room}\`, and \`tmux send-keys\` reaches any pane
on this machine, including sessions outside the room.

It is the transport \`thalamus dispatch\` delivers over, so this is not a different
capability — it is the same one with the pre-flight and the ledger removed. A send
into a session holding an approval dialog is discarded and its Enter actuates the
highlighted default, approving a tool call the sender cannot see (measured);
dispatch refuses that case and a raw send cannot.

Use \`thalamus dispatch ${room} "<message>"\`, which pre-flights every target, refuses
the whole fan-out rather than announcing to half a room, and writes a row.
EOF
  exit 2
fi

# 2. Addressing a room by name. `dispatch` refuses a room mismatch itself; this
#    catches it one layer earlier, where the operator sees it, and covers `spawn`/`pin`
#    placing a *new* session in a room this one is not in.
#    `thalamus` must be *invoked*, not merely named: the verb follows the binary with
#    only flags between, which is the shape of a command and not the shape of a path.
#    `src/thalamus/harness/dispatch.py` names both words and invokes nothing.
#
#    Measured across three sessions on 2026-08-15, the previous form — `thalamus`,
#    then any text without a shell separator, then a verb — produced 8 false positives
#    and 0 true ones. Every one was a path or a search pattern, and every one was
#    worked around with a glob or a here-doc within seconds. That rate is not a
#    conservative guard: a member who has learned to rewrite the command is a member
#    who has the rewrite ready for the case this exists to stop, so precision is a
#    security property here and not an ergonomic one.
#
#    What *follows* `thalamus` is the discriminator, never what precedes it. A path
#    invocation — `.venv/bin/thalamus dispatch alpha` — is a real reach and still
#    matches, so the leading boundary stays wide.
INVOKES_ROOM_VERB='(^|[^A-Za-z0-9_-])thalamus[[:space:]]+(-[^[:space:]]+[[:space:]]+)*(dispatch|spawn|pin|roster)([^A-Za-z0-9_-]|$)'
#    Asking what a verb does reaches no room: argparse prints and exits before an
#    argument is read. Matched as the *shape* of a help invocation rather than as the
#    presence of the flag, so a `--help` inside a quoted message buys no exemption.
HELP_SHAPE='thalamus[[:space:]]+(dispatch|spawn|pin|roster)[[:space:]]+(--help|-h)([^A-Za-z0-9_-]|$)'

if printf '%s' "$command" | grep -qE "$INVOKES_ROOM_VERB"; then
  if printf '%s' "$command" | grep -qE "$HELP_SHAPE"; then
    log_event pass help "$room"
    exit 0
  fi
  if names_own_room; then
    log_event pass peer-command "$room"
    exit 0
  fi
  log_event block outside-room "unnamed room"
  cat >&2 <<EOF
Blocked: this session is in room \`${room}\`, and this command addresses a room
without naming it.

A room's config root bounds what a member can *read* — its transcripts, its discovery
roster. It does not bound a shell command, so the peer channel is the one direction a
room is not partitioned in, and it is bounded here instead.

If you meant your own room, name it literally: \`thalamus dispatch ${room} …\`. If you
meant another room, that is a cross-scope reach and it goes through a consultation
ticket (\`consult_request\`), which opens an exchange record and returns an answer whose
citations are validated — not through a broadcast into a room that never agreed to it.
EOF
  exit 2
fi

exit 0
