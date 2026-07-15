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

# --force: a resumed session that was distilled at an earlier stop gets re-extracted
# with its newer, longer transcript. Claims are content-addressed, so unchanged
# judgement converges on the same nodes rather than duplicating.
nohup uv --directory "${CLAUDE_PROJECT_DIR:-$cwd}" run thalamus extract \
  --session "$session_id" --force --write -- "$project_dir" \
  >"$log" 2>&1 </dev/null &

exit 0
