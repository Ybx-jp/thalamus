#!/bin/bash
# Thalamus PreToolUse hook (codex) — delegates to ../claude-code/budget.sh, which
# is told it runs under codex and so denies a call past a cap without asking codex to
# stop the turn: a codex PreToolUse hook that returns `continue: false` is marked
# failed and the call goes ahead (A0184, cites-as-live).

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_codex_delegate budget.sh
