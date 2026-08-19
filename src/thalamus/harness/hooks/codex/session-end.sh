#!/bin/bash
# Thalamus SessionEnd hook — codex. The distillation trigger.
#
#   stdin: {session_id, transcript_path, cwd, hook_event_name, reason}
#
# Its own script rather than a delegator over ../claude-code/session-end.sh, and the
# reason is structural rather than stylistic: that script derives the project dir and
# the transcript root from the transcript's *path*
# (`basename(dirname($transcript_path))`), which encodes Claude Code's
# `~/.claude/projects/<flattened-cwd>/<session>.jsonl` layout. A codex rollout lives
# at `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl`, so that derivation
# would name the project `17` and the projects root `<CODEX_HOME>/sessions/2026/08`,
# find no matching session, and exit 0 having distilled nothing — silently, which is
# the failure this whole layer exists to prevent. It also hardcodes
# `extract --harness claude`.
#
# **No settle loop, and that is measured rather than assumed.** Cursor's distill.sh
# polls the transcript's size and mtime until they hold still, because Cursor is not
# documented to flush before firing. Codex is: the binary carries the string "failed
# to flush transcript before SessionEnd hook", and three live probes agree —
# 19 lines / 40361 bytes at hook time and 19 / 40361 in the final file for a headless
# `codex exec`, 14 / 14 for an interactive TUI. So this distills directly, the way the
# Claude Code hook does, and nothing here is a port of the Cursor poll.
#
# `--transcript` is codex extraction's contract (harness/codex_transcripts.py): the
# hook already knows the exact file, and re-deriving it by scanning the sessions tree
# for a matching id is a second chance to pick the wrong one. A codex rollout is filed
# under the day it ran rather than under its cwd, so there is no project-dir argument
# to pass and no `--projects-dir` analogue.
#
# The log file shares the Claude Code hook's `session-end-<sid8>.log` name on purpose:
# the console's distillation widget (console/distill.py) is a state machine over
# exactly that name joined against the pin ledger, and codex sessions write a ledger
# row, so keeping the name gives codex distillation the same live status view for
# free. Session ids do not collide across harnesses.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

# Checked before anything uses them: without this the script dies on the first `jq`
# under `set -euo pipefail` and the session is lost in silence. With it, the loss is a
# dated line in ~/.thalamus/logs/hook-failures.log that `thalamus init --check` reads
# back.
thalamus_require_binaries jq uv || exit 0

input=$(cat)

session_id=$(printf '%s' "$input" | jq -r '.session_id // empty')
transcript_path=$(printf '%s' "$input" | jq -r '.transcript_path // empty')

[ -n "$session_id" ] || exit 0

log_dir="$HOME/.thalamus/logs"
log="$log_dir/session-end-${session_id:0:8}.log"
ledger="$HOME/.thalamus/pins/pins.jsonl"

# Extraction's precondition, checked before paying for it — a `uv run`, a model call
# and a chained `eval sync` each time. `transcript_path` is nullable in codex's own
# schema, and a session that completed no turn has a rollout that may never appear.
#
# A ledger row means this *was* a real session, so a missing transcript is a fault
# worth surfacing (the console widget renders it as an error). With neither, leave
# nothing behind at all — the same rule the Claude Code hook uses to keep subagent
# residue out of the log directory.
if [ -z "$transcript_path" ] || [ ! -f "$transcript_path" ]; then
  if [ -f "$ledger" ] && jq -e --arg sid "$session_id" \
       'select(.session_id == $sid and (has("event") | not))' \
       "$ledger" >/dev/null 2>&1; then
    mkdir -p "$log_dir"
    echo "no transcript at ${transcript_path:-<none>} — nothing to distill" >>"$log"
  fi
  exit 0
fi

mkdir -p "$log_dir"

# The distillation scope: ledger first, env fallback ("the process is the pin").
# Ledger-first keeps re-extraction deterministic — the same session recovered later
# from an unpinned shell still lands in the scope it was pinned to, instead of forking
# its Session vertex identity into a second scope.
#
# `has("event") | not` skips the lifecycle rows that share this ledger: pin-engaged.sh
# appends {event: "engaged", session_id, scope, ts}, which carries no room. Last-wins
# across both would read that field as empty, silently.
#
# Codex has one exposure the other harnesses do not, and it is the reason the env
# fallback still matters: in the interactive TUI, SessionStart fires at the first
# submitted turn rather than at launch, so a session that ended before its first turn
# has no spawn row here at all.
env_scope="$(thalamus_resolve_scope)"
ledger_scope=""
room=""
if [ -f "$ledger" ]; then
  ledger_scope=$(jq -r --arg sid "$session_id" \
    'select(.session_id == $sid and (has("event") | not)) | .scope' \
    "$ledger" 2>/dev/null | tail -1)
  room=$(jq -r --arg sid "$session_id" \
    'select(.session_id == $sid and (has("event") | not)) | .room // ""' \
    "$ledger" 2>/dev/null | tail -1)
fi
scope="${ledger_scope:-$env_scope}"
if [ -n "$ledger_scope" ] && [ "$ledger_scope" != "$env_scope" ]; then
  echo "pin mismatch: ledger=$ledger_scope env=$env_scope — using ledger" >>"$log"
fi

# The room, ledger-first for the same reason as the scope and with one more: by
# SessionEnd the spawner's environment may be gone, so the row written at session
# start is the only surviving record that this session shared a conversation with
# others. Losing it turns correlated witnesses back into apparent independent ones.
room="${room:-$(thalamus_resolve_room)}"

if [ -n "$room" ]; then
  echo "distilling session ${session_id:0:8} into scope $scope (room $room)" >>"$log"
else
  echo "distilling session ${session_id:0:8} into scope $scope" >>"$log"
fi

# Detached, and everything that costs time runs inside the fork. A SessionEnd hook
# still running when the process exits is cancelled — measured twice on Claude Code,
# once as `Hook cancelled` and once as a fork whose staging never happened — and a few
# seconds of `uv run` in the foreground is enough to lose that race.
#
# `--force`: a resumed session distilled at an earlier stop gets re-extracted against
# its longer rollout. Claims are content-addressed, so unchanged judgement converges
# on the same nodes rather than duplicating.
#
# `eval sync --write` afterwards lands this session's tap traces as priced Trace nodes
# (they can only land post-distill) and sweeps whatever backlog other sessions left.
# It runs even when extract declines, because the sweep is still worth it.
#
# `uv run --project <checkout>` rather than the session's cwd: a codex session pinned
# into another repo has a cwd that is not a uv project with thalamus in it, so a
# cwd-anchored invocation resolves no `thalamus` command and the session silently
# never distills. `--project` (not `--directory`) leaves the child's cwd alone.
repo_root="$(thalamus_repo_root)"

nohup sh -c "
  uv run --project '$repo_root' thalamus extract --harness codex \
    --session '$session_id' --scope '$scope' --room '$room' \
    --transcript '$transcript_path' --force --write
  uv run --project '$repo_root' thalamus eval sync --write
" >>"$log" 2>&1 </dev/null &

exit 0
