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
    def hook(name):
        return {"type": "command", "command": f"$CLAUDE_PROJECT_DIR/hooks/{name}"}

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
    def run(*a):
        return subprocess.run(
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


# ---------------------------------------------------------------------------
# Infra-fault classification (lab/012-013; arXiv 2111.03382, 2605.05564)
# ---------------------------------------------------------------------------
#
# The failure texts below are verbatim shapes from ~/.thalamus/counterfactuals/
# runs.jsonl and the lab/013 write-up, not invented strings — a classifier
# tested only against strings its author imagined is green and ungrounded.

AUTH_TAIL = "Failed to authenticate: OAuth session expired and could not be refreshed"
LIMIT_TAIL = "You've hit your session limit · resets 3:50pm (America/Los_Angeles)"
COLLECTION_TAIL = (
    "ImportError while importing test module '/w/tests/test_reader.py'.\n"
    "ModuleNotFoundError: No module named 'gremlin_python'\n"
    "!!!!!! Interrupted: 22 errors during collection !!!!!!"
)


class TestInfraFaultClassification:
    def test_missing_third_party_dependency_is_infra(self):
        """The lab/013 fault: a dep the candidate's diff cannot have removed."""
        assert arms.classify_infra_fault(COLLECTION_TAIL, 2) == "missing_dependency"

    def test_missing_first_party_submodule_is_a_candidate_defect(self):
        """
        A candidate that deletes or renames thalamus/reader.py genuinely
        breaks `thalamus.reader`. Calling that infra would excuse a real
        defect — the exact error the classification must not make.
        """
        tail = "ModuleNotFoundError: No module named 'thalamus.reader'"
        assert arms.classify_infra_fault(tail, 1) is None

    def test_missing_top_level_thalamus_package_is_infra(self):
        """
        `No module named 'thalamus'` is the un-synced-venv symptom
        (sync_worktree_env's docstring): the package is installed by the
        worktree sync, not authored by the candidate.
        """
        tail = "ModuleNotFoundError: No module named 'thalamus'"
        assert arms.classify_infra_fault(tail, 2) == "missing_dependency"

    def test_ordinary_test_failure_is_not_reclassified(self):
        """Conservative by construction: unrecognized failure = candidate defect."""
        tail = "FAILED tests/test_reader.py::test_case_insensitive - assert 0 == 3\n1 failed"
        assert arms.classify_infra_fault(tail, 1) is None

    def test_command_not_found_is_infra(self):
        assert arms.classify_infra_fault("uv: command not found", 127) == "command_not_found"

    def test_session_fault_shapes_are_distinguished(self):
        """
        lab/012 had to separate these by hand from the raw transcripts.
        A closing-turn death leaves a real worktree the oracles can grade; a
        pre-work death leaves nothing (1 turn, $0.00); an interruption
        mid-attempt leaves a half-finished one (lab/016).
        """
        void = AgentRun("s", AUTH_TAIL, 0.0, 130, 1, True)
        worked = AgentRun("s", AUTH_TAIL, 0.91, 197000, 33, True)
        capped = AgentRun("s", "", 1.67, 200000, 41, True)
        assert arms.classify_session_fault(void) == "session_fault_void"
        assert arms.classify_session_fault(worked) == "session_fault_interrupted"
        # is_error alone is NOT a session-death signal — every capped run has it.
        assert arms.classify_session_fault(capped) is None

    def test_session_limit_is_caught_not_just_auth_expiry(self):
        """
        lab/016: the guard matched only lab/012's observed auth string, so
        `You've hit your session limit` walked past it and 16 arms were
        recorded as $0.00 candidate failures. Match the class, not the phrasing.
        """
        void = AgentRun("s", LIMIT_TAIL, 0.0, 90, 1, True)
        interrupted = AgentRun("s", LIMIT_TAIL, 2.62, 180000, 18, True)
        assert arms.classify_session_fault(void) == "session_fault_void"
        assert arms.classify_session_fault(interrupted) == "session_fault_interrupted"

    def test_a_session_that_did_nothing_is_void_whatever_it_printed(self):
        """
        The first confined arm died with `Not logged in · Please run /login` —
        an auth failure by any reading, but not the phrase the marker list
        carried. The gate returned None and an untouched worktree was graded
        RUNG 1: a verdict manufactured out of thin air, which is the one thing
        this classifier exists to prevent (lab/016).

        `void` is therefore decided on behavior, not vocabulary. No marker list
        can enumerate every way a session fails to start, but "errored, took no
        turn, spent nothing" describes all of them.
        """
        unknown = AgentRun("s", "Not logged in · Please run /login", 0.0, 69, 1, True)
        assert arms.classify_session_fault(unknown) == "session_fault_void"

        never_seen = AgentRun("s", "sandbox: exec format error", 0.0, 12, 1, True)
        assert arms.classify_session_fault(never_seen) == "session_fault_void"

    def test_behavioral_void_cannot_resurrect_the_healthy_arm_false_positive(self):
        """
        lab/020 stamped a healthy 49-turn arm void because its own summary
        used the marker vocabulary. The behavioral test must not reopen that:
        an arm that did work is never void, and a concluded arm is never a
        dead session at all.
        """
        healthy_prose = AgentRun("s", "I broadened markers to session/quota", 3.4,
                                 210000, 49, False)
        assert arms.classify_session_fault(healthy_prose) is None

        errored_but_worked = AgentRun("s", LIMIT_TAIL, 2.62, 180000, 18, True)
        assert arms.classify_session_fault(errored_but_worked) == "session_fault_interrupted"

    def test_acceptance_stamps_the_fault_but_keeps_the_verdict(self, tmp_path):
        """
        Flag, never exclude (arXiv 2111.03382/2605.05564): `passed` stays
        exactly as measured; the fault rides alongside it.
        """
        task = _task(acceptance=[{"run": f"echo \"{COLLECTION_TAIL}\" >&2; exit 2"}])
        results = evaluate_acceptance(task, tmp_path)
        assert results[0]["passed"] is False
        assert results[0]["infra_fault"] == "missing_dependency"

    def test_passing_command_is_never_an_infra_fault(self, tmp_path):
        """A command that prints the words but exits 0 is still a pass."""
        task = _task(acceptance=[{"run": "echo 'No module named X'; exit 0"}])
        results = evaluate_acceptance(task, tmp_path)
        assert results[0]["passed"] is True
        assert results[0]["infra_fault"] is None


class TestRunArmFaultStamping:
    def _stub(self, monkeypatch, agent):
        monkeypatch.setattr(arms, "sync_worktree_env", lambda *a, **k: None)
        monkeypatch.setattr(arms, "run_agent", lambda *a, **k: agent)
        monkeypatch.setattr(arms, "transcript_text", lambda *a, **k: "")

    def test_infra_faulted_run_is_recorded_as_not_attributable(self, tmp_path, monkeypatch):
        repo = _git_repo(tmp_path)
        task = _task(acceptance=[{"run": f"echo \"{COLLECTION_TAIL}\" >&2; exit 2"}])
        self._stub(monkeypatch, AgentRun("s1", "done", 0.1, 3000, 5, False))

        record = run_arm(repo, task, parse_arm("memory-off", SCOPES),
                         runs_base=tmp_path / "runs")

        assert record["accepted"] is False
        assert record["attributable"] is False
        assert record["infra_faults"] == ["missing_dependency"]
        rendered = render_run(record)
        assert "INFRA-FAULT[missing_dependency]" in rendered
        assert "NOT attributable to the candidate" in rendered

    def test_clean_run_is_attributable(self, tmp_path, monkeypatch):
        repo = _git_repo(tmp_path)
        self._stub(monkeypatch, AgentRun("s2", "done", 0.1, 3000, 5, False))

        record = run_arm(repo, _task(), parse_arm("memory-off", SCOPES),
                         runs_base=tmp_path / "runs")

        assert record["attributable"] is True
        assert record["infra_faults"] == []
        assert "INFRA FAULT" not in render_run(record)

    def test_session_death_before_any_work_voids_the_record_and_stops(self, tmp_path, monkeypatch):
        """
        lab/012's void arms: 1 turn, $0.00. The runner must refuse to grade an
        untouched worktree and must raise SessionFault so the campaign halts
        rather than launching the next arm against dead credentials.
        """
        repo = _git_repo(tmp_path)
        self._stub(monkeypatch, AgentRun("s3", AUTH_TAIL, 0.0, 130, 1, True))

        with pytest.raises(arms.SessionFault):
            run_arm(repo, _task(), parse_arm("memory-off", SCOPES),
                    runs_base=tmp_path / "runs")

        # The record still lands — a stopped campaign must leave evidence.
        record = json.loads((tmp_path / "runs" / "runs.jsonl").read_text().strip())
        assert record["void"] is True
        assert record["infra_fault"] == "session_fault_void"
        assert record["attributable"] is False
        assert "acceptance" not in record
        assert "VOID" in render_run(record)

    def test_session_death_after_real_work_is_void_and_ungraded(self, tmp_path, monkeypatch):
        """
        lab/016's fable arms: killed at turns 11 and 18 of 40 by a session
        limit, and recorded as `attributable: true, accepted: false` — a
        trustworthy-looking candidate defect that was nothing of the kind.
        An attempt of unknown completeness must not be graded at all.
        """
        repo = _git_repo(tmp_path)
        self._stub(monkeypatch, AgentRun("s4", LIMIT_TAIL, 2.62, 180000, 18, True))

        with pytest.raises(arms.SessionFault):
            run_arm(repo, _task(), parse_arm("memory-off", SCOPES),
                    runs_base=tmp_path / "runs")

        record = json.loads((tmp_path / "runs" / "runs.jsonl").read_text().strip())
        assert record["void"] is True
        assert record["infra_fault"] == "session_fault_interrupted"
        assert record["attributable"] is False
        # The trap: no verdict at all, rather than a verdict nobody should read.
        assert "acceptance" not in record
        assert "accepted" not in record


class TestTurnCapDetection:
    """
    lab/015: `num_turns > max_turns` marked *completed* opus runs as censored.
    The shapes below are the measured ones from runs.jsonl, not invented.
    """

    def _run(self, tmp_path, monkeypatch, agent, max_turns=40):
        repo = _git_repo(tmp_path)
        monkeypatch.setattr(arms, "sync_worktree_env", lambda *a, **k: None)
        monkeypatch.setattr(arms, "run_agent", lambda *a, **k: agent)
        monkeypatch.setattr(arms, "transcript_text", lambda *a, **k: "")
        return run_arm(repo, _task(), parse_arm("memory-off", SCOPES),
                       runs_base=tmp_path / "runs", max_turns=max_turns)

    def test_genuine_cap_is_flagged(self, tmp_path, monkeypatch):
        """Sonnet's shape: max+1 turns, errored, no closing summary."""
        agent = AgentRun("s", "", 1.16, 198000, 41, True)
        assert self._run(tmp_path, monkeypatch, agent)["turn_capped"] is True

    def test_run_that_exceeded_the_cap_but_concluded_is_not_capped(self, tmp_path, monkeypatch):
        """
        Opus's shape: 53 reported turns against --max-turns 40, is_error=False,
        and a real closing summary. It concluded; its metrics are not censored.
        """
        agent = AgentRun("s", "…say the word and I'll fold that one too.", 2.12, 311000, 53, False)
        assert self._run(tmp_path, monkeypatch, agent)["turn_capped"] is False

    def test_short_clean_run_is_not_capped(self, tmp_path, monkeypatch):
        agent = AgentRun("s", "done", 1.32, 262000, 22, False)
        assert self._run(tmp_path, monkeypatch, agent)["turn_capped"] is False


class TestRecallCallCounting:
    def _transcript(self, *names):
        lines = []
        for name in names:
            lines.append(json.dumps({
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": name, "input": {}}]},
            }))
        # Noise the counter must survive: a non-tool line and a malformed one.
        lines.append(json.dumps({"type": "user", "message": {"content": "hi"}}))
        lines.append("{not json")
        return "\n".join(lines)

    def test_counts_thalamus_and_toolsearch_separately(self):
        counts = arms.count_recall_calls(self._transcript(
            "ToolSearch", "mcp__thalamus__memory_open_threads", "Bash", "Read",
        ))
        assert counts == {"thalamus": 1, "tool_search": 1}

    def test_arm_that_never_reached_for_memory(self):
        """The reader/memory-on shape under sonnet and fable: zero of both."""
        counts = arms.count_recall_calls(self._transcript("Bash", "Read", "Edit"))
        assert counts == {"thalamus": 0, "tool_search": 0}

    def test_empty_transcript_is_zero_not_an_error(self):
        assert arms.count_recall_calls("") == {"thalamus": 0, "tool_search": 0}


class TestWorktreeEscapeDetection:
    """The lab/020 leak, mechanised.

    Two memory-off arms read the operator's live task file by absolute path and
    scored at or above the gate's pre-registered memory-off ceiling. The shapes
    below are those arms' shapes, not invented ones.
    """

    # Synthetic roots. Detection compares prefixes, so the only thing that has
    # to be real is the *shape*: an arm worktree named task--arm--id, and a
    # checkout it must never reach into.
    REPO = Path("/repo/thalamus")
    WORKTREE = Path("/wt/task--memory-off--x")

    def _transcript(self, *calls):
        lines = []
        for name, tool_input in calls:
            lines.append(json.dumps({
                "type": "assistant",
                "message": {"content": [
                    {"type": "tool_use", "name": name, "input": tool_input},
                ]},
            }))
        lines.append(json.dumps({"type": "user", "message": {"content": "hi"}}))
        lines.append("{not json")
        return "\n".join(lines)

    def _detect(self, transcript):
        return arms.detect_worktree_escape(transcript, self.WORKTREE, self.REPO)

    def test_reading_the_task_file_is_an_answer_key_escape(self):
        escapes = self._detect(self._transcript(
            ("Read", {"file_path": str(
                self.REPO / "config/tasks/arm-runner-session-death-classification.yaml")}),
        ))
        assert len(escapes) == 1
        assert escapes[0]["kind"] == "answer_key"
        assert escapes[0]["tool"] == "Read"
        assert escapes[0]["path"].startswith("config/tasks/")

    def test_other_reads_of_the_live_checkout_are_the_weaker_class(self):
        escapes = self._detect(self._transcript(
            ("Read", {"file_path": str(self.REPO / "lab/019-x.md")}),
        ))
        assert [e["kind"] for e in escapes] == ["operator_repo"]

    def test_work_inside_the_worktree_is_not_an_escape(self):
        """The overwhelmingly common case: an arm that stayed home."""
        escapes = self._detect(self._transcript(
            ("Read", {"file_path": str(self.WORKTREE / "src/thalamus/eval/arms.py")}),
            ("Edit", {"file_path": str(self.WORKTREE / "src/thalamus/eval/arms.py")}),
            ("Bash", {"command": "uv run pytest -q"}),
        ))
        assert escapes == []

    def test_relative_paths_resolve_in_the_worktree_and_do_not_fire(self):
        """`ls config/tasks/` runs with cwd=worktree, where the file does not
        exist at the task's ref. Only the absolute-path read is the leak."""
        assert self._detect(self._transcript(
            ("Bash", {"command": "ls config/tasks/"}),
        )) == []

    def test_bash_reads_of_the_answer_key_are_caught_too(self):
        escapes = self._detect(self._transcript(
            ("Bash", {"command": f"cat {self.REPO}/config/tasks/t.yaml"}),
        ))
        assert [e["kind"] for e in escapes] == ["answer_key"]

    def test_repeated_reads_collapse_to_one_finding(self):
        path = str(self.REPO / "config/tasks/t.yaml")
        escapes = self._detect(self._transcript(
            ("Read", {"file_path": path}), ("Read", {"file_path": path}),
        ))
        assert len(escapes) == 1

    def test_empty_transcript_is_clean_not_an_error(self):
        assert self._detect("") == []

    def test_a_file_the_fix_touched_is_the_answer_key_in_code_form(self):
        """The third lab/020 escape, which the write-up did not report: an arm
        ran the live `arms.py`, which at HEAD already carries the fix."""
        transcript = self._transcript(
            ("Bash", {"command":
                f"grep -n classify {self.REPO}/src/thalamus/eval/arms.py"}),
        )
        weak = arms.detect_worktree_escape(transcript, self.WORKTREE, self.REPO)
        assert [e["kind"] for e in weak] == ["operator_repo"]

        strong = arms.detect_worktree_escape(
            transcript, self.WORKTREE, self.REPO,
            frozenset({"src/thalamus/eval/arms.py"}),
        )
        assert [e["kind"] for e in strong] == ["answer_key"]

    def test_a_task_with_no_fix_ref_has_no_such_set(self, tmp_path):
        """`authored` tasks have no historical fix to leak."""
        assert arms.fix_touched_paths(tmp_path, "abc123", "") == frozenset()
        assert arms.fix_touched_paths(tmp_path, "", "def456") == frozenset()


class TestHistoryReachDetection:
    """The leak filesystem confinement cannot close.

    Every command below is a real one, lifted from `runs.jsonl` transcripts.
    """

    REF, FIX = "1fc6aef", "4432703"

    def _t(self, *commands):
        return "\n".join(json.dumps({
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": c}},
            ]},
        }) for c in commands)

    def _reach(self, *commands):
        return arms.detect_history_reach(self._t(*commands), self.REF, self.FIX)

    def test_the_answer_key_sweep_across_every_commit(self):
        """The worst measured case: a grep for the task's own id over all revs."""
        hits = self._reach(
            'git grep -l "arm-runner-session-death-classification" $(git rev-list --all)'
        )
        assert hits and hits[0]["kind"] == "history_reach"
        assert "rev-list --all" in hits[0]["path"]

    def test_showing_the_tasks_own_fix_is_the_answer_key(self):
        hits = arms.detect_history_reach(
            self._t("git show 8b70330 -- tests/test_reader.py"),
            "9f28895", "8b70330",
        )
        assert [h["kind"] for h in hits] == ["answer_key"]

    def test_log_all_and_named_branches_are_reaches(self):
        assert self._reach("git log --all --oneline")
        assert self._reach("git log origin/master --oneline -3")
        assert self._reach("git diff master --stat 2>/dev/null")

    def test_naming_its_own_pinned_ref_is_not_a_reach(self):
        """Measured twice: `git show <source.ref> --stat`. The arm is entitled
        to inspect the commit it was handed."""
        assert self._reach("git show 1fc6aef --stat") == []
        assert self._reach("git show 1fc6aef -- docs/04-eval-loop.md") == []

    def test_ordinary_work_in_the_checkout_is_not_a_reach(self):
        assert self._reach("git diff", "git status", "git log --oneline -5",
                           "uv run pytest -q") == []

    def test_empty_transcript_is_clean(self):
        assert arms.detect_history_reach("", self.REF, self.FIX) == []


class TestSelfLeakingTaskRefusal:
    def test_a_task_whose_battery_file_predates_its_ref_is_refused(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "config" / "tasks").mkdir(parents=True)
        (repo / "config" / "tasks" / "leaky.yaml").write_text("task: 1\n")
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                        "-c", "user.name=t", "commit", "-qm", "x"], check=True)
        with pytest.raises(arms.ArmError, match="ships its own answer key"):
            arms.refuse_self_leaking_task(repo, "HEAD", "leaky")
        # A task with no battery file at that ref is fine.
        arms.refuse_self_leaking_task(repo, "HEAD", "not-yet-authored")


class TestSandboxConfinement:
    """Properties verified live against the built image before these were written."""

    REPO = Path("/repo/thalamus")
    WT = Path("/wt/t--memory-on--x")
    HOME = Path("/wt/t--memory-on--x--home")

    def _argv(self, **kw):
        return arms.sandbox_argv(self.WT, self.HOME, **kw)

    def test_the_operators_checkout_is_never_mounted(self):
        """The whole point: the paths lab/020's arms read must not exist."""
        mounts = [a for a in self._argv() if ":" in a and a.count("/") > 1]
        assert not any(str(self.REPO) in m for m in mounts)

    def test_the_arm_checkout_and_home_are_mounted(self):
        argv = self._argv()
        assert f"{self.WT}:{self.WT}" in argv
        assert f"{self.HOME}:{self.HOME}" in argv

    def test_network_host_for_memory_on_bridge_for_isolated_memory_off(self):
        assert self._argv(network="host")[self._argv().index("--network") + 1] == "host"
        assert "bridge" in self._argv(network="bridge")

    def test_store_isolation_never_selects_none(self):
        """`none` isolates the store and the model API together, so the arm dies
        on turn 1 with `Unable to connect to API` and halts the campaign — the
        measured outcome of the first 24-arm attempt. `bridge` leaves the graph
        unreachable on both the container loopback and the gateway, since the
        server binds loopback-only, while the API still answers."""
        def chosen(arm_mcp, sandbox=True, isolate=True):
            # The selection in run_one_arm, verbatim.
            return "bridge" if (sandbox and isolate and not arm_mcp) else "host"

        assert chosen(arm_mcp=False) == "bridge", "isolated memory-off must still run"
        assert chosen(arm_mcp=True) == "host", "memory-on needs the graph"
        assert chosen(arm_mcp=False, isolate=False) == "host"
        assert chosen(arm_mcp=False, sandbox=False) == "host"

    def test_it_pins_the_native_daemon_not_docker_desktop(self):
        """Desktop runs containers in a VM: bind mounts are restricted to
        configured shares and `--network host` is the VM's host, so a memory-on
        arm could not reach the graph. Measured both ways."""
        argv = self._argv()
        assert argv[:4] == ["docker", "--context", arms.ARM_DOCKER_CONTEXT, "run"]

    def test_the_toolchain_is_mounted_read_only_and_on_path(self):
        argv = self._argv(claude_bin=Path("/opt/c/bin/claude"),
                          uv_bin=Path("/opt/u/uv"))
        assert "/opt/c:/opt/c:ro" in argv
        assert "/opt/u/uv:/opt/u/uv:ro" in argv
        path = argv[argv.index("-e") + 1] if False else next(
            a for a in argv if a.startswith("PATH=")
        )
        assert "/opt/c/bin" in path and "/opt/u" in path

    def test_the_transcript_is_read_from_the_arms_own_home(self, tmp_path):
        """The mounter and the reader must agree on the private HOME.

        When they did not, a confined arm's transcript read empty and every
        recall/probe signal silently went to zero — on exactly the arms whose
        recall behaviour is the campaign's primary outcome.
        """
        from thalamus.eval.cost import project_slug

        worktree = tmp_path / "wt" / "t--memory-on--x"
        worktree.mkdir(parents=True)
        projects = arms.arm_home_for(worktree) / ".claude" / "projects"
        slug_dir = projects / project_slug(worktree)
        slug_dir.mkdir(parents=True)
        (slug_dir / "sid.jsonl").write_text('{"hello": "world"}')

        # The operator's HOME does not resolve it; the arm's own does.
        assert arms.transcript_text(worktree, "sid") == ""
        assert arms.transcript_text(worktree, "sid", projects) == '{"hello": "world"}'

    def test_a_sandboxed_arm_refuses_when_the_image_is_missing(self, tmp_path, monkeypatch):
        """Refusing beats silently running unconfined — an unconfined record
        looks exactly like a confined one."""
        monkeypatch.setattr(arms, "docker_available", lambda *a, **k: False)
        with pytest.raises(arms.ArmError, match="is not built"):
            arms.run_agent(tmp_path, "p", scope="main", project="thalamus",
                           sandbox=True)

    def test_a_sandboxed_arm_refuses_when_the_image_cannot_run_the_hooks(
        self, tmp_path, monkeypatch
    ):
        """The first confined image had no `jq`, so every retained hook died on
        its first line under `set -euo pipefail`. SessionStart aborting does not
        stop a session — it just never injects — so the memory-on arm was never
        told a memory surface existed and recorded `recall_calls: 0`, which
        reads exactly like a candidate that declined to recall. Refusing is the
        only way that stays distinguishable."""
        monkeypatch.setattr(arms, "docker_available", lambda *a, **k: True)
        monkeypatch.setattr(arms, "image_missing_hook_deps", lambda *a, **k: ("jq",))
        with pytest.raises(arms.ArmError, match="missing jq"):
            arms.run_agent(tmp_path, "p", scope="main", project="thalamus",
                           sandbox=True)

    def test_a_sandboxed_arm_refuses_before_launch_without_credentials(
        self, tmp_path, monkeypatch
    ):
        """The container gets its own HOME and cannot reach the operator's
        login. The first confined arm discovered that inside the container,
        which costs a prepared worktree and yields a record about the
        infrastructure rather than the candidate — so it is refused up front."""
        monkeypatch.setattr(arms, "docker_available", lambda *a, **k: True)
        monkeypatch.setattr(arms, "image_missing_hook_deps", lambda *a, **k: ())
        monkeypatch.setattr(arms.Path, "home", classmethod(lambda cls: tmp_path / "home"))
        (tmp_path / "home").mkdir()
        with pytest.raises(arms.ArmError, match="no credentials"):
            arms.run_agent(tmp_path, "p", scope="main", project="thalamus",
                           sandbox=True, home=tmp_path / "armhome")

    def test_the_token_not_just_the_config_reaches_the_arm(self, tmp_path, monkeypatch):
        """`.claude.json` is config and state; the OAuth token lives in
        `.claude/.credentials.json`. Copying only the former produced a session
        that reported "Not logged in" and exited in 69ms."""
        host = tmp_path / "home"
        (host / ".claude").mkdir(parents=True)
        (host / ".claude.json").write_text('{"oauthAccount": {}}')
        (host / ".claude" / ".credentials.json").write_text('{"token": "x"}')
        monkeypatch.setattr(arms, "docker_available", lambda *a, **k: True)
        monkeypatch.setattr(arms, "image_missing_hook_deps", lambda *a, **k: ())
        monkeypatch.setattr(arms.Path, "home", classmethod(lambda cls: host))

        arm_home = tmp_path / "armhome"
        with pytest.raises(arms.ArmError):
            # `claude` is not on PATH in the test env; the copy happens first.
            arms.run_agent(tmp_path, "p", scope="main", project="thalamus",
                           sandbox=True, home=arm_home)
        assert (arm_home / ".claude.json").is_file()
        creds = arm_home / ".claude" / ".credentials.json"
        assert creds.is_file(), "the token must reach the arm, not just the config"
        assert creds.stat().st_mode & 0o077 == 0, "the token must not widen"


class TestCrossArmFaultSignal:
    def _record(self, tail, passed=False):
        return {"acceptance": [{"run": "uv run pytest -q", "passed": passed,
                                "infra_fault": None, "tail": tail, "exit": 1}]}

    def test_identical_failure_across_arms_is_flagged(self):
        """
        lab/013's reader pair: both arms failed identically and it read as a
        candidate defect for a day. Two arms are two different candidates, so
        an identical failure is usually the harness (arXiv 2605.05564).
        """
        out = arms.render_campaign_faults([
            self._record("No module named 'gremlin_python' — 22 errors"),
            self._record("No module named 'gremlin_python' — 22 errors"),
        ])
        assert "CROSS-ARM FAULT SIGNAL" in out
        assert "uv run pytest -q" in out

    def test_differing_failures_are_not_flagged(self):
        """Different candidates failing different ways is ordinary evidence."""
        out = arms.render_campaign_faults([
            self._record("assert 0 == 3"),
            self._record("assert 1 == 3"),
        ])
        assert out == ""

    def test_a_passing_arm_clears_the_signal(self):
        out = arms.render_campaign_faults([
            self._record("boom"), self._record("boom", passed=True),
        ])
        assert out == ""

    def test_void_records_are_not_compared(self):
        """A void arm never ran an oracle; pairing against it means nothing."""
        void = {"void": True, "infra_fault": "session_fault_void"}
        assert arms.render_campaign_faults([self._record("boom"), void]) == ""

    def test_same_fault_through_different_worktree_paths_still_matches(self):
        """
        The two arms of a pair run in differently-named worktrees
        (<task>--memory-on--<ts> vs --memory-off--<ts>), so the same infra
        failure arrives carrying different paths and durations. Normalizing
        exactly those away is what lets the signal fire at all.
        """
        out = arms.render_campaign_faults([
            self._record("ImportError /wt/reader--memory-on--20260726T01Z/tests/t.py\n"
                         "No module named 'gremlin_python'\n22 errors in 1.20s"),
            self._record("ImportError /wt/reader--memory-off--20260726T09Z/tests/t.py\n"
                         "No module named 'gremlin_python'\n22 errors in 3.44s"),
        ])
        assert "CROSS-ARM FAULT SIGNAL" in out


def _bare_worktree(repo: Path, dest: Path) -> Path:
    """A worktree without prepare_worktree's `uv sync` — these fixtures are bare
    git repos, and the pin is a git operation with no environment to build."""
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "--detach",
                    str(dest), "HEAD"], check=True, capture_output=True)
    return dest


class TestArmGradesAgainstTheInheritedSuite:
    """L1 grades the suite the candidate inherited, not the one it left behind.

    The defect this pins down (lab/020): `pin_pre_existing_suite` landed with the
    oracle gate and for a while only the gate called it, so `eval oracle` graded
    anchors against the inherited suite while a real arm was graded against
    whatever tests the candidate wrote. The first gated arm scored rung 0 because
    it authored an ambitious test its own fix did not satisfy — a defect the gate
    by construction could never see, which means the gate's validation did not
    transfer to the thing being measured.
    """

    def _repo_with_suite(self, tmp_path):
        repo = _git_repo(tmp_path)
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_inherited.py").write_text("def test_inherited():\n    assert True\n")
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                        "-c", "user.name=t", "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                        "-c", "user.name=t", "commit", "-qm", "suite"],
                       check=True, capture_output=True)
        return repo

    def test_a_test_the_candidate_added_does_not_grade_it(self, tmp_path):
        """A candidate cannot fail L1 on a standard it invented mid-run."""
        repo = self._repo_with_suite(tmp_path)
        worktree = _bare_worktree(repo, tmp_path / "wt")
        (worktree / "tests" / "test_candidate_wrote_this.py").write_text(
            "def test_impossible():\n    assert False\n")

        arms.pin_pre_existing_suite(repo, worktree, "HEAD")

        assert not (worktree / "tests" / "test_candidate_wrote_this.py").exists()
        assert (worktree / "tests" / "test_inherited.py").exists()

    def test_a_test_the_candidate_weakened_is_restored(self, tmp_path):
        """The other direction: L1 cannot be passed by gutting the suite."""
        repo = self._repo_with_suite(tmp_path)
        worktree = _bare_worktree(repo, tmp_path / "wt")
        (worktree / "tests" / "test_inherited.py").write_text("# deleted the assertion\n")

        arms.pin_pre_existing_suite(repo, worktree, "HEAD")

        assert "assert True" in (worktree / "tests" / "test_inherited.py").read_text()

    def test_a_ref_with_no_suite_is_a_no_op_not_an_error(self, tmp_path):
        """Nothing inherited means nothing to restore — and nothing to game."""
        repo = _git_repo(tmp_path)
        worktree = _bare_worktree(repo, tmp_path / "wt")
        arms.pin_pre_existing_suite(repo, worktree, "HEAD")  # must not raise


class TestConcludedRunIsNeverADeadSession:
    """A healthy arm's own prose must not be read as evidence it died.

    lab/020 lost a campaign to this. The task under test is *about* session-death
    detection, so the candidate's closing summary said it had broadened the
    marker list to cover session/usage/rate/quota — and the runner matched its
    own vocabulary against that sentence, stamped a successful 49-turn $2.59 arm
    void, and halted. lab/016's error class inverted: the right string, in the
    wrong place.
    """

    def test_a_concluded_run_reporting_the_markers_is_not_a_fault(self):
        agent = AgentRun(
            "s",
            "Broadened the guard to match session limit, usage limit, rate "
            "limit and quota rather than one vendor string. All 226 tests pass.",
            2.59, 300000, 49, False,
        )
        assert arms.classify_session_fault(agent) is None

    def test_a_dead_session_is_still_caught(self):
        """The necessary condition must not have become a sufficient one."""
        agent = AgentRun("s", LIMIT_TAIL, 2.62, 180000, 18, True)
        assert arms.classify_session_fault(agent) == "session_fault_interrupted"

    def test_a_turn_capped_run_is_still_not_a_session_fault(self):
        """`is_error` alone never meant death — every capped run carries it."""
        agent = AgentRun("s", "ran out of turns mid-refactor", 1.8, 200000, 40, True)
        assert arms.classify_session_fault(agent) is None


# ---------------------------------------------------------------------------
# Harness selection — plumbing is shared, capability is declared (docs/07)
# ---------------------------------------------------------------------------


def test_arms_refuse_a_harness_they_cannot_honestly_drive():
    """Extraction is harness-agnostic; arms are not. Swapping the binary alone
    would emit records that read as measurements and are not — the failure
    lab/016 and lab/022 are both about — so the gaps are refused by name."""
    with pytest.raises(arms.ArmError) as exc:
        arms.agent_cli("cursor")
    message = str(exc.value)
    assert "cannot run under `cursor`" in message
    assert "credential staging" in message  # itemised, not a bare refusal


def test_arms_still_run_under_claude():
    assert arms.agent_cli("claude").binary == "claude"


def test_an_unknown_harness_is_refused_as_an_arm_error():
    with pytest.raises(arms.ArmError, match="no agent CLI"):
        arms.agent_cli("emacs")


def test_the_arm_default_model_comes_from_the_registry():
    from thalamus.harness import agents

    assert arms.DEFAULT_MODEL == agents.cli_for("claude").default_model


class TestCeilingArm:
    """The skyline arm (E2) — what a perfect retrieval would be worth."""

    def test_the_ceiling_strips_the_memory_surface_like_memory_off(self):
        """
        Scenario: the ceiling arm is parsed.

        Verification: no MCP and the memory hooks stripped, exactly as memory-off.
        The treatment is the injected fact, not a live retrieval surface — if the
        arm could also recall, it would measure "perfect memory plus retrieval"
        and could not bound retrieval on its own.
        """
        from thalamus.eval.arms import parse_arm

        ceiling = parse_arm("ceiling", ["main"])
        off = parse_arm("memory-off", ["main"])
        assert ceiling.mcp is False
        assert ceiling.strip_hooks == off.strip_hooks
        assert ceiling.inject_fact is True
        assert off.inject_fact is False

    def test_the_fact_is_handed_over_as_memory_not_as_instruction(self):
        """The comparison is against arms that retrieve, so the ceiling must differ
        in retrieval quality alone. "A past session established X" is the speech act
        a perfect recall performs; "you must do X" is a different experiment."""
        from thalamus.eval.arms import ceiling_prompt
        from thalamus.eval.tasks import Task, TaskSource, UnderSpecification

        task = Task(
            id="t", title="t", overlap="memorization",
            source=TaskSource(kind="replayed", ref="abc"),
            prompt="Fix the failing classifier.",
            under_specification=UnderSpecification(gated=True, fact="Turn counts do not separate the cases."),
        )
        rendered = ceiling_prompt(task)
        assert task.prompt in rendered
        assert "Turn counts do not separate the cases." in rendered
        assert "Recalled from memory" in rendered
        assert "you must" not in rendered.lower()

    def test_a_task_with_nothing_withheld_has_no_ceiling(self):
        """On an ungated task the ceiling is memory-off under another name, and
        running it would spend money to produce a duplicate labelled a treatment."""
        import pytest

        from thalamus.eval.arms import ArmError, ceiling_prompt
        from thalamus.eval.tasks import Task, TaskSource

        task = Task(
            id="t", title="t", overlap="memorization",
            source=TaskSource(kind="replayed", ref="abc"), prompt="Fix it.",
        )
        with pytest.raises(ArmError, match="conclusion-framed ceiling"):
            ceiling_prompt(task)


class TestProblemFramedCeiling:
    """experiments/005 — the same knowledge, framed as a situation."""

    def test_the_two_framings_are_separate_arms_over_one_task(self):
        from thalamus.eval.arms import parse_arm

        conclusion = parse_arm("ceiling", ["main"])
        problem = parse_arm("ceiling-problem", ["main"])
        assert conclusion.framing == "conclusion" and problem.framing == "problem"
        # Everything except the framing is held fixed: same stripped harness, no MCP,
        # same injection mechanism. The experiment varies one thing.
        assert conclusion.mcp == problem.mcp is False
        assert conclusion.strip_hooks == problem.strip_hooks
        assert conclusion.inject_fact and problem.inject_fact

    def test_the_problem_framing_keeps_the_evidence_and_drops_the_prescription(self):
        """
        Scenario: the two memos are compared.

        Verification: the problem framing carries the same load-bearing facts — the
        33-of-40 arm, the 11 and 18 cut-offs, the turn-count attempt — and none of
        the conclusion's imperative or answer. Otherwise the experiment would vary
        information content and framing at once, and could not attribute either.
        """
        from thalamus.eval.arms import injected_memo
        from thalamus.eval.tasks import load_battery

        task = next(
            t for t in load_battery()[0] if t.id == "arm-runner-session-death-classification"
        )
        conclusion = injected_memo(task, "conclusion")
        problem = injected_memo(task, "problem")

        for evidence in ("33", "11", "18", "turn count"):
            assert evidence in problem, f"problem framing dropped `{evidence}`"
        for prescription in ("must not", "ungraded", "surviving design"):
            assert prescription in conclusion
            assert prescription not in problem, f"problem framing kept `{prescription}`"

    def test_a_task_without_a_problem_framing_refuses_that_arm(self):
        import pytest

        from thalamus.eval.arms import ArmError, ceiling_prompt
        from thalamus.eval.tasks import Task, TaskSource, UnderSpecification

        task = Task(
            id="t", title="t", overlap="memorization", prompt="p",
            source=TaskSource(kind="replayed", ref="abc"),
            under_specification=UnderSpecification(gated=True, fact="only the conclusion"),
        )
        assert ceiling_prompt(task, "conclusion")
        with pytest.raises(ArmError, match="problem_framing"):
            ceiling_prompt(task, "problem")


# --------------------------------------------------------------------------------------
# A probe that cannot fire for an arm is inapplicable, never a miss.
# --------------------------------------------------------------------------------------


def _probe_task(requires: str = "memory_surface"):
    from thalamus.eval.tasks import Probe, Task, TaskSource

    return Task(
        id="t", title="t", overlap="memorization", prompt="p",
        source=TaskSource(kind="replayed", ref="HEAD"),
        probes=[
            Probe(id="memo-surfaced", kind="transcript_regex", pattern="deadbeef-uuid",
                  meaning="the memo reached context by recall", requires=requires),
            Probe(id="fix-name-convergence", kind="diff_regex", pattern="_helper",
                  meaning="converged on the memorized helper name"),
        ],
    )


def test_a_memory_surface_probe_is_inapplicable_to_an_arm_with_no_mcp(tmp_path):
    """
    Scenario: A `memo-surfaced` probe runs against a ceiling arm, which has its MCP
    server removed before the session starts

    Verifications:
    - the probe is `inapplicable`, not `miss`
    - it is dropped from the decided denominator but counted on its own key
    - the reason names the arm

    The probe matches a session UUID that exists only in the memory graph, so for an
    arm with no memory surface it asks whether a fact arrived through a channel that
    was deleted before the run. Recorded as a miss, that structural zero sits in the
    same denominator as a real one — the mistake lab/030 already paid for, where a
    miss rate turned out to be describing the stratum rather than the system.
    """
    task = _probe_task()
    ceiling = arms.parse_arm("ceiling", ["main"])

    results = arms.evaluate_probes(task, "no uuid here", "no diff", tmp_path, arm=ceiling)

    memo = next(p for p in results if p["id"] == "memo-surfaced")
    assert memo["status"] == "inapplicable"
    assert memo["applicable"] is False
    assert "no memory surface" in memo["reason"]

    # Verifies: the ordinary probe is still decided, so this is not a blanket opt-out
    other = next(p for p in results if p["id"] == "fix-name-convergence")
    assert other["status"] == "miss" and other["applicable"] is True

    tally = arms.probe_tally(results)
    assert tally == {"hit": 0, "decided": 1, "inapplicable": 1}


def test_the_same_probe_is_decided_for_an_arm_that_has_memory(tmp_path):
    """
    Scenario: The same probe runs against memory-on, which keeps its MCP server

    Applicability is a property of the arm, not of the outcome — so an arm that
    *could* have surfaced the memo and did not is a real miss and must stay in the
    denominator. Otherwise the fix would delete the measurement it exists to clean.
    """
    task = _probe_task()
    on = arms.parse_arm("memory-on", ["main"])

    results = arms.evaluate_probes(task, "no uuid here", "no diff", tmp_path, arm=on)
    memo = next(p for p in results if p["id"] == "memo-surfaced")

    assert memo["status"] == "miss" and memo["applicable"] is True
    assert arms.probe_tally(results)["decided"] == 2

    # Verifies: and it still hits when the UUID is actually present
    hit = arms.evaluate_probes(task, "saw deadbeef-uuid", "", tmp_path, arm=on)
    assert next(p for p in hit if p["id"] == "memo-surfaced")["status"] == "hit"


def test_a_probe_with_no_requirement_is_always_decided(tmp_path):
    """
    Scenario: An ordinary probe evaluated against a no-MCP arm

    Only probes that *declare* a requirement become inapplicable. Silence means the
    probe is arm-independent, which is the common case and must not change.
    """
    task = _probe_task(requires="")
    results = arms.evaluate_probes(
        task, "no uuid", "no diff", tmp_path, arm=arms.parse_arm("memory-off", ["main"])
    )

    assert all(p["applicable"] for p in results)
    assert arms.probe_tally(results)["inapplicable"] == 0


def test_an_inapplicable_probe_does_not_render_as_a_miss():
    """
    Scenario: Render a ceiling arm's record

    Verifications:
    - the line reads `n/a`, not `miss`
    - the reason is shown in place of the meaning, so the reader is not invited to
      interpret a verdict that was never reached
    - the tally states what was excluded

    This is the whole visible symptom: the probe appeared as a "miss" in every
    ceiling arm's output, which is noise pretending to be a measurement.
    """
    record = {
        "task": "t", "arm": "ceiling", "scope": "main", "ref": "HEAD",
        "order_index": 0, "rung": 1, "acceptance": [],
        "probes": [
            {"id": "memo-surfaced", "kind": "transcript_regex", "hit": False,
             "status": "inapplicable", "applicable": False,
             "reason": "arm `ceiling` runs with no memory surface — nothing to surface",
             "meaning": "the memo reached context by recall"},
        ],
        "probe_tally": {"hit": 0, "decided": 0, "inapplicable": 1},
    }

    rendered = arms.render_run(record)

    assert "probe n/a " in rendered
    assert "probe miss" not in rendered
    assert "nothing to surface" in rendered
    assert "1 inapplicable (excluded from the denominator)" in rendered


def test_an_unknown_requirement_is_a_pre_registration_violation():
    """
    Scenario: A task declares `requires: telepathy`

    A requirement the runner does not understand would silently evaluate as an
    ordinary probe, which is the failure mode in reverse — so it is caught at
    validation, where every other pre-registration fault is.
    """
    task = _probe_task(requires="telepathy")

    assert any("requires `telepathy`" in issue for issue in task.check())
