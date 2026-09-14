#!/bin/bash
# claims-ledger pin guard — an agent-harness hook. PostToolUse, matcher Edit|Write|MultiEdit.
#
# A ledger pinning prose to the artifacts under it has two failures no checker catches in time:
#
#   1. An edit lands inside a pinned section and nothing says so until `git commit`, by
#      which point the edit is finished and its author has moved on. `freshness` answers
#      in well under a second, so the answer can be had at edit time instead.
#   2. A commitment gets written into prose with no entry behind it. `references` only
#      checks citations that were actually written, so a sentence that asserts something
#      and cites nothing passes every check — which is the drift a ledger exists to
#      prevent, arriving through the one door the checkers do not watch.
#
# Both classes are throttled, because an always-on reminder is wallpaper. (1) is keyed on
# the digest of the finding, so unchanged drift is reported once and NEW drift still
# speaks; (2) is keyed once per session, on the first edit to a configured document.
#
# Nothing here is repository-specific: the interpreter is discovered, and which files
# count as documents is asked of the ledger's own configuration rather than restated.
#
# The hook never blocks: every failure path exits 0 silently. A guard that can break the
# session is worse than no guard.

set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0
input=$(cat) || exit 0


# Which harness is calling, read off the payload rather than passed in at install time:
# Claude Code and codex send `hook_event_name` and take an answer under
# `hookSpecificOutput`; Cursor sends neither, names its events its own way, and reads
# `additional_context` and `permission` at the top level. One script serves all three, so
# there is no flag here to be wired wrong.
dialect=claude
printf '%s' "$input" | jq -e 'has("hook_event_name")' >/dev/null 2>&1 || dialect=cursor

event=$(printf '%s' "$input" | jq -r '.hook_event_name // "postToolUse"' 2>/dev/null) || exit 0
case "$event" in PostToolUse|postToolUse) ;; *) exit 0 ;; esac

# Cursor calls it a conversation; the throttle only needs something stable per session.
session=$(printf '%s' "$input" | jq -r '.session_id // .conversation_id // empty' 2>/dev/null)
[ -n "$session" ] || exit 0

# Absent on codex, whose editor is `apply_patch` and whose payload carries the patch on
# `tool_input.command` instead. That costs the new-claim reminder below, which has to know
# WHICH file was edited; the drift class asks the whole tree and needs no path at all, so
# it still runs. A hook that returned early here would be silent on the harness that edits
# files that way.
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .file_path // empty' 2>/dev/null)

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || exit 0

# The project root, asked rather than counted. `claims-ledger harness install` writes this
# script into a project's own hook directory, while the copy inside the installed package
# sits several directories deeper, so a fixed number of `..` guards the wrong tree from
# one of those two places. Three tries, narrowest first: what the harness says the project
# is, then the nearest ancestor of this script that looks like a project, then two
# directories up, which is where an installed copy sits. The root is never taken from
# `cwd`, which is wherever the session happens to be.
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

rel=""
case "$path" in
  "") ;;
  "$root"/*) rel=${path#"$root"/} ;;
  *) exit 0 ;;
esac

# A virtualenv in the project, then whatever python3 can import the package. Named as an
# interpreter plus `-m`, never as the `claims-ledger` console script, for the reason the
# installed pre-commit hook gives: a console script in a virtualenv that is not active is
# not on PATH, and the hook would fail on every firing.
python=""
for candidate in "$root/.venv/bin/python" "$root/venv/bin/python" "$(command -v python3 2>/dev/null)"; do
  [ -n "$candidate" ] && [ -x "$candidate" ] || continue
  if "$candidate" -c 'import claims_ledger' >/dev/null 2>&1; then python="$candidate"; break; fi
done
[ -n "$python" ] || exit 0

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/claims-ledger/pin-guard"
state_file="$state_dir/$session"

fired() { [ -f "$state_file" ] && grep -qxF "$1" "$state_file" 2>/dev/null; }
remember() { mkdir -p "$state_dir" 2>/dev/null && printf '%s\n' "$1" >> "$state_file" 2>/dev/null || true; }
emit() {
  if [ "$dialect" = cursor ]; then
    jq -cn --arg ctx "$1" '{additional_context: $ctx}'
  else
    jq -cn --arg ctx "$1" \
      '{hookSpecificOutput:{hookEventName:"PostToolUse", additionalContext:$ctx}}'
  fi
}

# --- class drift: measured, re-fires when the finding changes -------------------------
# Read-only, and not gated on the document list: a `code:` ground can pin a file that is
# not a document at all, since documents are the prose scanned for citations and grounds
# are the evidence. `--write` is a judgement about the ledger and belongs to the session,
# never to a hook firing behind the author's back.
finding=$(cd "$root" && timeout 20 "$python" -m claims_ledger freshness 2>&1) || true
if [ -n "$finding" ] && ! printf '%s' "$finding" | grep -q '0 failure(s), 0 flag(s)'; then
  key="drift:$(printf '%s' "$finding" | cksum | tr -d ' ')"
  if ! fired "$key"; then
    remember "$key"
    emit "claims-ledger pin guard: an edit in this repository has drifted a pinned ground.

$finding

A pin is what holds the prose to the artifact under it. Read the finding before deciding anything: \`has moved\` and \`unstable pin\` are FLAGS and exit 0, so the pre-commit hook does not refuse them and this is a report to act on rather than a block to clear; \`withdrawn\` and \`unknown\` are failures and the hook does refuse those. Either way the moment to answer it is now, while the edit is in hand and the artifact is still in front of you.

A flag is not a penalty and not a thing to design around. Drift is this ledger noticing that something a claim rests on has changed, which is what it is for; where the claim is untouched, the answer is a re-read verdict and takes a minute. The \`repair-a-drifted-pin\` skill has each finding and what discharges it. Verdicts append and only append: a ground edited or a verdict removed is caught against history on the next run."
    exit 0
  fi
fi

# --- class newclaim: once per session, on a document the checkers read ----------------
# Which files are documents is asked of the package, not restated here. `tree_documents`
# is the same function the checkers use, so the excludes, the single-level glob semantics
# and the rule that the ledger does not cite itself all come along; a hook that
# reimplemented any of that would drift from the checker it is meant to serve. Anything
# unreadable means silence, not a guess.
[ -n "$rel" ] || exit 0
is_document=$(cd "$root" && timeout 20 "$python" - "$rel" <<'PY' 2>/dev/null
import sys
try:
    from claims_ledger import open_ledger
    from claims_ledger.schema import tree_documents
    docs, _ = tree_documents(open_ledger(root=".").config)
    print("yes" if sys.argv[1] in {rel for rel, _ in docs} else "no")
except Exception:
    pass
PY
) || true
[ "$is_document" = "yes" ] || exit 0

if ! fired newclaim; then
  remember newclaim
  emit "claims-ledger pin guard (once per session): you just edited $rel, one of the documents this ledger reads.

If this edit states a NEW commitment — a sentence a reader would take as a promise the project is answerable for — it needs an entry, grounded in the artifact that keeps it true and cited from the sentence. No checker can find this for you: \`references\` only checks citations that were actually written, so prose that asserts something and cites nothing passes every check.

An entry lands in one commit with the code and the citation: write each ground's anchor as \`=?\`, and \`claims-ledger sha --write\` fills it from the tree; the \`tagging-prose-with-claims\` skill says how. Once you have chosen the ground, \`claims-ledger neighbours 'code: <path> § \"<section>\" =?'\` says which entries are already about it — the pair that is one claim said twice, or two different claims about one artifact, is out of range of every checker and this is the moment anything asks.

Write it in this pass rather than noting it for a later one. Nothing will come back for it: a sentence that promises something and cites nothing is exactly what passes every check, and the citation goes inside the span the entry pins, so a later pass pays the same commit over again plus the drift its own citation causes. If the edit states no new commitment, ignore this."
fi

exit 0
