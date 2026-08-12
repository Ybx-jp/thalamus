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
# This script runs on Cursor too, and nothing under `.cursor/` wires it: Cursor
# translates `~/.claude/settings.json`, including the `|`-separated matcher, and
# shims `permissionDecision` onto its own `permission` field. So the path boundary
# binds there — measured, `cursor/2026.08.11-e8db854` — while the capability boundary
# is vacuous, because Cursor has no `Artifact` tool and reaches a skill by reading its
# SKILL.md rather than by a call this matcher could see. Do not add a Cursor adapter
# for this guard: a second registration runs it twice on one call. The per-harness
# states and their evidence live in `contract/boundaries.py`.
#
# All misses, and lab/008's standing trade says a miss is the cheaper error — a
# false positive teaches route-around, and route-around costs more than a gap.
#
# Install (user or project settings.json):
#   {"hooks": {"PreToolUse": [{"matcher": "Edit|Write|NotebookEdit|Skill|Artifact",
#     "hooks": [{"type": "command",
#     "command": ".../hooks/claude-code/role-guard.sh"}]}]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

input=$(cat)

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')

scope="$(thalamus_scope_from_payload "$input")"
# `main` has no manifest by design, and is the overwhelmingly common case. Test it
# before spending a Python start-up on every call in every unpinned session.
[ "$scope" != "main" ] || exit 0

# Two boundaries, one guard, because they are one role decision resolved from one
# manifest. `kind` selects which of them the Python below consults.
case "$tool_name" in
  # NotebookEdit names its target differently from the two text editors.
  Edit|Write|NotebookEdit)
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
  *) exit 0 ;;
esac
[ -n "$target" ] || exit 0

repo_root="$(thalamus_repo_root)"
py="$repo_root/.venv/bin/python"
[ -x "$py" ] || py="python3"

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
    '{ts: $ts,
      session_id: (.session_id // ""),
      agent_type: (.agent_type // ""),
      scope: $scope,
      cwd: (.cwd // ""),
      guard: "role-boundary",
      guard_version: 2,
      verdict: $verdict,
      tool: (.tool_name // ""),
      kind: $kind,
      pattern: $pattern,
      path: $path}' >> "$guard_dir/$(date -u +%Y-%m).jsonl" || true
}

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
can widen. If the work genuinely belongs to another scope, hand it over: open a
thread describing it, or mint a consultation ticket to the scope that owns it. If
the boundary itself is wrong, that is an operator decision and an edit to the
manifest — say so rather than routing around it.
EOF
exit 2
