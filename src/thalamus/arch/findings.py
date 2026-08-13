"""What a scan asserts about the tree it read.

A finding is perishable. It is true of the commit it was measured at and of very few
others, which is why nothing here is stored anywhere. `thalamus arch rules` recomputes
the whole list in under a second against whatever tree you are actually on, and
`arch/model.yaml` — versioned by git beside the code it describes — retains the edge
list the findings are derived from. A *stored* finding needs supersession machinery to
carry the qualifier "this held at commit X"; a file in git carries it by being in git,
and a recomputed answer does not need the qualifier at all because it cannot be stale.

**Findings, never metrics.** Propagation cost is not an assertion, it is a reading. What
this module produces is a *finding* — a cycle, a violated rule, a module the declared
partition does not place — because those are the things a reader can act on or refute.

**No description names its scan.** A finding reads identically on every run that still
observes it, so two scans of one unchanged cycle produce the same sentence and the diff
between them is empty. That is what makes `arch diff` able to report structural change
rather than scan churn, and it is why the commit anchor lives on the model file rather
than folded into the text.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from thalamus.arch.extractor import DependencyGraph
from thalamus.arch.metrics import Metrics
from thalamus.arch.model import ArchModel

# Why a finding was raised, which decides who it is addressed to. A design finding is
# about the code and is the architect's to answer; an understanding finding is about the
# scanner's own reach and is a gap in the measurement, not in the tree.
DESIGN = "design"
UNDERSTANDING = "understanding"


@dataclass(frozen=True)
class Finding:
    """One thing a scan asserts, and the modules it is about."""

    description: str
    category: str = DESIGN
    artifacts: tuple[str, ...] = field(default_factory=tuple)


def findings(graph: DependencyGraph, metrics: Metrics, model: ArchModel) -> list[Finding]:
    """What this scan asserts. Empty is the healthy outcome, not a failed run."""
    found: list[Finding] = []

    for cycle in metrics.cycles:
        found.append(
            Finding(
                description=f"Import cycle among {len(cycle)} modules: {', '.join(cycle)}.",
                category=DESIGN,
                artifacts=tuple(cycle),
            )
        )

    for violation in model.violations(graph):
        found.append(
            Finding(
                description=f"Dependency rule violated: {violation.describe()}.",
                category=DESIGN,
                artifacts=(violation.from_path, violation.to_path),
            )
        )

    unplaced = model.unplaced(graph) if model.layers else []
    if unplaced:
        found.append(
            Finding(
                description=(
                    f"The declared layer partition does not place {len(unplaced)} of "
                    f"{len(graph.modules)} scanned modules."
                ),
                category=DESIGN,
                artifacts=tuple(sorted(unplaced)[:20]),
            )
        )

    for note in graph.unresolved:
        found.append(
            Finding(
                description=f"Scanner could not read a module: {note}.",
                category=UNDERSTANDING,
                artifacts=(note.split(":")[0],),
            )
        )

    for note in model.stale_authored_paths(graph):
        found.append(
            Finding(
                description=f"Authored model has rotted: {note}.",
                category=DESIGN,
                artifacts=(),
            )
        )
    return found
