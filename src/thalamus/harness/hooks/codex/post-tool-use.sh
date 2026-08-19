#!/bin/bash
# Thalamus PostToolUse hook — retrieval traces (codex).
#
# A delegator over ../claude-code/post-tool-use.sh. Cursor needed `mcp-tap.sh` to
# re-prefix a bare tool name and to move `result_json` onto `tool_response`; codex
# needs neither. Measured 2026-08-17 against a live `codex exec` with the thalamus
# server registered through `codex mcp add`:
#
#   tool_name:     mcp__thalamus__memory_open_threads
#   tool_input:    {"project": "thalamus"}
#   tool_response: {"content": [{"type": "text", "text": "## ◐ [in_progress] …"}]}
#
# — the same `mcp__<server>__<tool>` naming and the same response envelope Claude
# Code produces, so the traces land in the shared monthly JSONL in one shape and
# `eval sync` prices them with no harness awareness.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard
thalamus_codex_delegate post-tool-use.sh
