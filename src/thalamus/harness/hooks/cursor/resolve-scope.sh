# Shared pin resolution for Cursor hooks — source this, then call thalamus_resolve_scope.
#
# Env-only: Cursor has no agent picker, so the Claude Code precedence
# (picked-agent-first, env-fallback — see ../claude-code/resolve-scope.sh)
# collapses to THALAMUS_SCOPE with `main` as default. An unpinned session *is*
# a main-plane session. Kept as a separate mirror so a future Cursor
# pin channel has exactly one place to land.

thalamus_resolve_scope() {
  printf '%s' "${THALAMUS_SCOPE:-main}"
}

# Sandbox guard — call at the top of every hook, right after sourcing this file.
#
# Thalamus runs headless `agent -p` / `claude -p` subprocesses to distill sessions
# and to ingest documents (harness/agents.py). Each is a full session to its own
# harness: transcript on disk, sessionEnd fired, the user-scope hook suite armed.
# Unguarded, the hooks that make memory fire inside the machinery that makes
# memory — the sandbox distills itself, its summary paraphrases the session it was
# distilling, and its own headless run distills one level deeper.
#
# THALAMUS_SANDBOX is set by the parent (agents.sandbox_env) and inherited by the
# CLI, hence by these hooks. A sandbox is not a session: no hook fires in one.
thalamus_sandbox_guard() {
  if [ -n "${THALAMUS_SANDBOX:-}" ]; then
    exit 0
  fi
}

# The refusal a Cursor guard prints when it cannot read the call it exists to examine.
#
# Mirror of ../claude-code/resolve-scope.sh's thalamus_refuse_unreadable, in Cursor's
# protocol: a permission object on stdout and exit 0, where Claude Code uses stderr
# and exit 2. Both message channels carry the reason, for the reason gremlin-guard's
# adapter measured — on `cursor/2026.08.11-e8db854` a denial's tool result carries
# `user_message` and no occurrence of `agent_message`, so a guard explaining itself
# through the documented channel alone blocks in silence.
#
# printf and not `jq -n`, because jq being absent or broken is one of the three
# reasons this function is reached: building the refusal with the tool whose absence
# provoked it would emit nothing at all. That is safe only because the message is
# fixed prose assembled from a guard's own filename and one of this file's own
# reason strings — no payload text reaches it, and none of it contains a quote, a
# backslash or a newline to escape.
#
# $1: the guard's name. $2: the reason, as a noun phrase.
thalamus_refuse_unreadable() {
  local msg
  msg="Blocked by $1: $2, so the guard could not read the tool call it exists to examine. A guard that cannot parse its input denies rather than permits — otherwise an unreadable payload passes every boundary. Run \`thalamus init --check\` and report this to the operator; nothing inside this session can repair it."
  printf '{"permission": "deny", "agent_message": "%s", "user_message": "%s"}\n' \
    "$msg" "$msg"
  exit 0
}

# The stdin read for a Cursor guard, and the only one any of them may use.
#
# Same three unreadable inputs as the Claude Code twin — jq missing (127), jq
# refusing malformed JSON (5), and an empty payload — and the same reason for
# catching them: from outside, a guard that examined the call and approved it and a
# guard that died before looking are the same event.
#
# The Cursor adapters had both halves of that open. Each began `input=$(cat)` and
# parsed it immediately under `set -euo pipefail`, so malformed JSON killed the
# script at its first jq with *no permission object on stdout at all*; and a payload
# whose command field it could not find returned an explicit
# `{"permission": "allow"}`. Cursor's payload schema is Cursor's, versioned on their
# release cadence rather than this repo's, so a field that moves takes the write
# boundary, the gremlin terminal-step rule and the room-command rule out together,
# silently and with exit 0.
#
# Call it as a bare statement, never in a command substitution: the `exit` has to end
# the guard, not a subshell.
#
# $1 (optional): the guard's name, for the message the user is shown.
thalamus_guard_input=""
thalamus_read_guard_input() {
  local name="${1:-this guard}" reason="" rc=0
  thalamus_guard_input=$(cat)

  if [ -z "$thalamus_guard_input" ]; then
    reason="the hook payload was empty"
  else
    # One jq invocation answers both questions: 127 is the shell's own "no such
    # command" and is not in jq's exit set (0/1/2/3/5), so a jq that is missing and a
    # jq that is present and broken separate without a second probe.
    printf '%s' "$thalamus_guard_input" | jq . >/dev/null 2>&1 || rc=$?
    if [ "$rc" = 127 ]; then
      reason="jq is not on PATH"
    elif [ "$rc" != 0 ]; then
      reason="the hook payload is not valid JSON"
    fi
  fi
  [ -n "$reason" ] || return 0
  thalamus_refuse_unreadable "$name" "$reason"
}

# The command a `beforeShellExecution` guard was given, or a refusal.
#
# Cursor puts it in `.command`. The event is a shell execution, so a payload with no
# command in the place this adapter knows to look is drift in a schema this repo does
# not own — the case that used to return `{"permission": "allow"}`.
#
# $1 (optional): the guard's name, for the message the user is shown.
thalamus_guard_command=""
thalamus_read_guard_command() {
  local name="${1:-this guard}"
  thalamus_guard_command=$(printf '%s' "$thalamus_guard_input" \
    | jq -r '.command // empty' 2>/dev/null || true)
  [ -n "$thalamus_guard_command" ] && return 0
  thalamus_refuse_unreadable "$name" "the payload carries no command to examine"
}
