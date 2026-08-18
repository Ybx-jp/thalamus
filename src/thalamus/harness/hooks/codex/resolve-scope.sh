# Shared pin resolution and delegation for codex hooks — source this, then call
# thalamus_resolve_scope (or thalamus_codex_delegate to hand a payload to the real
# implementation under ../claude-code/).
#
# **Codex's hook payloads are Claude Code's payloads, verbatim** (measured
# 2026-08-17, codex-cli 0.147.0): the same `hooks.json` shape with matcher groups,
# the same stdin keys, the same output vocabulary, the same exit-2-plus-stderr
# blocking channel, and matchers that are regexes rather than literals — a probe
# wiring `Bash`, `mcp__thalamus__.*` and `Edit|Write|apply_patch` on PostToolUse saw
# each fire for exactly the tool names those patterns describe. Cursor needed eight
# reshaping adapters because its payloads differ; codex needs almost none, so the
# scripts in this directory delegate into `../claude-code/` rather than restate
# anything.
#
# This file exists anyway, for two reasons that a symlink or a direct hooks.json
# pointing at `../claude-code/` could not carry:
#
#   1. `THALAMUS_HARNESS=codex`, which is what the conditioning telemetry joins on.
#      A shared script file has no way to know which harness invoked it.
#   2. `CLAUDE_CODE_AGENT` is unset before delegating. Codex has no agent picker, so
#      that variable can only ever arrive here by inheritance from some Claude Code
#      process up the tree — where it names an agent *definition* codex never loaded.
#      Honouring it would apply another persona's boundary to a session that has none
#      of its tooling. On codex the pin arrives as THALAMUS_SCOPE and nowhere else
#      (harness/launcher.launch_argv puts `env THALAMUS_SCOPE=<scope>` in the argv for
#      persona-less harnesses), so scrubbing the variable makes the delegated script
#      resolve the same scope this file does.

# The Claude Code library, for the helpers whose behaviour is harness-independent:
# thalamus_repo_root, thalamus_config_root, thalamus_require_binaries,
# thalamus_resolve_room, thalamus_resolve_forked_from, thalamus_roster.
# `thalamus_resolve_scope` is redefined below; everything else is taken as-is rather
# than mirrored, because a second copy of `thalamus_require_binaries` would be a
# second failure log to keep in step.
#
# Sourcing does not disturb `thalamus_repo_root`: it reads `${BASH_SOURCE[0]}` inside
# the function body, which is the file the function was *defined* in — the Claude
# Code library — and both directories sit at the same depth under the checkout.
. "$(dirname "${BASH_SOURCE[0]}")/../claude-code/resolve-scope.sh"

# Env-only, replacing the Claude Code precedence (picked agent, then env). Codex has
# no agent picker and its tool payloads carry no `agent_type`, so the two channels
# above the environment do not exist here and an unpinned session *is* a main-plane
# session. Kept as a named override rather than left to inheritance so a future codex
# pin channel has exactly one place to land — the same shape `../cursor/` uses.
thalamus_resolve_scope() {
  printf '%s' "${THALAMUS_SCOPE:-main}"
}

# Run the real implementation of a hook, with this harness's identity and without a
# Claude Code persona leaking into the pin. $1 is a script name under ../claude-code/.
#
# `exec` rather than a call: the delegated script owns stdin, stdout, stderr and the
# exit code from here on, which is what makes an exit-2 denial and its stderr reason
# reach codex unaltered.
thalamus_codex_delegate() {
  exec env -u CLAUDE_CODE_AGENT THALAMUS_HARNESS=codex \
    "$(dirname "${BASH_SOURCE[0]}")/../claude-code/$1"
}
