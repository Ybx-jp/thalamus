#!/bin/bash
# Thalamus UserPromptSubmit hook — conditioning tier (codex).
#
# A delegator over ../claude-code/conditioning.sh: one set of lexical intent classes,
# one per-session throttle, one telemetry log in `~/.thalamus/conditioning/` — the
# join `thalamus eval conditioning` reads. Duplicating the classifier per harness
# would fork the detection logic and desynchronise that telemetry silently.
#
# Firings are stamped `harness: codex` (THALAMUS_HARNESS, set by
# thalamus_codex_delegate), so the rescue-rate join can separate the harnesses
# instead of averaging them.
#
# Unlike Cursor, the reminder is delivered on the same event that classified it:
# codex's UserPromptSubmit both reads `prompt` and honours `additionalContext`, so
# there is no delivery lag to record and no spool to prune.
#
# No carrier for the milestone class: `PostToolUse:TaskCreate` is Claude Code's
# task-list UI, and codex ships no analogous tool (the measured tool vocabulary is
# `Bash`, `apply_patch` and `mcp__<server>__<tool>`). The two lexical classes on the
# prompt are the load-bearing ones and both cross.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_codex_delegate conditioning.sh
