"""Emptiness must be asked with `not_(...)`, never with `count().is_(0)`.

Corpus record: `orphan-predicate-answered-clean` (`07dab84`). The orphan audit asked
`where(both_e().count().is_(0))` and got a clean `0` no matter how many orphans the
graph held: on an edgeless vertex `both_e()` yields an empty stream, so `where()` drops
the vertex before `count()` ever emits its zero. The predicate cannot be satisfied by
the vertices it exists to select. Asking the same question as `not_(both_e())` returned
**1114**, matching `contract check`.

Two properties make this the worst shape in the Gremlin vocabulary and worth a permanent
ban rather than a review note:

- It does not error. It answers *the graph is clean* — the reassuring direction — so
  nothing downstream has a reason to look twice.
- The terminal-step guard cannot catch it. The traversal does terminate; it terminates
  on the wrong thing, which is invisible to a check that only asks whether a result was
  materialised.

Asserted over the source. The behavioural version — build a graph holding one known
orphan, run both predicates, watch them disagree — is the better test and it needs a
live graph, which puts it in the deep tier alongside every other case that must write
vertices to mean anything. Until that tier exists, the shape itself is the thing that
can be checked, and the shape is what recurs: nobody reintroduces this by writing a
novel bug, they reintroduce it by writing the obvious-looking predicate.

The `gremlin-python` skill already teaches this in RECIPES.md ("Find orphan vertices"),
with the working `not_(__.both_e())` form and the measured 0-versus-1114 beside it. A
skill teaches the reader who consults it; this enforces it on the one who does not.

The rule this generalises to is in the corpus record and belongs beside the case: every
"is X clean" query needs a positive control holding one known-bad row. A query that can
only ever return the reassuring answer is not a check.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SRC = Path(__file__).resolve().parents[3] / "src" / "thalamus"

# `.count().is_(0)` in any filter position. Whitespace and line breaks between the steps
# are allowed because a formatter will put them there — the first version of this
# pattern required them adjacent and would have missed the defect as it actually shipped,
# which was wrapped across three lines.
_BANNED = re.compile(r"\.count\(\)\s*(?:\n\s*)?\.is_\(\s*0\s*\)")
# The traversal steps whose empty stream makes the predicate unsatisfiable. Named in the
# finding so the reader sees why this instance is the broken one.
_EDGE_STEPS = ("both_e", "in_e", "out_e", "bothE", "inE", "outE", "out", "in_")

_POISONED = """
orphans = (
    g.V()
    .has_label("Entity")
    .where(__.both_e().count()
           .is_(0))
    .count()
    .next()
)
"""


def _offenders(source: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for match in _BANNED.finditer(source):
        line = source[: match.start()].count("\n") + 1
        window = source[max(0, match.start() - 120) : match.end()].replace("\n", " ")
        step = next((s for s in _EDGE_STEPS if f"{s}(" in window), "")
        out.append((line, f"{'edge-step ' + step if step else 'traversal'} .count().is_(0)"))
    return out


def run() -> Finding | None:
    # CONTROL: the detector must flag the predicate as it shipped — wrapped across
    # lines, which is how it was written and how it will be written again.
    if not _offenders(_POISONED):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the detector no longer flags the predicate this defect shipped as, "
                    "so a clean scan of src/ would mean nothing",
            witness="poisoned fixture produced no match",
            site="tests/qe/cases/emptiness_predicate.py::_POISONED",
        )

    if not _SRC.is_dir():
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="source tree not found, so 'no banned predicate' means 'nothing read'",
            witness=str(_SRC),
            site="tests/qe/cases/emptiness_predicate.py",
        )

    files = sorted(_SRC.rglob("*.py"))
    violations: list[str] = []
    traversals = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        traversals += text.count("g.V(") + text.count("__.")
        violations += [
            f"{path.relative_to(_SRC.parents[1])}:{line} {why}"
            for line, why in _offenders(text)
        ]

    # CONTROL: the tree must contain Gremlin at all. A repo with no traversals satisfies
    # a rule about traversal shape trivially, and this case would then be guarding a
    # surface that had moved rather than a surface that is clean.
    if traversals == 0:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no Gremlin traversal was found in src/, so a clean result reports on "
                    "the scan rather than on the queries",
            witness=f"scanned {len(files)} file(s), matched 0 traversal constructions",
            site="tests/qe/cases/emptiness_predicate.py",
        )

    if not violations:
        return None

    return Finding(
        failure_class=FailureClass.FAILED_OPEN,
        summary=(
            "an emptiness predicate is written as count().is_(0): the empty stream drops "
            "the vertex before the zero is emitted, so the query cannot be satisfied by "
            "the rows it selects for and answers that the graph is clean"
        ),
        witness=f"{len(violations)} site(s) across {len(files)} file(s): "
                + "; ".join(violations[:6]),
        site="src/thalamus/** (Gremlin emptiness predicates)",
    )


CASE = Case(
    name="emptiness-asked-with-not-never-count-is-zero",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.FAILED_OPEN, FailureClass.COLLAPSED_SENTINEL),
    summary="the count().is_(0) predicate always answers clean; emptiness needs not_()",
    run=run,
)
