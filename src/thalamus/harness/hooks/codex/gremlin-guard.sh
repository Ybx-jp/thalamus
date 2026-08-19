#!/bin/bash
# Thalamus PreToolUse hook — gremlin terminal-step guard (codex).
#
# A delegator over ../claude-code/gremlin-guard.sh. Cursor needed an adapter here
# because its shell payload is `{command}` and its verdict is a permission JSON
# object; codex needs none of that. Measured 2026-08-17: codex's shell tool is named
# **`Bash`**, its payload is `{tool_name, tool_input: {command}, session_id, cwd,
# turn_id, ...}`, and exit 2 with a reason on stderr is its documented blocking
# channel — the same three facts the Claude Code guard was written against.
#
# (The rollout transcript tells a different story, and it is the reason to trust the
# hook payload rather than the file: in the rollout every tool call is a
# `custom_tool_call` named `exec` whose input is a JavaScript program calling
# `tools.exec_command(...)`. The hook layer presents the resolved operation instead.)
#
# One detection logic, one event log (~/.thalamus/guards/), three harnesses.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_codex_delegate gremlin-guard.sh
