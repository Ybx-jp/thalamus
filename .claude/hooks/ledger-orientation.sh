#!/bin/bash
# claims-ledger orientation — an agent-harness hook. SessionStart.
#
# The other hooks fire when something is wrong, which is the right place for anything that
# can wait. This one runs first and carries the map: which command answers which question,
# what the vocabulary is and where to print it, and which skill takes over for which
# finding. A session that has it reads a finding instead of deciphering one.
#
# Everything variable is asked of the installed package rather than written here — the
# counts, the evidence types this project configures, the statuses. A tally or a table in
# prose is wrong as soon as the project changes and nothing checks it.
#
# The hook never blocks: every failure path exits 0 silently.

set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0

# The payload is read for one thing only: which harness is calling. Claude Code and codex
# send `hook_event_name` and take an answer under `hookSpecificOutput`; Cursor sends
# neither and reads `additional_context` at the top level. Guarded on a terminal so that
# running this by hand to see what it says does not wait forever for a payload.
if [ -t 0 ]; then input=""; else input=$(cat 2>/dev/null || true); fi
dialect=claude
printf '%s' "$input" | jq -e 'has("hook_event_name")' >/dev/null 2>&1 || dialect=cursor

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

# Silent unless this really is a ledger checkout: the hook ships inside an example
# directory that people copy, and firing in a project with no ledger is noise.
[ -d "$root/ledger/entries" ] || exit 0

# An interpreter plus `-m`, never the `claims-ledger` console script: a console script in a
# virtualenv that is not active is not on PATH, and the hook would fail on every firing.
python=""
for candidate in "$root/.venv/bin/python" "$root/venv/bin/python" "$(command -v python3 2>/dev/null)"; do
  [ -n "$candidate" ] && [ -x "$candidate" ] || continue
  if "$candidate" -c 'import claims_ledger' >/dev/null 2>&1; then python="$candidate"; break; fi
done
[ -n "$python" ] || exit 0

counts=$(cd "$root" && timeout 20 "$python" -m claims_ledger status 2>/dev/null | tail -1) || true
[ -n "$counts" ] || counts="a ledger under ledger/entries"

# What a claim may rest on is per project, so it is asked rather than assumed. A ledger
# over source configures different types from one over papers or design documents.
kinds=$(cd "$root" && timeout 20 "$python" -c \
  'from claims_ledger import open_ledger; print(", ".join(open_ledger().config.evidence_types))' 2>/dev/null) || true
[ -n "$kinds" ] || kinds="see the project configuration"

ctx="This project keeps a claims ledger: __COUNTS__. An entry states one thing the project is answerable for, grounded in the artifact that makes it true and cited from the prose that says the same thing in words. This project's grounds may name: __KINDS__. \`claims-ledger check\` runs in the pre-commit hook and again in CI.

EACH COMMAND ANSWERS A DIFFERENT QUESTION, and the wording of a finding says which one you are holding — that is what decides the repair.

  claims-ledger status       what every entry is, and the status it derives to right now
  claims-ledger validate     is each entry well formed?           frontmatter, sections, verdicts, wording
  claims-ledger resolve      does every pointer resolve?          'does not resolve', 'has no section'
  claims-ledger references   does a citation match its target?    '<act> against <id>, whose status is ...'
  claims-ledger propagate    are the entry-to-entry edges sound?
  claims-ledger freshness    has a pinned ground changed?         'has moved', 'withdrawn', 'unstable pin', 'unknown'
  claims-ledger neighbours   which entries are already about this?  advisory; it decides nothing

The middle five are the checkers \`claims-ledger check\` runs, and each exits non-zero on a failure. \`status\` and \`neighbours\` hold nothing to a rule: \`neighbours\` takes an entry, an entry file, or a ground pointer written as an entry would write it, and answers with the entries sharing that ground span or whose Scope cohort nests inside it, saying which of those the ledger already relates. It exits 0 whatever it finds and \`check\` does not run it. Ask it while the grounds are being chosen — nothing downstream asks it, by design.

\`claims-ledger --help\` lists them all and \`claims-ledger <command> --help\` its options. The package is importable, and exports its own vocabulary rather than asking you to remember it:

  python -c 'from claims_ledger import STATUSES, ACTS, ENTRY_ACTS, GRADES, KINDS; print(STATUSES, ACTS)'

THREE THINGS TO HAVE STRAIGHT. A citation names an entry and an act, and the act has to be true of that entry's status as it stands — matching them is the whole of what a citing sentence promises. A ground is evidence that can name any path the project holds, while the configured document globs decide only where citations are read. And there are two act lists: ACTS is what a document may write, ENTRY_ACTS adds the acts only an entry may perform on another entry — \`challenges\`, which demands a verdict on its target, and \`distinguishes\`, which records that two entries are different claims about the same artifact, propagates nothing, and is not support.

A CITATION GOES INSIDE THE SECTION ITS ENTRY PINS. The sentence that makes the promise and the code that keeps it then sit in one span and move together. Writing it there flags the entries already pinned to that section, and that is the mechanism working rather than a cost to route around: \`has moved\` is a FLAG, it exits 0, the pre-commit hook does not refuse it, and a claim the change did not touch is discharged by a re-read verdict. A citation parked in a module docstring to keep the checker quiet passes every check and is invisible to the one reader who needs it, the person editing the code. Watch the boundary on a module-level definition: a section starts at its own line, so a comment ABOVE \`NAME = ...\` belongs to whatever is defined before it — put the citing comment below the assignment, or inside the literal.

AN ENTRY THAT IS OWED IS WRITTEN IN THE PASS THAT OWES IT. Prose that promises something and cites nothing passes every check, so nothing comes back for a deferred entry; and the citation sits inside the span the entry pins, so a later pass pays the same commit again plus the drift its own citation causes. The same goes for a repair a checker has already named. A supporting change made so that other work can rely on it — something exported, configured or guaranteed — is a commitment like any other, and is not smaller for having been in service of something else.

WHERE TO GO. \`tagging-prose-with-claims\` to turn prose into entries, and for the questions to ask before choosing a ground. \`choosing-a-citation-act\` for a finding naming an act and a status, for a parenthesis whose act is not a citation act, and for deciding what to do with a pair \`neighbours\` surfaced. \`repair-a-drifted-pin\` for a moved, withdrawn, unstable or unknown ground — including the case where the artifact moved and the claim is untouched, which is acknowledged rather than superseded. Each skill carries a reference/ directory with the detail." \

if [ "$dialect" = cursor ]; then
  jq -cn --arg counts "$counts" --arg kinds "$kinds" --arg ctx "$ctx" \
    '{additional_context:($ctx | sub("__COUNTS__"; $counts) | sub("__KINDS__"; $kinds))}'
else
  jq -cn --arg counts "$counts" --arg kinds "$kinds" --arg ctx "$ctx" \
    '{hookSpecificOutput:{hookEventName:"SessionStart",
      additionalContext:($ctx | sub("__COUNTS__"; $counts) | sub("__KINDS__"; $kinds))}}'
fi

exit 0
