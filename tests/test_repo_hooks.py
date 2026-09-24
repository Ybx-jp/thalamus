"""
Project-scope hooks for working on this repository (`.claude/hooks/`).

Interfaces: .claude/hooks/harness-fact-reminder.sh, driven live (bash) with a
            synthetic PostToolUse payload; .claude/settings.json's wiring of it
Infrastructure: tmp_path as TMPDIR; jq on PATH
Scope: when the reminder speaks and when it stays silent. Whether a flagged sentence is
       a harness fact is a judgement the reminder hands to the agent; what is tested is
       that the triggers and the silences are the ones it states.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "harness-fact-reminder.sh"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")


def _run(tmp_path, file_path, new_string, session="s1"):
    payload = {
        "session_id": session, "tool_name": "Edit",
        "tool_input": {"file_path": str(ROOT / file_path), "old_string": "x",
                       "new_string": new_string},
    }
    result = subprocess.run(
        ["bash", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
        timeout=30, env={"PATH": "/usr/bin:/bin:/usr/local/bin", "TMPDIR": str(tmp_path),
                         "CLAUDE_PROJECT_DIR": str(ROOT)},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"] \
        if result.stdout.strip() else ""


CLAIM = "# Claude Code never fires PostToolUse for a Bash call that exits non-zero."


def test_an_uncited_harness_fact_on_a_repo_surface_is_flagged(tmp_path):
    """
    Verifications:
    - a line naming a harness beside a behaviour word, on a repo surface, is quoted back
      with the skill that measures and pins it
    - once per file per session: the second edit to the same file says nothing
    - control: another session editing the same file is told again
    """
    first = _run(tmp_path, "src/thalamus/harness/reflex.py", CLAIM)
    assert "states how a harness behaves" in first
    assert "Claude Code never fires PostToolUse" in first
    assert "probe-harness-behaviour" in first

    assert _run(tmp_path, "src/thalamus/harness/reflex.py", CLAIM) == ""
    assert _run(tmp_path, "src/thalamus/harness/reflex.py", CLAIM, session="s2")


@pytest.mark.parametrize("file_path, text", [
    ("src/thalamus/harness/reflex.py", CLAIM + " (A0161, cites-as-live)"),
    ("src/thalamus/harness/reflex.py", "# The digest is sized in characters."),
    ("src/thalamus/harness/reflex.py", "# Claude Code's reflex digest, rendered here."),
    ("tests/test_reflex.py", CLAIM),
])
def test_it_stays_silent_on_a_cited_line_a_plain_line_and_off_the_repo_surfaces(
    tmp_path, file_path, text
):
    assert _run(tmp_path, file_path, text) == ""


def test_the_project_settings_wire_it_after_every_edit():
    groups = json.loads((ROOT / ".claude" / "settings.json").read_text())["hooks"]["PostToolUse"]
    wired = [
        (group.get("matcher"), hook["command"])
        for group in groups for hook in group["hooks"]
        if hook["command"].endswith("harness-fact-reminder.sh")
    ]
    assert wired == [("Edit|Write|MultiEdit|apply_patch",
                      "$CLAUDE_PROJECT_DIR/.claude/hooks/harness-fact-reminder.sh")]
