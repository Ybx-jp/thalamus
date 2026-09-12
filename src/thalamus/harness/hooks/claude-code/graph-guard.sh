#!/bin/bash
# Thalamus PreToolUse hook — the graph is reached through the MCP surface (Claude Code).
#
# Scope confinement on reads is a property of the MCP surface and not of the graph
# connection. `reader.recall` filters Sessions and session-contained Claims to the
# caller's own scope (substrate/reader.py:677, :692), and `memory_query` refuses an
# expert pin outright, on the stated rationale that a free-form traversal cannot be
# scope-confined (harness/mcp_server.py:402)
# (A0149-memory-query-refuses-a-pinned-session, cites-as-live).
# `substrate.writer.connect()` hands back a source over the whole graph
# (A0148-graph-connection-carries-no-scope-filter, cites-as-live),
# and `Bash` is not in `ROSTER_CAPABILITY_DEFAULT.deny_tools`
# (contract/manifest.py:241) — so a pin that can run a shell reads every vertex and edge
# in the graph, including `main`'s episodic memory and every other expert's. The
# `gremlin-python` skill installs at user scope for every pin and documented that path
# as a first-class surface, which is how a hole stays open with nobody routing around
# anything.
#
# The rule is one line: outside `main`, a command that opens a graph connection — on its
# own line, or in a `.py` file it names — is blocked. This is the federation contract
# rather than a perimeter against a hostile process — the same operator runs every pin.
# What it prevents is an expert producing a generalisation compounded across a boundary
# the contract says is not crossable, which is the argument that made attribution
# scope-closed.
#
# `Bash` is NOT denied to roster pins, and answering this by denying it would be the
# wrong repair: experts run the same work sessions do, and the capability default denies
# design skills and publishing tools, not the shell.
#
# NAMED MISSES, on the standing trade where a miss is cheaper than a false positive,
# because a false positive teaches route-around:
#
#   - A script that does not name the client itself: one that imports a house module
#     which connects, or builds the import at runtime. The file a command names is read
#     one level deep and its own imports are not followed, so the question answered is
#     "does the thing being run reach the graph", not "could anything downstream of it".
#   - A file that does not exist when the guard runs — written by the same command that
#     runs it, or fetched mid-pipeline. A heredoc followed by a separate `python q.py`
#     is not this case: the heredoc passes as text and the run that follows is read.
#   - A house entrypoint that reaches the graph on the session's behalf — `thalamus
#     eval sync`, `thalamus quick ask`, `python -c 'from thalamus.eval...'`, a pytest
#     run. Each has its own confinement question, and gating them here would attach an
#     unrelated decision to this one.
#   - `docker exec` into the gremlin-server container, which is the graph without the
#     client.
#
# Install (user or project settings.json):
#   {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
#     "command": ".../hooks/claude-code/graph-guard.sh"}]}]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

thalamus_read_guard_input graph-guard.sh
input="$thalamus_guard_input"

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')
[ "$tool_name" = "Bash" ] || exit 0

# Past the Bash gate the command is the event, so an absent one is a payload this
# guard cannot read rather than a call with nothing in it.
thalamus_read_guard_command graph-guard.sh
command="$thalamus_guard_command"

# Marker gate, first because it is cheap and because almost no command carries one:
# the ways a shell reaches the graph client. `thalamus.substrate` is the module the
# skill documents; the three gremlin markers are the same client reached without it;
# `:8182` is the endpoint reached with no Python at all. A command that carries none of
# them, on its line or in a file it names, exits below and writes no ledger row — the
# ledger records this boundary's decisions, not every Bash call.
MARKERS='thalamus\.substrate|gremlin_python|DriverRemoteConnection|with_remote\(|:8182'

marked=""
if printf '%s' "$command" | grep -qE "$MARKERS"; then
  marked=command
else
  # A script file carries the connection where the command line does not, and writing
  # one is two ordinary calls: a heredoc passes as text, then `python q.py` names no
  # marker at all. Measured as a live bypass under an expert pin before this branch
  # existed, which is why the file it names is read rather than trusted.
  #
  # Only `.py` arguments that resolve to a real file, and no recursion into what they
  # import: this answers "does the thing being run reach the graph", not "could
  # anything downstream of it".
  # (A0150-graph-guard-fires-on-client-markers, cites-as-live)
  # `set -f` because the split below is deliberate and glob expansion of an argument
  # is not.
  case "$command" in *.py*) ;; *) exit 0 ;; esac
  cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
  set -f
  for token in $command; do
    token=${token%\"}; token=${token#\"}
    token=${token%\'}; token=${token#\'}
    case "$token" in
      *.py) ;;
      *) continue ;;
    esac
    case "$token" in
      /*) candidate="$token" ;;
      *) candidate="${cwd:-.}/$token" ;;
    esac
    [ -f "$candidate" ] || continue
    if grep -qE "$MARKERS" "$candidate" 2>/dev/null; then
      marked=script
      break
    fi
  done
  set +f
fi
[ -n "$marked" ] || exit 0

scope="$(thalamus_scope_from_payload "$input")"

# Passes are logged beside blocks, for the reason `role-guard.sh` logs them: the
# roster's granularity audit asks whether a scope earned its partition, and how often
# `main` uses the code path this denies an expert is evidence for that question.
log_event() {
  local guard_dir="$HOME/.thalamus/guards"
  mkdir -p "$guard_dir"
  printf '%s' "$input" | jq -c \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg scope "$scope" \
    --arg verdict "$1" \
    --arg branch "$2" \
    --arg guard "graph-access" \
    --arg hash "$(printf '%s' "$command" | sha256sum | cut -c1-16)" \
    '{ts: $ts,
      session_id: (.session_id // ""),
      agent_type: (.agent_type // ""),
      scope: $scope,
      cwd: (.cwd // ""),
      guard: $guard,
      guard_version: 1,
      verdict: $verdict,
      branch: $branch,
      tool: (.tool_name // ""),
      command_hash: $hash}' >> "$guard_dir/$(date -u +%Y-%m).jsonl" || true
}

if [ "$scope" = "main" ]; then
  log_event pass main
  exit 0
fi

# A house entrypoint that reaches the graph on the session's behalf is struck out of
# the command rather than short-circuiting the test below, because a short-circuit is
# a route around: `python -c '<traversal>'; thalamus status` carries an entrypoint and
# a connection, and a branch that returns on the first one never sees the second.
# What is left after the strike is what this guard actually judges.
residual=$(printf '%s' "$command" | sed -E \
  's/(^|[;&|] )(uv run |uvx |poetry run )?([A-Za-z0-9_.~\/-]*\/)?(python[0-9.]*[[:space:]]+-m[[:space:]]+)?(pytest|thalamus)([[:space:]]|$)/\1 /g')

# Markers carried as data rather than run: reading the code that connects, grepping
# for it, committing a message that names it. This class was already paid for twice on
# the other two Bash guards — each tripped on the commit message explaining its own
# amendment — so it is a branch here from the first version rather than after the first
# false positive.
#
# Asked as "is anything invoked that could open the connection", not as "does this look
# like a text command", because the second spelling is defeated by prefixing one:
# `ls; python -c '...'` leads with a text command and connects anyway. So the test is
# the interpreters and network clients that can reach a socket, and everything else is
# data by construction.
#
# The leading `VAR=value` runs are part of the anchor rather than a second branch:
# `THALAMUS_SCOPE=main python -c '...'` is an invocation, and an anchor that only knows
# the bare name lets one through. Anchoring at all is what keeps a commit message out
# of this branch — prose says `python` mid-sentence, never after a `;`.
if ! printf '%s' "$residual" | grep -qE \
  '(^|[;&|] |[$]\()([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*([A-Za-z0-9_.~/-]*/)?(python[0-9.]*|ipython|uv|uvx|poetry|curl|wget|nc|ncat|websocat|wscat)[[:space:]]'
then
  if [ "$residual" != "$command" ]; then
    log_event pass entrypoint
  else
    log_event pass textedit
  fi
  exit 0
fi

branch=direct
[ "$marked" != "script" ] || branch=script
log_event block "$branch"

cat >&2 <<EOF
Blocked: this command opens a graph connection directly, and scope \`${scope}\` reads
the graph through the MCP tools.

\`connect()\` applies no scope filter, so a traversal run from here sees \`main\`'s
episodic memory and every other expert's — the confinement the recall tools apply is a
property of that surface, not of the client. Reading across the boundary is what the
federation contract denies: an expert generalises inside its own scope, which is why
attribution is scope-closed too.

What to use instead, all of them confined to \`${scope}\`:

  - \`mcp__thalamus__memory_recall\` / \`memory_recall_by_project\` /
    \`memory_recall_recent\` / \`memory_recall_by_artifact\` — episodic recall.
  - \`mcp__thalamus__memory_open_threads\` / \`memory_open_problems\` /
    \`memory_thread\` — continuation points and their history.
  - \`mcp__thalamus__memory_exchanges\` / \`memory_consultations\` — the consultation
    record.

A free-form traversal is a master-plane instrument, and \`memory_query\` refuses this
pin for the same reason this guard does. A question that genuinely needs one is a
consultation: mint \`consult_request\` to the scope that owns it, or ask the operator
to run the traversal from a \`main\` session.

If this boundary is wrong, it is an operator decision and an edit to the guard — say so
rather than routing around it.
EOF
exit 2
