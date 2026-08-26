#!/bin/bash
# Thalamus PreToolUse hook — role boundary on writes (codex).
#
# The one script in this directory that is a real adapter rather than a delegator,
# because codex's editing surface is shaped differently from Claude Code's. Measured
# 2026-08-17 against a live `codex exec`:
#
#   {"tool_name": "apply_patch",
#    "tool_input": {"command": "*** Begin Patch\n*** Update File: /abs/path/note.txt\n
#                               @@\n hello\n+second\n*** End Patch"}}
#
# There is no `file_path`, and one call can touch several files. So the guard cannot
# be handed this payload as it stands — `../claude-code/role-guard.sh` reads
# `.tool_input.file_path` and decides about exactly one target.
#
# Lifting the paths out is **parsing a declared grammar, not guessing at a string**:
# `*** Add File:`, `*** Update File:`, `*** Delete File:` and `*** Move to:` are the
# patch envelope's own header lines. That distinction is the same one
# `harness/transcripts.py` draws when it refuses to infer touched files from a shell
# command — a shell line has no grammar to parse, and this does.
#
# One guard invocation per named path, and the first denial denies the whole call.
# That is not a simplification: `apply_patch` applies atomically, so a partial verdict
# has no meaning — either every file it names may be written or the call may not run.
# Each invocation leaves its own `role-boundary` row in ~/.thalamus/guards/, which is
# what an audit of a multi-file patch wants: one decision per file, not one summary.
#
# Every other tool name is passed through untouched. `mcp__penpot__*` is the live case
# — codex prefixes MCP tools exactly as Claude Code does (measured:
# `mcp__thalamus__memory_open_threads`), so the capability boundary over a named
# server's tool surface needs no translation at all.
#
# What is NOT wired, and why it is an absence rather than an oversight: codex's skill
# and artifact surfaces have not been measured, so `Skill` and `Artifact` are not in
# this hook's matcher. A matcher naming a tool nobody has observed is a guess that
# reads as enforcement. The capability half of the role boundary is therefore
# unmeasured on codex; the path half — the one that binds `qe` and `designer`, and
# the only one that binds `main` — is what this enforces.

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"
. "$here/resolve-scope.sh"
thalamus_sandbox_guard

guard="$here/../claude-code/role-guard.sh"

# The shared read, not a bare `cat`: this was the last entry point still parsing its
# own stdin, and under `set -euo pipefail` malformed JSON killed it at the jq below
# with jq's exit code rather than the blocking one. codex reads exit 2 as a denial,
# the same as Claude Code, so the claude-code helper is the right one here.
thalamus_read_guard_input role-guard.sh
input="$thalamus_guard_input"
tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')

if [ "$tool_name" != "apply_patch" ]; then
  # `exec` inside a pipeline replaces that subshell only, so this script keeps
  # running afterwards — the delegate's verdict has to be carried back by hand. Left
  # to `set -e` it would still work today and stop working the moment anything is
  # added below, which is exactly the kind of silence a guard must not have.
  set +e
  printf '%s' "$input" | thalamus_codex_delegate role-guard.sh
  rc=$?
  set -e
  exit "$rc"
fi

patch=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
[ -n "$patch" ] || exit 0
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')

# The header lines, in the order the patch names them. `sed -n s///p` rather than a
# grep-and-cut pipeline so a path containing a colon survives intact.
paths=$(printf '%s\n' "$patch" | sed -n \
  -e 's/^\*\*\* Add File: //p' \
  -e 's/^\*\*\* Update File: //p' \
  -e 's/^\*\*\* Delete File: //p' \
  -e 's/^\*\*\* Move to: //p')
[ -n "$paths" ] || exit 0

while IFS= read -r path; do
  [ -n "$path" ] || continue
  # A deny_glob like `*/src/*` is matched against the path as written, so a relative
  # target has to be resolved before it is asked about — otherwise `src/foo.py` slips
  # a boundary that `<repo>/src/foo.py` would have hit. Codex sent absolute paths in
  # the measured case; this covers the shape it does not promise not to send.
  case "$path" in
    /*) ;;
    *) [ -z "$cwd" ] || path="$cwd/$path" ;;
  esac

  # `tool_name` stays `apply_patch`: the guard's event row records the tool that was
  # actually called, and a row claiming `Write` would put a tool codex does not have
  # into a ledger that is read as evidence. `../claude-code/role-guard.sh` names
  # `apply_patch` alongside the Claude Code editors for exactly this call.
  payload=$(printf '%s' "$input" | jq -c --arg p "$path" \
    '{tool_name: "apply_patch",
      tool_input: {file_path: $p},
      session_id: (.session_id // ""),
      cwd: (.cwd // "")}')

  set +e
  reason=$(printf '%s' "$payload" | env -u CLAUDE_CODE_AGENT THALAMUS_HARNESS=codex \
    "$guard" 2>&1 >/dev/null)
  rc=$?
  set -e

  if [ "$rc" -eq 2 ]; then
    printf '%s\n' "$reason" >&2
    exit 2
  fi
done <<EOF
$paths
EOF

exit 0
