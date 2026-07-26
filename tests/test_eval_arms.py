"""
Arm-runner tests (docs/04 layer 2 — the execution half).

Interfaces: thalamus.eval.arms — parse_arm, apply_arm, evaluate_acceptance,
evaluate_probes, run_arm, render_run
Infrastructure: throwaway git repos in tmp_path; the headless session is stubbed
(no live model calls in the suite)
Scope: the arm is realized by editing the worktree's harness files and recorded
verbatim; no arm may keep a memory write-back path; unbuilt arms are refused,
never approximated.
"""

import json
import subprocess
from pathlib import Path

import pytest

from thalamus.eval import arms
from thalamus.eval.arms import (
    AgentRun,
    Arm,
    ArmError,
    apply_arm,
    evaluate_acceptance,
    evaluate_probes,
    parse_arm,
    render_run,
    run_arm,
)
from thalamus.eval.tasks import Task

SCOPES = ["main", "literature", "eval-methodology"]


def _task(**overrides) -> Task:
    data = dict(
        id="sample-task",
        title="t",
        overlap="memorization",
        source={"kind": "replayed", "ref": "HEAD", "evidence": "e"},
        prompt="Fix the thing.",
        acceptance=[{"run": "true"}],
        probes=[{"id": "p1", "kind": "transcript_regex", "pattern": "floor",
                 "meaning": "engaged the rationale"}],
    )
    data.update(overrides)
    return Task(**data)


def _settings() -> dict:
    hook = lambda name: {"type": "command", "command": f"$CLAUDE_PROJECT_DIR/hooks/{name}"}
    return {
        "hooks": {
            "SessionStart": [{"hooks": [hook("session-start.sh")]}],
            "SessionEnd": [{"hooks": [hook("session-end.sh")]}],
            "UserPromptSubmit": [
                {"hooks": [hook("timestamp.sh"), hook("conditioning.sh"),
                           hook("pin-engaged.sh")]}
            ],
            "PreToolUse": [{"matcher": "Bash", "hooks": [hook("gremlin-guard.sh")]}],
            "PostToolUse": [
                {"matcher": "mcp__thalamus__.*", "hooks": [hook("post-tool-use.sh")]},
                {"matcher": "Bash", "hooks": [hook("gremlin-tap.sh")]},
            ],
        }
    }


def _worktree(tmp_path: Path) -> Path:
    wt = tmp_path / "wt"
    (wt / ".claude").mkdir(parents=True)
    (wt / ".claude" / "settings.json").write_text(json.dumps(_settings()))
    (wt / ".mcp.json").write_text("{}")
    return wt


def _hook_names(settings: dict) -> set[str]:
    names = set()
    for entries in settings.get("hooks", {}).values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                names.add(Path(hook["command"]).name)
    return names


def test_arm_specs_parse_to_their_surfaces():
    """
    Scenario: The three built arms, parsed

    memory-on keeps the MCP surface and strips only write-back; memory-off
    strips the whole memory surface; scoping-degraded is memory-on under the
    wrong pin.
    """
    on = parse_arm("memory-on", SCOPES)
    off = parse_arm("memory-off", SCOPES)
    degraded = parse_arm("scoping-degraded:literature", SCOPES)

    assert on.mcp and on.scope == "main"
    assert on.strip_hooks == arms.WRITE_BACK_HOOKS
    assert not off.mcp
    assert off.strip_hooks == arms.WRITE_BACK_HOOKS | arms.MEMORY_SURFACE_HOOKS
    assert degraded.mcp and degraded.scope == "literature"
    assert degraded.strip_hooks == arms.WRITE_BACK_HOOKS


def test_unbuilt_and_bogus_arms_are_refused():
    """
    Scenario: The designed-but-unbuilt arms, a fake scope, and a typo

    Refusing beats approximating: a freshness arm without snapshot pinning
    would measure nothing it claims to.
    """
    with pytest.raises(ArmError, match="not built"):
        parse_arm("freshness-degraded", SCOPES)
    with pytest.raises(ArmError, match="not built"):
        parse_arm("volume-degraded:1", SCOPES)
    with pytest.raises(ArmError, match="real non-main expert scope"):
        parse_arm("scoping-degraded:phantom", SCOPES)
    with pytest.raises(ArmError, match="real non-main expert scope"):
        parse_arm("scoping-degraded:main", SCOPES)
    with pytest.raises(ArmError, match="unknown arm"):
        parse_arm("memory-onn", SCOPES)


def test_memory_off_strips_the_whole_surface(tmp_path):
    """
    Scenario: Apply memory-off to a worktree carrying the full hook suite

    Verifications:
    - the MCP config is gone and every memory/write-back hook is stripped
    - the neutral discipline (timestamp, gremlin-guard) survives — stripping it
      would confound the contrast
    - what was stripped is recorded, so the run record shows the arm was real
    """
    wt = _worktree(tmp_path)

    applied = apply_arm(wt, parse_arm("memory-off", SCOPES))

    assert applied["mcp_removed"] is True
    assert not (wt / ".mcp.json").exists()
    remaining = _hook_names(json.loads((wt / ".claude" / "settings.json").read_text()))
    assert remaining == {"timestamp.sh", "gremlin-guard.sh"}
    assert len(applied["stripped_hooks"]) == 6


def test_memory_on_still_strips_write_back(tmp_path):
    """
    Scenario: Apply memory-on

    Memory-on means the READ surface is on. Distillation and the trace taps are
    stripped in every arm: an arm session distilling into the live graph would
    let later arms recall earlier arms' work, and never-distilled tap lines
    would sit in `eval report` as pending forever.
    """
    wt = _worktree(tmp_path)

    applied = apply_arm(wt, parse_arm("memory-on", SCOPES))

    assert applied["mcp_removed"] is False
    assert (wt / ".mcp.json").exists()
    remaining = _hook_names(json.loads((wt / ".claude" / "settings.json").read_text()))
    assert remaining == {"session-start.sh", "timestamp.sh", "conditioning.sh",
                        "pin-engaged.sh", "gremlin-guard.sh"}
    assert sorted(applied["stripped_hooks"]) == [
        "PostToolUse:gremlin-tap.sh",
        "PostToolUse:post-tool-use.sh",
        "SessionEnd:session-end.sh",
    ]


def test_acceptance_and_probes_evaluate_mechanically(tmp_path):
    """
    Scenario: One passing and one failing acceptance; one probe of each kind
    """
    task = _task(
        acceptance=[{"run": "true"}, {"run": "false"}],
        probes=[
            {"id": "t", "kind": "transcript_regex", "pattern": "match floor",
             "meaning": "m1"},
            {"id": "d", "kind": "diff_regex", "pattern": r"re\.escape", "meaning": "m2"},
            {"id": "c", "kind": "command", "run": "test -f marker", "meaning": "m3"},
        ],
    )

    acceptance = evaluate_acceptance(task, tmp_path)
    assert [a["passed"] for a in acceptance] == [True, False]

    (tmp_path / "marker").write_text("")
    probes = evaluate_probes(
        task, transcript="…the match floor survives…", diff="+ re.escape(term)",
        worktree=tmp_path,
    )
    assert [p["hit"] for p in probes] == [True, True, True]

    probes = evaluate_probes(task, transcript="nothing", diff="nothing", worktree=tmp_path)
    assert [p["hit"] for p in probes] == [False, False, True]


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *a: subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
        check=True, capture_output=True,
    )
    run("init", "-q")
    (repo / "README.md").write_text("hello")
    run("add", ".")
    run("commit", "-qm", "seed")
    return repo


def test_prepare_worktree_syncs_current_hooks_over_the_pinned_refs(tmp_path, monkeypatch):
    """
    Scenario: a runner-side hook fix lands after a task's ref was pinned

    The worktree checks out the task's historical ref, which freezes the
    *content* of every file at that ref — including the runner's own hook
    scripts (lab/012's THALAMUS_PROJECT fix landed in the repo but a worktree
    pinned to a pre-fix ref still ran the pre-fix session-start.sh, silently
    reverting it — lab/013). sync_runner_hooks must overwrite the worktree's
    hook scripts with the current repo's, regardless of the pinned ref.
    """
    monkeypatch.setattr(arms, "sync_worktree_env", lambda *a, **k: None)
    repo = _git_repo(tmp_path)
    hooks_dir = repo / arms.HOOKS_REL_PATH
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "session-start.sh").write_text("echo old\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", "pin this ref"],
        check=True, capture_output=True,
    )
    pinned_ref = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    # The fix lands after the ref is pinned — an uncommitted change, exactly
    # like this session's THALAMUS_PROJECT fix before it's committed.
    (hooks_dir / "session-start.sh").write_text("echo fixed\n")

    worktree = tmp_path / "wt"
    arms.prepare_worktree(repo, pinned_ref, worktree)

    assert (worktree / arms.HOOKS_REL_PATH / "session-start.sh").read_text() == "echo fixed\n"


def test_sync_worktree_env_installs_the_dev_extra(tmp_path, monkeypatch):
    """
    Scenario: pytest must exist in the worktree's own venv before anyone runs it

    Root cause (lab/013): pytest lives under `[project.optional-dependencies]
    dev`, not the base dependency list, so a freshly-created worktree venv
    never has it — `uv run pytest` then silently falls through to PATH and
    runs the unrelated system pytest, which can't see anything the worktree
    actually installed. sync_worktree_env must run `uv sync --extra dev` in
    the worktree so this can't happen. A failure must surface as ArmError,
    not a silently-broken later acceptance run.
    """
    captured = {}

    def fake_run(cmd, *, cwd, capture_output, text, timeout):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(arms.subprocess, "run", fake_run)
    arms.sync_worktree_env(tmp_path)

    assert captured["cmd"] == ["uv", "sync", "--extra", "dev"]
    assert captured["cwd"] == tmp_path


def test_sync_worktree_env_raises_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        arms.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess([], 1, stdout="", stderr="resolution failed"),
    )
    with pytest.raises(ArmError, match="resolution failed"):
        arms.sync_worktree_env(tmp_path)


def test_run_arm_records_and_cleans_up(tmp_path, monkeypatch):
    """
    Scenario: A full orchestrated run with the headless session stubbed

    Verifications:
    - a JSONL record lands with the arm application, oracle verdicts, and agent
      accounting; NOT ACCEPTED is honest (the stub solved nothing)
    - the worktree is removed after the run (kept only on request)
    """
    repo = _git_repo(tmp_path)
    task = _task(acceptance=[{"run": "test -f README.md"}, {"run": "grep -q hello README.md"}])
    monkeypatch.setattr(arms, "sync_worktree_env", lambda *a, **k: None)
    monkeypatch.setattr(
        arms, "run_agent",
        lambda *a, **k: AgentRun("sess-1", "done", 0.12, 3000, 5, False),
    )
    monkeypatch.setattr(arms, "transcript_text", lambda *a, **k: "match floor talk")

    record = run_arm(
        repo, task, parse_arm("memory-off", SCOPES),
        runs_base=tmp_path / "runs", order_index=1,
    )

    lines = (tmp_path / "runs" / "runs.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["task"] == "sample-task"
    assert record["accepted"] is True
    assert record["probes"][0]["hit"] is True
    assert record["agent"]["num_turns"] == 5
    assert record["turn_capped"] is False
    assert record["applied"]["stripped_hooks"] == []  # bare fixture repo: no hooks to strip
    assert record["order_index"] == 1
    assert not Path(record["worktree"]).exists()
    assert "ACCEPTED" in render_run(record)


def test_run_arm_keeps_worktree_on_request(tmp_path, monkeypatch):
    """
    Scenario: --keep for post-run inspection
    """
    repo = _git_repo(tmp_path)
    task = _task()
    monkeypatch.setattr(arms, "sync_worktree_env", lambda *a, **k: None)
    monkeypatch.setattr(
        arms, "run_agent", lambda *a, **k: AgentRun("sess-2", "", 0.0, 0, 1, False)
    )
    monkeypatch.setattr(arms, "transcript_text", lambda *a, **k: "")

    record = run_arm(
        repo, task, parse_arm("memory-off", SCOPES),
        runs_base=tmp_path / "runs", keep=True,
    )

    assert Path(record["worktree"]).exists()
    assert record["kept"] is True
    assert record["transcript_captured"] is False


def test_run_arm_passes_repos_name_as_project(tmp_path, monkeypatch):
    """
    Scenario: run_arm must tell the arm session its real project

    session-start.sh resolves recall's project from basename(cwd), which
    inside a worktree is the disposable run directory, not the repo — the
    session-start pull silently found nothing in every arm run to date
    (lab/012). run_arm must pass the checkout's own name so run_agent can
    override that resolution.
    """
    repo = _git_repo(tmp_path)
    task = _task()
    captured = {}

    def fake_run_agent(*args, **kwargs):
        captured.update(kwargs)
        return AgentRun("sess-3", "", 0.0, 0, 1, False)

    monkeypatch.setattr(arms, "sync_worktree_env", lambda *a, **k: None)
    monkeypatch.setattr(arms, "run_agent", fake_run_agent)
    monkeypatch.setattr(arms, "transcript_text", lambda *a, **k: "")

    run_arm(repo, task, parse_arm("memory-on", SCOPES), runs_base=tmp_path / "runs")

    assert captured["project"] == repo.name == "repo"


def test_run_agent_threads_scope_and_project_into_the_subprocess_env(tmp_path, monkeypatch):
    """
    Scenario: run_agent's env must carry THALAMUS_PROJECT alongside THALAMUS_SCOPE

    Low-level counterpart to the run_arm test above: this is the layer that
    actually builds the subprocess env session-start.sh reads.
    """
    captured = {}

    def fake_run(cmd, *, input, capture_output, text, timeout, cwd, env):
        captured["env"] = env
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"session_id": "s", "total_cost_usd": 0}), stderr="",
        )

    monkeypatch.setattr(arms.subprocess, "run", fake_run)

    arms.run_agent(tmp_path, "prompt", scope="literature", project="thalamus")

    assert captured["env"]["THALAMUS_SCOPE"] == "literature"
    assert captured["env"]["THALAMUS_PROJECT"] == "thalamus"
