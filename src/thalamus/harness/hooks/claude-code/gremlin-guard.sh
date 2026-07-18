#!/bin/bash
# Thalamus PreToolUse hook — gremlin-python terminal-step guard (Claude Code).
#
# gremlin-python traversals are lazy: a traversal that never reaches a terminal
# step (iterate(), to_list(), next(), has_next(), or being consumed as an
# iterator) is never sent to the server. It doesn't error — it silently does
# nothing, which is worse. This guard intercepts inline Bash gremlin-python
# (python -c, heredocs) whose text builds a traversal but never terminates one,
# and blocks it with instruction instead of letting it run doomed. The
# gremlin-lang side of the same slip (python dialect on `memory_query`) is
# caught by the lexical guard in substrate/query.py — together they police both
# directions of the dialect boundary. Deterministic pre-execution feedback is
# the cheap half of the execution-feedback loop (Self-Debugging, arXiv
# 2304.05128): the error arrives before the query instead of after.
#
# Every verdict is an event: gremlin-marker commands append one JSONL line
# (block or pass) to ~/.thalamus/guards/<YYYY-MM>.jsonl, so the guard's own
# effectiveness is measurable — block counts, rescue rate (block followed by a
# pass in the same session), and friction (repeat blocks) all read from this
# file (`thalamus eval gremlin`). The guard without the event log would be
# activity without measurement.
#
# Scope: fires only when the command text itself contains gremlin-python
# connection markers. Running a script file (`python lab/x.py`) carries no
# markers and is never touched — this guards the ad-hoc one-liner path where
# the doomed queries were actually observed.
#
# Install (project .claude/settings.json):
#   {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
#     "command": "$CLAUDE_PROJECT_DIR/src/thalamus/harness/hooks/claude-code/gremlin-guard.sh"}]}]}}

set -euo pipefail

input=$(cat)

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')
[ "$tool_name" = "Bash" ] || exit 0

command=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
[ -n "$command" ] || exit 0

# Only inline gremlin-python concerns this guard.
printf '%s' "$command" | grep -qE \
  'gremlin_python|with_remote\(|DriverRemoteConnection|substrate\.writer import|from thalamus\.substrate' \
  || exit 0

log_event() {
  local verdict="$1"
  local guard_dir="$HOME/.thalamus/guards"
  mkdir -p "$guard_dir"
  printf '%s' "$input" | jq -c \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg scope "${THALAMUS_SCOPE:-main}" \
    --arg verdict "$verdict" \
    --arg guard "terminal-step" \
    --arg hash "$(printf '%s' "$command" | sha256sum | cut -c1-16)" \
    '{ts: $ts,
      session_id: (.session_id // ""),
      scope: $scope,
      cwd: (.cwd // ""),
      guard: $guard,
      verdict: $verdict,
      command_hash: $hash}' >> "$guard_dir/$(date -u +%Y-%m).jsonl" || true
}

# Any terminal step or iterator consumption satisfies the guard. `.result(` is
# the Client.submit path, where the server iterates and laziness is not in play.
# House wrappers (recall, run_query) iterate internally, and text-manipulation
# commands (sed/re.sub/read_text) merely mention marker strings while editing
# code — the retrospective baseline (lab/008) found every archive hit without
# these allowances was a false positive, and false positives teach agents to
# route around the guard.
if printf '%s' "$command" | grep -qE \
  '\.iterate\(|\.to_list\(|\.toList\(|next\(|\.has_next\(|list\(|\.result\(|for [A-Za-z_]+ in |run_query\(|recall\(|re\.sub\(|read_text\(|write_text\(|(^|[;&| ])sed '
then
  log_event pass
  exit 0
fi

log_event block

cat >&2 <<'EOF'
Blocked: this command builds a gremlin-python traversal but never invokes the
iterator. Traversals are lazy — without a terminal step nothing is sent to the
server and the traversal silently does nothing. Terminate every traversal with
one of: .iterate() (effects, discard results), .to_list() (all results),
.next() (one result). See the gremlin-python skill
(.claude/skills/gremlin-python/SKILL.md) and check its RECIPES.md for a proven
query before writing a new one.
EOF
exit 2
