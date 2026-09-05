"""The occasion counter must land on the same final state regardless of call order.

The ordering-independence shape of the qe charter's write-path gap (issue #76): apply
the same set of inputs in two different orders and assert the same final state.
`next_index()` (`src/thalamus/harness/ceremonies.py:185`) numbers *occasions*, not
*runs* — its own docstring is explicit that "a skipped ceremony consumes an index," so a
room's `start()` and `skip()` calls share one counter. That makes order a live question:
if `skip()` secretly failed to consume an index the way `start()` does, or consumed two,
the same three calls made in a different order would land on different final indices —
exactly the kind of drift item 2 in the module's docstring exists to keep from being
invisible.

This case writes the same multiset — two `start()`s and one `skip()`, on one
`(room, kind)` — in two different orders against two independent ledgers, and asserts
both land on occasion indices `{1, 2, 3}` with none skipped or repeated. Every write here
is real: `ceremonies.start()` and `ceremonies.skip()` unmodified, each against its own
tmpdir ledger via the `path` parameter.

**The mutation, run as the control.** The comparison the case makes is a small pure
function, `_indices_consistent()`, over two lists of ints. Before trusting it against
the real orderings, the case calls it once against a poisoned pair — the first order's
real indices against a copy with one index duplicated and another dropped (a
same-length forgery a lazy `len(a) == len(b)` check would miss) — and requires it to
report the mismatch. A comparator that passed the poisoned pair could not be trusted to
fail the real one either, so that result is COLLAPSED_SENTINEL rather than a pass.

Green here is a claim about `next_index()` and `_append()`'s shared counting logic, not
about this case's arithmetic — the poisoned-pair check is what tells them apart.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_ROOM = "qe-ordering-room"
_KIND = "review"


def _run_order(ops: tuple[str, ...]) -> list[int]:
    from thalamus.harness import ceremonies  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ceremonies.jsonl"
        for op in ops:
            if op == "start":
                ceremonies.start(_ROOM, _KIND, path=ledger)
            elif op == "skip":
                ceremonies.skip(_ROOM, _KIND, path=ledger)
            else:  # pragma: no cover - a case bug, not a finding
                raise ValueError(f"unknown op {op!r}")
        return [row["occasion_index"] for row in ceremonies.read_rows(ledger)]


def _indices_consistent(a: list[int], b: list[int]) -> bool:
    """True iff both orderings produced the same set of consecutive indices from 1."""
    expected = list(range(1, len(a) + 1))
    return sorted(a) == expected and sorted(b) == expected


def run() -> Finding | None:
    order_a = ("start", "skip", "start")
    order_b = ("skip", "start", "start")

    indices_a = _run_order(order_a)
    indices_b = _run_order(order_b)

    # CONTROL: the comparator itself must be able to see a divergence. A same-length
    # forgery (one index duplicated, another dropped) is what a naive `len()`-only
    # check would miss.
    poisoned = sorted(indices_a)[:-1] + [sorted(indices_a)[0]] if indices_a else [1, 1]
    if _indices_consistent(indices_a, poisoned):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the ordering comparator did not flag a poisoned index list with "
                    "a duplicate and a gap, so it cannot be trusted to flag a real "
                    "ordering divergence either",
            witness=f"real={sorted(indices_a)} poisoned={sorted(poisoned)} both read "
                    f"as consistent",
            site="tests/qe/cases/ceremony_index_ordering.py:_indices_consistent",
        )

    if _indices_consistent(indices_a, indices_b):
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "the same set of start()/skip() calls on one (room, kind) landed on "
            "different final occasion indices depending on call order, so "
            "next_index()'s counting is order-dependent rather than counting "
            "occasions as its own docstring claims"
        ),
        witness=f"order {order_a} -> indices {indices_a}; "
                f"order {order_b} -> indices {indices_b}",
        site="src/thalamus/harness/ceremonies.py:next_index",
    )


CASE = Case(
    name="ceremony-occasion-count-is-order-independent",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="the same start()/skip() calls in a different order must land on the "
            "same final occasion indices",
    run=run,
)
