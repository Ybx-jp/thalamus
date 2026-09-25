#!/bin/bash
# Thalamus PostToolUse / PostToolUseFailure hook — memory reflex (Claude Code).
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
# harness/reflex.py, which is where the logic is measured and typed. On no match the
# agent pays for no `uv run`: the shadow record below runs detached.
#
# Two events, one payload shape each. Claude Code sends a Bash call that exits 0 to
# `PostToolUse`, with the output in `tool_response.stdout`/`.stderr` and the flag in
# `.interrupted`; it sends one that exits non-zero to `PostToolUseFailure`, with the
# output in `error` — an `Exit code N` line, then stdout and stderr interleaved — and
# the flag in `is_interrupt` (A0160, cites-as-live).
#
# The exit status decides which event runs this script, and nothing else. Whether the
# reflex fires is decided the same way on both: the output contains a failure line
# (FAILURE_PATTERN), or the call was interrupted. So a non-zero exit with ordinary
# output — `grep` finding no match, `test -f` on a missing file, `diff` finding a
# difference — reaches this script and exits here, and a pytest run that exits 0
# behind `| tail` but prints `FAILED` fires (A0165, cites-as-live). The regex is
# harness/reflex.py's FAILURE_PATTERN verbatim; tests/test_reflex.py holds the two
# equal.
#
# Bulk content travels by file, resolved fields as flags — `extract --transcript` and
# `delegate --input`'s idiom. A 40-failure pytest dump on argv is what ARG_MAX exists
# to break.
#
# Install (project .claude/settings.json), the same group under each event:
#   {"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
#     "command": "$CLAUDE_PROJECT_DIR/src/thalamus/harness/hooks/claude-code/reflex.sh"}]}],
#     "PostToolUseFailure": [ …the same group… ]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_require_binaries jq uv || exit 0

input=$(cat)

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')
[ "$tool_name" = "Bash" ] || exit 0

session=$(printf '%s' "$input" | jq -r '.session_id // empty')
[ -n "$session" ] || exit 0

event=$(printf '%s' "$input" | jq -r '.hook_event_name // "PostToolUse"')

# The output as the model saw it: a result's stdout then stderr (the order
# gremlin-tap.sh records), or a failure's `error` string whole.
if [ "$event" = "PostToolUseFailure" ]; then
  output=$(printf '%s' "$input" | jq -r '.error // ""')
  interrupted=$(printf '%s' "$input" | jq -r '.is_interrupt // false')
else
  output=$(printf '%s' "$input" \
    | jq -r '(.tool_response.stdout // "" | sub("\n+$"; "")) + "\n" + (.tool_response.stderr // "")')
  interrupted=$(printf '%s' "$input" | jq -r '.tool_response.interrupted // false')
fi

failure_re='^(FAILED|ERROR) |^Traceback \(most recent call last\)|: command not found|^[A-Za-z_.]*(Error|Exception): |^error(\[[A-Za-z0-9_-]+\])?: |^E {2,}'

agent_id=$(printf '%s' "$input" | jq -r '.agent_id // ""')

response=$(mktemp "${TMPDIR:-/tmp}/thalamus-reflex.XXXXXX")
printf '%s\n' "$output" >"$response"

log_dir="$HOME/.thalamus/logs"
mkdir -p "$log_dir"

# A call the failure test passes over is shadow-logged: `thalamus reflex --shadow`
# records what it would have anchored on and retrieves nothing. Detached, with every
# stream closed, so the hook returns at once and the agent never waits on a `uv run`
# for a call that was not a failure; the child removes the response file itself
# (A0167, cites-as-live).
if [ "$interrupted" != "true" ] \
  && ! printf '%s\n' "$output" | grep -qE "$failure_re"; then
  nohup sh -c '
    uv run --project "$1" thalamus reflex --shadow \
      --session-id "$2" --agent-id "$3" --event "$4" --response-file "$5"
    rm -f "$5"
  ' shadow "$(thalamus_repo_root)" "$session" "$agent_id" "$event" "$response" \
    </dev/null >/dev/null 2>>"$log_dir/reflex.log" &
  exit 0
fi

scope="$(thalamus_scope_from_payload "$input")"
agent_type=$(printf '%s' "$input" | jq -r '.agent_type // ""')
cwd=$(printf '%s' "$input" | jq -r '.cwd // ""')
# An agentic firing is queued rather than served here: its worker builds an excerpt
# of the session from the transcript, keeping this call's result by its id, and the
# carrier measures delivery depth from the same id.
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // ""')
tool_use_id=$(printf '%s' "$input" | jq -r '.tool_use_id // ""')

# `--project <checkout>`, not the session's cwd: a session pinned into another repo
# has a cwd that is not a uv project with thalamus in it (session-end.sh's reason).
# The worker's stderr — a graph that is down, a refusal — goes to a log rather than
# to the session: a PostToolUse hook's stderr reaches the user as noise, and a reflex
# that cannot serve is meant to be silent.
context=$(uv run --project "$(thalamus_repo_root)" thalamus reflex \
  --session-id "$session" --scope "$scope" \
  --agent-id "$agent_id" --agent-type "$agent_type" \
  --cwd "$cwd" --tool-name "$tool_name" --event "$event" \
  --transcript "$transcript" --tool-use-id "$tool_use_id" \
  --response-file "$response" 2>>"$log_dir/reflex.log") || context=""
rm -f "$response"

[ -n "$context" ] || exit 0

jq -cn --arg event "$event" --arg ctx "$context" \
  '{hookSpecificOutput:{hookEventName:$event, additionalContext:$ctx}}'

exit 0
