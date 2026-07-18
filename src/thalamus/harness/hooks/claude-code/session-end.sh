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

input=$(cat)

session_id=$(printf '%s' "$input" | jq -r '.session_id // empty')
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')

if [ -z "$session_id" ] || [ -z "$cwd" ]; then
  exit 0
fi

# Claude Code names its project dirs by flattening the absolute cwd: / -> -
project_dir=$(printf '%s' "$cwd" | tr '/' '-')

log_dir="$HOME/.thalamus/logs"
mkdir -p "$log_dir"
log="$log_dir/session-end-${session_id:0:8}.log"

# The distillation scope: ledger first, env fallback (docs/07 "the process is the
# pin"). Ledger-first keeps re-extraction deterministic — the same session recovered
# later from an unpinned shell still lands in the scope it was pinned to, instead of
# forking its Session vertex identity into a second scope. An env/ledger mismatch is
# pin-quality data, not a failure: log it and trust the ledger.
env_scope="${THALAMUS_SCOPE:-main}"
ledger="$HOME/.thalamus/pins/pins.jsonl"
ledger_scope=""
if [ -f "$ledger" ]; then
  ledger_scope=$(jq -r --arg sid "$session_id" \
    'select(.session_id == $sid) | .scope' "$ledger" 2>/dev/null | tail -1)
fi
scope="${ledger_scope:-$env_scope}"
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
nohup sh -c "
  uv --directory '${CLAUDE_PROJECT_DIR:-$cwd}' run thalamus extract \
    --session '$session_id' --scope '$scope' --force --write -- '$project_dir'
  uv --directory '${CLAUDE_PROJECT_DIR:-$cwd}' run thalamus eval sync --write
" >>"$log" 2>&1 </dev/null &

exit 0
