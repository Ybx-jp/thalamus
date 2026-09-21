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

# `timeout` is GNU coreutils and macOS ships none, so a hook written with it bare behaves
# differently on the two platforms this package tests on: this guard denied every merge with
# `line 140: timeout: command not found`, and the three guards that append `|| true` went
# the other way and reported nothing at all — a drift check that is silent on a whole
# platform. Where the utility is absent the command is run unbounded, which is the same
# answer one moment later rather than a different answer immediately; the walks it wraps are
# bounded by the package's own git timeout in any case.
if command -v timeout >/dev/null 2>&1; then
  bounded() { timeout 20 "$@"; }
else
  bounded() { "$@"; }
fi


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

# A merge that would land two entries answering to one number. Nothing reported that until
# `validate` learned to, and the repair — rewriting the branch being merged so its entries
# are created under the ids they will keep — has to happen BEFORE the merge: measured on
# git 2.43.0, a conflicted merge fires no hook at all, its resolution commit fires
# `pre-commit`, and a clean auto-merge fires `post-merge`, so every hook a merge has fires
# once the merge has already happened.
#
# What to do about it is the project's to configure rather than this script's to decide.
# `--on-merge` is the package reading `merge-renumber`: `off` says nothing, `refuse` exits
# non-zero with the repair named, and `rewrite` renumbers the branch and lets the merge
# proceed. A branch this checkout cannot plan — a merge of something that is not a branch
# here, a project with no ledger — exits zero, because a guard is asked about every merge
# and most of them are not its business.
#
# `git merge <branch>` only. `gh pr merge` merges on the server, where nothing local can
# rewrite the branch first and the branch has been pushed by then anyway.
if printf '%s' "$cmd" | grep -qE "${at}(sudo[[:space:]]+)?git[[:space:]]+${opts}merge\b"; then
  # The FIRST thing after `merge` that is not an option and is not an option's value.
  # Taking the last one reads `git merge topic -m "a message"` as a merge of `msg`, and a
  # branch nobody has is answered with an allow — so the guard went quiet on exactly the
  # merges that carry a message.
  incoming=$(printf '%s' "$cmd" \
    | sed -E 's/.*[[:space:]]merge[[:space:]]+//; s/[|;&].*//' \
    | tr ' \t' '\n\n' \
    | awk '
        skip { skip = 0; next }
        $0 == "" { next }
        /^-/ {
          if ($0 == "-m" || $0 == "-s" || $0 == "-X" || $0 == "-F" || $0 == "--message" ||
              $0 == "--strategy" || $0 == "--strategy-option" || $0 == "--file" ||
              $0 == "--into-name") { skip = 1 }
          next
        }
        { print; exit }')

  # Derived from this script's own location rather than from `cwd`, so a copy living in a
  # scratch worktree guards that worktree.
  here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || exit 0

  # The project root, asked rather than counted: an installed copy of this script and the
  # one inside the package sit at different depths, so a fixed number of `..` would guard
  # the wrong tree from one of them.
  project_root() {
    local dir=$1
    for named in "${CLAIMS_LEDGER_PROJECT_DIR:-}" "${CLAUDE_PROJECT_DIR:-}"; do
      if [ -n "$named" ] && [ -d "$named" ]; then (cd -- "$named" && pwd) && return 0; fi
    done
    while [ "$dir" != "/" ] && [ -n "$dir" ]; do
      for marker in claims-ledger.toml pyproject.toml .git; do
        [ -e "$dir/$marker" ] && { printf '%s\n' "$dir"; return 0; }
      done
      dir=$(dirname -- "$dir")
    done
    (cd -- "$1/../.." && pwd)
  }
  root=$(project_root "$here") || exit 0

  # An interpreter plus `-m`, never the `claims-ledger` console script: a console script in
  # a virtualenv that is not active is not on PATH, and the hook would fail on every firing.
  python=""
  for candidate in "$root/.venv/bin/python" "$root/venv/bin/python" "$(command -v python3 2>/dev/null)"; do
    [ -n "$candidate" ] && [ -x "$candidate" ] || continue
    if "$candidate" -c 'import claims_ledger' >/dev/null 2>&1; then python="$candidate"; break; fi
  done

  if [ -n "$incoming" ] && [ -n "$python" ]; then
    receiving=$(cd "$root" && git rev-parse --abbrev-ref HEAD 2>/dev/null)
    if [ -n "$receiving" ] && [ "$receiving" != "HEAD" ]; then
      finding=$(cd "$root" && bounded "$python" -m claims_ledger renumber \
        --onto "$receiving" --branch "$incoming" --on-merge 2>&1)
      [ $? -eq 0 ] || deny "$finding"
    fi
  fi
fi

exit 0
