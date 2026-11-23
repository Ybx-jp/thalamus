#!/bin/bash
# Thalamus PreToolUse hook — the session preflight (Claude Code).
#
# At a session's first tool call this runs `thalamus preflight --hook`
# (harness/preflight.py): tool surface, hooks runnable, guards armed, budget, and a
# dry run of the write path. The first tool call is the earliest point the check can
# see what it checks: at SessionStart and UserPromptSubmit the transcript does not
# exist yet, and by the first PreToolUse it holds the harness's record of the tool
# surface (measured on Claude Code 2.1.330, 2026-11-23).
#
# What a failure does is decided by the session type (thalamus_resolve_session_type):
#
#   autonomous — the call is denied and the run stopped, and every later call in the
#                session is denied the same way. Nobody is there to read a warning.
#   attended   — the failures are shown to the operator on screen and reach the
#                session as context, and the call proceeds. The operator is there and
#                decides. session-start.sh has already run every check but the tool
#                surface before the first prompt, so this run tells only what that one
#                did not.
#
# The result is recorded either way at ~/.thalamus/preflight/<session_id>.json, and
# that file is also this hook's state: once it exists the check is not repeated, and
# a later call costs one file read. A subagent's calls carry the session's id and
# reuse the session's result.
#
# A preflight that cannot run at all is itself a failure for an autonomous session —
# the run is stopped with the reason — and silent for an attended one.
#
# Install (user settings.json, by `thalamus init`):
#   {"hooks": {"PreToolUse": [{"hooks": [{"type": "command",
#     "command": ".../hooks/claude-code/preflight.sh"}]}]}}

set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

input=$(cat)
session_id=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)
[ -n "$session_id" ] || exit 0

session_type="$(thalamus_resolve_session_type)"
state="$HOME/.thalamus/preflight/$session_id.json"

abort() {
  jq -cn --arg reason "Thalamus preflight failed — $1" '{
    continue: false, stopReason: $reason,
    hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny",
                         permissionDecisionReason: $reason}}'
}

if [ -f "$state" ]; then
  if [ "$session_type" = "autonomous" ] && [ "$(jq -r '.passed' "$state" 2>/dev/null)" != "true" ]; then
    abort "$(jq -r '[.checks[] | select(.ok != true) | "\(.name): \(.detail)"] | join("; ")' "$state" 2>/dev/null)"
  fi
  exit 0
fi

transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty')
scope="$(thalamus_scope_from_payload "$input")"
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')

if ! thalamus_cli_argv; then
  [ "$session_type" = "autonomous" ] && abort "the thalamus CLI could not be run, so the preflight did not"
  exit 0
fi

mkdir -p "$HOME/.thalamus/logs"
output=$("${THALAMUS_CLI[@]}" preflight --hook --session-id "$session_id" \
  --transcript "$transcript" --scope "$scope" --session-type "$session_type" \
  --project-dir "${CLAUDE_PROJECT_DIR:-$cwd}" 2>>"$HOME/.thalamus/logs/preflight.log")
status=$?
if [ "$status" -ne 0 ] || [ -z "$output" ]; then
  [ "$session_type" = "autonomous" ] && abort "the preflight exited $status without a result"
  exit 0
fi
printf '%s\n' "$output"
