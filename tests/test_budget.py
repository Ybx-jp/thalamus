"""
The budget guard: a scope's `budget` preset counted from hook payloads.

Interfaces: thalamus.harness.budget, hooks/claude-code/budget.sh,
            hooks/codex/budget.sh, harness/launcher.launch_argv
Infrastructure: tmp_path config roots and transcripts; the hook scripts run as
                subprocesses with HOME pointed at tmp_path
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from thalamus.harness import budget
from thalamus.harness.budget import claude_output_env, decide, limits

HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks"


def _config(tmp_path, preset: str | None = "short", sets: str = "max_tool_calls: 2") -> Path:
    root = tmp_path / "config"
    (root / "experts").mkdir(parents=True)
    (root / "presets").mkdir()
    body = "scope: s\nname: S\n" + (f"budget: {preset}\n" if preset else "")
    (root / "experts" / "s.yaml").write_text(body)
    (root / "presets" / "budget.yaml").write_text(f"short:\n  {sets}\n")
    return root


def _pre(prompt="p1", agent=None, **extra):
    payload = {"hook_event_name": "PreToolUse", "session_id": "sess", "prompt_id": prompt,
               "tool_name": "Bash"}
    if agent:
        payload["agent_id"] = agent
    return payload | extra


def _batch(prompt="p1", **extra):
    return {"hook_event_name": "PostToolBatch", "session_id": "sess",
            "prompt_id": prompt} | extra


def test_limits_come_from_the_scopes_preset_and_the_environment_overrides_them(tmp_path):
    root = _config(tmp_path, sets="max_tool_calls: 5")

    assert limits("s", root, {}) == {"max_tool_calls": 5}
    assert limits("s", root, {"THALAMUS_MAX_TOOL_CALLS": "3", "THALAMUS_MAX_TURNS": "7"}) == {
        "max_tool_calls": 3, "max_turns": 7,
    }


def test_a_scope_with_no_budget_and_no_override_has_no_limits(tmp_path):
    assert limits("s", _config(tmp_path, preset=None), {}) == {}
    assert limits("main", _config(tmp_path / "x", preset=None), {}) == {}


def test_a_bad_override_is_refused_rather_than_read_as_zero(tmp_path):
    with pytest.raises(ValueError, match="an integer"):
        limits("s", _config(tmp_path, preset=None), {"THALAMUS_MAX_TURNS": "0"})


def test_the_call_past_the_cap_is_denied_and_stops_the_prompt_on_claude_code():
    """Deny alone lets the prompt run on; `continue: false` alone runs the call first.
    The call past the cap needs both."""
    state: dict = {}
    caps = {"max_tool_calls": 2}

    assert decide(_pre(), "claude", caps, state) is None
    assert decide(_pre(), "claude", caps, state) is None
    out = decide(_pre(), "claude", caps, state)

    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert out["continue"] is False
    assert "2 tool calls" in out["stopReason"]


def test_codex_gets_the_deny_without_continue_false():
    """A codex PreToolUse hook that returns `continue: false` is marked failed and the
    call goes ahead, so the key would undo the deny."""
    state: dict = {}
    decide(_pre(turn_id="t1", prompt=None), "codex", {"max_tool_calls": 1}, state)
    out = decide(_pre(turn_id="t1", prompt=None), "codex", {"max_tool_calls": 1}, state)

    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "continue" not in out


def test_a_new_prompt_resets_turns_and_tool_calls():
    state: dict = {}
    caps = {"max_tool_calls": 1}
    decide(_pre("p1"), "claude", caps, state)
    assert decide(_pre("p1"), "claude", caps, state) is not None

    assert decide(_pre("p2"), "claude", caps, state) is None


def test_the_turn_cap_stops_the_prompt_at_the_batch_that_reaches_it():
    state: dict = {}
    caps = {"max_turns": 2}

    assert decide(_batch(), "claude", caps, state) is None
    out = decide(_batch(), "claude", caps, state)

    assert out == {"continue": False, "stopReason": out["stopReason"]}
    assert "2 turns" in out["stopReason"]


def test_each_subagent_counts_on_its_own_and_not_against_the_session():
    state: dict = {}
    caps = {"max_tool_calls": 1}
    decide(_pre(), "claude", caps, state)

    assert decide(_pre(agent="a1"), "claude", caps, state) is None
    assert decide(_pre(agent="a2"), "claude", caps, state) is None
    assert decide(_pre(agent="a1"), "claude", caps, state) is not None


def test_a_payload_with_no_prompt_is_not_counted():
    """Cursor runs Claude Code's settings file with its own payloads; a counter that can
    never reset would leave that session unable to act after its first prompt."""
    state: dict = {}
    for _ in range(5):
        assert decide(_pre(prompt=None), "claude", {"max_tool_calls": 1}, state) is None


def _claude_transcript(path: Path, messages) -> Path:
    lines = []
    for mid, usage in messages:
        # One line per content block, each repeating the message's usage.
        for _ in range(2):
            lines.append(json.dumps({"type": "assistant", "message": {"id": mid, "usage": usage}}))
    path.write_text("\n".join(lines) + "\n")
    return path


def test_claude_tokens_are_summed_once_per_message_across_calls(tmp_path):
    usage = {"input_tokens": 10, "cache_creation_input_tokens": 100,
             "cache_read_input_tokens": 1000, "output_tokens": 5}
    transcript = _claude_transcript(tmp_path / "t.jsonl", [("m1", usage)])
    state: dict = {}
    caps = {"max_tokens": 2000}

    assert decide(_batch(transcript_path=str(transcript)), "claude", caps, state) is None
    assert state["tokens"]["total"] == 1115

    with transcript.open("a") as f:
        for _ in range(2):
            f.write(json.dumps({"message": {"id": "m2", "usage": usage}}) + "\n")
    out = decide(_batch(transcript_path=str(transcript)), "claude", caps, state)

    assert state["tokens"]["total"] == 2230
    assert "2,000 tokens" in out["stopReason"]


def test_codex_tokens_are_its_own_running_total(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text("\n".join(json.dumps({"type": "event_msg", "payload": {
        "type": "token_count", "info": {"total_token_usage": {"total_tokens": n}}}})
        for n in (11949, 24013)) + "\n")

    out = decide(_pre(prompt=None, turn_id="t", transcript_path=str(rollout)), "codex",
                 {"max_tokens": 20000}, {})

    assert "24,013 spent" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_tokens_are_not_read_for_a_subagent(tmp_path):
    """Which transcript a subagent's payload names is unmeasured; reading the
    launcher's would charge the session's spend to the subagent."""
    transcript = _claude_transcript(tmp_path / "t.jsonl", [("m1", {"output_tokens": 50})])

    assert decide(_pre(agent="a1", transcript_path=str(transcript)), "claude",
                  {"max_tokens": 10}, {}) is None


def test_the_tool_output_cap_projects_onto_claude_codes_three_variables():
    env = claude_output_env({"max_tool_output_tokens": "5000"})

    assert env == {"BASH_MAX_OUTPUT_LENGTH": "20000", "MAX_MCP_OUTPUT_TOKENS": "5000",
                   "CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS": "5000"}
    assert claude_output_env({"max_tool_output_tokens": "100000"})[
        "BASH_MAX_OUTPUT_LENGTH"] == str(budget.BASH_MAX_OUTPUT_CEILING)


def test_a_claude_pin_carries_the_output_cap_on_its_argv(tmp_path, monkeypatch):
    from thalamus.harness.launcher import launch_argv

    root = _config(tmp_path, sets="max_tool_output_tokens: 1000")
    monkeypatch.setenv("THALAMUS_CONFIG_DIR", str(root))

    argv = launch_argv("claude", "s", persona="thalamus-s", selections={})

    assert argv[0] == "env"
    assert "MAX_MCP_OUTPUT_TOKENS=1000" in argv
    assert argv[argv.index("claude"):][:3] == ["claude", "--agent", "thalamus-s"]


def test_a_pin_with_no_budget_launches_exactly_as_before(tmp_path, monkeypatch):
    from thalamus.harness.launcher import launch_argv

    monkeypatch.setenv("THALAMUS_CONFIG_DIR", str(_config(tmp_path, preset=None)))

    assert launch_argv("claude", "s", persona="thalamus-s", selections={})[0] == "claude"
    assert launch_argv("codex", "s", persona="thalamus-s", selections={})[:2] == [
        "env", "THALAMUS_SCOPE=s"]


def _hook(harness_dir: str, payload: dict, tmp_path: Path, env_extra: dict) -> dict | None:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("THALAMUS_", "CLAUDE_CODE_"))}
    env |= {"HOME": str(tmp_path)} | env_extra
    proc = subprocess.run([str(HOOKS / harness_dir / "budget.sh")],
                          input=json.dumps(payload), capture_output=True, text=True,
                          env=env, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout) if proc.stdout.strip() else None


@pytest.mark.parametrize("harness_dir", ["claude-code", "codex"])
def test_the_hook_denies_the_call_past_the_cap_end_to_end(tmp_path, harness_dir):
    root = _config(tmp_path, sets="max_tool_calls: 1")
    env = {"THALAMUS_CONFIG_DIR": str(root), "THALAMUS_SCOPE": "s"}
    payload = _pre(turn_id="t1") | {"session_id": f"e2e-{harness_dir}"}

    assert _hook(harness_dir, payload, tmp_path, env) is None
    out = _hook(harness_dir, payload, tmp_path, env)

    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert ("continue" in out) == (harness_dir == "claude-code")


def test_the_hook_does_not_start_python_for_a_scope_with_no_budget(tmp_path):
    """The fast path: every tool call runs this hook, so a scope with nothing to count
    must not pay for an interpreter. A config the Python half would refuse proves it
    was never reached."""
    root = _config(tmp_path, preset=None)
    (root / "presets" / "budget.yaml").write_text("broken: [")
    env = {"THALAMUS_CONFIG_DIR": str(root), "THALAMUS_SCOPE": "s"}

    assert _hook("claude-code", _pre(), tmp_path, env) is None
    assert not (tmp_path / ".thalamus" / "logs" / "budget.log").exists()


def test_a_config_the_hook_cannot_read_lets_the_call_through(tmp_path):
    root = _config(tmp_path)
    (root / "presets" / "budget.yaml").write_text("broken: [")
    env = {"THALAMUS_CONFIG_DIR": str(root), "THALAMUS_SCOPE": "s"}

    assert _hook("claude-code", _pre(), tmp_path, env) is None
    assert "not enforced" in (tmp_path / ".thalamus" / "logs" / "budget.log").read_text()
