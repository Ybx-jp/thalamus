# Shared pin resolution for Cursor hooks — source this, then call thalamus_resolve_scope.
#
# Env-only: Cursor has no agent picker, so the Claude Code precedence
# (picked-agent-first, env-fallback — see ../claude-code/resolve-scope.sh)
# collapses to THALAMUS_SCOPE with `main` as default. An unpinned session *is*
# a main-plane session (docs/07). Kept as a separate mirror so a future Cursor
# pin channel has exactly one place to land.

thalamus_resolve_scope() {
  printf '%s' "${THALAMUS_SCOPE:-main}"
}
