#!/bin/bash
# Thalamus PreToolUse hook — the graph is reached through the MCP surface (codex).
#
# A delegator over ../claude-code/graph-guard.sh, following `gremlin-guard.sh` and
# `write-guard.sh`: codex's shell tool is named `Bash`, its payload is `{tool_name,
# tool_input: {command}, session_id, cwd, ...}`, and exit 2 with a reason on stderr is
# its blocking channel — the three facts the Claude Code guard was written against, so
# there is nothing to adapt.
#
# Wired here rather than left a Claude-only gap because the boundary is a decision
# about the graph, and the graph does not care which harness ran the command. A codex
# session pinned to an expert reaches `connect()` exactly as a Claude Code one does.
#
# One detection logic, one event log (~/.thalamus/guards/), three harnesses.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_codex_delegate graph-guard.sh
