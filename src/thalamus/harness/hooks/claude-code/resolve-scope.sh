# Shared pin resolution for hooks — source this, then call thalamus_resolve_scope
# (or thalamus_repo_root for the checkout the harness itself lives in).
#
# Precedence, highest first: the subagent that issued this tool call, then the
# agent picker, then the environment. Each channel exists because the one below
# it lies in a case the one above it sees.
#
# The agent picker (`claude --agent thalamus-<scope>`) starts a pinned persona
# without threading THALAMUS_SCOPE, so the env alone lies about the pin (measured
# 2026-07-18: all three roster expert sessions carried
# CLAUDE_CODE_AGENT=thalamus-<scope> with THALAMUS_SCOPE=main).
#
# A subagent inherits its launcher's environment wholesale, so both CLAUDE_CODE_AGENT
# and THALAMUS_SCOPE describe who *spawned* it and never who is running. Only the
# tool-hook payload's `agent_type` names the running agent, and it is authoritative
# where it is present. Measured 2026-08-11 over ~/.thalamus/traces: across 1132 tool
# calls issued by thalamus-* subagents in 52 sessions, env-only resolution named the
# right scope 6.4% of the time — `main` 75.9%, and a *different* expert's scope 17.8%,
# which applies the wrong boundary rather than none.
#
# This is where the hook and harness/pin.resolve_pin legitimately diverge, and the
# divergence is the point rather than drift to be repaired: the payload channel exists
# only per tool call, so the MCP server — which reads its env once at process start —
# cannot see it. The hook is the more accurate of the two. Precedence and manifest
# check stay in step; the extra channel does not.

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

# The session this one was forked from (`claude --resume <id> --fork-session`), empty
# when it started cold. Mirror of harness/pin.resolve_forked_from. The launcher must
# supply it: the harness mints the fork a new session id and tells it nothing about the
# old one, and recovering the link from transcript content afterwards would be inference
# over model-written text. Where room says "we saw the same thing", this says "I came
# from you" — so a fork's agreement with its parent corroborates nothing.
thalamus_resolve_forked_from() {
  printf '%s' "${THALAMUS_FORKED_FROM:-}"
}

# $1 (optional): the tool-hook payload's `agent_type`. Pass it from every hook that
# receives a tool payload; omit it in session-lifecycle hooks, which have none.
#
# Ordering, not short-circuiting. A non-Thalamus subagent (`general-purpose`,
# `Explore`) names an agent_type that matches no manifest, and it must fall through
# to the launcher's pin — otherwise "spawn a general-purpose subagent to write the
# fix" is a one-line route around every boundary in the roster.
thalamus_resolve_scope() {
  local config scope candidate
  config="${THALAMUS_CONFIG_DIR:-$(thalamus_repo_root)/config}"
  for candidate in "${1:-}" "${CLAUDE_CODE_AGENT:-}"; do
    [ -n "$candidate" ] || continue
    [ "${candidate#thalamus-}" != "$candidate" ] || continue
    scope="${candidate#thalamus-}"
    if [ -f "$config/experts/$scope.yaml" ]; then
      printf '%s' "$scope"
      return
    fi
  done
  printf '%s' "${THALAMUS_SCOPE:-main}"
}

# What every tool hook actually wants: resolve against the payload it already read.
# $1 is the raw payload. Session-lifecycle hooks have no payload field to pass and
# call thalamus_resolve_scope directly.
thalamus_scope_from_payload() {
  thalamus_resolve_scope "$(printf '%s' "${1:-}" | jq -r '.agent_type // empty' 2>/dev/null)"
}
