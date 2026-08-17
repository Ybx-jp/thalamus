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
