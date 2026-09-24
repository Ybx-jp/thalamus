#!/bin/bash
# Thalamus PostToolUse hook — memory reflex (Claude Code).
#
# Retrieval triggered by the observation stream rather than by the agent. When a
# Bash result reads as a failure, the harness retrieves against the identifiers in it
# and injects a digest of what the graph holds, labelled as unsolicited, naming the
# file that holds the records verbatim. The agent did not ask;
# that is the point — the failure it prevents is a session re-deriving over an hour
# what one recall would have served, at the moment it did not know to recall.
#
# A matcher only. The cheap preconditions run here in bash — sandbox guard, the
# failure test on the tool result, scope from the pin — and everything that costs
# anything (anchor extraction, a graph round trip, rendering) is `thalamus reflex` in
# harness/reflex.py, which is where the logic is measured and typed. On no match this
# exits before paying for a `uv run` at all.
#
# The failure test is lexical over stdout and stderr, OR `tool_response.interrupted`.
# It reads the `PostToolUse` payload, which only a call that exited 0 reaches: a Bash
# command that exits non-zero goes to `PostToolUseFailure`, where nothing runs this
# script, so the reflex sees a failure only when its output arrives with status 0, as
# through a pipe (#262) (A0161, cites-as-live). The regex is harness/reflex.py's
# FAILURE_PATTERN verbatim; tests/test_reflex.py holds the two equal.
#
# Bulk content travels by file, resolved fields as flags — `extract --transcript` and
# `delegate --input`'s idiom. A 40-failure pytest dump on argv is what ARG_MAX exists
# to break.
#
# Install (project .claude/settings.json):
#   {"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
#     "command": "$CLAUDE_PROJECT_DIR/src/thalamus/harness/hooks/claude-code/reflex.sh"}]}]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_require_binaries jq uv || exit 0

input=$(cat)

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')
[ "$tool_name" = "Bash" ] || exit 0

session=$(printf '%s' "$input" | jq -r '.session_id // empty')
[ -n "$session" ] || exit 0

stdout=$(printf '%s' "$input" | jq -r '.tool_response.stdout // ""')
stderr=$(printf '%s' "$input" | jq -r '.tool_response.stderr // ""')
interrupted=$(printf '%s' "$input" | jq -r '.tool_response.interrupted // false')

failure_re='^(FAILED|ERROR) |^Traceback \(most recent call last\)|: command not found|^[A-Za-z_.]*(Error|Exception): |^error(\[[A-Za-z0-9_-]+\])?: |^E {2,}'

if [ "$interrupted" != "true" ] \
  && ! printf '%s\n%s\n' "$stdout" "$stderr" | grep -qE "$failure_re"; then
  exit 0
fi

scope="$(thalamus_scope_from_payload "$input")"
agent_id=$(printf '%s' "$input" | jq -r '.agent_id // ""')
agent_type=$(printf '%s' "$input" | jq -r '.agent_type // ""')
cwd=$(printf '%s' "$input" | jq -r '.cwd // ""')

# stdout then stderr, as the model saw them — the order gremlin-tap.sh records.
response=$(mktemp "${TMPDIR:-/tmp}/thalamus-reflex.XXXXXX")
printf '%s\n%s\n' "$stdout" "$stderr" >"$response"

log_dir="$HOME/.thalamus/logs"
mkdir -p "$log_dir"

# `--project <checkout>`, not the session's cwd: a session pinned into another repo
# has a cwd that is not a uv project with thalamus in it (session-end.sh's reason).
# The worker's stderr — a graph that is down, a refusal — goes to a log rather than
# to the session: a PostToolUse hook's stderr reaches the user as noise, and a reflex
# that cannot serve is meant to be silent.
context=$(uv run --project "$(thalamus_repo_root)" thalamus reflex \
  --session-id "$session" --scope "$scope" \
  --agent-id "$agent_id" --agent-type "$agent_type" \
  --cwd "$cwd" --tool-name "$tool_name" \
  --response-file "$response" 2>>"$log_dir/reflex.log") || context=""
rm -f "$response"

[ -n "$context" ] || exit 0

jq -cn --arg ctx "$context" \
  '{hookSpecificOutput:{hookEventName:"PostToolUse", additionalContext:$ctx}}'

exit 0
