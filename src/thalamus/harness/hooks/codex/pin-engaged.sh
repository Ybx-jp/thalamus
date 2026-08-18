#!/bin/bash
# Thalamus UserPromptSubmit hook — mark this session engaged in the pin ledger (codex).
#
# A delegator over ../claude-code/pin-engaged.sh: the first user prompt is the
# engagement boundary for the sampling frame, because spawn records alone conflate
# infrastructure churn with operator routing. One {"event":"engaged"} line per
# session, idempotent, in the ledger both harnesses share.
#
# It carries more weight on codex than on Claude Code, and that is measured. In the
# interactive TUI, SessionStart does **not** fire at launch — it fires at the first
# submitted turn (2026-08-17: a TUI left idle 20s fired no hook at all, and one quit
# without submitting fired only SessionEnd). So on a codex roster window the spawn
# row and the engagement row appear at the same moment rather than minutes apart,
# and a spawned-but-unused window leaves neither.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_codex_delegate pin-engaged.sh
