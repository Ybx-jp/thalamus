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

# The agent definition a session with this pin would actually load, or empty.
#
# Precedence mirrors Claude Code's: the definition closest to the working directory
# wins, so the project's `.claude/agents/` outranks the user scope. CLAUDE_CONFIG_DIR
# is honoured for the user half because a room member's config dir is somewhere else
# entirely (harness/pin.ROOMS_DIR), and its `agents` is a symlink to the operator's.
thalamus_agent_file() {
  local scope="$1" candidate
  for candidate in "${CLAUDE_PROJECT_DIR:-}/.claude/agents/thalamus-$scope.md" \
                   "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/agents/thalamus-$scope.md"; do
    case "$candidate" in /.claude/*) continue ;; esac
    if [ -f "$candidate" ]; then
      printf '%s' "$candidate"
      return
    fi
  done
}

# Warn when this scope declares MCP servers that this process cannot have. Prints the
# warning, or nothing at all. Always succeeds — a detector that aborts its own hook
# reports less than no detector.
#
# The condition is worth detecting because it is otherwise invisible from inside. A
# scope whose tooling is its reason for existing (`designer` works through the Penpot
# server) gets a system prompt asserting that it is a visual designer working in a
# design tool; if the process has no design tool, nothing in the session says so and
# the model has no way to find out. Measured: a designer session ran this way for a
# whole task. Same shape as the Cursor workspace-trust gate — a launch condition the
# shared argv knew about and the hand path had nowhere to declare.
#
# Arming rides the agent definition (harness/pin._mcp_frontmatter), which is what
# makes the check possible at all: both failure modes reduce to a file on disk, so
# this needs neither a probe of the MCP surface (a hook cannot see it) nor a network
# call. Either the process did not pick this scope's agent, or the generated agent is
# stale and predates the scope's tooling.
thalamus_mcp_arming_warning() {
  local scope="${1:-main}" config mcp_file agent_file frontmatter name missing=""
  config="${THALAMUS_CONFIG_DIR:-$(thalamus_repo_root)/config}"
  mcp_file="$config/mcp/$scope.json"
  [ -f "$mcp_file" ] || return 0

  local servers
  servers=$(jq -r '(.mcpServers // {}) | keys[]' "$mcp_file" 2>/dev/null) || return 0
  [ -n "$servers" ] || return 0

  if [ "${CLAUDE_CODE_AGENT:-}" != "thalamus-$scope" ]; then
    printf 'MIS-ARMED SESSION — READ THIS FIRST. The `%s` scope arms its own MCP servers (%s), declared in `config/mcp/%s.json` and carried on the `thalamus-%s` agent definition. This process was not launched with `--agent thalamus-%s`, so it does NOT have them. Do not attempt work that depends on those tools and do not improvise a substitute: report this to the operator and stop. The fix is to relaunch as `claude --agent thalamus-%s` (or `thalamus pin %s`); MCP servers arm per process, so nothing can repair it from inside this one.' \
      "$scope" "$(printf '%s' "$servers" | tr '\n' ' ' | sed 's/ $//')" "$scope" "$scope" "$scope" "$scope" "$scope"
    return 0
  fi

  agent_file="$(thalamus_agent_file "$scope")"
  if [ -z "$agent_file" ]; then
    printf 'MIS-ARMED SESSION — READ THIS FIRST. This session is pinned to `%s`, whose MCP servers (%s) are declared on its agent definition — and no `thalamus-%s.md` is on disk in either the project or user agents directory. Report this to the operator and stop; `thalamus pin %s` regenerates it, but only a new process can arm the servers.' \
      "$scope" "$(printf '%s' "$servers" | tr '\n' ' ' | sed 's/ $//')" "$scope" "$scope"
    return 0
  fi

  # Frontmatter only: the body names the servers in prose (the self-check paragraph
  # render_agent writes), so scanning the whole file would find the names in the very
  # text that exists to describe their absence and report every stale file as healthy.
  frontmatter=$(awk 'NR==1 && $0=="---"{inside=1; next} inside && $0=="---"{exit} inside' "$agent_file")
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    printf '%s' "$frontmatter" | grep -qE "^[[:space:]]*-[[:space:]]*${name}:" || missing="$missing $name"
  done <<< "$servers"

  [ -n "$missing" ] || return 0
  printf 'MIS-ARMED SESSION — READ THIS FIRST. `config/mcp/%s.json` declares MCP servers (%s) that `%s` does not carry in its frontmatter, so this process never armed them. The generated agent file is stale. Report this to the operator and stop rather than working around the missing tools; `thalamus pin %s` regenerates the file, and the servers arm only in a new process.' \
    "$scope" "${missing# }" "$agent_file" "$scope"
}
