"""
Counterfactual task battery tests (docs/04 layer 2 — the pre-registered half).

Interfaces: thalamus.eval.tasks.load_battery/render_battery, Task.check
Infrastructure: none; YAML fixtures written to tmp_path
Scope: pre-registration is enforced structurally — a task without a mechanical
oracle, without consequence probes, or without a disclosed overlap stratum does
not arm. The battery in config/tasks/ must itself validate.

Grounding: consequence probes encode MQuAKE's dichotomy — recall of a stored
fact and action on its entailed consequences are different measurements (arXiv
2305.14795); zero-probe tasks would measure only surfacing. The overlap tag is
the disclosed-stratification answer to the replay validity threat (docs/04,
consultation scope:main:exchange:8644614d1b1242a4).
"""

from pathlib import Path

from thalamus.eval.tasks import Task, load_battery, render_battery

VALID = """\
task: v0
id: sample-task
title: A sample
overlap: transferable
source:
  kind: authored
  ref: "abc123"
prompt: Do the thing.
acceptance:
  - run: "uv run pytest -q"
probes:
  - id: p1
    kind: transcript_regex
    pattern: "(?i)floor"
    meaning: engaged the memorized rationale
"""


def _write(directory: Path, name: str, text: str) -> None:
    (directory / "tasks").mkdir(exist_ok=True)
    (directory / "tasks" / name).write_text(text)


def test_a_valid_task_arms_with_no_issues(tmp_path):
    """
    Scenario: One well-formed task in the battery
    """
    _write(tmp_path, "sample-task.yaml", VALID)

    tasks, issues = load_battery(tmp_path)

    assert issues == []
    assert [t.id for t in tasks] == ["sample-task"]
    rendered = render_battery(tasks, issues)
    assert "Battery OK" in rendered
    assert "sample-task [transferable · authored]" in rendered


def test_preregistration_violations_are_each_named():
    """
    Scenario: A task missing its oracle, its probes, and its stratum

    Verifications:
    - no mechanical acceptance is a violation (success decided after the runs)
    - zero probes is a violation (measures surfacing, not consequences)
    - an undisclosed overlap stratum is a violation (the hidden confound)
    - a replayed task without an evidence pointer is a violation
    """
    task = Task(
        id="bad",
        title="t",
        overlap="mystery",
        source={"kind": "replayed"},
        prompt="  ",
        acceptance=[],
        probes=[],
    )

    issues = task.check()

    text = "\n".join(issues)
    assert "no mechanical acceptance" in text
    assert "consequence probes" in text
    assert "overlap `mystery`" in text
    assert "no evidence pointer" in text
    assert "prompt is empty" in text


def test_probe_obligations(tmp_path):
    """
    Scenario: Probes with a non-compiling pattern, a missing meaning, and a
    duplicate id
    """
    task = Task(
        id="probes",
        title="t",
        overlap="memorization",
        source={"kind": "authored"},
        prompt="p",
        acceptance=[{"run": "true"}],
        probes=[
            {"id": "p1", "kind": "diff_regex", "pattern": "(", "meaning": "m"},
            {"id": "p1", "kind": "command", "meaning": ""},
        ],
    )

    issues = task.check()

    text = "\n".join(issues)
    assert "does not compile" in text
    assert "duplicate probe id" in text
    assert "command probe needs a run" in text
    assert "no meaning" in text


def test_prompt_echo_probes_are_refused():
    """
    Scenario: A transcript probe whose pattern the task's own prompt satisfies

    Measured on the first live smoke run (2026-07-19): the transcript always
    contains the prompt, so such a probe hits in every arm and measures nothing.
    """
    task = Task(
        id="echo",
        title="t",
        overlap="memorization",
        source={"kind": "authored"},
        prompt="Fix recall without loosening the match floor.",
        acceptance=[{"run": "true"}],
        probes=[{"id": "p1", "kind": "transcript_regex", "pattern": "(?i)match floor",
                 "meaning": "m"},
                {"id": "p2", "kind": "diff_regex", "pattern": "loosening",
                 "meaning": "m"}],
    )

    issues = task.check()

    assert sum("pre-satisfied" in issue for issue in issues) == 2


def test_filename_is_the_id_and_duplicates_are_caught(tmp_path):
    """
    Scenario: A task file whose declared id differs from its filename
    """
    _write(tmp_path, "other-name.yaml", VALID)

    tasks, issues = load_battery(tmp_path)

    assert any("the filename is the id" in issue for issue in issues)
    rendered = render_battery(tasks, issues)
    assert "does not arm" in rendered


def test_memorization_only_battery_is_flagged_not_pooled(tmp_path):
    """
    Scenario: Every task in the battery sits in the memorization stratum

    The replay validity threat (the task's own solution in memory-on's graph)
    is disclosed stratification — a battery with no transferable tasks must say
    that campaign claims stay scoped, not silently generalize.
    """
    _write(tmp_path, "sample-task.yaml", VALID.replace("transferable", "memorization"))

    tasks, issues = load_battery(tmp_path)

    rendered = render_battery(tasks, issues)
    assert issues == []
    assert "no transferable-stratum tasks yet" in rendered


def test_the_shipped_battery_validates(monkeypatch):
    """
    Scenario: The real config/tasks/ battery in this repo

    The enforcement is only real if the shipped battery passes its own gate.
    """
    monkeypatch.delenv("THALAMUS_CONFIG_DIR", raising=False)

    tasks, issues = load_battery()

    assert issues == []
    assert len(tasks) >= 2
    assert all(task.probes for task in tasks)


# ---------------------------------------------------------------------------
# The graded ladder (docs/04; eval-methodology exchange 06723ce1b78345a9)
# ---------------------------------------------------------------------------


def _laddered(**overrides):
    data = dict(
        id="t", title="t", overlap="memorization",
        source={"kind": "replayed", "ref": "HEAD", "evidence": "e", "fix_ref": "abc123"},
        prompt="Fix the thing.",
        acceptance=[{"run": "a", "level": 1}, {"run": "b", "level": 2}],
        probes=[{"id": "p", "kind": "diff_regex", "pattern": "zzz", "meaning": "m"}],
    )
    data.update(overrides)
    return Task(**data)


class TestLadderValidation:
    def test_a_clean_ladder_validates(self):
        assert _laddered().check() == []

    def test_rung_referencing_the_memory_surface_is_refused(self):
        """
        The circularity guard. A rung a memory-off arm cannot reach is an arm
        label wearing a score: grading it would make memory-on > memory-off
        true by construction. Delivery belongs in `probes`, never the score.
        """
        task = _laddered(acceptance=[
            {"run": "a", "level": 1},
            {"run": "grep mcp__thalamus__ transcript.jsonl", "level": 2},
        ])
        issues = task.check()
        assert any("no memory surface" in i for i in issues)

    def test_gap_in_the_ladder_is_refused(self):
        """A rung above a missing one is unreachable by the scoring rule."""
        task = _laddered(acceptance=[{"run": "a", "level": 1}, {"run": "c", "level": 3}])
        assert any("none at 2" in i for i in task.check())

    def test_unbuilt_judge_rung_is_refused(self):
        task = _laddered(acceptance=[{"run": "a", "level": 1}, {"run": "j", "level": 4}])
        assert any("reserved" in i for i in task.check())

    def test_replayed_task_without_fix_ref_is_refused(self):
        """No positive anchor means the grading can't be checked against truth."""
        task = _laddered(source={"kind": "replayed", "ref": "HEAD", "evidence": "e"})
        assert any("fix_ref" in i for i in task.check())

    def test_authored_task_with_fix_ref_is_refused(self):
        """An authored task has no historical fix; anchors don't apply to it."""
        task = _laddered(
            source={"kind": "authored", "ref": "HEAD", "fix_ref": "abc123"},
            overlap="transferable",
        )
        assert any("no historical fix" in i for i in task.check())
