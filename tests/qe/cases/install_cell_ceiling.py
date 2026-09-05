"""`CELL_CEILING_S` must stay at least as large as a cell may legitimately spend.

`tests/qe/install/spec.py::CELL_CEILING_S` is a hard kill: `virt-install --wait`
destroys the domain the instant the guest has run this long, wherever it is in the
sequence. A ceiling smaller than the sum of the bounds a cell may legitimately spend
does not fail the install faster — it turns a reported finding into lost evidence,
because the domain dies mid-phase and the cell reports missing artifacts rather than
whatever it was reproducing.

That is not hypothetical. `CELL_CEILING_S` sat at 1800s (30 minutes) after both the
`wheel` phase and the `distill` phase were added to the matrix without anyone
re-deriving it — `installed-wheel`, which runs both, could legitimately need over
6000s. Twice is a pattern, and a hardcoded pair of numbers with a prose comment
between them (which is what caught it the first two times) will drift a third time the
same way: silently, the next time a phase or a timeout is added.

So this is not a check on today's number. It is a check that `CELL_CEILING_S` and
`spec.worst_case_matrix_seconds()` — a function over `spec.py`'s own STEPS, TIMEOUTS
and CONFIGS, not a second transcription of them — never disagree, on every push, for
as long as either one exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_INSTALL = Path(__file__).resolve().parents[1] / "install"
if str(_INSTALL) not in sys.path:
    sys.path.insert(0, str(_INSTALL))

import spec  # noqa: E402


def _ceiling_covers_the_worst_cell() -> Finding | None:
    worst = spec.worst_case_matrix_seconds()
    if worst > spec.CELL_CEILING_S:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary="a cell in the matrix may legitimately spend more time than "
                    "CELL_CEILING_S allows it, so virt-install's --wait would destroy "
                    "the domain mid-phase and the cell would report missing "
                    "artifacts rather than whatever it was reproducing",
            witness=f"worst_case_matrix_seconds()={worst}s > "
                    f"CELL_CEILING_S={spec.CELL_CEILING_S}s",
            site="tests/qe/install/spec.py CELL_CEILING_S",
        )
    return None


def _control_a_raised_timeout_is_caught() -> Finding | None:
    """The check above must be able to fail, or it is a check on nothing.

    A hardcoded ceiling that happens to sit above today's sum would pass this file
    forever without ever having read a single `TIMEOUTS` entry. The only way to show
    `worst_case_cell_seconds` actually sums what it claims to is to raise one bucket by
    more than the matrix's current headroom and watch the computed worst case cross
    `CELL_CEILING_S` in response — proving a future raise of a real timeout would be
    caught here too, not just today's number.
    """
    worst = spec.worst_case_matrix_seconds()
    headroom = spec.CELL_CEILING_S - worst
    raised = dict(spec.TIMEOUTS)
    raised["distill"] += headroom + 60
    raised_worst = spec.worst_case_matrix_seconds(raised)
    if raised_worst <= spec.CELL_CEILING_S:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="raising a real TIMEOUTS entry well past the matrix's current "
                    "headroom did not push the computed worst case over "
                    "CELL_CEILING_S, so the check above cannot actually detect a "
                    "timeout that grows past what the ceiling allows — it is "
                    "asserting on a number that does not read TIMEOUTS at all",
            witness=f"TIMEOUTS['distill'] raised by {headroom + 60}s -> "
                    f"worst_case_matrix_seconds()={raised_worst}s, still <= "
                    f"CELL_CEILING_S={spec.CELL_CEILING_S}s",
            site="tests/qe/install/spec.py worst_case_cell_seconds",
        )
    return None


def run() -> Finding | None:
    for probe in (_ceiling_covers_the_worst_cell, _control_a_raised_timeout_is_caught):
        finding = probe()
        if finding is not None:
            return finding
    return None


CASE = Case(
    name="install-cell-ceiling-covers-the-worst-case-sum",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="CELL_CEILING_S must stay at least as large as the worst cell's own "
            "phase timeouts can legitimately sum to, and the check must be shown to "
            "catch a timeout that grows past it",
    run=run,
)
