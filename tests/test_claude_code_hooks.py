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
import time
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


class TestForeignCwdPinResolution:
    """A pinned session opened outside the checkout (`thalamus spawn --dir`).

    CLAUDE_PROJECT_DIR then names the *working* repo, not the Thalamus checkout.
    Anchoring manifest lookup on it made the hooks resolve `main` while the MCP
    server — which anchors on contract/manifest._DEFAULT_CONFIG and never reads
    CLAUDE_PROJECT_DIR — enforced the real scope. Because session-end is
    ledger-first, that mismatch distilled the whole session into the wrong
    scope: the 2026-07-18 mis-scoping leak arriving through the ledger instead
    of the env. The bash mirror must stay anchored the way the Python is.
    """

    def resolve(self, tmp_path, env):
        full_env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        full_env.update(env)
        return subprocess.run(
            ["bash", "-c", f'. "{HOOKS}/resolve-scope.sh"; thalamus_resolve_scope'],
            capture_output=True, text=True, env=full_env, cwd=str(tmp_path), timeout=30,
        ).stdout.strip()

    def test_picked_agent_wins_when_project_dir_is_a_foreign_repo(self, tmp_path):
        assert self.resolve(tmp_path, {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "CLAUDE_CODE_AGENT": "thalamus-literature",
        }) == "literature"

    def test_ledger_records_the_launch_channel_beside_the_resolved_scope(self, tmp_path):
        """Scope alone cannot audit its own resolution.

        When agent and env disagreed before ed18887, the ledger kept only the
        resolved scope — the value that was wrong — so the mis-scoped-writes
        audit could not separate a mis-scoped expert session from a main session
        that consulted an expert. Recording the channel makes divergence visible.
        """
        run_hook(
            session_start_payload(cwd=str(tmp_path)),
            tmp_path,
            env={"CLAUDE_CODE_AGENT": "thalamus-literature", "THALAMUS_SCOPE": "main"},
        )
        row = json.loads(
            (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()[0])
        assert row["agent"] == "thalamus-literature"
        assert row["scope"] == "literature"

    def test_ledger_agent_is_empty_for_an_unpinned_session(self, tmp_path):
        run_hook(session_start_payload(cwd=str(tmp_path)), tmp_path)
        row = json.loads(
            (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()[0])
        assert row["agent"] == "" and row["scope"] == "main"

    def test_ledger_records_the_pin_from_a_foreign_cwd(self, tmp_path):
        """End-to-end: the ledger session-end reads must carry the real pin."""
        run_hook(
            session_start_payload(cwd=str(tmp_path)),
            tmp_path,
            env={"CLAUDE_PROJECT_DIR": str(tmp_path),
                 "CLAUDE_CODE_AGENT": "thalamus-literature"},
        )
        pins = [
            json.loads(line)
            for line in (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()
            if line.strip()
        ]
        assert pins[0]["scope"] == "literature"

    def test_unknown_agent_still_falls_through_to_env(self, tmp_path):
        """The manifest check is what makes agent-first safe; keep it load-bearing."""
        assert self.resolve(tmp_path, {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "CLAUDE_CODE_AGENT": "thalamus-nosuchexpert",
            "THALAMUS_SCOPE": "main",
        }) == "main"

    def test_config_dir_override_still_takes_precedence(self, tmp_path):
        """THALAMUS_CONFIG_DIR overrides the anchor, mirroring manifest.experts_dir."""
        assert self.resolve(tmp_path, {
            "THALAMUS_CONFIG_DIR": str(tmp_path / "nonexistent"),
            "CLAUDE_CODE_AGENT": "thalamus-literature",
        }) == "main"

    def test_repo_root_is_the_checkout_not_the_working_project(self, tmp_path):
        root = subprocess.run(
            ["bash", "-c", f'. "{HOOKS}/resolve-scope.sh"; thalamus_repo_root'],
            capture_output=True, text=True, timeout=30, cwd=str(tmp_path),
            env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin",
                 "CLAUDE_PROJECT_DIR": str(tmp_path)},
        ).stdout.strip()
        assert Path(root) == HOOKS.parents[4]
        assert (Path(root) / "pyproject.toml").is_file()


class TestDistillationAnchor:
    """session-end must run `thalamus` from the checkout, not the session's cwd.

    A foreign cwd is not a uv project with thalamus in it, so a cwd-anchored
    invocation resolves no `thalamus` command and the session silently never
    distills — the failure is invisible because extraction is detached.
    """

    def test_uv_is_pointed_at_the_checkout_from_a_foreign_cwd(self, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        argv_log = tmp_path / "uv-argv.txt"
        stub = bin_dir / "uv"
        stub.write_text(f'#!/bin/bash\nprintf "%s\\n" "$*" >> "{argv_log}"\n')
        stub.chmod(0o755)

        subprocess.run(
            [str(HOOKS / "session-end.sh")],
            input=json.dumps({"session_id": "cc-sess-9", "cwd": str(tmp_path),
                              "hook_event_name": "SessionEnd", "reason": "exit"}),
            capture_output=True, text=True, timeout=30,
            env={"HOME": str(tmp_path),
                 "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin",
                 "CLAUDE_PROJECT_DIR": str(tmp_path),
                 "THALAMUS_SCOPE": "literature"},
        )

        deadline = time.time() + 20
        while time.time() < deadline and not argv_log.exists():
            time.sleep(0.2)
        assert argv_log.exists(), "session-end never invoked uv"
        calls = argv_log.read_text()

        checkout = str(HOOKS.parents[4])
        assert f"--project {checkout}" in calls
        assert f"--directory {tmp_path}" not in calls
        assert "thalamus extract" in calls
