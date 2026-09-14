#!/bin/bash
# claims-ledger merge guard — PreToolUse, matcher Bash.
#
# A `code:` ground pins a section of a file at a commit. A squash merge replaces those
# commits with a new one and a rebase merge rewrites them; either way `resolve` can no
# longer find the commit a ground names, every pinned entry fails at once, and the repair
# is a supersession per entry. CLAUDE.md states the constraint; this refuses the two
# commands that break it.
#
# Scoped deliberately narrow — the two merge-time history rewrites, not `git rebase` in
# general — so that it never fires on ordinary branch work. The wider hazard is prose in
# CLAUDE.md, because a guard that cries wolf gets switched off.
#
# The match is anchored at a command position: the start of a line, or just past a shell
# operator. Without that anchor the guard reads its own subject matter as an instance of
# it — the commit that introduced this file was refused by it, because the message quoted
# the two commands it forbids. Known limit: a heredoc line that BEGINS with one of them
# still matches, since this reads the command as text and does not parse it. That case is
# rare and visible, where a backticked mention inside prose is neither.
#
# The durable fix is server-side: `allow_squash_merge` and `allow_rebase_merge` false on
# the GitHub repository, which stops the merge button as well as the CLI. This hook is
# the half that can be kept in the repository.

set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0
input=$(cat) || exit 0

# `tool_input.command` is Claude Code's shape and codex's; Cursor's
# `beforeShellExecution` puts the command at the top level. One read covers all three.
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // .command // empty' 2>/dev/null) || exit 0
[ -n "$cmd" ] || exit 0

# And one refusal, in the shape the caller understands. Cursor answers with a top-level
# permission and carries the reason on both message fields: measured elsewhere, a denial's
# tool result shows `user_message` and not `agent_message`, and a block with no reason
# reaching the agent is a stall rather than a redirection.
deny() {
  if printf '%s' "$input" | jq -e 'has("hook_event_name")' >/dev/null 2>&1; then
    jq -cn --arg r "$1" \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",
                            permissionDecision:"deny",
                            permissionDecisionReason:$r}}'
  else
    jq -cn --arg r "$1" '{permission:"deny", agent_message:$r, user_message:$r}'
  fi
  exit 0
}

reason="claims-ledger: this repository's ledger pins claims to commit ids, so a squashed or rebased merge breaks every pinned entry at once and costs a supersession each. Merge commits only — see CLAUDE.md. Use the --merge strategy, or --no-ff. If you genuinely mean to rewrite the history and accept the repair, the operator has to run it."

# A command position: the start of a line, or just past a shell operator.
at='(^|[;&|(){}])[[:space:]]*'

# The GitHub CLI merging a pull request with a rewriting strategy, long or short flag.
if printf '%s' "$cmd" | grep -qE \
  "${at}(sudo[[:space:]]+)?gh[[:space:]]+pr[[:space:]]+merge\b[^|;&]*(--squash|--rebase|[[:space:]]-[a-zA-Z]*[sr]([[:space:]]|\$))"; then
  deny "$reason"
fi

# git, collapsing a branch into one commit. `merge` has to be the subcommand — only
# git's own global options may sit in front of it — or the pattern reads the word out of
# a quoted argument: `git commit -m "never gh pr merge --squash here"` matched, once.
opts="(-[cC][[:space:]]+[^[:space:]]+[[:space:]]+|--[a-z-]+=[^[:space:]]+[[:space:]]+)*"
if printf '%s' "$cmd" | grep -qE \
  "${at}(sudo[[:space:]]+)?git[[:space:]]+${opts}merge\b[^|;&]*--squash"; then
  deny "$reason"
fi

exit 0
