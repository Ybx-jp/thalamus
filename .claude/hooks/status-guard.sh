#!/bin/bash
# claims-ledger status guard — an agent-harness hook. PostToolUse, matcher Edit|Write|MultiEdit.
#
# `pin-guard.sh` watches the ground; this watches the citation. Different findings, and
# different repairs, which is why they are separate hooks.
#
# When an entry's status moves — a drift contests it, a ground it cites falls, a person
# refutes it — every sentence citing it under an act that status does not allow says
# something untrue, and `references` names it. The finding is precise; the repair is a
# judgement, and four of them are legitimate. They differ in what they assert and in what
# they cost, and that difference is not in the finding.
#
# So this hook does one thing: when `references` objects to an act against a status, it
# lays the four out and leaves the choice where it belongs. It never chooses, and it never
# writes.
#
# It reports a second shape for the same reason, and separately: an id the ledger minted, a
# comma, and an act-shaped word that is not a citation act. That is a citation with the wrong act rather
# than the wrong target, its repair is the act and not the sentence, and the two ways in —
# a mistyped act, and an act only an entry may perform written into a document — are both
# things an editing session produces and can fix on the spot.
#
# Throttled per shape, on the digest of the finding, so an unchanged objection is reported
# once and a NEW one still speaks. Nothing here is repository-specific: the interpreter is
# discovered and the ledger is asked about itself.
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

# Derived from this script's own location rather than from `cwd`, so a copy living in a
# scratch worktree guards that worktree. Adjust the number of `..` if you move it.
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

case "$path" in
  ""|"$root"/*) ;;
  *) exit 0 ;;
esac

# An interpreter plus `-m`, never the `claims-ledger` console script: a console script in
# a virtualenv that is not active is not on PATH, and the hook would fail on every firing.
python=""
for candidate in "$root/.venv/bin/python" "$root/venv/bin/python" "$(command -v python3 2>/dev/null)"; do
  [ -n "$candidate" ] && [ -x "$candidate" ] || continue
  if "$candidate" -c 'import claims_ledger' >/dev/null 2>&1; then python="$candidate"; break; fi
done
[ -n "$python" ] || exit 0

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/claims-ledger/status-guard"
state_file="$state_dir/$session"

emit() {
  if [ "$dialect" = cursor ]; then
    jq -cn --arg ctx "$1" '{additional_context: $ctx}'
  else
    jq -cn --arg ctx "$1" \
      '{hookSpecificOutput:{hookEventName:"PostToolUse", additionalContext:$ctx}}'
  fi
}

fired() { [ -f "$state_file" ] && grep -qxF "$1" "$state_file" 2>/dev/null; }
remember() { mkdir -p "$state_dir" 2>/dev/null && printf '%s\n' "$1" >> "$state_file" 2>/dev/null || true; }

# Read-only. Whether an act is legal against a status is `references`' question and is
# asked of the package rather than reimplemented here; a hook that restated ACT_ALLOWS
# would drift from the checker it serves.
finding=$(cd "$root" && timeout 20 "$python" -m claims_ledger references 2>&1) || true
[ -n "$finding" ] || exit 0

# Two act shapes, and no others. Every remaining `references` failure — a dangling id, a
# one-way reference, an Assertion carried verbatim — has its own repair and is left to the
# checker's own words at commit time.
mismatch=$(printf '%s\n' "$finding" | grep -E 'against .*, whose status is ' || true)

# The other act shape: a parenthesis that is a citation in every respect but the act.
# Which words are citation acts is `references`' question and is left to it; this reads
# what it said.
miswritten=$(printf '%s\n' "$finding" | grep -F 'is not a citation act' || true)

if [ -n "$miswritten" ]; then
  key="miscite:$(printf '%s' "$miswritten" | cksum | tr -d ' ')"
  if ! fired "$key"; then
    remember "$key"
    emit "claims-ledger status guard: a document holds a parenthesis shaped like a citation whose act is not a citation act.

$miswritten

The citation pattern is built from the citation acts, so this matched nothing and no other rule reads documents — before this check it sat in a checked document as prose nothing looked at. Two ways in, and the repair differs:

  - A mistyped act. Print the list rather than retyping from memory: \`python -c 'from claims_ledger import ACTS; print(ACTS)'\`. Then write it on both sides — the document AND the row in the entry's ## References.
  - An act only an entry may perform, written in a document. \`challenges\` and \`distinguishes\` are relations one entry states about another, in an \`entry:\` ground; a document has no Scope to hold apart from anything. If the sentence means to record that two entries are different claims about one artifact, that belongs in the newer entry's Grounds, not here. The \`choosing-a-citation-act\` skill has both acts in full.

An id in a parenthesis of its own, or named in running prose, is a document mentioning an entry rather than citing it, and is not what this reports."
    exit 0
  fi
fi

# The third shape, and the only one that arrives because a project asked for it. Whether
# it is reported at all is `citation-placement` in the configuration; this reads what
# `references` said rather than asking the configuration itself.
placement=$(printf '%s\n' "$finding" | grep -F 'from outside' || true)

if [ -n "$placement" ]; then
  key="placement:$(printf '%s' "$placement" | cksum | tr -d ' ')"
  if ! fired "$key"; then
    remember "$key"
    emit "claims-ledger status guard: a citation sits outside the span the entry it names is pinned to.

$placement

The entry rests on a section of this very document, and the citing sentence is somewhere else in it. Move the sentence into that section: what the rule holds is that a promise and the code keeping it sit in one span, so an edit reaches both and a reader who finds either finds the other. Changing the act or the ground is not the repair.

Moving it will flag every entry already pinned to the section it lands in. That is the mechanism working and not a reason to leave the citation where it is — \`has moved\` is a flag, it exits 0, and a claim the change did not touch is discharged by a re-read verdict. The \`choosing-a-citation-act\` skill has the rule and \`repair-a-drifted-pin\` the discharge."
    exit 0
  fi
fi

[ -n "$mismatch" ] || exit 0

key="act:$(printf '%s' "$mismatch" | cksum | tr -d ' ')"
fired "$key" && exit 0
remember "$key"

emit "claims-ledger status guard: a citing sentence names an entry under an act its current status does not allow.

$mismatch

This is \`claims-ledger references\`: the entry's STATUS is what the sentence disagrees with, so re-pinning does not reach it. Several repairs make them agree, and they differ in what they assert and what they cost:

  - Say what is now the case. Change the act in the document AND the matching row in the entry's ## References. \`cites-as-contested\` speaks of a claim under question; \`cites-as-fallen\` is legal against any status.
  - Acknowledge an immaterial change. If a ground moved but the claim is untouched, the entry can return to a live status without a successor. The \`repair-a-drifted-pin\` skill has the sequence.
  - Supersede. The claim now rests on different evidence, so it becomes a new entry with its citations moved.
  - Record that it did not survive — a refuted or retracted verdict, and the prose rewritten.

\`claims-ledger status\` is what the statuses are right now, and the \`choosing-a-citation-act\` skill covers which act each status allows. Removing the citation also clears the finding, by removing the link the ledger exists to keep."

exit 0
