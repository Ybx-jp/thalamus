"""The session preflight (#395 autonomous, blocking; #396 attended, reporting).

Each check is held against a fixture that makes it pass and one that makes it fail,
and the hook is run end to end as Claude Code runs it: an autonomous session that is
not armed is stopped at its first tool call and every later one, and an attended
session is told and carries on.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from thalamus.harness import preflight
from thalamus.substrate.schema import SessionType

HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks" / "claude-code"
ROLE_GUARD = HOOKS / "role-guard.sh"
BUDGET = HOOKS / "budget.sh"


def _transcript(path: Path, *records: dict) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return path


def _delta(added=(), failed=(), pending=()):
    return {"type": "attachment", "attachment": {
        "type": "deferred_tools_delta", "addedNames": list(added), "readdedNames": [],
        "removedNames": [], "failedMcpServers": list(failed),
        "pendingMcpServers": list(pending)}}


def _shape(*tools):
    return {"type": "api-request-shape", "shape": {"tools": [{"name": t} for t in tools]}}


# ---------------------------------------------------------------------------
# Tool surface


def test_the_surface_is_read_from_deltas_and_request_shapes(tmp_path):
    """A narrowed run (`--tools`) writes no delta, only the request shape; an
    interactive one defers its MCP tools and lists them in a delta. Either counts."""
    t = _transcript(tmp_path / "t.jsonl",
                    _delta(["mcp__thalamus__memory_recall"]),
                    _shape("Bash", "mcp__penpot__create_shape"))
    surface = preflight.observed_surface(t)
    assert {"mcp__thalamus__memory_recall", "mcp__penpot__create_shape", "Bash"} <= surface.tools


def test_a_transcript_with_no_record_is_unknown_not_empty(tmp_path):
    t = _transcript(tmp_path / "t.jsonl", {"type": "user", "message": {"content": "hi"}})
    assert preflight.observed_surface(t) is None
    check = preflight.check_tool_surface(t, ["thalamus"])
    assert check.ok is None


def test_a_missing_server_fails_and_says_why(tmp_path):
    t = _transcript(tmp_path / "t.jsonl",
                    _delta(["mcp__claude_ai_Gmail__search"], failed=["penpot"]))
    check = preflight.check_tool_surface(t, ["thalamus", "penpot", "claude.ai Gmail"])
    assert check.ok is False
    assert "thalamus" in check.detail and "penpot (failed to connect)" in check.detail
    assert "Gmail" not in check.detail


def test_required_tools_follow_the_session_type(monkeypatch):
    monkeypatch.setattr(preflight.pin, "scope_mcp_servers", lambda scope, base=None: {})
    assert preflight.required_tools("main", SessionType.ATTENDED, {}) == ["thalamus"]
    # An autonomous job needs only what it declares.
    assert preflight.required_tools("main", SessionType.AUTONOMOUS, {}) == []
    assert preflight.required_tools(
        "main", SessionType.AUTONOMOUS, {"THALAMUS_PREFLIGHT_REQUIRES": "WebSearch, thalamus"}
    ) == ["WebSearch", "thalamus"]


# ---------------------------------------------------------------------------
# Settings files and hooks


def _settings(path: Path, hooks: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": hooks}))
    return path


def _wire(*entries):
    """{event: [(matcher, command)]} -> a settings `hooks` block."""
    out: dict = {}
    for event, matcher, command in entries:
        group = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            group["matcher"] = matcher
        out.setdefault(event, []).append(group)
    return out


def test_settings_sources_follow_the_launcher(tmp_path):
    home, project = tmp_path / "home", tmp_path / "project"
    _settings(home / ".claude" / "settings.json", {})
    _settings(project / ".claude" / "settings.json", {})
    env = {"HOME": str(home)}
    assert len(preflight.settings_files(env, str(project))) == 2
    only = preflight.settings_files({**env, "THALAMUS_SETTING_SOURCES": "project"}, str(project))
    assert only == [project / ".claude" / "settings.json"]


def test_a_hook_whose_script_is_gone_is_reported(tmp_path):
    """The case measured on this box: hooks wired at a path a refactor moved fail with
    exit 127 on every call, as a non-blocking error nobody reads."""
    present = tmp_path / "present.sh"
    present.write_text("#!/bin/sh\n")
    present.chmod(0o755)
    settings = _settings(tmp_path / ".claude" / "settings.json", _wire(
        ("PostToolUse", None, str(tmp_path / "gone.sh")),
        ("PreToolUse", None, "$CLAUDE_PROJECT_DIR/present.sh"),
        ("PreToolUse", None, "uv run thalamus something"),
    ))
    wired = preflight.wired_hooks([settings])
    check = preflight.check_hooks_runnable(wired, {}, str(tmp_path))
    assert check.ok is False and "gone.sh" in check.detail and "present.sh" not in check.detail


# ---------------------------------------------------------------------------
# Guards


@pytest.fixture
def config(tmp_path, monkeypatch):
    root = tmp_path / "config"
    (root / "experts").mkdir(parents=True)
    (root / "ownership.json").write_text(json.dumps({"oracle": {
        "glob": "*/tests/qe/*", "owner": "qe", "reason": "the oracle"}}))
    monkeypatch.setenv("THALAMUS_CONFIG_DIR", str(root))
    return root


def test_the_guard_is_armed_when_wired_and_it_denies_the_probe(tmp_path, config):
    settings = _settings(tmp_path / "s.json", _wire(
        ("PreToolUse", "Edit|Write|NotebookEdit|Skill|Artifact", str(ROLE_GUARD))))
    check = preflight.check_guards("main", preflight.wired_hooks([settings]), {}, "", config)
    assert check.ok is True, check.detail


def test_an_unwired_guard_fails(tmp_path, config):
    settings = _settings(tmp_path / "s.json", _wire(("PreToolUse", "Bash", str(ROLE_GUARD))))
    check = preflight.check_guards("main", preflight.wired_hooks([settings]), {}, "", config)
    assert check.ok is False and "not enforced" in check.detail


def test_a_wired_guard_that_allows_the_probe_fails(tmp_path, config):
    permissive = tmp_path / "role-guard.sh"
    permissive.write_text("#!/bin/sh\ncat >/dev/null\nexit 0\n")
    permissive.chmod(0o755)
    settings = _settings(tmp_path / "s.json", _wire(("PreToolUse", None, str(permissive))))
    check = preflight.check_guards("main", preflight.wired_hooks([settings]), {}, "", config)
    assert check.ok is False and "did not deny" in check.detail


def test_the_owner_has_nothing_to_probe(config):
    check = preflight.check_guards("qe", [], {}, "", config)
    assert check.ok is True


# ---------------------------------------------------------------------------
# Budget


def test_a_job_that_names_no_preset_promises_nothing(config):
    assert preflight.check_budget("main", [], {}, config).ok is True


def test_a_cap_needs_the_hook_that_enforces_it(tmp_path, config):
    env = {"THALAMUS_MAX_TOOL_CALLS": "30"}
    check = preflight.check_budget("main", [], env, config)
    assert check.ok is False and "budget.sh" in check.detail
    settings = _settings(tmp_path / "s.json", _wire(("PreToolUse", None, str(BUDGET))))
    check = preflight.check_budget("main", preflight.wired_hooks([settings]), env, config)
    assert check.ok is True


def test_the_named_preset_must_be_what_is_enforced(tmp_path, config):
    (config / "presets").mkdir()
    (config / "presets" / "budget.yaml").write_text("weekly:\n  max_tool_calls: 60\n")
    settings = preflight.wired_hooks([_settings(
        tmp_path / "s.json", _wire(("PreToolUse", None, str(BUDGET))))])
    env = {"THALAMUS_BUDGET_PRESET": "weekly", "THALAMUS_MAX_TOOL_CALLS": "30"}
    check = preflight.check_budget("main", settings, env, config)
    assert check.ok is False and "promises" in check.detail
    env["THALAMUS_MAX_TOOL_CALLS"] = "60"
    assert preflight.check_budget("main", settings, env, config).ok


# ---------------------------------------------------------------------------
# The write path


def test_the_write_path_is_read_as_extract_reads_it(tmp_path):
    pins = tmp_path / "pins.jsonl"
    assert preflight.check_write_path("s1", SessionType.AUTONOMOUS, pins).ok is False
    pins.write_text(json.dumps({"session_id": "s1", "entrypoint": "sdk-cli"}) + "\n")
    ok = preflight.check_write_path("s1", SessionType.AUTONOMOUS, pins)
    assert ok.ok is True and "tier 2" in ok.detail
    wrong = preflight.check_write_path("s1", SessionType.ATTENDED, pins)
    assert wrong.ok is False and "autonomous" in wrong.detail


# ---------------------------------------------------------------------------
# What a failure does


def _report(session_type, ok):
    return preflight.Report("s1", "main", session_type.value,
                            [preflight.Check("budget", ok, "detail")])


def test_an_autonomous_failure_denies_and_stops():
    out = preflight.hook_output(_report(SessionType.AUTONOMOUS, False))
    assert out["continue"] is False
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_an_autonomous_session_fails_closed_on_what_it_could_not_check():
    assert not _report(SessionType.AUTONOMOUS, None).passed
    assert _report(SessionType.ATTENDED, None).passed


def test_a_broken_hook_is_told_to_an_attended_session_and_stops_no_autonomous_one():
    broken = preflight.Check("hooks runnable", False, "gone.sh", advisory=True)
    autonomous = preflight.Report("s1", "main", "autonomous", [broken])
    assert autonomous.passed and preflight.hook_output(autonomous) == {}
    attended = preflight.Report("s1", "main", "attended", [broken])
    assert "gone.sh" in preflight.hook_output(attended)["hookSpecificOutput"]["additionalContext"]


def test_an_attended_failure_is_told_and_proceeds():
    out = preflight.hook_output(_report(SessionType.ATTENDED, False))
    assert "continue" not in out
    assert "PREFLIGHT" in out["hookSpecificOutput"]["additionalContext"]
    assert preflight.hook_output(_report(SessionType.ATTENDED, True)) == {}


# ---------------------------------------------------------------------------
# The hook, end to end


def _hook(tmp_path, home, env, session_id="s-hook"):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    uv = bin_dir / "uv"
    # `uv run --project <checkout> thalamus ...` -> this interpreter's thalamus.
    uv.write_text(f'#!/bin/bash\nshift 3\nshift\nexec "{sys.executable}" -m thalamus "$@"\n')
    uv.chmod(0o755)
    payload = {"session_id": session_id, "transcript_path": str(tmp_path / "none.jsonl"),
               "cwd": str(tmp_path), "hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": "ls"}}
    return subprocess.run(
        [str(HOOKS / "preflight.sh")], input=json.dumps(payload), capture_output=True,
        text=True, timeout=120,
        env={"HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin", **env},
    )


def test_an_unarmed_autonomous_run_is_stopped_at_every_call(tmp_path, config):
    home = tmp_path / "home"
    home.mkdir()
    env = {"CLAUDE_CODE_ENTRYPOINT": "sdk-cli", "THALAMUS_CONFIG_DIR": str(config),
           "THALAMUS_SETTING_SOURCES": "project"}
    first = _hook(tmp_path, home, env)
    out = json.loads(first.stdout)
    assert out["continue"] is False and "write path" in out["stopReason"]
    recorded = json.loads((home / ".thalamus" / "preflight" / "s-hook.json").read_text())
    assert recorded["passed"] is False and recorded["session_type"] == "autonomous"
    # Later calls read the recorded result rather than checking again.
    again = json.loads(_hook(tmp_path, home, env).stdout)
    assert again["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_an_attended_session_is_told_once_and_proceeds(tmp_path, config):
    home = tmp_path / "home"
    home.mkdir()
    env = {"CLAUDE_CODE_ENTRYPOINT": "cli", "THALAMUS_CONFIG_DIR": str(config),
           "THALAMUS_SETTING_SOURCES": "project"}
    first = json.loads(_hook(tmp_path, home, env).stdout)
    assert "PREFLIGHT" in first["hookSpecificOutput"]["additionalContext"]
    assert _hook(tmp_path, home, env).stdout.strip() == ""
