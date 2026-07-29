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
# and a turn that calls no tool carries its *clock* forward to the next turn.
# Time-sensitive content is therefore NOT stored here — the clock is a bare
# marker, regenerated at drain (see inject.sh). Storing a rendered timestamp
# would deliver a stale one, which is the exact failure timestamp.sh exists to
# prevent.
#
# The conditioning text is time-sensitive in the other currency: it was
# classified against one specific prompt, so carrying it forward delivers a
# design reminder against whatever the user asked next. Late binding has to
# cover both halves of the payload or it covers neither, so conditioning.sh
# prunes prior conditioning entries on every prompt — a spooled classification
# never outlives the turn that produced it. Undelivered guidance is a message
# past its freshness lifetime (RFC 9111 §4.2), and agents measurably act on
# superseded state even when the fresh state is available to them (STALE,
# arXiv 2605.06527), so it is dropped rather than delivered late.

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

# Drop every pending item of one kind. Called at the start of a turn by the
# hook that owns that kind, so a classification made for the previous prompt
# cannot be delivered against this one.
thalamus_spool_prune() {  # $1 = session, $2 = kind
  local session="$1" kind="$2" file
  [ -n "$session" ] || return 0
  file="$(thalamus_spool_file "$session")"
  [ -s "$file" ] || return 0
  local tmp="${file}.pruning.$$"
  if jq -c --arg kind "$kind" 'select(.kind != $kind)' "$file" > "$tmp" 2>/dev/null; then
    mv "$tmp" "$file"
  else
    rm -f "$tmp"
  fi
}
