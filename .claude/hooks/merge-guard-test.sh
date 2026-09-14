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

fail=0
while IFS=$'\t' read -r want cmd; do
  case "$want" in ''|'#'*) continue ;; esac
  got=$(printf '{"tool_input":{"command":%s}}' "$(jq -Rn --arg c "$cmd" '$c')" \
        | "$guard" \
        | jq -r 'if .hookSpecificOutput.permissionDecision=="deny" then "DENY" else "allow" end' 2>/dev/null)
  [ -n "$got" ] || got=allow
  if [ "$got" = "$want" ]; then
    printf '  ok    %-6s %s\n' "$got" "$cmd"
  else
    printf '  FAIL  want=%s got=%s  %s\n' "$want" "$got" "$cmd"
    fail=1
  fi
done < "$cases"

[ "$fail" -eq 0 ] && echo "merge guard: all cases hold"
exit $fail
