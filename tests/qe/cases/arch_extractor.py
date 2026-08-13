"""The architect's extractor must reproduce a hand-counted edge list, exactly.

This case is the gate the instrument's own design named a hard one. The reason is
recorded rather than inferred: the architect published propagation-cost figures twice
from ad-hoc extractors and retracted them both, and its self-audit found the errors ran
in one direction — a *cleaner* answer, fewer edges, fewer cycles. An extractor with no
ground truth cannot tell a clean repo from a lossy walk, and every number it emits
inherits that ambiguity.

So the fixture at `tests/qe/fixtures/arch_fixture/` is five modules whose every edge was
counted by hand, chosen to cover exactly the forms that separate two defensible
implementations:

- `from app import core` where the alias IS a submodule (the package half is a second,
  real dependency)
- `from app.deep.inner import late` where the alias is a *function* (the package half is
  the same module, and a second edge would be double-counting)
- `import app.util`, the dotted form
- `from .. import util`, a relative import climbing two levels
- a deferred `from app import core` inside a function body, closing a cycle that a
  module-level-only reading cannot see
- `import os`, which must leave no edge at all

The expectations are literals. When this case fails, the question is which side is
wrong — and the fixture is small enough that a human can settle it in a minute, which is
the property that makes it ground truth rather than a second opinion.
"""

from __future__ import annotations

from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "arch_fixture"

# Hand-counted. One row per (from, to, kind); a pair imported both at module level and
# inside a function is one row at the shallower depth.
EXPECTED_EDGES = (
    "src/app/__init__.py -> src/app/core.py [from,module]",
    "src/app/core.py -> src/app/deep/__init__.py [package,deferred]",
    "src/app/core.py -> src/app/deep/inner.py [from,module]",
    "src/app/core.py -> src/app/util.py [import,module]",
    "src/app/deep/inner.py -> src/app/__init__.py [package,module]",
    "src/app/deep/inner.py -> src/app/core.py [from,deferred]",
    "src/app/deep/inner.py -> src/app/util.py [from,module]",
)

EXPECTED_MODULES = 5

# (import_depth, resolve) -> (counted edges, modules in cycles)
EXPECTED_READINGS = {
    ("all", "deepest-matching-module"): (5, 2),
    ("module-level", "deepest-matching-module"): (4, 0),
    ("all", "module-and-package"): (7, 3),
    ("module-level", "module-and-package"): (5, 3),
}

# Visibility density under the default policy, counted by hand over the five modules:
# app/__init__ reaches {itself, core, inner, util} = 4, core {itself, inner, util} = 3,
# inner {itself, core, util} = 3, util 1, deep/__init__ 1. 12 of 25 cells = 48%.
EXPECTED_PROPAGATION = 48.0


def run() -> Finding | None:
    from thalamus.arch.extractor import ExtractorPolicy, scan_repo  # noqa: PLC0415
    from thalamus.arch.metrics import measure  # noqa: PLC0415

    graph = scan_repo(FIXTURE, ExtractorPolicy(roots=("src",)))
    observed = tuple(edge.as_row() for edge in graph.edges)

    if observed != EXPECTED_EDGES:
        missing = [row for row in EXPECTED_EDGES if row not in observed]
        extra = [row for row in observed if row not in EXPECTED_EDGES]
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "The extractor's edge list disagrees with the hand-counted fixture: "
                f"{len(missing)} missing, {len(extra)} unexpected."
            ),
            witness=f"missing: {missing}; unexpected: {extra}",
            site="src/thalamus/arch/extractor.py:scan_repo",
        )

    if len(graph.modules) != EXPECTED_MODULES:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary="The extractor did not collect the fixture's five modules.",
            witness=f"expected {EXPECTED_MODULES}, collected {len(graph.modules)}: {graph.modules}",
            site="src/thalamus/arch/extractor.py:_collect_modules",
        )

    for (depth, resolve), (edges, in_cycles) in EXPECTED_READINGS.items():
        policy = ExtractorPolicy(roots=("src",), import_depth=depth, resolve=resolve)
        metrics = measure(scan_repo(FIXTURE, policy))
        if (metrics.dependencies, metrics.modules_in_cycles) != (edges, in_cycles):
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary=(
                    f"Policy import_depth={depth}/resolve={resolve} counted "
                    f"{metrics.dependencies} edges and {metrics.modules_in_cycles} modules "
                    f"in cycles; the fixture is hand-counted at {edges} and {in_cycles}."
                ),
                witness=(
                    f"counted={metrics.dependencies} expected={edges}; "
                    f"in_cycles={metrics.modules_in_cycles} expected={in_cycles}"
                ),
                site="src/thalamus/arch/extractor.py:ExtractorPolicy.counts_edge",
            )

    propagation = round(measure(scan_repo(FIXTURE, ExtractorPolicy(roots=("src",)))).propagation_cost * 100, 2)
    if propagation != EXPECTED_PROPAGATION:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                f"Propagation cost over the fixture is {propagation}%, hand-counted at "
                f"{EXPECTED_PROPAGATION}%."
            ),
            witness=f"observed {propagation}%, expected {EXPECTED_PROPAGATION}% (12 of 25 cells)",
            site="src/thalamus/arch/metrics.py:propagation_cost",
        )

    return None


CASE = Case(
    name="arch-extractor-ground-truth",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED,),
    summary=(
        "The import extractor reproduces a hand-counted edge list over a five-module "
        "fixture, under all four declared policy readings."
    ),
    run=run,
)
