"""
Cursor hook-suite tests (docs/07 harness integration; lab/010).

Interfaces: src/thalamus/harness/hooks/cursor/*.sh, driven live (bash) with
synthetic stdin payloads shaped per Cursor's documented hook contract
(verified against docs.cursor.com 2026-07-19).
Infrastructure: tmp_path as $HOME so ledger/trace/guard writes are sandboxed;
no live graph, no Cursor.
Scope: the adapter boundary — each Cursor hook must reshape its payload into
the Claude Code shape, produce Cursor-valid output, and leave the same
on-disk records the Claude Code suite leaves, so eval reads stay
harness-agnostic. This is contract conformance, not an end-to-end Cursor
test: only a live Cursor run can validate the payloads Cursor actually sends.
"""

import json
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks" / "cursor"

DOOMED_GREMLIN = (
    "python -c \"from gremlin_python.driver.driver_remote_connection import"
    " DriverRemoteConnection; g.V().has_label('Session')\""
)


def run_hook(script, payload, home, env=None):
    full_env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full_env,
        timeout=30,
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def session_start_payload(**overrides):
    payload = {
        "session_id": "cur-sess-1",
        "conversation_id": "cur-conv-1",
        "workspace_roots": ["/home/user/code/myproject"],
        "is_background_agent": False,
        "hook_event_name": "sessionStart",
    }
    payload.update(overrides)
    return payload


class TestSessionStart:
    def test_primes_context_and_records_pin(self, tmp_path):
        """
        Scenario: a foreground Cursor session starts in a workspace.

        Verifications:
        - stdout is Cursor-shaped: bare `additional_context`, no
          hookSpecificOutput wrapper
        - the context names the project and the bare (unprefixed) tool names
        - it does *not* carry the Claude Code variant's deferred-tool
          (ToolSearch) step — that mechanism is Claude Code's, and naming a
          tool Cursor has no notion of would be an instruction the agent
          cannot follow, the same class of defect lab/013 found in the other
          direction
        - the pin ledger gets one line in the same record shape the Claude
          Code hook writes (session-end + eval read both harnesses' lines)
        """
        result = run_hook("session-start.sh", session_start_payload(), tmp_path)
        assert result.returncode == 0
        out = json.loads(result.stdout)
        ctx = out["additional_context"]
        assert "hookSpecificOutput" not in out
        assert 'project="myproject"' in ctx
        assert "memory_open_threads" in ctx
        assert "mcp__thalamus__" not in ctx
        assert "ToolSearch" not in ctx

        pins = read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")
        assert pins == [
            {
                "session_id": "cur-sess-1",
                "scope": "main",
                "cwd": "/home/user/code/myproject",
                "ts": pins[0]["ts"],
            }
        ]

    def test_env_pin_is_announced_and_recorded(self, tmp_path):
        """
        Scenario: the session was launched with THALAMUS_SCOPE=literature
        (env is the only pin channel on Cursor — no agent picker).

        Verifications: the pin lands in the ledger and the context leads with
        the pinned-scope announcement.
        """
        result = run_hook(
            "session-start.sh",
            session_start_payload(),
            tmp_path,
            env={"THALAMUS_SCOPE": "literature"},
        )
        ctx = json.loads(result.stdout)["additional_context"]
        assert ctx.startswith("This session is pinned to expert scope `literature`")
        pins = read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")
        assert pins[0]["scope"] == "literature"

    def test_background_agent_is_not_primed(self, tmp_path):
        result = run_hook(
            "session-start.sh",
            session_start_payload(is_background_agent=True),
            tmp_path,
        )
        assert json.loads(result.stdout) == {}
        assert not (tmp_path / ".thalamus" / "pins" / "pins.jsonl").exists()


class TestGremlinGuard:
    def test_blocks_doomed_traversal_with_cursor_permission_json(self, tmp_path):
        """
        Scenario: inline gremlin-python with no terminal step, arriving in
        Cursor's beforeShellExecution shape ({command}, not {tool_input}).

        Verifications:
        - the Claude Code guard's exit-2 protocol maps to permission=deny
        - the block instruction reaches the agent via agent_message
        - the shared guard event log gets the block verdict (one log, two
          harnesses)
        """
        result = run_hook(
            "gremlin-guard.sh",
            {"command": DOOMED_GREMLIN, "cwd": "/w", "conversation_id": "c1"},
            tmp_path,
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out["permission"] == "deny"
        assert "terminal step" in out["agent_message"]

        guard_dir = tmp_path / ".thalamus" / "guards"
        events = read_jsonl(next(guard_dir.glob("*.jsonl")))
        assert events[-1]["verdict"] == "block"
        assert events[-1]["session_id"] == "c1"

    def test_allows_terminated_traversal(self, tmp_path):
        result = run_hook(
            "gremlin-guard.sh",
            {"command": DOOMED_GREMLIN.replace("g.V()", "g.V().to_list() #"),
             "conversation_id": "c1"},
            tmp_path,
        )
        assert json.loads(result.stdout) == {"permission": "allow"}
        events = read_jsonl(next((tmp_path / ".thalamus" / "guards").glob("*.jsonl")))
        assert events[-1]["verdict"] == "pass"

    def test_non_gremlin_command_passes_without_event(self, tmp_path):
        result = run_hook("gremlin-guard.sh", {"command": "ls -la"}, tmp_path)
        assert json.loads(result.stdout) == {"permission": "allow"}
        assert not (tmp_path / ".thalamus" / "guards").exists()


class TestGremlinTap:
    def test_gremlin_command_lands_as_bash_gremlin_trace(self, tmp_path):
        """
        Scenario: an executed inline gremlin command arrives in Cursor's
        afterShellExecution shape, with its single combined `output` string.

        Verifications: the trace record is byte-compatible with the Claude
        Code tap's — tool_name bash_gremlin, output on the stdout leg — so
        `eval sync` prices it with no harness awareness.
        """
        result = run_hook(
            "gremlin-tap.sh",
            {"command": DOOMED_GREMLIN, "output": "v[abc]", "duration": 40,
             "conversation_id": "c9", "cwd": "/w"},
            tmp_path,
        )
        assert result.returncode == 0
        traces = read_jsonl(next((tmp_path / ".thalamus" / "traces").glob("*.jsonl")))
        assert traces[-1]["tool_name"] == "bash_gremlin"
        assert traces[-1]["tool_response"] == "v[abc]"
        assert traces[-1]["session_id"] == "c9"

    def test_non_gremlin_command_leaves_no_trace(self, tmp_path):
        run_hook("gremlin-tap.sh", {"command": "git status", "output": "clean"}, tmp_path)
        assert not (tmp_path / ".thalamus" / "traces").exists()


class TestMcpTap:
    def test_bare_tool_name_is_reprefixed_in_trace(self, tmp_path):
        """
        Scenario: Cursor reports a thalamus MCP call by bare name with the
        result under result_json.

        Verifications: the trace restores the mcp__thalamus__ prefix and maps
        result_json to tool_response — uniform records across harnesses.
        """
        result = run_hook(
            "mcp-tap.sh",
            {"tool_name": "memory_recall",
             "tool_input": {"query": "pin ledger"},
             "result_json": "## Recalled memory ...",
             "conversation_id": "c2"},
            tmp_path,
        )
        assert result.returncode == 0
        traces = read_jsonl(next((tmp_path / ".thalamus" / "traces").glob("*.jsonl")))
        assert traces[-1]["tool_name"] == "mcp__thalamus__memory_recall"
        assert traces[-1]["tool_input"] == {"query": "pin ledger"}
        assert traces[-1]["tool_response"] == "## Recalled memory ..."

    def test_foreign_mcp_tool_is_not_traced(self, tmp_path):
        run_hook(
            "mcp-tap.sh",
            {"tool_name": "list_issues", "tool_input": {}, "result_json": "[]"},
            tmp_path,
        )
        assert not (tmp_path / ".thalamus" / "traces").exists()


class TestPinEngaged:
    def test_first_prompt_marks_engaged_once(self, tmp_path):
        """
        Scenario: two prompts in the same Cursor conversation.

        Verifications: exactly one engaged event lands in the ledger
        (idempotent per session), and every response is {"continue": true} —
        this hook must never block a prompt.
        """
        payload = {"prompt": "hello", "conversation_id": "c3"}
        for _ in range(2):
            result = run_hook("pin-engaged.sh", payload, tmp_path)
            assert json.loads(result.stdout) == {"continue": True}
        pins = read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")
        engaged = [p for p in pins if p.get("event") == "engaged"]
        assert len(engaged) == 1
        assert engaged[0]["session_id"] == "c3"


class TestSessionEnd:
    def test_records_undistilled_end_with_ledger_first_scope(self, tmp_path):
        """
        Scenario: a Cursor session that session-start pinned to `literature`
        ends from a shell whose env says main.

        Verifications:
        - the end record trusts the ledger over env (same rule as Claude Code)
        - distilled is explicitly false with the lab/010 wall named — the
          missing Cursor transcript adapter must be visible in the record,
          not silent
        - the transcript_path evidence pointer survives
        """
        ledger = tmp_path / ".thalamus" / "pins" / "pins.jsonl"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(
            json.dumps({"session_id": "c4", "scope": "literature", "cwd": "/w",
                        "ts": "2026-07-19T00:00:00Z"}) + "\n"
        )
        result = run_hook(
            "session-end.sh",
            {"session_id": "c4", "reason": "user_closed",
             "transcript_path": "/home/user/.cursor/transcripts/c4.json"},
            tmp_path,
        )
        assert result.returncode == 0
        ends = read_jsonl(tmp_path / ".thalamus" / "logs" / "cursor-session-end.jsonl")
        assert ends[-1]["scope"] == "literature"
        assert ends[-1]["distilled"] is False
        assert ends[-1]["transcript_path"] == "/home/user/.cursor/transcripts/c4.json"
        assert "lab/010" in ends[-1]["note"]


@pytest.mark.parametrize(
    "script",
    ["session-start.sh", "session-end.sh", "pin-engaged.sh",
     "gremlin-guard.sh", "gremlin-tap.sh", "mcp-tap.sh"],
)
def test_registered_in_project_hooks_json(script):
    """Every shipped Cursor hook is wired in the committed .cursor/hooks.json."""
    config = json.loads((HOOKS.parents[4] / ".cursor" / "hooks.json").read_text())
    assert config["version"] == 1
    commands = [
        entry["command"]
        for entries in config["hooks"].values()
        for entry in entries
    ]
    assert f"./src/thalamus/harness/hooks/cursor/{script}" in commands
