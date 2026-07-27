"""The counterfactual task battery — layer 2's pre-registered half (docs/04).

A task is a tier-0 operator artifact under config/tasks/: one YAML file holding
the prompt, a mechanical acceptance check, 1–3 consequence probes, an optional
judge rubric, and a disclosed memory-overlap tag. Pre-registration is enforced
structurally, not by promise: the battery must validate before any arm runs, and
the file's git history is the registration timestamp — an acceptance test edited
after a campaign is a visible diff, not a silent regrade.

Like expert manifests, tasks are operator files rather than graph nodes: what
counts as success is a curation decision, and tier-0 lives where no feed or model
can write (docs/01). Consequence probes are the live analog of MQuAKE's multi-hop
checks — recall of a stored fact and action on its implications are different
measurements (arXiv 2305.14795) — and of Mem2ActBench's memory-grounded tool-call
tasks (arXiv 2601.19935). Design: docs/04 layer 2; eval-methodology consultation
`scope:main:exchange:8644614d1b1242a4`.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

_DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "config"

OVERLAP_STRATA = ("memorization", "transferable")
SOURCE_KINDS = ("replayed", "authored")
PROBE_KINDS = ("transcript_regex", "diff_regex", "command")

# The built rungs: 1 no-regression gate, 2 behavioral oracle, then one rung per
# nested metamorphic relation (3=R1, 4=R2, 5=R3, each strictly implying the one
# below). Successive rungs are how nested relations supply resolution — and this
# is *not* the counting that would reimport the cardinality bias, precisely
# because the relations nest: a further relation can only extend the top of the
# ladder, never let a cheap check buy a rung.
#
# 6 (judge) is reserved and deliberately unbuilt: judge reliability is an open
# problem needing its own meta-evaluation, and nesting supplies resolution
# without it.
LADDER_LEVELS = (1, 2, 3, 4, 5)
JUDGE_LEVEL = 6

# Tokens that betray the memory surface. A rung mentioning one of these is
# measuring whether the arm had memory, not whether its fix is good.
ARM_REVEALING_TOKENS = (
    "mcp__thalamus__",
    "memory_recall",
    "memory_open_threads",
    "THALAMUS_SCOPE",
    "ToolSearch",
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class Acceptance(BaseModel):
    """One mechanical check on a rung of the ladder.

    `level` is the ladder rung this check belongs to (docs/04): the run's score
    is the highest level whose checks — and every lower level's — all pass.
    Ordinal, not a weighted sum: there are no weights to fit, and adding a
    cheap check to a rung cannot buy a higher score, which is the cardinality
    bias a weighted sum imports (arXiv 2601.03525).
    """

    run: str
    expect_exit: int = 0
    level: int = Field(
        1,
        description=(
            "1 = no-regression gate, 2 = targeted behavioral oracle, "
            "3/4/5 = nested metamorphic relations R1 ⊂ R2 ⊂ R3. "
            "Level 6 (judge) is reserved. "
            "Defaults to the gate: an undeclared check is the most basic "
            "requirement, so a task that never opts into the ladder still "
            "scores rung 1 rather than tripping the gap rule."
        ),
    )
    name: str = Field("", description="Short label for the rung's report line")


class Probe(BaseModel):
    """A consequence probe: true only if the memory's *implications* were acted on.

    `meaning` is mandatory — a probe nobody can interpret is decoration, and the
    report quotes it next to the verdict.
    """

    id: str
    kind: str
    meaning: str
    pattern: str = ""  # transcript_regex / diff_regex
    run: str = ""  # command
    expect_exit: int = 0


class TaskSource(BaseModel):
    kind: str
    ref: str = Field("", description="Git ref the arm's worktree starts from")
    evidence: str = Field(
        "", description="Replayed tasks: the session/commit this replays"
    )
    fix_ref: str = Field(
        "",
        description=(
            "Replayed tasks: the commit that actually fixed this bug — the "
            "oracle's positive anchor. Structured because the anchor is graded "
            "mechanically; naming it only in `evidence` prose puts it out of "
            "reach of the runner."
        ),
    )


class Mutant(BaseModel):
    """A degradation of the known-good fix, with its rung committed in advance.

    Mutants exist because the anchor pair validates the ladder's *range* and
    nothing else: the negative anchor is the worst possible candidate and the
    positive anchor the best, while every observed arm sits in the interior
    between them. Discrimination there has to be measured against candidates
    whose quality is known by construction (arXiv 2212.06118).

    `mimics` is mandatory, and it is the whole reason this is not classical
    mutation testing. The classical licence for mutants-as-fault-proxies is the
    competent programmer hypothesis plus the coupling effect (arXiv 2103.07189
    finds mutants coupled to real high-priority faults; arXiv 2512.16741 makes
    coupling a measured quantity rather than an assumption) — but both describe
    *human* programmers making small syntactic slips. The defects this instrument
    grades come from LLM agents, which fail differently: plausible wholesale
    rewrites, over-fixes that touch behavior the report never mentioned, fixes
    correct at one call site and absent at the others. A mutant built from
    classical operators would be coupled to the wrong fault distribution, so each
    one here names the observed arm behavior it stands in for, and the naming is
    enforced rather than attested.
    """

    id: str
    patch: str = Field(description="Patch file, relative to the task file's directory")
    expected_rung: int = Field(
        description=(
            "The rung this degraded candidate should score. Committed before the "
            "gate runs — git history is the pre-registration timestamp. A "
            "disagreement is resolved in the open (either the expectation was "
            "wrong or the ladder is), never by quietly editing this number."
        )
    )
    mimics: str = Field(
        description=(
            "The observed agent failure mode this mutant stands in for. Required: "
            "see the class docstring — an unnamed mutant is coupled to the human "
            "fault distribution, not the one being sampled."
        )
    )
    rationale: str = ""


class Task(BaseModel):
    task: str = "v0"
    id: str
    title: str
    overlap: str
    source: TaskSource
    prompt: str
    acceptance: list[Acceptance] = Field(default_factory=list)
    probes: list[Probe] = Field(default_factory=list)
    mutants: list[Mutant] = Field(default_factory=list)
    rubric: str = ""

    def check(self) -> list[str]:
        """The pre-registration obligations, as issues. Empty means armable."""
        issues: list[str] = []
        if self.task != "v0":
            issues.append(f"unknown task format `{self.task}` (this build reads v0)")
        if not _ID_RE.match(self.id):
            issues.append(f"id `{self.id}` is not a lowercase slug")
        if self.overlap not in OVERLAP_STRATA:
            issues.append(
                f"overlap `{self.overlap}` is not a stratum "
                f"({', '.join(OVERLAP_STRATA)}) — undisclosed overlap is the hidden "
                "confound the tag exists to surface"
            )
        if self.source.kind not in SOURCE_KINDS:
            issues.append(f"source.kind `{self.source.kind}` not in {SOURCE_KINDS}")
        elif self.source.kind == "replayed" and not self.source.evidence.strip():
            issues.append(
                "replayed task carries no evidence pointer — a replay that can't "
                "name the session/commit it replays is an authored task wearing a tag"
            )
        if self.source.kind == "replayed" and not self.source.fix_ref.strip():
            issues.append(
                "replayed task has no source.fix_ref — the commit that actually "
                "fixed the bug is the oracle's positive anchor, and without it "
                "the task's grading cannot be validated against ground truth"
            )
        if self.source.kind == "authored" and self.source.fix_ref.strip():
            issues.append(
                "authored task declares a fix_ref — an authored task has no "
                "historical fix; anchor-based validation does not apply to it "
                "(it needs metamorphic relations instead)"
            )
        if not self.prompt.strip():
            issues.append("prompt is empty")
        if not self.acceptance:
            issues.append(
                "no mechanical acceptance — success may not be decided after the "
                "runs (pre-registration, docs/04 layer 2)"
            )
        for i, acc in enumerate(self.acceptance):
            if not acc.run.strip():
                issues.append(f"acceptance[{i}] has an empty run command")
            if acc.level not in LADDER_LEVELS:
                issues.append(
                    f"acceptance[{i}] level {acc.level} is not a built rung "
                    f"({', '.join(str(x) for x in LADDER_LEVELS)}; "
                    f"{JUDGE_LEVEL} is reserved for the judge and unbuilt)"
                )
            # Arm-independent reachability. A rung a memory-off arm cannot reach
            # on its own merits is not a rung — it is an arm label wearing a
            # score, and grading it would make memory-on > memory-off true by
            # construction. The manipulation check (`probes`) is where delivery
            # of the intervention is measured; it stays outside the score.
            leaked = sorted({
                token for token in ARM_REVEALING_TOKENS
                if token in acc.run
            })
            if leaked:
                issues.append(
                    f"acceptance[{i}] references {', '.join(leaked)} — a ladder "
                    "rung must be reachable by an arm with no memory surface. "
                    "Delivery of the intervention belongs in `probes`, never in "
                    "the score."
                )
        levels = {acc.level for acc in self.acceptance}
        for missing in sorted(x for x in levels if x - 1 in LADDER_LEVELS and x - 1 not in levels):
            issues.append(
                f"ladder has a rung at level {missing} but none at {missing - 1} "
                "— the score is the highest rung with every lower rung satisfied, "
                "so a gap makes the upper rung unreachable"
            )
        if not 1 <= len(self.probes) <= 3:
            issues.append(
                f"{len(self.probes)} consequence probes — the design says 1–3 "
                "(recall of a fact and action on its implications are different "
                "measurements; zero probes measures only surfacing)"
            )
        seen_probe_ids: set[str] = set()
        for probe in self.probes:
            where = f"probe `{probe.id}`"
            if probe.id in seen_probe_ids:
                issues.append(f"{where}: duplicate probe id")
            seen_probe_ids.add(probe.id)
            if probe.kind not in PROBE_KINDS:
                issues.append(f"{where}: kind `{probe.kind}` not in {PROBE_KINDS}")
                continue
            if not probe.meaning.strip():
                issues.append(f"{where}: no meaning — an uninterpretable probe")
            if probe.kind in ("transcript_regex", "diff_regex"):
                if not probe.pattern:
                    issues.append(f"{where}: {probe.kind} needs a pattern")
                else:
                    try:
                        compiled = re.compile(probe.pattern)
                    except re.error as exc:
                        issues.append(f"{where}: pattern does not compile ({exc})")
                    else:
                        # Prompt echo, both routes (measured 2026-07-19): the
                        # transcript always contains the prompt, and prompt-named
                        # strings reach the diff through test fixtures and
                        # comments. Either way the probe is pre-satisfied by the
                        # task itself.
                        if compiled.search(self.prompt):
                            issues.append(
                                f"{where}: pattern matches the task's own prompt — "
                                "pre-satisfied in every arm (the transcript "
                                "contains the prompt; diffs inherit prompt-named "
                                "strings through fixtures and comments)"
                            )
            elif probe.kind == "command" and not probe.run.strip():
                issues.append(f"{where}: command probe needs a run")
        issues.extend(self._check_mutants())
        return issues

    def _check_mutants(self) -> list[str]:
        """Mutant well-formedness. The set's *size* is the gate's business, not
        arming's: a half-authored mutant set should not stop a campaign, but a
        malformed mutant should never reach the gate."""
        issues: list[str] = []
        if self.mutants and not self.source.fix_ref.strip():
            issues.append(
                "mutants declared with no source.fix_ref — a mutant is a "
                "degradation *of the known-good fix*, so without one there is "
                "nothing to degrade and no rung to expect"
            )
        top = max(LADDER_LEVELS)
        seen: set[str] = set()
        for mutant in self.mutants:
            where = f"mutant `{mutant.id}`"
            if not _ID_RE.match(mutant.id):
                issues.append(f"{where}: id is not a lowercase slug")
            if mutant.id in seen:
                issues.append(f"{where}: duplicate mutant id")
            seen.add(mutant.id)
            if not mutant.patch.strip():
                issues.append(f"{where}: no patch file")
            if not 0 <= mutant.expected_rung <= top:
                issues.append(
                    f"{where}: expected_rung {mutant.expected_rung} outside 0–{top} "
                    "(0 is the rung of a candidate that fails the no-regression gate)"
                )
            if not mutant.mimics.strip():
                issues.append(
                    f"{where}: no `mimics` — a mutant that names no observed agent "
                    "failure mode is coupled to the human fault distribution the "
                    "classical hypotheses describe, not the one being sampled"
                )
        return issues


def tasks_dir(base: Path | None = None) -> Path:
    override = os.environ.get("THALAMUS_CONFIG_DIR")
    root = base or (Path(override) if override else _DEFAULT_CONFIG)
    return root / "tasks"


def load_battery(base: Path | None = None) -> tuple[list[Task], list[str]]:
    """Every task in the battery, plus every violation. Both lists are honest:
    a task that fails validation still loads if it parses, so the report can
    name what's wrong with it rather than pretending it doesn't exist."""
    directory = tasks_dir(base)
    tasks: list[Task] = []
    issues: list[str] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            issues.append(f"{path.name}: unparseable YAML ({exc})")
            continue
        try:
            task = Task(**(data or {}))
        except ValidationError as exc:
            issues.append(f"{path.name}: {exc.error_count()} schema error(s) — {exc}")
            continue
        if task.id != path.stem:
            issues.append(
                f"{path.name}: declares id `{task.id}` — the filename is the id"
            )
        issues.extend(f"{path.name}: {issue}" for issue in task.check())
        tasks.append(task)
    counts = Counter(task.id for task in tasks)
    issues.extend(
        f"duplicate task id `{task_id}`" for task_id, n in counts.items() if n > 1
    )
    return tasks, issues


def render_battery(tasks: list[Task], issues: list[str]) -> str:
    """The battery as the operator reads it before a campaign."""
    lines: list[str] = []
    if not tasks:
        lines.append("Battery is empty — no tasks under config/tasks/.")
    for task in tasks:
        rubric = "rubric" if task.rubric.strip() else "no rubric (mechanical only)"
        # An unvalidated ladder is worth naming: anchors cover the range, mutants
        # cover the interior where the arms actually sit (docs/04).
        mutants = (
            f"{len(task.mutants)} mutant(s)" if task.mutants
            else "no mutant set (ladder unvalidated in the interior)"
        )
        lines.append(
            f"{task.id} [{task.overlap} · {task.source.kind}] — {task.title}\n"
            f"  {len(task.acceptance)} acceptance, {len(task.probes)} probe(s), "
            f"{mutants}, {rubric}"
        )
    strata = Counter(task.overlap for task in tasks)
    if tasks:
        strata_line = ", ".join(
            f"{strata.get(s, 0)} {s}" for s in OVERLAP_STRATA
        )
        lines.append(f"\nStrata: {strata_line} — arms report per stratum, never pooled.")
        if not strata.get("transferable"):
            lines.append(
                "  Note: no transferable-stratum tasks yet; campaign claims stay "
                "scoped to the memorization stratum until some exist."
            )
    if issues:
        lines.append(f"\n{len(issues)} pre-registration violation(s):")
        lines.extend(f"  - {issue}" for issue in issues)
        lines.append("The battery does not arm until these are fixed.")
    elif tasks:
        lines.append("Battery OK — every task carries its oracle before any arm runs.")
    return "\n".join(lines)
