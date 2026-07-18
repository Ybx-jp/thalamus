# Shared pin resolution for hooks — source this, then call thalamus_resolve_scope.
#
# Mirror of harness/pin.resolve_pin, same precedence, same reason: the agent
# picker (`claude --agent thalamus-<scope>`) starts a pinned persona without
# threading THALAMUS_SCOPE, so the env alone lies about the pin (measured
# 2026-07-18: all three roster expert sessions carried
# CLAUDE_CODE_AGENT=thalamus-<scope> with THALAMUS_SCOPE=main). The picked
# agent wins when it names a real expert manifest; env is the fallback. Keep
# the two implementations in step — a hook that resolves differently from the
# armed MCP server records a pin the server never enforced.

thalamus_resolve_scope() {
  local agent="${CLAUDE_CODE_AGENT:-}" root scope
  if [ -n "$agent" ] && [ "${agent#thalamus-}" != "$agent" ]; then
    scope="${agent#thalamus-}"
    root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)}"
    if [ -f "$root/config/experts/$scope.yaml" ]; then
      printf '%s' "$scope"
      return
    fi
  fi
  printf '%s' "${THALAMUS_SCOPE:-main}"
}
