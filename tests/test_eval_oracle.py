"""
Oracle-gate tests (docs/04 — validating the graded oracle before trusting it).

Interfaces: thalamus.eval.oracle.anchor_candidates/mutant_candidates/run_gate/render_gate
Infrastructure: none; grading is stubbed, since what is under test is the gate's
verdict logic, not the ladder's ability to run pytest.
Scope: the gate is a GATE, never a kill-rate. These tests pin the three properties
that distinguishes it from one — an exact pre-registered rung per candidate, a
mismatch failing the whole gate regardless of how many others matched, and the
mismatching candidate being named in the output.

Grounding: mutation score is rejected as a metric on two counts. It is the
cardinality bias the ordinal ladder exists to avoid — the denominator is a set the
author chose (arXiv 2601.03525) — and coverage-family metrics say nothing about
oracle quality in the first place (arXiv 2212.06118). Its denominator is also not
well defined: equivalent mutants are unkillable and detecting them is undecidable,
so every rate carries unknown bias. Mutants stand in for real faults under the
competent programmer hypothesis and the coupling effect (arXiv 2103.07189;
measured rather than assumed in arXiv 2512.16741), which is why `mimics` is
mandatory — those hypotheses describe human slips, not LLM failure modes.
"""

from pathlib import Path

import pytest

from thalamus.eval import oracle
from thalamus.eval.tasks import Task

TASK = Task(
    id="sample",
    title="A sample",
    overlap="memorization",
    source={"kind": "replayed", "ref": "aaa111", "fix_ref": "bbb222", "evidence": "e"},
    prompt="Fix the thing.",
    acceptance=[{"run": "a", "level": 1}, {"run": "b", "level": 2}],
    probes=[{"id": "p", "kind": "diff_regex", "pattern": "zzz", "meaning": "m"}],
    mutants=[
        {"id": "m1", "patch": "m/m1.patch", "expected_rung": 3, "mimics": "one-site fix"},
        {"id": "m2", "patch": "m/m2.patch", "expected_rung": 4, "mimics": "over-fix"},
        {"id": "m3", "patch": "m/m3.patch", "expected_rung": 4, "mimics": "floor drop"},
        {"id": "m4", "patch": "m/m4.patch", "expected_rung": 5, "mimics": "correct, renamed"},
    ],
)


@pytest.fixture
def graded(monkeypatch):
    """Drive the gate with a rung table instead of real worktrees."""

    def drive(rungs: dict[str, int]):
        def fake(repo, task, candidate, timeout=900, keep=False):
            return oracle.Grade(candidate, rungs[candidate.label], [])

        monkeypatch.setattr(oracle, "grade_candidate", fake)
        return oracle.run_gate(Path("/repo"), TASK, Path("/cfg/tasks"))

    return drive


AS_EXPECTED = {
    "negative-anchor": 1, "positive-anchor": 5,
    "m1": 3, "m2": 4, "m3": 4, "m4": 5,
}


class TestAnchors:
    def test_the_pair_brackets_the_ladder(self):
        negative, positive = oracle.anchor_candidates(TASK)
        assert (negative.ref, negative.expected_rung) == ("aaa111", 1)
        assert (positive.ref, positive.expected_rung) == ("bbb222", 5)

    def test_mutants_all_start_from_the_fix(self):
        """A mutant is a degradation of the known-good fix, so its base is
        `fix_ref` — degrading anything else grades a different candidate."""
        assert {c.ref for c in oracle.mutant_candidates(TASK, Path("/cfg/tasks"))} == {"bbb222"}

    def test_negative_anchor_scoring_above_the_gate_is_an_issue(self, graded):
        """
        lab/011's competence echo, mechanized: the bug is present by construction
        at `source.ref`, so a rung above the no-regression gate means the check is
        measuring the repository rather than the candidate.
        """
        result = graded({**AS_EXPECTED, "negative-anchor": 3})
        assert not result["passed"]
        assert any("measuring the repo" in i for i in result["issues"])


class TestGateNotKillRate:
    def test_every_rung_reproduced_passes(self, graded):
        assert graded(AS_EXPECTED)["passed"]

    def test_one_mismatch_fails_the_whole_gate(self, graded):
        """
        The property that makes this a gate: 3 of 4 mutants landing on their
        pre-registered rung is not 75% of a pass, it is a failure. A rate would
        report 0.75 and move on.
        """
        result = graded({**AS_EXPECTED, "m2": 5})
        assert not result["passed"]

    def test_the_mismatching_candidate_is_named(self, graded):
        """A rate cannot say WHICH mutant survived, and the survivor's identity
        is the entire signal."""
        rendered = oracle.render_gate(graded({**AS_EXPECTED, "m2": 5}))
        assert "m2" in rendered and "MISMATCH" in rendered
        assert "m1" in rendered and "ok" in rendered

    def test_scoring_higher_than_expected_also_fails(self, graded):
        """Pre-registration cuts both ways. A candidate beating its expected rung
        means the expectation or the ladder was wrong, and which one is a finding
        — it is not a bonus to be silently absorbed."""
        assert not graded({**AS_EXPECTED, "m1": 5})["passed"]

    def test_the_equivalent_mutant_must_score_full_marks(self, graded):
        """
        The equivalent mutant is deliberate, not a nuisance: m4 is a *correct* fix
        written differently. Undecidability does not bite because equivalence is
        known by construction. If it scores below the top rung the ladder is
        rewarding imitation of the historical fix rather than grading behavior.
        """
        assert not graded({**AS_EXPECTED, "m4": 4})["passed"]


class TestSetSize:
    def test_a_thin_mutant_set_is_flagged(self, monkeypatch):
        """docs/04 says 4–6. One mutant measures a single interior point and
        calls it discrimination."""
        thin = TASK.model_copy(update={"mutants": TASK.mutants[:1]})
        monkeypatch.setattr(
            oracle, "grade_candidate",
            lambda repo, task, candidate, timeout=900, keep=False: oracle.Grade(
                candidate, candidate.expected_rung, []
            ),
        )
        result = oracle.run_gate(Path("/repo"), thin, Path("/cfg/tasks"))
        assert not result["passed"]
        assert any("the interior" in i for i in result["issues"])

    def test_a_task_with_no_fix_ref_cannot_be_gated(self):
        authored = TASK.model_copy(
            update={"source": TASK.source.model_copy(update={"fix_ref": ""})}
        )
        result = oracle.run_gate(Path("/repo"), authored, Path("/cfg/tasks"))
        assert not result["passed"]
        assert any("nothing to degrade" in i for i in result["issues"])
