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

# Sandbox guard — call at the top of every hook, right after sourcing this file.
#
# Thalamus runs headless `claude -p` / `agent -p` subprocesses to distill sessions
# and to ingest documents (harness/agents.py). Each is a full session to its own
# harness: transcript on disk, SessionEnd fired, the user-scope hook suite armed.
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

# The room this session belongs to — the collaboration it witnessed, empty when it
# worked alone. Mirror of harness/pin.resolve_room. Env-only and deliberately without
# the agent-picker fallback the pin has: a room is one launch decision covering a set
# of processes, so there is no second channel to disagree with. Empty is the honest
# default — inferring a room from co-timing would manufacture the very correlation
# the field exists to make detectable.
thalamus_resolve_room() {
  printf '%s' "${THALAMUS_ROOM:-}"
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
