# Shared pin resolution for hooks — source this, then call thalamus_resolve_scope
# (or thalamus_repo_root for the checkout the harness itself lives in).
#
# Mirror of harness/pin.resolve_pin, same precedence, same reason: the agent
# picker (`claude --agent thalamus-<scope>`) starts a pinned persona without
# threading THALAMUS_SCOPE, so the env alone lies about the pin (measured
# 2026-07-18: all three roster expert sessions carried
# CLAUDE_CODE_AGENT=thalamus-<scope> with THALAMUS_SCOPE=main). The picked
# agent wins when it names a real expert manifest; env is the fallback. Keep
# the two implementations in step — a hook that resolves differently from the
# armed MCP server records a pin the server never enforced.

# The Thalamus checkout — the tree this script sits in, five levels up from
# src/thalamus/harness/hooks/claude-code/. Anchored on BASH_SOURCE and NOT on
# CLAUDE_PROJECT_DIR, which names the session's *working* project and is a
# different repo entirely whenever a session runs outside the checkout
# (`thalamus spawn --dir`). THALAMUS_CONFIG_DIR still overrides the config
# location, exactly as contract/manifest.experts_dir does on the Python side.
thalamus_repo_root() {
  (cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)
}

thalamus_resolve_scope() {
  local agent="${CLAUDE_CODE_AGENT:-}" config scope
  if [ -n "$agent" ] && [ "${agent#thalamus-}" != "$agent" ]; then
    scope="${agent#thalamus-}"
    config="${THALAMUS_CONFIG_DIR:-$(thalamus_repo_root)/config}"
    if [ -f "$config/experts/$scope.yaml" ]; then
      printf '%s' "$scope"
      return
    fi
  fi
  printf '%s' "${THALAMUS_SCOPE:-main}"
}
