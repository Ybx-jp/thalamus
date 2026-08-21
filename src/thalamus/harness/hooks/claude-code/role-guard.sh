#!/bin/bash
# Thalamus PreToolUse hook — role boundary on writes and on capability (Claude Code).
#
# Some expert scopes are defined as much by what they do NOT produce as by what
# they do: the visual designer's deliverables are design artifacts and never
# software; the quality engineer holds the oracle and does not repair the code it
# asserts against. Those boundaries were stated in each manifest's `domain`
# paragraph first, and prose is the configuration that was measured failing —
# MAST names "Disobey Role Specification" as a distinct multi-agent failure mode,
# and in the system it studied the repair that worked was structural authority
# rather than better instructions (`scope:literature:claim:db0928fe2cfd3616`).
# This hook is that structure.
#
# Two boundaries, declared tier-0 in the manifest so they version with the rest of
# the contract and no model can widen them.
#
# `write_boundary.deny_globs` (contract/manifest.WriteBoundary) bounds paths, and a
# scope that declares nothing is untouched — every scope today except `qe` and
# `designer`, since `architect` writes code by charter.
#
# `capability_boundary` (contract/manifest.CapabilityBoundary) bounds tools and
# named skills, and its default runs the other way: a scope that declares nothing
# inherits ROSTER_CAPABILITY_DEFAULT, which denies the design skills and artifact
# publishing. `designer` is the one scope that opts out, because those are its
# charter. The defaults differ because the decisions did — path bounds were drawn
# per scope, this one was drawn once for the whole roster.
#
# Gated on the resolved pin rather than on the derived agent file, deliberately. A
# `tools:` list in agent frontmatter would bind only sessions launched through the
# agent picker; the pin also arrives by THALAMUS_SCOPE and, inside a subagent, only
# by the payload's `agent_type`. resolve-scope.sh reconciles all three, so gating
# where the pin is resolved means the guard covers every launch path.
#
# Scope of enforcement, named rather than papered over. This gates the file-editing
# tools, `Skill`, and `Artifact`, and each has a live route around it:
#
#   - Bash writes files without touching an editing tool, and a repository that does
#     not put implementation under `src/` escapes qe's `*/src/*` deny.
#   - `Read` on a SKILL.md gets the procedure into context with no `Skill` call. No
#     tool-name matcher can see that.
#   - A denied `Artifact` can become a hand-written page: qe's write boundary denies
#     `*/src/*` and says nothing about `.html`.
#   - A skill name this list has never heard of is permitted silently, because the
#     namespace is owned upstream and a boundary that is never hit looks exactly
#     like one that is respected.
#
# Codex is the third caller, and it does wire an adapter: its editing tool is
# `apply_patch`, whose argument is a patch envelope naming several files and carrying
# no `file_path` at all, so there is a real translation to make rather than a second
# registration of the same call. Codex does not read `~/.claude/settings.json`
# (measured: three codex sessions ran with the Claude Code suite installed at user
# scope and fired none of it), so the double-fire hazard below does not arise there.
#
# This script runs on Cursor too, and nothing under `.cursor/` wires it: Cursor
# translates `~/.claude/settings.json`, including the `|`-separated matcher, and
# shims `permissionDecision` onto its own `permission` field. So the path boundary
# binds there — measured, `cursor/2026.08.11-e8db854` — while the capability boundary
# is vacuous, because Cursor has no `Artifact` tool and reaches a skill by reading its
# SKILL.md rather than by a call this matcher could see. Do not add a Cursor adapter
# for this guard: a second registration runs it twice on one call. The per-harness
# states and their evidence live in `contract/boundaries.py`.
#
# All misses, and the project's standing trade says a miss is the cheaper error — a
# false positive teaches route-around, and route-around costs more than a gap.
#
# Install (user or project settings.json):
#   {"hooks": {"PreToolUse": [{"matcher": "Edit|Write|NotebookEdit|Skill|Artifact|mcp__penpot__.*",
#     "hooks": [{"type": "command",
#     "command": ".../hooks/claude-code/role-guard.sh"}]}]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

thalamus_read_guard_input role-guard.sh
input="$thalamus_guard_input"

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')

scope="$(thalamus_scope_from_payload "$input")"

# Two boundaries, one guard, because they are one role decision resolved from one
# manifest. `kind` selects which of them the Python below consults.
case "$tool_name" in
  # NotebookEdit names its target differently from the two text editors. `apply_patch`
  # is codex's editing tool and is named here rather than translated to `Write` by its
  # adapter, so the guard's event row records the tool that was actually called; the
  # adapter (../codex/role-guard.sh) lifts one path per patch header and calls this
  # once per path, since a patch names several files and a verdict is about one.
  Edit|Write|NotebookEdit|apply_patch)
    kind=path
    target=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty') ;;
  Skill)
    kind=skill
    target=$(printf '%s' "$input" | jq -r '.tool_input.skill // empty') ;;
  Artifact)
    # Listing is read-only: a scope that may not publish may still see what exists.
    [ "$(printf '%s' "$input" | jq -r '.tool_input.action // empty')" != "list" ] || exit 0
    kind=tool
    target="$tool_name" ;;
  mcp__penpot__*)
    # Named individually rather than folded into Artifact's `kind=tool`: the target
    # is the specific MCP tool (`mcp__penpot__create_shape`, not a bare `Artifact`),
    # because `allow_tools` carves permitted names back out of a scope's deny by
    # matching against exactly this string (contract/manifest.CapabilityBoundary).
    kind=tool
    target="$tool_name" ;;
  *) exit 0 ;;
esac
repo_root="$(thalamus_repo_root)"
py="$repo_root/.venv/bin/python"
[ -x "$py" ] || py="python3"

guard_label="role-boundary"

log_event() {
  local guard_dir="$HOME/.thalamus/guards"
  mkdir -p "$guard_dir"
  printf '%s' "$input" | jq -c \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg scope "$scope" \
    --arg verdict "$1" \
    --arg pattern "$2" \
    --arg kind "$kind" \
    --arg path "$target" \
    --arg guard "$guard_label" \
    '{ts: $ts,
      session_id: (.session_id // ""),
      agent_type: (.agent_type // ""),
      scope: $scope,
      cwd: (.cwd // ""),
      guard: $guard,
      guard_version: 3,
      verdict: $verdict,
      tool: (.tool_name // ""),
      kind: $kind,
      pattern: $pattern,
      path: $path}' >> "$guard_dir/$(date -u +%Y-%m).jsonl" || true
}

# ---- Path ownership, ordered AHEAD of the `main` exemption ----
#
# `contract/ownership.PATH_OWNERSHIP` says who owns a path. Unlike `write_boundary`
# it must bind `main`, which has no manifest to declare a deny in — so the test runs
# before the short-circuit below rather than after it. The ordering is what keeps the
# fast path: an unowned target exits here, and the `main` exemption is still consulted
# before anything loads a manifest.
#
# The cost is measured, and it is why `ownership.py` imports no pydantic: bare
# interpreter 15ms, that module ~15ms, `contract.manifest` 151ms. Importing the typed
# contract here would make the cheap test more expensive than the expensive one.
#
# This rule fails CLOSED, which the guard around it does not. That is the
# `write-guard.sh` posture applied to one rule: when the structured read fails, the
# RAW payload is searched instead. The other boundaries can afford failing open
# because their failure is a bad edit; this one's failure is a scope editing the
# oracle that indicts it, and `guards-fail-closed-on-unparseable-input` is an open qe
# finding that the shared jq prologue permits exactly when something unusual is
# happening.
if [ "$kind" = "path" ]; then
  ownership=""
  if [ -n "$target" ]; then
    ownership=$("$py" - "$scope" "$target" <<'PY' 2>/dev/null || true
import sys
try:
    from thalamus.contract.ownership import denies
except Exception:
    sys.exit(3)
row = denies(sys.argv[1], sys.argv[2])
if row:
    print("DENY"); print(row[0]); print(row[1]); print(row[2])
else:
    print("PASS")
PY
)
  fi

  case "$(printf '%s' "$ownership" | head -n1)" in
    PASS) : ;;
    DENY)
      glob=$(printf '%s' "$ownership" | sed -n '2p')
      owner=$(printf '%s' "$ownership" | sed -n '3p')
      reason=$(printf '%s' "$ownership" | sed -n '4,$p')
      guard_label="path-ownership"
      log_event block "$glob"
      cat >&2 <<EOF
Blocked: \`${target}\` is owned by scope \`${owner}\`, and this session is \`${scope}\`
(matched \`${glob}\`).

${reason}

This is an ownership row in \`contract/ownership.PATH_OWNERSHIP\`, declared tier-0 and
not something this session can widen. Hand the change to \`${owner}\` — mint a
consultation ticket, or report it to the operator. If the boundary itself is wrong,
that is an operator decision and an edit to the table, not a route around it.
EOF
      exit 2 ;;
    *)
      # Degraded: no target parsed, or the ownership module would not load. Markers
      # are inlined from `ownership.fallback_markers()` because the interpreter that
      # could compute them is the thing that just failed; `test_ownership.py` asserts
      # the two lists agree, so the duplication is checked rather than denied.
      for pair in "/tests/qe/:qe"; do
        marker="${pair%%:*}"
        owner="${pair##*:}"
        [ "$scope" != "$owner" ] || continue
        case "$input" in
          *"$marker"*)
            guard_label="path-ownership"
            log_event block-degraded "$marker"
            cat >&2 <<EOF
Blocked: this payload names \`${marker}\`, which scope \`${owner}\` owns, and this
session is \`${scope}\`.

The structured ownership check could not run — no target could be parsed out of the
hook payload, or \`thalamus.contract.ownership\` would not import — so the raw payload
was searched instead. This rule fails closed: it refuses rather than guessing, because
its failure mode is the scope under test editing the oracle that tests it.

If this is a false match, say so rather than working around it; the degraded path is
deliberately cruder than the real one.
EOF
            exit 2 ;;
        esac
      done ;;
  esac
fi

# `main` has no manifest by design, and is the overwhelmingly common case. Test it
# before spending a Python start-up on every call in every unpinned session. Ordered
# after the ownership gate above, which is the one rule that must bind `main` too.
[ "$scope" != "main" ] || exit 0

[ -n "$target" ] || exit 0

# Resolve the manifest's boundary in-process. Prints the matched glob and the
# operator's reason on a block, nothing at all on a pass. A scope whose manifest
# is missing or unreadable fails OPEN: this guard is defence-in-depth over a
# boundary the manifest also states in prose, and a hook that hard-fails every
# edit because a YAML file moved is a worse outcome than an unenforced boundary.
verdict=$("$py" - "$scope" "$kind" "$target" <<'PY' 2>/dev/null || true
import sys
try:
    from thalamus.contract.manifest import load_manifest
    scope, kind, target = sys.argv[1], sys.argv[2], sys.argv[3]
    manifest = load_manifest(scope)
    if kind == "path":
        boundary = manifest.write_boundary
        pattern = boundary.denies(target)
    else:
        # Never the raw field: its None is "inherit the roster default", and
        # reading it directly would unbind every scope that declared nothing.
        boundary = manifest.effective_capability_boundary
        pattern = (boundary.denies_skill(target) if kind == "skill"
                   else boundary.denies_tool(target))
    if pattern:
        print(pattern)
        print(boundary.reason.strip())
except Exception:
    pass
PY
)

if [ -z "$verdict" ]; then
  # Passes are logged too. The roster's granularity audit asks whether a scope
  # earned its partition, and "never came near its own boundary" is evidence for
  # that question exactly as a block is.
  log_event pass ""
  exit 0
fi

pattern=$(printf '%s' "$verdict" | head -n1)
reason=$(printf '%s' "$verdict" | tail -n +2)
log_event block "$pattern"

case "$kind" in
  path)
    verb="does not write"
    declared="config/experts/${scope}.yaml (\`write_boundary\`)" ;;
  skill)
    verb="does not invoke the skill"
    declared="the roster capability default (contract/manifest.ROSTER_CAPABILITY_DEFAULT), unless config/experts/${scope}.yaml overrides it" ;;
  *)
    verb="does not use the tool"
    declared="the roster capability default (contract/manifest.ROSTER_CAPABILITY_DEFAULT), unless config/experts/${scope}.yaml overrides it" ;;
esac

cat >&2 <<EOF
Blocked: scope \`${scope}\` ${verb} \`${target}\` (matched \`${pattern}\`).

${reason}

This boundary is declared tier-0 in ${declared}, and is not something this session
can widen. If the work genuinely belongs to another scope, hand it over: mint a
consultation ticket to the scope that owns it, or report it to the operator. If
the boundary itself is wrong, that is an operator decision and an edit to the
manifest — say so rather than routing around it.
EOF
exit 2
