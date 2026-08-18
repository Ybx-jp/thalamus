#!/bin/bash
# Thalamus PreToolUse hook — room boundary on the command channel (codex).
#
# A delegator over ../claude-code/room-command-guard.sh, and — as on Cursor — the
# only shape the room boundary can take here. `room-guard.sh` matches the
# `SendMessage` tool name; codex has no such tool (its measured vocabulary is `Bash`,
# `apply_patch` and `mcp__<server>__<tool>`), so peer traffic is a shell command or
# it is nothing.
#
# Rooms and dispatch are not built for codex, so today this guards a boundary no
# codex session is inside: it fires only when THALAMUS_ROOM is set and exits
# immediately otherwise. It is wired now because the alternative is a boundary that
# arrives after the first room does.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_codex_delegate room-command-guard.sh
