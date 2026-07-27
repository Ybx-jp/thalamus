"""Validating the graded oracle before trusting it — anchors and the mutant gate.

The ladder in `tasks.py`/`arms.py` scores candidates; this module grades *the
ladder*. Nothing here runs a model: every candidate it scores has a quality known
by construction, so the whole instrument can be validated at zero inference cost.

Two kinds of candidate, doing different jobs:

**Anchors** establish range. The negative anchor is the worktree at `source.ref`
(the bug present by construction) and the positive anchor is `source.fix_ref` (the
commit that actually fixed it). Necessary but nowhere near sufficient — the
saturated binary oracle passes the anchor pair too, and a test the status quo
passes cannot justify replacing the status quo. Anchors also carry a second value:
a rung that fires against the *negative* anchor is measuring the repo rather than
the candidate, which mechanizes lab/011's competence-echo catch.

**Mutants** establish discrimination in the interior, which is where every observed
arm actually sits. Each is a degradation of the known-good fix with its rung
committed in advance, so the gate asks the only question that matters of an
instrument: does it reproduce an ordering it was not fitted to?

The verdict is a **gate, never a kill-rate**. A rate would be the pass ratio
wearing a new name — the denominator is a set the author chose, so adding easy
mutants moves the number, which is the cardinality bias the ordinal ladder exists
to avoid (arXiv 2601.03525), and the general objection to coverage-family metrics
is that they say nothing about oracle quality (arXiv 2212.06118). Worse, the
denominator is not even well defined: equivalent mutants are semantically identical
to the original and unkillable by any test, and detecting them is undecidable, so
every kill-rate carries an unknown bias. Pre-registered rungs dodge both problems
and are strictly stronger besides — "5 of 6 killed" does not say *which* survived,
and the survivor's identity is the entire signal.

Equivalent mutants are not a threat here but a deliberate instrument: a mutant
declared at the top rung is a *correct fix written differently*, and the ladder
failing to award it full marks would mean the ladder rewards imitating the
historical fix. Undecidability does not bite because these are authored, not
generated — equivalence is known by construction.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from thalamus.eval.arms import (
    ArmError,
    _git,
    evaluate_acceptance,
    ladder_score,
    prepare_worktree,
    remove_worktree,
)
from thalamus.eval.tasks import LADDER_LEVELS, Task

# docs/04: 4–6 per task. Selective-mutation practice is that a small, well-chosen
# set beats exhaustive generation; the floor is here because a one-mutant "set"
# measures a single point and calls it discrimination.
MUTANT_SET_MIN = 4
MUTANT_SET_MAX = 6


@dataclass
class Candidate:
    """A thing to grade, whose correct rung is known before it runs."""

    label: str
    kind: str  # "anchor-negative" | "anchor-positive" | "mutant"
    ref: str
    expected_rung: int
    patch: Path | None = None
    mimics: str = ""


@dataclass
class Grade:
    candidate: Candidate
    rung: int
    acceptance: list[dict] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.rung == self.candidate.expected_rung


def anchor_candidates(task: Task) -> list[Candidate]:
    """The range pair. Positive anchor expects the top built rung: the commit that
    actually fixed the bug should satisfy every relation, and if it does not, the
    relations encode something the fix never claimed."""
    return [
        Candidate(
            label="negative-anchor",
            kind="anchor-negative",
            ref=task.source.ref,
            # The bug is present by construction, so the targeted oracle must
            # fail. The no-regression gate should still pass — this is the
            # untouched historical tree, and a suite red at its own ref would
            # mean the gate is measuring the repo, not the candidate.
            expected_rung=1,
        ),
        Candidate(
            label="positive-anchor",
            kind="anchor-positive",
            ref=task.source.fix_ref,
            expected_rung=max(LADDER_LEVELS),
        ),
    ]


def mutant_candidates(task: Task, task_dir: Path) -> list[Candidate]:
    """Mutants are degradations *of the fix*, so every one starts at `fix_ref`."""
    return [
        Candidate(
            label=mutant.id,
            kind="mutant",
            ref=task.source.fix_ref,
            expected_rung=mutant.expected_rung,
            patch=(task_dir / mutant.patch).resolve(),
            mimics=mutant.mimics,
        )
        for mutant in task.mutants
    ]


def pin_pre_existing_suite(repo: Path, worktree: Path, source_ref: str) -> None:
    """Restore `tests/` to the task's starting ref before grading.

    L1 is "the *pre-existing* suite stays green", and pre-existing means the suite
    at `source.ref` — the one a candidate arm actually inherits. Anchors and
    mutants start from `fix_ref` instead, whose tree carries the tests the fix
    shipped with itself, and grading against those measures something no arm was
    ever measured against. Two concrete distortions, both observed on this task:

    - Every degradation collapses to rung 0. The fix's own unit test fails on any
      mutant that weakens case-insensitivity, so L1 falls and the ladder never
      gets to say *how* degraded the candidate was — the discrimination the
      mutant set exists to measure is destroyed before rung 2.
    - Worse, it rewards imitation. `test_keyword_matching_is_case_insensitive_and_regex_safe`
      imports `_keyword_predicate` by name, so a *correct* fix that structures the
      predicate differently fails L1 on an ImportError. docs/04 requires the
      opposite: relations are behavioral precisely so they "cannot reward
      imitating the historical fix's names", and a gate that does is not a gate
      on quality.

    Only `tests/` is pinned. Source stays at the candidate's ref — that is the
    thing under grading.
    """
    _git(worktree, "checkout", source_ref, "--", "tests")


def apply_patch(worktree: Path, patch: Path) -> None:
    if not patch.is_file():
        raise ArmError(f"patch not found: {patch}")
    proc = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", str(patch)],
        cwd=worktree, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise ArmError(
            f"git apply failed for {patch.name}: {proc.stderr.strip()[:300]} — a "
            "mutant that no longer applies is a mutant graded against a fix it was "
            "not derived from"
        )


def grade_candidate(
    repo: Path, task: Task, candidate: Candidate, timeout: int = 900,
    keep: bool = False,
) -> Grade:
    """Score one known-quality candidate on the ladder. No model in the loop."""
    dest = Path(tempfile.mkdtemp(prefix=f"oracle-{task.id}-{candidate.label}-"))
    worktree = dest / "tree"
    try:
        prepare_worktree(repo, candidate.ref, worktree)
        pin_pre_existing_suite(repo, worktree, task.source.ref)
        if candidate.patch is not None:
            apply_patch(worktree, candidate.patch)
        acceptance = evaluate_acceptance(task, worktree, timeout=timeout)
        return Grade(candidate, ladder_score(acceptance), acceptance)
    except (ArmError, subprocess.SubprocessError) as exc:
        return Grade(candidate, -1, [], str(exc)[:400])
    finally:
        if not keep:
            remove_worktree(repo, worktree)


def run_gate(
    repo: Path, task: Task, task_dir: Path, timeout: int = 900,
    keep: bool = False, anchors_only: bool = False,
) -> dict:
    """Grade anchors and mutants; the gate passes iff every rung matched."""
    issues: list[str] = []
    if not task.source.fix_ref.strip():
        return {
            "task": task.id,
            "passed": False,
            "grades": [],
            "issues": [
                "no source.fix_ref — the positive anchor is the fix commit, and "
                "without it there is nothing to validate against and nothing to "
                "degrade into mutants"
            ],
        }

    candidates = anchor_candidates(task)
    if not anchors_only:
        count = len(task.mutants)
        if not MUTANT_SET_MIN <= count <= MUTANT_SET_MAX:
            issues.append(
                f"{count} mutants — the design says {MUTANT_SET_MIN}–{MUTANT_SET_MAX} "
                "(docs/04). Anchors alone cover the range endpoints; the interior, "
                "where every observed arm sits, needs the mutant set"
            )
        candidates += mutant_candidates(task, task_dir)

    grades = [grade_candidate(repo, task, c, timeout=timeout, keep=keep)
              for c in candidates]

    # A rung that the *negative* anchor reaches beyond the gate is measuring the
    # repository rather than the candidate — lab/011's competence echo, mechanized.
    negative = next((g for g in grades if g.candidate.kind == "anchor-negative"), None)
    if negative and negative.rung > 1:
        issues.append(
            f"negative anchor scored rung {negative.rung}: the bug is present by "
            "construction, so a rung above the no-regression gate is measuring the "
            "repo, not the candidate (lab/011 competence echo)"
        )

    return {
        "task": task.id,
        "passed": all(g.ok for g in grades) and not issues,
        "grades": grades,
        "issues": issues,
    }


def render_gate(result: dict) -> str:
    """The full table, always — a gate that prints only its verdict hides which
    candidate disagreed, and the identity of the disagreement is the finding."""
    lines = [f"Oracle gate — {result['task']}", ""]
    # Width from the data, not a guess: a label wider than the column shoves every
    # later field right and the table stops being scannable exactly when it has
    # something to report.
    width = max([len(g.candidate.label) for g in result["grades"]] + [len("candidate")])
    header = f"  {'candidate':<{width}} {'kind':<16} {'expect':>6} {'got':>5}   verdict"
    lines += [header, "  " + "-" * (len(header) - 2)]
    for grade in result["grades"]:
        cand = grade.candidate
        got = "err" if grade.rung < 0 else f"L{grade.rung}"
        mark = "ok" if grade.ok else "MISMATCH"
        lines.append(
            f"  {cand.label:<{width}} {cand.kind:<16} {'L' + str(cand.expected_rung):>6} "
            f"{got:>5}   {mark}"
        )
        if grade.error:
            lines.append(f"      error: {grade.error}")
        elif not grade.ok:
            failed = [a for a in grade.acceptance if not a["passed"]]
            for entry in failed[:3]:
                name = entry.get("name") or entry["run"]
                lines.append(f"      L{entry.get('level', 1)} {name}: exit {entry['exit']}")
        if cand.mimics:
            lines.append(f"      mimics: {cand.mimics}")
    if result["issues"]:
        lines += ["", "Issues:"] + [f"  - {issue}" for issue in result["issues"]]
    lines += [
        "",
        "PASSED — the ladder reproduced every pre-registered rung"
        if result["passed"] else
        "FAILED — resolve in the open: either the expectation was wrong or the "
        "ladder is. Do not edit expected_rung to match the observation.",
    ]
    return "\n".join(lines)
