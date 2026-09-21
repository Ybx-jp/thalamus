#!/bin/bash
# Holds merge-guard.sh to merge-guard.cases. Run it after touching either.
#
#     bash .claude/hooks/merge-guard-test.sh
#
# Not part of the package and not run by CI: the guard protects an operator's local
# session, and CI has no session to protect. It is here so that a change to the matching
# has somewhere to fail.

set -uo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
guard="$here/merge-guard.sh"
cases="$here/merge-guard.cases"

command -v jq >/dev/null 2>&1 || { echo "jq is needed to run these cases"; exit 2; }

# Each case is put to the guard in BOTH payload dialects and has to come back the same in
# each: Claude Code and codex send `hook_event_name` and read
# `hookSpecificOutput.permissionDecision`, while Cursor's `beforeShellExecution` sends
# neither and reads a top-level `permission`. The guard answers in whichever dialect it was
# asked in, so a runner that only spoke one of them read every Cursor-shaped refusal as an
# allow — which is what this file did, and every DENY case here was failing because of it
# rather than because of the guard.
verdict() { # $1 dialect, $2 command
  local payload
  if [ "$1" = claude ]; then
    payload=$(jq -cn --arg c "$2" \
      '{hook_event_name:"PreToolUse", tool_name:"Bash", tool_input:{command:$c}}')
  else
    payload=$(jq -cn --arg c "$2" '{command:$c}')
  fi
  printf '%s' "$payload" | "$guard" | jq -r '
    if (.hookSpecificOutput.permissionDecision == "deny") or (.permission == "deny")
    then "DENY" else "allow" end' 2>/dev/null
}

fail=0
while IFS=$'\t' read -r want cmd; do
  case "$want" in ''|'#'*) continue ;; esac
  claude=$(verdict claude "$cmd"); [ -n "$claude" ] || claude=allow
  cursor=$(verdict cursor "$cmd"); [ -n "$cursor" ] || cursor=allow
  if [ "$claude" != "$cursor" ]; then
    printf '  FAIL  dialects disagree: claude=%s cursor=%s  %s\n' "$claude" "$cursor" "$cmd"
    fail=1
  elif [ "$claude" = "$want" ]; then
    printf '  ok    %-6s %s\n' "$claude" "$cmd"
  else
    printf '  FAIL  want=%s got=%s  %s\n' "$want" "$claude" "$cmd"
    fail=1
  fi
done < "$cases"

[ "$fail" -eq 0 ] && echo "merge guard: all cases hold"
exit $fail
