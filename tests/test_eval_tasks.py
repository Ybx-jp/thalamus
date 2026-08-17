"""
Counterfactual task battery tests — eval layer 2, the pre-registered half.

Interfaces: thalamus.eval.tasks.load_battery/render_battery, Task.check
Infrastructure: none; YAML fixtures written to tmp_path
Scope: pre-registration is enforced structurally — a task without a mechanical
oracle, without consequence probes, or without a disclosed overlap stratum does
not arm. The battery in config/tasks/ must itself validate.

Grounding: consequence probes encode MQuAKE's dichotomy — recall of a stored
fact and action on its entailed consequences are different measurements (arXiv
2305.14795); zero-probe tasks would measure only surfacing. The overlap tag is
the disclosed-stratification answer to the replay validity threat (consultation
scope:main:exchange:8644614d1b1242a4).
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

    The violation is reported and the task is quarantined — it will not arm at
    `thalamus eval run`, while the rest of the battery still can.
    """
    _write(tmp_path, "other-name.yaml", VALID)

    tasks, issues = load_battery(tmp_path)

    assert any("the filename is the id" in issue for issue in issues)
    rendered = render_battery(tasks, issues)
    assert "QUARANTINED, will not run" in rendered


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

    The enforcement is only real if whatever ships passes its own gate, so the
    assertion is over the battery on disk rather than over a count. A task is a
    tier-0 operator artifact naming commits in the repository it grades, so a
    clone starts with none — and the empty case is the second half of this: it
    renders as an empty battery rather than as a fault, and the moment a task
    file lands the pre-registration obligations above bind it.
    """
    monkeypatch.delenv("THALAMUS_CONFIG_DIR", raising=False)

    tasks, issues = load_battery()

    assert issues == []
    assert all(task.probes for task in tasks)
    if not tasks:
        assert "Battery is empty" in render_battery(tasks, issues)


# ---------------------------------------------------------------------------
# The graded ladder (eval-methodology exchange 06723ce1b78345a9)
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
        """Level 6 is the judge: reserved, and refused until it is built."""
        task = _laddered(acceptance=[{"run": "a", "level": 1}, {"run": "j", "level": 6}])
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


class TestMutantValidation:
    """The mutant set is the discrimination bar: anchors establish the
    ladder's range, mutants establish its resolution in the interior where every
    observed arm sits. Structure is enforced here; the rung comparison is the
    gate's job (test_eval_oracle.py)."""

    def _m(self, **overrides):
        mutant = {
            "id": "m1-partial",
            "patch": "mutants/t/m1.patch",
            "expected_rung": 3,
            "mimics": "fix applied at one call site only",
        }
        mutant.update(overrides)
        return mutant

    def test_a_well_formed_mutant_set_validates(self):
        assert _laddered(mutants=[self._m()]).check() == []

    def test_mutant_without_a_named_failure_mode_is_refused(self):
        """
        `mimics` carries the coupling argument. The classical licence for
        mutants-as-fault-proxies (competent programmer hypothesis + coupling
        effect, arXiv 2103.07189) describes human programmers making small
        syntactic slips; these candidates are LLM agents, which fail differently.
        An unnamed mutant is coupled to the wrong fault distribution.
        """
        issues = _laddered(mutants=[self._m(mimics="  ")]).check()
        assert any("coupled to the human fault distribution" in i for i in issues)

    def test_mutant_rung_above_the_built_ladder_is_refused(self):
        issues = _laddered(mutants=[self._m(expected_rung=6)]).check()
        assert any("outside 0–5" in i for i in issues)

    def test_mutants_without_a_fix_to_degrade_are_refused(self):
        """A mutant is a degradation *of the known-good fix* — no fix, nothing
        to degrade, and no ground truth to expect a rung against."""
        task = _laddered(
            source={"kind": "authored", "ref": "HEAD"},
            overlap="transferable",
            mutants=[self._m()],
        )
        assert any("nothing to degrade" in i for i in task.check())

    def test_duplicate_mutant_ids_are_refused(self):
        issues = _laddered(mutants=[self._m(), self._m()]).check()
        assert any("duplicate mutant id" in i for i in issues)


class TestUnderSpecification:
    """The declared-gate half of a memory-gated task.

    A measured run held the arm harness completely fixed and varied only the prompt: a
    self-contained bug report produced zero thalamus calls, a past-work question
    produced three. So under-specification is the mechanism that makes a memory
    contrast possible at all — and an undeclared one is indistinguishable from a
    prompt that is merely vague. These tests enforce that the declaration is
    checkable and that it leaves a floor.
    """

    RUNGS = [{"run": f"r{n}", "level": n} for n in (1, 2, 3, 4, 5)]

    def _spec(self, **overrides):
        spec = dict(
            gated=True,
            fact="the withheld constraint",
            fact_nodes=["scope:main:claim:deadbeef"],
            absence_check="exit 0",
            gates_rungs=[4],
            floor_rung=2,
        )
        spec.update(overrides)
        return _laddered(acceptance=self.RUNGS, under_specification=spec)

    def test_a_declared_gate_validates(self):
        assert self._spec().check() == []

    def test_gate_without_fact_nodes_is_refused(self):
        """A fact no recall can reach does not gate — it just adds difficulty."""
        assert any("does not gate anything" in i
                   for i in self._spec(fact_nodes=[]).check())

    def test_gate_without_an_absence_check_is_refused(self):
        """The absence claim is the load-bearing one, so prose will not do.

        Three candidate facts failed this check during the battery's design pass
        — the repo documents its own reasoning in code comments, so most
        decisions are recoverable from the worktree and gate nothing."""
        assert any("prose is an assertion rather than evidence" in i
                   for i in self._spec(absence_check="  ").check())

    def test_floor_at_or_above_the_gate_is_refused(self):
        """The circularity guard, in its source-input form.

        If the withheld fact gates the bottom of the ladder, a memory-off arm
        scores nothing on its own merits and the contrast measures the arm label
        rather than the candidate."""
        issues = self._spec(floor_rung=4).check()
        assert any("memory-on win by construction" in i for i in issues)

    def test_gating_a_rung_the_task_does_not_declare_is_refused(self):
        """Gating rung 4 on a ladder that stops at 2 gates nothing."""
        task = _laddered(
            acceptance=[{"run": "a", "level": 1}, {"run": "b", "level": 2}],
            under_specification=dict(
                gated=True, fact="f", fact_nodes=["scope:main:claim:x"],
                absence_check="exit 0", gates_rungs=[4], floor_rung=2,
            ),
        )
        assert any("declares no acceptance check" in i for i in task.check())

    def test_a_rung_cannot_be_both_strongly_and_weakly_gated(self):
        issues = self._spec(gates_rungs=[4], gates_rungs_weak=[4]).check()
        assert any("one of the two claims is wrong" in i for i in issues)

    def test_attributable_outcome_on_a_weakly_gated_rung_is_refused(self):
        """A rung reachable without memory cannot be evidence of memory use.

        R3 on the session-death task is derivable in principle from a 33-turn
        fixture in the pinned suite, so the endpoint is pre-registered at the
        strongly-gated rung instead."""
        issues = self._spec(gates_rungs_weak=[5],
                            attributable_outcome="rung >= 5").check()
        assert any("cannot be evidence of memory use" in i for i in issues)

    def test_retired_tests_must_be_re_asserted_somewhere(self):
        """L1 exemptions relocate an assertion; they do not drop it."""
        task = _laddered(
            acceptance=self.RUNGS,
            no_regression={"obsolete_tests": ["tests/t.py::x"], "relocated_to": 6},
        )
        assert any("re-asserted somewhere" in i for i in task.check())


def test_a_ref_that_no_longer_resolves_is_reported():
    """
    Scenario: the repository's history is rewritten and every SHA changes — which
    happened here on 2026-07-29, killing all six refs across all three tasks.

    Verification: validation says so. It previously reported "Battery OK" because
    it checked that a task carried its oracle and never that the oracle could be
    reached, so the failure surfaced at worktree-checkout time instead.
    """
    from thalamus.eval.tasks import Task, TaskSource, unresolvable_refs

    dead = Task(
        id="t", title="t", overlap="memorization", prompt="p",
        source=TaskSource(kind="replayed", ref="deadbeef", fix_ref="cafed00d"),
    )
    problems = unresolvable_refs([dead])
    assert len(problems) == 2
    assert "does not resolve" in problems[0]
    assert "commit-map" in problems[0]

    live = Task(
        id="t", title="t", overlap="memorization", prompt="p",
        source=TaskSource(kind="replayed", ref="HEAD"),
    )
    assert unresolvable_refs([live]) == []


# --------------------------------------------------------------------------------------
# Quarantine: the refusal is as wide as the fault, and the exclusion is recorded.
# --------------------------------------------------------------------------------------


def _task(task_id: str, ref: str = "HEAD"):
    from thalamus.eval.tasks import Task, TaskSource

    return Task(
        id=task_id, title=task_id, overlap="memorization", prompt="p",
        source=TaskSource(kind="replayed", ref=ref),
    )


def test_an_issue_is_attributed_to_the_task_it_is_about():
    """
    Scenario: One task in a three-task battery has a dead ref

    Verifications:
    - the issue lands against that task, not against the battery
    - the other two tasks are unaffected

    A campaign runs one task at a time, so a battery-wide refusal for a fault in a
    task the run never touches refuses for a reason untrue of the run. That is the
    gate operators learn to route around; per-task, the refusal is exactly as wide
    as the fault.
    """
    from thalamus.eval.tasks import quarantine

    tasks = [_task("alpha"), _task("beta"), _task("gamma")]
    issues = ["beta: source.ref `deadbeef` does not resolve — the battery cannot be run"]

    per_task, battery_wide = quarantine(tasks, issues)

    assert list(per_task) == ["beta"]
    assert battery_wide == []


def test_a_filename_prefixed_issue_is_attributed_too():
    """
    Scenario: A task file fails schema validation, so it never became a Task at all

    Its id is the filename (the battery enforces that), so the operator asking to
    run that id must be told what is wrong with it rather than handed a
    battery-level refusal that names no task.
    """
    from thalamus.eval.tasks import quarantine

    per_task, battery_wide = quarantine(
        [_task("alpha")], ["broken.yaml: 2 schema error(s) — ..."]
    )

    assert list(per_task) == ["broken"]
    assert battery_wide == []


def test_a_duplicate_task_id_blocks_the_whole_battery():
    """
    Scenario: Two files declare the same task id

    There is no task-scoped reading of this: it makes *which* task `eval run <id>`
    would pick ambiguous, so it stays battery-level and blocks everything.
    """
    from thalamus.eval.tasks import quarantine

    per_task, battery_wide = quarantine([_task("alpha")], ["duplicate task id `alpha`"])

    assert per_task == {}
    assert battery_wide == ["duplicate task id `alpha`"]


def test_strata_are_counted_over_the_runnable_set_only():
    """
    Scenario: Render a battery in which one task is quarantined

    Verifications:
    - the quarantined task is flagged in the listing
    - it is excluded from the strata count, and the exclusion is stated

    Strata are what a campaign's claims are scoped to. Counting a task that cannot
    run would describe a battery that does not exist and move the scope of every
    claim built on it, silently.
    """
    tasks = [_task("alpha"), _task("beta")]
    rendered = render_battery(tasks, ["beta: source.ref `deadbeef` does not resolve"])

    assert "beta [memorization · replayed] — beta — QUARANTINED, will not run" in rendered
    # Verifies: one of two tasks counted, and the reader is told why
    assert "Runnable strata (1 quarantined, excluded): 1 memorization" in rendered
    assert "the rest of the battery still arms" in rendered


def test_a_clean_battery_still_reports_ok():
    """A battery with no issues must not grow a quarantine section."""
    rendered = render_battery([_task("alpha")], [])

    assert "Battery OK" in rendered
    assert "QUARANTINED" not in rendered
    assert "Runnable strata: 1 memorization" in rendered
