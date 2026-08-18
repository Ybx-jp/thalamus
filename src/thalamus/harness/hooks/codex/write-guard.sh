#!/bin/bash
# Thalamus PreToolUse hook — a session does not write its own memory (codex).
#
# A delegator over ../claude-code/write-guard.sh, wired for the same reason it is
# wired on Cursor: the boundary is a decision about the graph, and the graph does not
# care which harness ran the command. Codex's `Bash` payload and its exit-2 blocking
# channel are Claude Code's, so no reshaping stands between the two.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_codex_delegate write-guard.sh
