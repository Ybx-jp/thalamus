#!/bin/bash
# Thalamus PostToolUse hook — stage validated graph queries for RECIPES.md.
#
# The gremlin-python skill's rule 5 is "check RECIPES.md before writing, add to
# it after validating". Step one is enforced by the PreToolUse guard; step two
# was left to the agent remembering, mid-task, a second obligation from a skill
# it invoked for the first one. Measured at 0-for-3 in one session: three
# reusable queries ran green against the live graph and none reached the store.
#
# Relying on an agent to remember step two of a skill is a losing bet, so this
# records the candidates instead. It does NOT write RECIPES.md — admission is a
# judgement ("it answered a real question a session actually had") and stays
# human. What it removes is the failure mode where the query is gone by the time
# anyone decides.
#
# Admission threshold, enforced here: the query RAN and RETURNED something. A
# traversal that errored or came back empty is not a proven recipe, and staging
# it would fill the queue with the exact thing the skill warns about — lazy
# traversals that silently do nothing.
#
# Read the queue with `thalamus eval recipes --staged`.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

input=$(cat)

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')

case "$tool_name" in
  mcp__thalamus__memory_query)
    surface="memory_query"
    query=$(printf '%s' "$input" | jq -r '.tool_input.query // empty')
    response=$(printf '%s' "$input" | jq -r '
      if (.tool_response | type) == "string" then .tool_response
      else (.tool_response.content // .tool_response | tostring) end')
    ;;
  Bash)
    surface="gremlin-python"
    query=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
    # Same marker heuristic as gremlin-guard.sh and gremlin-tap.sh: only Bash
    # that inlines gremlin-python is a graph query. Script files are invisible
    # here exactly as they are to the guard — a known, named residual.
    printf '%s' "$query" | grep -qE \
      'gremlin_python|with_remote\(|DriverRemoteConnection|substrate\.writer import|from thalamus\.substrate' \
      || exit 0
    response=$(printf '%s' "$input" | jq -r '(.tool_response.stdout // "")')
    ;;
  *)
    exit 0
    ;;
esac

[ -n "$query" ] || exit 0

# Did it actually answer? An empty or error-shaped response is not a validation.
[ -n "${response//[[:space:]]/}" ] || exit 0
printf '%s' "$response" | grep -qiE \
  'Traceback|GremlinServerError|^error:|is a master-plane instrument|No results|returned nothing' \
  && exit 0

# A GraphTraversal repr means the traversal was never iterated — the single most
# common gremlin mistake this project has, and the opposite of a proven recipe.
printf '%s' "$response" | grep -qE \
  'GraphTraversal object at|<gremlin_python' \
  && exit 0

stage_dir="$HOME/.thalamus/recipes"
mkdir -p "$stage_dir"

printf '%s' "$input" | jq -c \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg scope "$(thalamus_scope_from_payload "$input")" \
  --arg surface "$surface" \
  --arg query "$query" \
  --arg chars "$(printf '%s' "$response" | wc -c)" \
  '{ts: $ts,
    session_id: (.session_id // ""),
    scope: $scope,
    surface: $surface,
    query: $query,
    response_chars: ($chars | tonumber)}' \
  >> "$stage_dir/staged.jsonl"

exit 0
