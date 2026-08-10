#!/bin/bash
# Thalamus PreToolUse hook — role boundary on file writes (Claude Code).
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
# The boundary is declared tier-0 in the manifest (`write_boundary.deny_globs`,
# contract/manifest.WriteBoundary), so it versions with the rest of the contract
# and no model can widen it. Scopes that declare nothing are untouched, which is
# every scope that exists today except `qe` and `designer` — `architect` writes
# code by charter and carries no boundary at all.
#
# Env-based rather than agent-frontmatter based, deliberately. A `tools:` list on
# the derived agent file would bind only sessions launched through the agent
# picker; the pin also arrives by THALAMUS_SCOPE, and resolve-scope.sh is the one
# place that reconciles the two (the 2026-07-18 mis-arming measurement). Gating
# where the pin is resolved means the guard covers every launch path.
#
# Scope of enforcement, named rather than papered over: this gates the file-editing
# tools. A determined session can still write through Bash, and a repository that
# does not put implementation under `src/` escapes qe's `*/src/*` deny. Both are
# misses, and lab/008's standing trade says a miss is the cheaper error — a false
# positive teaches route-around, and route-around costs more than a gap.
#
# Install (user or project settings.json):
#   {"hooks": {"PreToolUse": [{"matcher": "Edit|Write|NotebookEdit", "hooks":
#     [{"type": "command", "command": ".../hooks/claude-code/role-guard.sh"}]}]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

input=$(cat)

tool_name=$(printf '%s' "$input" | jq -r '.tool_name // empty')
case "$tool_name" in
  Edit|Write|NotebookEdit) ;;
  *) exit 0 ;;
esac

scope="$(thalamus_resolve_scope)"
# `main` has no manifest by design, and is the overwhelmingly common case. Test it
# before spending a Python start-up on every edit in every unpinned session.
[ "$scope" != "main" ] || exit 0

# NotebookEdit names its target differently from the two text editors.
file_path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty')
[ -n "$file_path" ] || exit 0

repo_root="$(thalamus_repo_root)"
py="$repo_root/.venv/bin/python"
[ -x "$py" ] || py="python3"

# Resolve the manifest's boundary in-process. Prints the matched glob and the
# operator's reason on a block, nothing at all on a pass. A scope whose manifest
# is missing or unreadable fails OPEN: this guard is defence-in-depth over a
# boundary the manifest also states in prose, and a hook that hard-fails every
# edit because a YAML file moved is a worse outcome than an unenforced boundary.
verdict=$("$py" - "$scope" "$file_path" <<'PY' 2>/dev/null || true
import sys
try:
    from thalamus.contract.manifest import load_manifest
    boundary = load_manifest(sys.argv[1]).write_boundary
    pattern = boundary.denies(sys.argv[2])
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
    --arg path "$file_path" \
    '{ts: $ts,
      session_id: (.session_id // ""),
      scope: $scope,
      cwd: (.cwd // ""),
      guard: "role-boundary",
      guard_version: 1,
      verdict: $verdict,
      tool: (.tool_name // ""),
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

cat >&2 <<EOF
Blocked: scope \`${scope}\` does not write \`${file_path}\` (matched \`${pattern}\`).

${reason}

This boundary is declared tier-0 in config/experts/${scope}.yaml
(\`write_boundary\`) and is not something this session can widen. If the work
genuinely belongs to another scope, hand it over: open a thread describing it, or
mint a consultation ticket to the scope that owns it. If the boundary itself is
wrong, that is an operator decision and an edit to the manifest — say so rather
than routing around it.
EOF
exit 2
