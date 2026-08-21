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
# connection markers. Running a script file (`python query.py`) carries no
# markers and is never touched — this guards the ad-hoc one-liner path where
# the doomed queries were actually observed.
#
# Install (project .claude/settings.json):
#   {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
#     "command": "$CLAUDE_PROJECT_DIR/src/thalamus/harness/hooks/claude-code/gremlin-guard.sh"}]}]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

thalamus_read_guard_input gremlin-guard.sh
input="$thalamus_guard_input"

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')
[ "$tool_name" = "Bash" ] || exit 0

command=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
[ -n "$command" ] || exit 0

# Only inline gremlin-python concerns this guard.
printf '%s' "$command" | grep -qE \
  'gremlin_python|with_remote\(|DriverRemoteConnection|substrate\.writer import|from thalamus\.substrate' \
  || exit 0

# The event schema carries what the metrics need (verification consultation
# 8f6ad2d6f4024b2c): the command's step fingerprint (so a rescue can be joined
# on traversal intent, not "any later pass"), the branch that satisfied the
# guard (so wrapper/text-edit passes are excluded from rescue eligibility and
# the false-negative rate of the allowlist stays measurable), and the guard
# version (so the event stream stays interpretable across amendments).
log_event() {
  local verdict="$1"
  local branch="$2"
  local guard_dir="$HOME/.thalamus/guards"
  mkdir -p "$guard_dir"
  printf '%s' "$input" | jq -c \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg scope "$(thalamus_scope_from_payload "$input")" \
    --arg verdict "$verdict" \
    --arg branch "$branch" \
    --arg guard "terminal-step" \
    --arg hash "$(printf '%s' "$command" | sha256sum | cut -c1-16)" \
    --arg fp "$(printf '%s' "$command" | grep -oE '\.[A-Za-z_]+\(' | tr -d '.(_' | tr 'A-Z' 'a-z' | paste -sd, - || true)" \
    '{ts: $ts,
      session_id: (.session_id // ""),
      scope: $scope,
      cwd: (.cwd // ""),
      guard: $guard,
      guard_version: 5,
      verdict: $verdict,
      branch: $branch,
      fingerprint: $fp,
      command_hash: $hash}' >> "$guard_dir/$(date -u +%Y-%m).jsonl" || true
}

# Precision gate, ahead of every satisfaction branch: the markers above are
# imports and connection setup, not traversals. The guard's subject is a
# traversal that was *built* and never terminated, so a command that mentions
# a marker without building one — reading a module constant, calling a house
# writer, printing a path — has no laziness to guard and must not be blocked.
# Every traversal starts from a source step, so their joint absence means the
# trigger was over-broad rather than that the terminal step is missing.
# Measured: guard v4 blocked `from thalamus.substrate.snapshot import
# DEFAULT_SNAPSHOT_PATH` + os.path calls, whose own logged fingerprint
# (`exists,getsize,getmtime,…`) contains no graph step at all, and the session
# routed around the guard rather than being rescued by it — the exact
# route-around the v1 retrospective warned about.
if ! printf '%s' "$command" | grep -qE '\.(V|E|addV|addE|inject)\('; then
  log_event pass no-traversal
  exit 0
fi

# Satisfaction branches, most specific first. `terminal` is real iterator
# invocation (`.result(` is the Client.submit path, where the server iterates
# and laziness is not in play). `wrapper` is a house function that iterates
# internally; `textedit` is code manipulation that merely mentions marker
# strings — it stays a distinct branch because a text command may legitimately
# quote traversal syntax (`grep '\.V('`) and so survives the gate above. The
# retrospective baseline found every archive hit outside `terminal`
# was a false positive, and false positives teach agents to route around the
# guard.
if printf '%s' "$command" | grep -qE \
  '\.iterate\(|\.to_list\(|\.toList\(|next\(|\.has_next\(|list\(|\.result\(|for [A-Za-z_]+ in '
then
  log_event pass terminal
  exit 0
fi
if printf '%s' "$command" | grep -qE 'run_query\(|recall\(|from thalamus\.eval'; then
  log_event pass wrapper
  exit 0
fi
# `git commit`/`git tag` carry marker strings as prose in a message body — a
# commit describing this guard quotes `.V(` and names the import, which is the
# same "markers as data, not code" class as an editor invocation and was a
# measured v5 false positive on this very amendment. The residual false
# negative (a doomed traversal chained after a commit) is accepted knowingly:
# the standing trade is that a false positive costs more than a miss, because it
# teaches route-around.
if printf '%s' "$command" | grep -qE 're\.sub\(|read_text\(|write_text\(|(^|[;&| ])sed |(^|[;&| ])grep |(^|[;&| ])rg |(^|[;&| ])git (commit|tag|notes) '; then
  log_event pass textedit
  exit 0
fi

log_event block none

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
