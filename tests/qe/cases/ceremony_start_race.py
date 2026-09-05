"""Two concurrent `ceremonies.start()` calls on the same (room, kind) must not share
one `occasion_id`.

The concurrency shape of the qe charter's write-path gap (issue #76): two writers
interleaving on the same target must produce a consistent result, not a torn one.
`ceremonies.start()` (`src/thalamus/harness/ceremonies.py:301`) computes the next
occasion index by calling `next_index()`, which reads the whole ledger, and only *then*
calls `_append()`, whose `fcntl.LOCK_EX` covers just the write. The module's own
docstring on `_append` (line ~154) claims the lock is "held across read-then-append, not
just the write... two ceremonies opening in one room at once would otherwise both read
the same count and claim the same occasion." The code does not do this: the read
(`next_index`) happens in the caller, entirely outside `_append`'s lock, so the claim
describes an invariant the implementation does not enforce.

**Forcing the window, not hoping for it.** A real race between two `start()` calls is a
timing accident and would make this case flaky if it depended on scheduler luck.
Instead a `threading.Barrier(2)` is spliced into the case's own call to `next_index`
(rebound on the `ceremonies` module, restored in `finally`) so both threads are
guaranteed to finish reading the ledger before either is allowed to append — the exact
interleaving the docstring says cannot happen. This is a synchronization point injected
by the case, not a change to the module under test: `_append`'s lock, `next_index`'s
counting logic, and `start()`'s call order are exercised unmodified.

**The control.** Two sequential (non-racing) `start()` calls on the same (room, kind)
must produce two distinct occasion ids — asserted first, and reported as
COLLAPSED_SENTINEL if it fails, because a comparator that cannot tell apart two
sequential opens could not possibly tell apart two racing ones either.

**Confirmed as a real defect, not asserted.** Filed as issue #168, tagged `issue=168,
fixed=False`, and pinned in `expectations.json`. Reproduction: force the barrier as
above and call `start("room1", "retrospective")` from two threads; both rows land as
`occasion_id = "room1:retrospective:1"`. Widening the barrier to three threads
reproduces the same collision among three occasions instead of two, confirming the race
is in the read-then-append gap and not a two-thread special case.
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_ROOM = "qe-race-room"
_KIND = "retrospective"


def run() -> Finding | None:
    from thalamus.harness import ceremonies  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ceremonies.jsonl"

        # CONTROL: two sequential (non-racing) opens must claim distinct occasions.
        ceremonies.start(_ROOM, _KIND, path=ledger)
        ceremonies.start(_ROOM, _KIND, path=ledger)
        control_ids = sorted(
            row["occasion_id"] for row in ceremonies.read_rows(ledger)
            if row.get("event") == "start"
        )
        if len(set(control_ids)) != 2:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="two sequential (non-concurrent) start() calls did not claim "
                        "distinct occasion ids, so this case cannot distinguish a race "
                        "from ordinary behaviour",
                witness=f"sequential control ids: {control_ids}",
                site="tests/qe/cases/ceremony_start_race.py",
            )

    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ceremonies.jsonl"

        original_next_index = ceremonies.next_index
        barrier = threading.Barrier(2)

        def _racing_next_index(room, kind, rows=None, path=None):
            index = original_next_index(room, kind, rows=rows, path=path)
            # Both threads must finish this read before either is allowed to append —
            # the exact window the module's docstring says the lock closes.
            barrier.wait(timeout=5.0)
            return index

        ceremonies.next_index = _racing_next_index
        try:
            results: list[str] = []
            errors: list[str] = []

            def _worker():
                try:
                    row = ceremonies.start(_ROOM, _KIND, path=ledger)
                    results.append(row["occasion_id"])
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{type(exc).__name__}: {exc}")

            t1 = threading.Thread(target=_worker)
            t2 = threading.Thread(target=_worker)
            t1.start()
            t2.start()
            t1.join(timeout=10.0)
            t2.join(timeout=10.0)
        finally:
            ceremonies.next_index = original_next_index

        if errors or len(results) != 2:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the forced race did not complete both start() calls, so it "
                        "cannot be read as evidence about the race window",
                witness=f"results={results} errors={errors}",
                site="tests/qe/cases/ceremony_start_race.py",
            )

        if len(set(results)) == 2:
            return None

        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "ceremonies.start() reads next_index() outside _append()'s lock, so "
                "two concurrent opens of the same (room, kind) can both compute the "
                "same occasion index and append rows sharing one occasion_id — the "
                "module's own docstring claims this cannot happen"
            ),
            witness=f"two concurrent start() calls both produced occasion_id={results}",
            site="src/thalamus/harness/ceremonies.py:start,next_index,_append",
        )


CASE = Case(
    name="ceremony-start-serializes-concurrent-opens",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="two ceremonies opened at once in the same room must not share one occasion_id",
    run=run,
    issue=168,
    fixed=False,
)
