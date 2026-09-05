"""A writer that dies mid-append must not swallow the *next* writer's row.

The partial-write / crash-recovery shape of the qe charter's write-path gap (issue #76):
interrupt a write and assert the surviving state is consistent — the reader can still
parse it, or the write is absent, but never half-applied and silently accepted.

`closes._append()` (`src/thalamus/harness/closes.py:80`, byte-identical in shape to
`ceremonies._append()`) opens the ledger `"a"`, takes `fcntl.LOCK_EX`, and writes
`json.dumps(row, sort_keys=True) + "\\n"`. A process killed after the OS has accepted
some but not all of those bytes — a real and unremarkable failure mode, not a
contrived one — leaves the file with a trailing line that has no newline. `read_rows()`
tolerates a malformed *line* by design (`json.JSONDecodeError: continue`), which is the
right defense against a line that is garbage on its own. It does not defend against the
sharper case here: the next writer to open the file in append mode writes its own valid
JSON directly onto the end of that unterminated line, with nothing separating the two.
`read_rows()` then sees one line that parses as neither record and drops it whole —
discarding not only the row that was mid-write when the crash happened, but the
*next, fully valid write made after recovery*, with no error and no signal that
anything was lost.

**The mutation, run as the control.** `_append()` is not called for the crash: the
truncated bytes are written directly, byte-sliced from a real `json.dumps` encoding of a
row this module would have produced, cut at half its length with the trailing newline
withheld — the shape a `SIGKILL` mid-`write(2)` leaves. That is the only fabricated
input in this case; every other row comes from the real `propose()`. A clean-recovery
control (a valid row, properly newline-terminated, followed by another valid `propose()`
call) is run first and must recover both rows, or the comparator cannot be trusted to
tell a lost row from an absent one.

**Confirmed as a real defect, not asserted.** Filed as issue #169, tagged `issue=169,
fixed=False`, and pinned in `expectations.json`. Reproduction: propose one row, append
the first half of a second row's JSON with no trailing newline (the simulated crash),
then propose a third, valid row (the simulated post-crash resume) — `read_rows()`
returns only the first row; the third is gone, merged into the unparseable line the
crash left. Varying the truncation point (a quarter, three-quarters of the row) changes
nothing: any withheld newline reproduces the loss, which is what confirms the defect is
the missing separator rather than a specific offset.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier


def run() -> Finding | None:
    from thalamus.harness import closes  # noqa: PLC0415

    # --- Control: a clean, properly-terminated ledger recovers every row. ------------
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "closes.jsonl"
        closes.propose(thread_id="ctrl-1", scope="qe", basis="b", disposition="settled",
                        rationale="control row 1", proposed_by="qe-case", path=ledger)
        closes.propose(thread_id="ctrl-2", scope="qe", basis="b", disposition="settled",
                        rationale="control row 2 (simulates a clean post-restart write)",
                        proposed_by="qe-case", path=ledger)
        control_ids = [row["thread_id"] for row in closes.read_rows(ledger)]
        if control_ids != ["ctrl-1", "ctrl-2"]:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="two cleanly-appended rows were not both recovered, so this "
                        "case cannot distinguish crash-induced loss from ordinary "
                        "read_rows() behaviour",
                witness=f"recovered thread_ids: {control_ids}",
                site="tests/qe/cases/ledger_crash_recovery.py",
            )

    # --- The crash: a partial write with no trailing newline, then a resumed write. --
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "closes.jsonl"
        closes.propose(thread_id="pre-crash", scope="qe", basis="b",
                        disposition="settled", rationale="row before the crash",
                        proposed_by="qe-case", path=ledger)

        # The bytes a second `propose()` call would have written, truncated at half
        # its length with the newline withheld — a `write(2)` that lands only its
        # first half before the process dies.
        would_have_written = json.dumps(
            {"event": "proposed", "ref": "crashed-mid-write", "thread_id": "in-flight",
             "scope": "qe", "basis": "b", "disposition": "settled",
             "rationale": "never fully written", "proposed_by": "qe-case",
             "ts": "2026-01-01T00:00:00+00:00"},
            sort_keys=True,
        )
        truncated = would_have_written[: len(would_have_written) // 2]
        with ledger.open("a") as handle:
            handle.write(truncated)  # no trailing "\n" — the crash

        # The resumed process's first write after restart.
        closes.propose(thread_id="post-crash", scope="qe", basis="b",
                        disposition="settled", rationale="row written after recovery",
                        proposed_by="qe-case", path=ledger)

        recovered = [row["thread_id"] for row in closes.read_rows(ledger)]

    if recovered == ["pre-crash", "post-crash"]:
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "a partial write with no trailing newline is not fenced from the next "
            "writer's append: the next, fully valid row merges onto the truncated "
            "line and read_rows() drops the merged line whole, silently losing the "
            "row written after recovery rather than just the one in flight during "
            "the crash"
        ),
        witness=f"expected ['pre-crash', 'post-crash'], recovered {recovered}",
        site="src/thalamus/harness/closes.py:_append",
    )


CASE = Case(
    name="ledger-append-survives-a-partial-write",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a crash mid-append must not swallow the next writer's row",
    run=run,
    issue=169,
    fixed=False,
)
