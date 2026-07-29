# Shared spool helpers for Cursor's deferred injection — source this.
#
# Why a spool exists at all: Cursor splits across two events what Claude Code's
# UserPromptSubmit does in one. `beforeSubmitPrompt` sees the prompt text but
# cannot inject agent-visible context; `postToolUse` can inject
# (`additional_context`) but never sees the prompt. Neither alone carries the
# timestamp or conditioning tiers, so the prompt-side hooks *compute* and the
# tool-side hook *delivers*: one file per session, appended by the former,
# drained by the latter.
#
# Consequence to know when reading traces: injection lands one tool call late,
# and a turn that calls no tool carries its injection forward to the next turn.
# Time-sensitive content is therefore NOT stored here — the clock is a bare
# marker, regenerated at drain (see inject.sh). Storing a rendered timestamp
# would deliver a stale one, which is the exact failure timestamp.sh exists to
# prevent.

thalamus_spool_dir() {
  printf '%s' "$HOME/.thalamus/spool"
}

thalamus_spool_file() {  # $1 = session id
  printf '%s/%s.jsonl' "$(thalamus_spool_dir)" "$(printf '%s' "$1" | tr -c 'A-Za-z0-9_.-' '_')"
}

# Append one pending item. $1 = session, $2 = kind, $3 = text (may be empty).
thalamus_spool_append() {
  local session="$1" kind="$2" text="${3:-}"
  [ -n "$session" ] || return 0
  mkdir -p "$(thalamus_spool_dir)"
  jq -cn --arg kind "$kind" --arg text "$text" \
    '{kind:$kind, text:$text}' >> "$(thalamus_spool_file "$session")" || true
}
