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

# Any terminal step or iterator consumption satisfies the guard. `.result(` is
# the Client.submit path, where the server iterates and laziness is not in play.
printf '%s' "$command" | grep -qE \
  '\.iterate\(|\.to_list\(|\.toList\(|next\(|\.has_next\(|list\(|\.result\(|for [A-Za-z_]+ in ' \
  && exit 0

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
