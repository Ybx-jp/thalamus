"""No test definition may shadow another, because Python keeps the last one silently.

Corpus record: `merge-duplicated-the-guard` (`bde137d`). Git reported a clean automatic
merge and produced two stacked copies of the SessionEnd guard — and the test file merged
the same way, into two identical class definitions. Python binds the last one, so the
shadowed copy collected nothing, and the pass count went up rather than down. Coverage
disappeared while every visible signal said the suite was healthy.

That is the worst shape a test defect can take. A failing test is loud; a test that is
no longer collected is indistinguishable from a test that passes, and the thing it
guarded goes unwatched with a green tick beside it. It applies to this suite too: a
shadowed case here would leave an expectation acknowledging a defect nothing checks any
more, and the runner would report `known-red` for a case that never ran.

Scanned at module top level and inside class bodies only. A name bound in an `if` or
`try` branch is a deliberate fallback, not a shadow, and counting it would make this
case a nuisance rather than an oracle. Property setters and `@overload` chains
legitimately repeat a name and are exempted by decorator.

Nothing is shadowed today, so this is a forward guard, and a forward guard that asserts
an absence has to be shown capable of noticing the thing coming back. The detector is a
pure function over source text and runs first against a module carrying the exact
duplication the merge produced.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_TESTS = Path(__file__).resolve().parents[2]

# Decorators under which a repeated name is a language idiom rather than a shadow.
_REPEATABLE = ("setter", "getter", "deleter", "overload")

_POISONED = """
class TestSessionEndGuard:
    def test_a_room_transcript_is_not_skipped(self):
        assert True


class TestSessionEndGuard:
    def test_a_room_transcript_is_not_skipped(self):
        assert True
"""


def _decorators(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    out: set[str] = set()
    for deco in node.decorator_list:
        target = deco.func if isinstance(deco, ast.Call) else deco
        if isinstance(target, ast.Attribute):
            out.add(target.attr)
        elif isinstance(target, ast.Name):
            out.add(target.id)
    return out


def _shadowed(source: str) -> list[str]:
    """Names defined more than once in the same body. Pure over text, so it is testable."""
    tree = ast.parse(source)
    found: list[str] = []

    def scan(body: list[ast.stmt], where: str) -> None:
        counts: Counter[str] = Counter()
        exempt: set[str] = set()
        for node in body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                counts[node.name] += 1
                if _decorators(node) & set(_REPEATABLE):
                    exempt.add(node.name)
            elif isinstance(node, ast.ClassDef):
                counts[node.name] += 1
        for name, count in counts.items():
            if count > 1 and name not in exempt:
                found.append(f"{where}{name} defined {count}x — only the last one runs")

    scan(tree.body, "")
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            scan(node.body, f"{node.name}.")
    return found


def run() -> Finding | None:
    # CONTROL: the detector must flag the duplication the merge actually produced.
    # Run first, so a clean tree can never be reported by a detector that stopped
    # matching — "nothing is shadowed" and "nothing was examined" are the same output.
    if not _shadowed(_POISONED):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the detector no longer flags a duplicated class and method, so a "
                    "clean scan of the test tree would mean nothing",
            witness="poisoned fixture produced no finding",
            site="tests/qe/cases/shadowed_tests.py::_POISONED",
        )

    modules = sorted(_TESTS.rglob("*.py"))
    if not modules:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no test modules were found, so 'nothing shadowed' means 'nothing read'",
            witness=str(_TESTS),
            site="tests/qe/cases/shadowed_tests.py",
        )

    violations: list[str] = []
    unparseable: list[str] = []
    for path in modules:
        try:
            found = _shadowed(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError as exc:
            unparseable.append(f"{path.relative_to(_TESTS.parent)}: {exc}")
            continue
        violations += [f"{path.relative_to(_TESTS.parent)}: {entry}" for entry in found]

    # A module this pass cannot read is a module it cannot clear. Reported as a broken
    # check rather than folded into a clean result, since the alternative is a scan that
    # silently covers less of the tree every time something new fails to parse.
    if unparseable:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="a test module could not be parsed, so its definitions were neither "
                    "cleared nor flagged",
            witness="; ".join(unparseable[:4]),
            site="tests/**",
        )

    if not violations:
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "a test definition shadows another: Python binds the last one, so the "
            "shadowed body is never collected and its coverage vanishes while the pass "
            "count goes up"
        ),
        witness=f"{len(violations)} shadowed definition(s) across "
                f"{len(modules)} module(s): " + "; ".join(violations[:6]),
        site="tests/**",
    )


CASE = Case(
    name="no-test-definition-shadows-another",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a duplicated test name silently drops coverage while the suite stays green",
    run=run,
)
