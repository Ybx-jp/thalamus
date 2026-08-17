#!/bin/bash
# Thalamus SessionEnd hook — Claude Code.
#
# The distillation trigger: when a session ends, its transcript is
# retained in the archive and both bootstrap stages run over it — the deterministic
# layer (Source, Session, Artifacts, anchored TOUCHES) and the model-extracted layer
# (Claims, Threads). `thalamus extract` does both for a single session, so this path
# and the retroactive bootstrap are literally the same code — a session ending now is
# just a bootstrap of one.
#
#   stdin: {session_id, transcript_path, cwd, hook_event_name, reason}
#
# Extraction spawns a headless `claude -p` and takes a minute or two, so it runs
# detached — the hook returns immediately and the session exits cleanly. Output lands
# in ~/.thalamus/logs/ for the operator to inspect.
#
# Install (project .claude/settings.json):
#   {"hooks": {"SessionEnd": [{"hooks": [{"type": "command",
#     "command": "$CLAUDE_PROJECT_DIR/src/thalamus/harness/hooks/claude-code/session-end.sh"}]}]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

# Distillation's two binaries, checked before anything uses them. Without this the
# script dies on the first `jq` under `set -euo pipefail` and the session is lost in
# silence; with it, the loss is a dated line in ~/.thalamus/logs/hook-failures.log
# that `thalamus init --check` reads back.
thalamus_require_binaries jq uv || exit 0

input=$(cat)

session_id=$(printf '%s' "$input" | jq -r '.session_id // empty')
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
transcript_path=$(printf '%s' "$input" | jq -r '.transcript_path // empty')

if [ -z "$session_id" ] || [ -z "$cwd" ]; then
  exit 0
fi

# The project dir comes from the transcript's own location, never from the cwd.
# Claude Code files a transcript under the dir named for the cwd the session
# *started* in, but the SessionEnd payload's `cwd` is the cwd at exit — a session
# that cd'd elsewhere reports a different, often real, project dir, and extract
# then finds no session matching --session and distills nothing. Silent when the
# drifted-to dir exists, "Unknown project dir(s)" when it doesn't; both lose the
# session. `basename(dirname())` is exactly the key transcripts.discover() returns,
# so it cannot drift and needs no flattening rules.
#
# The transcript's location also names its *root*, which is what makes room members
# distillable at all: a room runs under its own CLAUDE_CONFIG_DIR and writes to that
# dir's `projects/`, where extract's default sweep of ~/.claude/projects never looks.
# Taking the root from the same path the project dir came from means this
# needs no room registry and no env var, and it is exact rather than inferred — a
# session distills where its transcript actually landed, in a room or out of one.
if [ -n "$transcript_path" ]; then
  project_dir=$(basename "$(dirname "$transcript_path")")
  projects_dir=$(dirname "$(dirname "$transcript_path")")
else
  # Claude Code names its project dirs by flattening the absolute cwd: / -> -
  project_dir=$(printf '%s' "$cwd" | tr '/' '-')
  projects_dir=""
fi

log_dir="$HOME/.thalamus/logs"
log="$log_dir/session-end-${session_id:0:8}.log"

# Extraction's precondition, checked before paying for it. **SessionEnd fires for
# subagents too** — they are sessions to the harness — but a subagent has no
# transcript of its own, so `extract --session <id>` can only ever come back "No
# session matching". Finding that out is not free: a `uv run`, a `claude -p` model
# call, and a chained `eval sync --write` each time. Measured on this box, 1234 of
# 1826 session-end logs were that residue, and under a fan-out it stops being
# merely wasteful — 12 concurrent jobs on 4 cores drove load past 20 and a real
# session with a 96KB transcript sat in the queue until its extract died with
# nothing written (lab: the console's distillation widget caught it as `stalled`).
#
# The file named for the session id is exactly what transcripts.discover() keys on,
# so this is the same question extract asks, asked cheaply. Deliberately not the pin
# ledger: ledger absence would also identify subagents, but it would silently skip a
# real session whenever SessionStart failed to record one — trading wasted CPU for
# lost memory, which is the worse failure. A real session always has a transcript.
transcript="${projects_dir:-$HOME/.claude/projects}/$project_dir/$session_id.jsonl"
if [ ! -f "$transcript" ]; then
  # A ledger row means this *was* a real session, so a missing transcript is a
  # fault worth surfacing (the console widget renders it as an error). A session
  # with neither is a subagent: leave nothing behind, not even a log.
  if [ -f "$HOME/.thalamus/pins/pins.jsonl" ] && jq -e --arg sid "$session_id" \
       'select(.session_id == $sid and (has("event") | not))' \
       "$HOME/.thalamus/pins/pins.jsonl" >/dev/null 2>&1; then
    mkdir -p "$log_dir"
    echo "no transcript at $transcript — nothing to distill" >>"$log"
  fi
  exit 0
fi

mkdir -p "$log_dir"

# The distillation scope: ledger first, env fallback ("the process is the pin").
# Ledger-first keeps re-extraction deterministic — the same session recovered
# later from an unpinned shell still lands in the scope it was pinned to, instead of
# forking its Session vertex identity into a second scope. An env/ledger mismatch is
# pin-quality data, not a failure: log it and trust the ledger.
env_scope="$(thalamus_resolve_scope)"
ledger="$HOME/.thalamus/pins/pins.jsonl"
#
# `has("event") | not` skips the lifecycle rows that share this ledger:
# pin-engaged.sh appends {event: "engaged", session_id, scope, ts}, which carries no
# room, no agent and no forked_from. Last-wins across both reads those fields as
# empty — silently, and in the direction that turns a dependent fork back into an
# apparent independent session.
ledger_scope=""
if [ -f "$ledger" ]; then
  ledger_scope=$(jq -r --arg sid "$session_id" \
    'select(.session_id == $sid and (has("event") | not)) | .scope' \
    "$ledger" 2>/dev/null | tail -1)
fi
scope="${ledger_scope:-$env_scope}"
if [ -n "$ledger_scope" ] && [ "$ledger_scope" != "$env_scope" ]; then
  echo "pin mismatch: ledger=$ledger_scope env=$env_scope — using ledger" >>"$log"
fi

# The room, resolved ledger-first for the same reason as the scope, and with one
# extra: by SessionEnd the spawner's environment may be gone, so the ledger row
# written at SessionStart is the only surviving record that this session shared a
# conversation with others. Losing it turns correlated witnesses back into apparent
# independent ones — silently, and in the direction that looks like more evidence.
room=""
if [ -f "$ledger" ]; then
  room=$(jq -r --arg sid "$session_id" \
    'select(.session_id == $sid and (has("event") | not)) | .room // ""' \
    "$ledger" 2>/dev/null | tail -1)
fi
room="${room:-$(thalamus_resolve_room)}"

# The fork parent, ledger-first for the same reasons. Distinct from the room: room
# says these sessions saw one event, forked_from says this session derives from that
# one, so its agreement with its parent is not corroboration at all.
forked_from=""
if [ -f "$ledger" ]; then
  forked_from=$(jq -r --arg sid "$session_id" \
    'select(.session_id == $sid and (has("event") | not)) | .forked_from // ""' \
    "$ledger" 2>/dev/null | tail -1)
fi
forked_from="${forked_from:-$(thalamus_resolve_forked_from)}"

if [ -n "$room" ]; then
  echo "distilling session ${session_id:0:8} into scope $scope (room $room)" >>"$log"
else
  echo "distilling session ${session_id:0:8} into scope $scope" >>"$log"
fi

# --force: a resumed session that was distilled at an earlier stop gets re-extracted
# with its newer, longer transcript. Claims are content-addressed, so unchanged
# judgement converges on the same nodes rather than duplicating.
#
# After distillation, `eval sync --write` lands this session's tap traces as
# priced Trace nodes (they can only land post-distill — sync.py) and sweeps any
# backlog other distilled sessions left pending. Sync runs even if extract
# declines (non-conversation session): the sweep is still worth it. Trace
# identity is content-addressed, so concurrent session-ends converge instead of
# duplicating. The Pulse dashboard's pending stamp reads this loop's result.
# `uv run --project <checkout>`, not the session's cwd: a session pinned into
# another repo (`thalamus spawn --dir`) has a cwd that is not a uv project with
# thalamus in it, so a cwd-anchored invocation resolves no `thalamus` command and
# the session silently never distills. --project (not --directory) keeps the
# child's cwd where it is while resolving the environment from the checkout, the
# same pattern the thalamus-pulse user unit already uses.
repo_root="$(thalamus_repo_root)"

# A fork distills its **delta**, not its transcript. A `--fork-session` JSONL is the
# parent's whole conversation restamped with the fork's own sessionId, the parent's
# message UUIDs preserved verbatim (562/562 measured) — so distilling it as
# an ordinary session mints a second Session re-asserting the parent's episode and
# archives a second near-identical Source that the archive cannot dedup, because
# archive_bytes is content-addressed and every sessionId line differs.
#
# `thalamus quick delta` writes the exact set difference under ~/.thalamus/forks/ and
# prints the projects root to distill from; the project *dir name* is unchanged, so
# everything below runs identically. It refuses when the parent's transcript is gone,
# and that refusal ends the distillation: re-asserting the parent's episode is worse
# than not distilling this fork at all.
#
# It runs **inside** the detached block, with everything else that costs time. The
# hook itself must return immediately: a headless `claude -p` exits the moment it has
# printed its envelope, and a SessionEnd hook still running is cancelled — measured
# twice, once as `Hook cancelled` and once as a fork whose staging never happened and
# whose log stops after the first line. A few seconds of `uv run` in the foreground is
# enough to lose the race.
nohup sh -c "
  projects_dir='$projects_dir'
  if [ -n '$forked_from' ] && [ -n '$transcript_path' ]; then
    if delta_root=\$(uv run --project '$repo_root' thalamus quick delta \
        --transcript '$transcript_path' --parent '$forked_from'); then
      projects_dir=\"\$delta_root\"
      echo \"fork of ${forked_from:0:8}: distilling delta only, from \$delta_root\"
    else
      echo 'fork: delta staging failed — not distilling, since the whole transcript'
      echo 'would re-assert the parent episode as a second Session'
      exit 0
    fi
  fi
  projects_arg=''
  [ -n \"\$projects_dir\" ] && projects_arg=\"--projects-dir \$projects_dir\"
  uv run --project '$repo_root' thalamus extract --harness claude \
    --session '$session_id' --scope '$scope' --room '$room' \
    --forked-from '$forked_from' \$projects_arg --force --write -- '$project_dir'
  uv run --project '$repo_root' thalamus eval sync --write
" >>"$log" 2>&1 </dev/null &

exit 0
