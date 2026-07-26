"""
Claude Code session-start hook tests (docs/07 harness integration; lab/012-013).

Interfaces: src/thalamus/harness/hooks/claude-code/session-start.sh, driven
live (bash) with synthetic stdin payloads shaped per Claude Code's hook
contract.
Infrastructure: tmp_path as $HOME so the pin ledger is sandboxed; no live
graph, no MCP server.
Scope: the *injected instruction* is the contract under test here — it is the
only channel by which a session learns the memory surface exists, and two
counterfactual campaigns were voided by it being wrong (lab/012: the project it
names; lab/013: the calling convention it omitted). Pin-ledger writes are
covered because session-end and eval both read them. The Cursor variant's
mirror of these checks lives in test_cursor_hooks.py.
"""

import json
import subprocess
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks" / "claude-code"


def run_hook(payload, home, env=None):
    full_env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(HOOKS / "session-start.sh")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full_env,
        timeout=30,
    )


def context_of(result):
    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


def session_start_payload(**overrides):
    payload = {
        "session_id": "cc-sess-1",
        "cwd": "/home/user/code/myproject",
        "hook_event_name": "SessionStart",
        "source": "startup",
    }
    payload.update(overrides)
    return payload


class TestInjectedInstruction:
    def test_names_the_deferred_tool_step_before_the_tools(self, tmp_path):
        """
        Scenario: a normal session starts.

        Verification: the injected text tells the agent how to *reach* the
        tools, not just to call them. lab/013 measured both memory-on arms of
        a campaign making zero thalamus calls with the server reachable and
        all tools registered — the instruction named tools whose schemas were
        deferred, so it could not be followed as written. The ToolSearch step
        must appear, must name both tools the instruction goes on to use, and
        must come before the first call instruction.
        """
        ctx = context_of(run_hook(session_start_payload(), tmp_path))
        assert "ToolSearch" in ctx
        assert (
            "select:mcp__thalamus__memory_open_threads,"
            "mcp__thalamus__memory_recall_by_project" in ctx
        )
        assert ctx.index("ToolSearch") < ctx.index("At the start of this session")

    def test_project_comes_from_cwd_by_default(self, tmp_path):
        ctx = context_of(run_hook(session_start_payload(), tmp_path))
        assert 'project="myproject"' in ctx

    def test_thalamus_project_overrides_the_cwd_guess(self, tmp_path):
        """
        Scenario: an eval arm's headless session, whose cwd is a disposable
        worktree named <task-id>--<arm>--<timestamp>.

        Verification: the injected project is the repo's real name, not the
        worktree's. basename(cwd) here is a string no session has ever
        distilled under, so recall scoped to it silently returns nothing —
        the bug that made two campaigns' memory-on arms inert (lab/012).
        """
        result = run_hook(
            session_start_payload(cwd="/tmp/wt/reader-recall--memory-on--20260726T000000Z"),
            tmp_path,
            env={"THALAMUS_PROJECT": "thalamus"},
        )
        ctx = context_of(result)
        assert 'project="thalamus"' in ctx
        assert "memory-on--" not in ctx

    def test_pinned_scope_leads_the_context_and_lands_in_the_ledger(self, tmp_path):
        result = run_hook(
            session_start_payload(),
            tmp_path,
            env={"THALAMUS_SCOPE": "literature"},
        )
        assert context_of(result).startswith("This session is pinned to expert scope `literature`")
        pins = [
            json.loads(line)
            for line in (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()
            if line.strip()
        ]
        assert pins[0]["scope"] == "literature"
        assert pins[0]["session_id"] == "cc-sess-1"

    def test_resume_is_not_primed(self, tmp_path):
        """Resume/compact already carry context; only startup and clear prime."""
        result = run_hook(session_start_payload(source="resume"), tmp_path)
        assert json.loads(result.stdout) == {}
        assert not (tmp_path / ".thalamus" / "pins" / "pins.jsonl").exists()
