#!/bin/bash
# Thalamus beforeSubmitPrompt hook — mark this session engaged (Cursor).
#
# Thin adapter over ../claude-code/pin-engaged.sh: the first user prompt is
# the engagement boundary (docs/04 sampling frame — spawn records alone
# conflate infrastructure churn with operator routing). Appends one
# {"event":"engaged"} line per session to the pin ledger, idempotent.
#
# Cursor's contract: stdin {prompt, attachments} + common fields; stdout
# {"continue": true|false, "user_message": ...}. This hook never blocks —
# beforeSubmitPrompt is Cursor's only per-prompt event, but unlike Claude
# Code's UserPromptSubmit it CANNOT inject agent-visible context (lab/010):
# the timestamp and conditioning tiers have no Cursor carrier, so this hook
# carries only the ledger side-effect.
#
# Install (project <root>/.cursor/hooks.json):
#   {"version": 1, "hooks": {"beforeSubmitPrompt": [{"command":
#     "./src/thalamus/harness/hooks/cursor/pin-engaged.sh"}]}}

set -euo pipefail

here="$(dirname "${BASH_SOURCE[0]}")"

printf '%s' "$(cat)" | jq -c \
  '{session_id: (.session_id // .conversation_id // "")}' \
  | "$here/../claude-code/pin-engaged.sh" >/dev/null

printf '{"continue": true}\n'
