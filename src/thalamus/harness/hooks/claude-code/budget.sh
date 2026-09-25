#!/bin/bash
# Thalamus PreToolUse + PostToolBatch hook — the scope's budget (Claude Code).
#
# Counts the prompt's tool calls and turns and the session's tokens against the
# scope's `budget` preset, and stops the prompt when one is spent. The counting and
# the decision are harness/budget.py; this is the matcher in front of it, and its job
# is to cost nothing for a scope with no budget — every tool call runs it.
#
# The fast path: no `THALAMUS_MAX_*` override in the environment, no `budget:` key in
# the resolved scope's manifest and no count already kept for this session means there
# is nothing to count, and the hook exits before starting Python. Scope comes from
# resolve-scope.sh, so a subagent is budgeted as the expert it is (its payload's
# `agent_type`) rather than as its launcher — and the session's count is checked too,
# since its total binds every subagent in it.
#
# A budget is a cost control, not a boundary: when the interpreter or the config
# cannot be read, it lets the call through. It does not read its payload through
# thalamus_read_guard_input, which exists to turn an unreadable payload into a block.
# For the same reason it is not named `*-guard.sh`: that suffix marks a boundary, and
# qe's guard_failopen case holds every script carrying it to failing closed.
#
# Install (user or project settings.json):
#   {"hooks": {"PreToolUse": [{"hooks": [{"type": "command",
#     "command": ".../hooks/claude-code/budget.sh"}]}],
#    "PostToolBatch": [{"hooks": [{"type": "command",
#     "command": ".../hooks/claude-code/budget.sh"}]}]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_require_binaries jq || exit 0

input=$(cat)
scope="$(thalamus_scope_from_payload "$input")"
config="$(thalamus_config_root)"

session="$(jq -r '.session_id // empty' <<<"$input" 2>/dev/null || true)"
if [ -z "${THALAMUS_MAX_TURNS:-}${THALAMUS_MAX_TOOL_CALLS:-}${THALAMUS_MAX_TOKENS:-}${THALAMUS_MAX_SUBAGENT_TOKENS:-}" ] \
  && ! grep -q '^budget:' "$config/experts/$scope.yaml" 2>/dev/null \
  && ! { [ -n "$session" ] && [ -f "$HOME/.thalamus/budget/$session.json" ]; }; then
  exit 0
fi

repo_root="$(thalamus_repo_root)"
py="$repo_root/.venv/bin/python"
if [ -x "$py" ]; then
  run=("$py")
else
  run=(uv run --project "$repo_root" python)
fi

log_dir="$HOME/.thalamus/logs"
mkdir -p "$log_dir"
printf '%s' "$input" \
  | "${run[@]}" -m thalamus.harness.budget "${THALAMUS_HARNESS:-claude}" "$scope" "$config" \
    2>>"$log_dir/budget.log" || true
exit 0
