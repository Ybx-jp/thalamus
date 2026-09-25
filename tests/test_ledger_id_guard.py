"""
The project-scope hook that refuses `claims-ledger new --id` (`.claude/hooks/`).

Interfaces: .claude/hooks/ledger-id-guard.py, driven live (python3) with a synthetic
            PreToolUse Bash payload; .claude/settings.json's wiring of it
Infrastructure: none beyond python3
Scope: which command lines are refused and which pass. The refusal's wording is not
       asserted beyond its naming `renumber`, the repair it points at.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "ledger-id-guard.py"


def _decision(command: str) -> dict | None:
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": command}}
    result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None


@pytest.mark.parametrize("command", [
    "claims-ledger new --id A0200 some-slug",
    "uv run claims-ledger new some-slug --id=A0200",
    ".venv/bin/claims-ledger --root . new --grade argued --id A0200 slug",
    "uv run --project /x claims-ledger new --id A0200 slug",
    "FOO=1 claims-ledger new --id A0200 slug",
    "python -m claims_ledger new --id A0200 slug",
    "cd ledger && claims-ledger new --id A0200 slug && git status",
])
def test_new_with_an_id_is_refused(command):
    decision = _decision(command)
    assert decision is not None
    assert decision["permissionDecision"] == "deny"
    assert "renumber" in decision["permissionDecisionReason"]


@pytest.mark.parametrize("command", [
    "claims-ledger new --grade argued some-slug",
    "claims-ledger source add --id codex-hooks --type documentation x.md",
    'claims-ledger source add --id s --citation "a new --id thing" x.md',
    "claims-ledger neighbours A0192",
    "claims-ledger new slug; echo --id",
    "echo claims-ledger new --id",
    "grep -- --id docs/concepts.md",
    "claims-ledger new 'unterminated",
])
def test_everything_else_passes(command):
    assert _decision(command) is None


def test_the_project_settings_wire_it_before_every_bash_call():
    groups = json.loads((ROOT / ".claude" / "settings.json").read_text())["hooks"]["PreToolUse"]
    wired = [
        (group.get("matcher"), hook["command"])
        for group in groups for hook in group["hooks"]
        if hook["command"].endswith("ledger-id-guard.py")
    ]
    assert wired == [("Bash", "$CLAUDE_PROJECT_DIR/.claude/hooks/ledger-id-guard.py")]
