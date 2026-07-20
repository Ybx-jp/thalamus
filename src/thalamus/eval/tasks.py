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

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class Acceptance(BaseModel):
    """One mechanical check: a command and the exit code that means pass."""

    run: str
    expect_exit: int = 0


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


class Task(BaseModel):
    task: str = "v0"
    id: str
    title: str
    overlap: str
    source: TaskSource
    prompt: str
    acceptance: list[Acceptance] = Field(default_factory=list)
    probes: list[Probe] = Field(default_factory=list)
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
                        # The transcript always contains the prompt (measured on
                        # the first live smoke run, 2026-07-19: a probe hit on a
                        # phrase the prompt itself used).
                        if probe.kind == "transcript_regex" and compiled.search(
                            self.prompt
                        ):
                            issues.append(
                                f"{where}: pattern matches the task's own prompt — "
                                "the transcript always contains the prompt, so "
                                "this probe is pre-satisfied in every arm"
                            )
            elif probe.kind == "command" and not probe.run.strip():
                issues.append(f"{where}: command probe needs a run")
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
        lines.append(
            f"{task.id} [{task.overlap} · {task.source.kind}] — {task.title}\n"
            f"  {len(task.acceptance)} acceptance, {len(task.probes)} probe(s), {rubric}"
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
