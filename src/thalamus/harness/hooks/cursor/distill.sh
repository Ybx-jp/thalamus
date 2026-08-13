#!/bin/bash
# Thalamus sessionEnd hook — Cursor auto-distillation.
#
# A Claude Code session distills itself at SessionEnd. A Cursor one could not, and the
# stated reason was that Cursor is not documented to flush its transcript before firing
# the hook, so reading there races an async writer and could silently distill a
# truncated session (forum thread 166592, no implementation timeline). A truncated
# distillation is a corrupted memory rather than a missing one, and nothing downstream
# can tell the difference — so the sweep was left to a human.
#
# **This does not assume the race is absent. It waits until it cannot matter.** The
# detached block below polls the transcript's size and mtime and only distills once
# they have stopped changing for `SETTLE_S`, capped at `MAX_WAIT_S`. That turns "not
# documented to flush" into "we watched until it had", which holds whether or not the
# vendor ever documents a guarantee, and keeps holding if a future Cursor build changes
# its buffering. Measured against 2026.08.11-e8db854: a one-turn session's transcript
# was already byte-identical at hook time to its settled state (same sha256), so on
# today's build the wait usually costs one poll — but one observation of a small
# transcript is not evidence that a long final turn never lags, which is the case this
# is built for.
#
# Kept as its **own** hook rather than folded into `session-end.sh`, because the two
# have different failure appetites: logging the pointer is free and must always happen,
# while distilling costs a model call per session. Separate entries mean auto-distill
# can be disarmed by removing one line from the registry, leaving the ledger intact.
#
# Cursor's contract: stdin {session_id, transcript_path, workspace_roots, ...}.
# `transcript_path` is null for a session that produced no transcript at all — one that
# ended without completing a turn — so a null there is "nothing to distill", not an
# error. Where it is null the filesystem is still swept for the session's own directory,
# since the payload's absence and the file's absence are different facts.
#
# Install (project <root>/.cursor/hooks.json, alongside session-end.sh):
#   {"version": 1, "hooks": {"sessionEnd": [{"command":
#     "./src/thalamus/harness/hooks/cursor/distill.sh"}]}}
# Not supported in Cursor cloud agents.

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"
. "$here/resolve-scope.sh"
thalamus_sandbox_guard

# How long the transcript must hold still, how often to look, and when to give up and
# distill anyway. The cap exists because never distilling is the worse failure: a
# session whose file somehow never settles still deserves the memory, and the extract
# reports `unrecognized` rows if it got a torn read.
SETTLE_S=3
POLL_S=1
MAX_WAIT_S=120

input=$(cat)

session_id=$(printf '%s' "$input" | jq -r '.session_id // .conversation_id // empty')
[ -n "$session_id" ] || exit 0

transcript_path=$(printf '%s' "$input" | jq -r '.transcript_path // empty')
if [ -z "$transcript_path" ]; then
  # Nothing in the payload. The file is addressed by the session id Cursor named its
  # directory after; the project dir is globbed rather than derived, because
  # un-sanitizing a flattened cwd is not known to be reversible.
  # `|| true`: no match is the ordinary case for a session that completed no turn, and
  # under `pipefail` the failing glob would otherwise abort the hook with its own exit
  # code — turning "nothing to distill" into a hook that looks broken.
  transcript_path=$(ls "$HOME"/.cursor/projects/*/agent-transcripts/"$session_id"/"$session_id".jsonl 2>/dev/null | head -1 || true)
fi
# A session that completed no turn has no transcript and never will. Exiting quietly is
# correct: `session-end.sh` has already logged the pointer row, so the session is on
# record as having ended even though it left nothing to remember.
[ -n "$transcript_path" ] || exit 0

# Ledger-first scope, env fallback — the same rule `session-end.sh` uses. The pin ledger
# carries the scope from sessionStart, which is what makes this correct regardless of
# which sessionEnd hook the harness happens to run first.
env_scope="$(thalamus_resolve_scope)"
ledger="$HOME/.thalamus/pins/pins.jsonl"
ledger_scope=""
if [ -f "$ledger" ]; then
  ledger_scope=$(jq -r --arg sid "$session_id" \
    'select(.session_id == $sid) | .scope' "$ledger" 2>/dev/null | tail -1)
fi
scope="${ledger_scope:-$env_scope}"

log_dir="$HOME/.thalamus/logs"
mkdir -p "$log_dir"
log="$log_dir/cursor-distill-${session_id:0:8}.log"
repo_root="$(cd "$here/../../../../.." && pwd)"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) waiting for ${session_id:0:8} to settle" >>"$log"

# Everything that costs time runs detached. The hook itself must return immediately —
# a sessionEnd hook still running when the process exits is cancelled, which is how the
# Claude Code side lost a fork's staging once and logged only its first line.
#
# --force so a resumed Cursor session re-distills against its longer transcript;
# claims are content-addressed, so unchanged judgement converges on the same nodes
# rather than duplicating. `uv run --project` resolves the environment from the
# checkout while leaving cwd alone, since a session pinned into another repo has a cwd
# that is not a uv project and would silently resolve no `thalamus` at all.
nohup sh -c "
  last=''
  stable=0
  waited=0
  while [ \$waited -lt $MAX_WAIT_S ]; do
    now=\$(stat -c '%s:%Y' '$transcript_path' 2>/dev/null || echo gone)
    if [ \"\$now\" = \"\$last\" ]; then
      stable=\$((stable + $POLL_S))
      [ \$stable -ge $SETTLE_S ] && break
    else
      stable=0
    fi
    last=\"\$now\"
    sleep $POLL_S
    waited=\$((waited + $POLL_S))
  done
  echo \"\$(date -u +%Y-%m-%dT%H:%M:%SZ) settled after \${waited}s; distilling into scope $scope\"
  uv run --project '$repo_root' thalamus extract --harness cursor \
    --session '$session_id' --scope '$scope' --force --write
" >>"$log" 2>&1 </dev/null &

exit 0
