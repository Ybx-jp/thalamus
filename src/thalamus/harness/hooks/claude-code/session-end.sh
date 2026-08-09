#!/bin/bash
# Thalamus SessionEnd hook — Claude Code.
#
# The distillation trigger from docs/07: when a session ends, its transcript is
# retained in the archive and both bootstrap stages run over it — the deterministic
# layer (Source, Session, Artifacts, anchored TOUCHES) and the model-extracted layer
# (Claims, Threads). `thalamus extract` does both for a single session, so the live
# memorize path and the retroactive bootstrap are literally the same code — a session
# ending now is just a bootstrap of one.
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

input=$(cat)

session_id=$(printf '%s' "$input" | jq -r '.session_id // empty')
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')

if [ -z "$session_id" ] || [ -z "$cwd" ]; then
  exit 0
fi

# Claude Code names its project dirs by flattening the absolute cwd: / -> -
project_dir=$(printf '%s' "$cwd" | tr '/' '-')

log_dir="$HOME/.thalamus/logs"
log="$log_dir/session-end-${session_id:0:8}.log"

# The distillation scope: ledger first, env fallback (docs/07 "the process is the
# pin"). Ledger-first keeps re-extraction deterministic — the same session recovered
# later from an unpinned shell still lands in the scope it was pinned to, instead of
# forking its Session vertex identity into a second scope. An env/ledger mismatch is
# pin-quality data, not a failure: log it and trust the ledger.
env_scope="$(thalamus_resolve_scope)"
ledger="$HOME/.thalamus/pins/pins.jsonl"
ledger_scope=""
if [ -f "$ledger" ]; then
  ledger_scope=$(jq -r --arg sid "$session_id" \
    'select(.session_id == $sid) | .scope' "$ledger" 2>/dev/null | tail -1)
fi
scope="${ledger_scope:-$env_scope}"

# Nothing to distill without a transcript, and spawning `uv run … claude -p` to
# discover that is not free. **Subagents fire SessionEnd too** — they are sessions
# to the harness — but they have no transcript of their own, so every one of them
# used to start a full extract that could only ever end in "No session matching",
# then run `eval sync --write` on top. On a box that fans out subagents that is not
# a rounding error: it was measured at 1234 of 1826 session-end logs, and a burst of
# them oversubscribed a 4-core machine badly enough to starve a *real* distillation
# until it died with its memory unwritten.
#
# The test is the transcript rather than the pin ledger deliberately. Ledger absence
# would also catch subagents, but it would silently skip a real session whenever
# SessionStart failed to record one — trading wasted CPU for lost memory, which is
# the worse failure. A real session always has a transcript.
transcript="$HOME/.claude/projects/$project_dir/$session_id.jsonl"
if [ ! -f "$transcript" ]; then
  # A ledger row means this was a real session, so a missing transcript is an
  # anomaly worth a log (the console's distillation widget surfaces it as an
  # error). A session with neither is a subagent: leave nothing behind at all.
  if [ -n "$ledger_scope" ]; then
    mkdir -p "$log_dir"
    echo "no transcript at $transcript — nothing to distill" >>"$log"
  fi
  exit 0
fi

mkdir -p "$log_dir"
if [ -n "$ledger_scope" ] && [ "$ledger_scope" != "$env_scope" ]; then
  echo "pin mismatch: ledger=$ledger_scope env=$env_scope — using ledger" >>"$log"
fi
echo "distilling session ${session_id:0:8} into scope $scope" >>"$log"

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
nohup sh -c "
  uv run --project '$repo_root' thalamus extract --harness claude \
    --session '$session_id' --scope '$scope' --force --write -- '$project_dir'
  uv run --project '$repo_root' thalamus eval sync --write
" >>"$log" 2>&1 </dev/null &

exit 0
