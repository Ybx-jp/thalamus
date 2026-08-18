#!/bin/bash
# Thalamus UserPromptSubmit hook — wall-clock tier (codex).
#
# A delegator, not an adapter. Codex's UserPromptSubmit payload carries `prompt`,
# `session_id`, `cwd`, `transcript_path` and `turn_id`, and its output vocabulary is
# Claude Code's `hookSpecificOutput{hookEventName, additionalContext}` — so
# ../claude-code/timestamp.sh runs here unchanged and injects on the same event that
# read the prompt. Cursor needed a spool because `beforeSubmitPrompt` cannot inject;
# codex needs nothing.
#
# The tier itself is unchanged: a long-running pinned session's notion of "today"
# drifts from the date stamped at launch, and the drift corrupts timestamps written
# into the graph. See ../claude-code/timestamp.sh for the measurement.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_codex_delegate timestamp.sh
