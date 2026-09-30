"""A writer that dies mid-append must not swallow the *next* writer's row.

The partial-write / crash-recovery shape of the qe charter's write-path gap (issue #76):
interrupt a write and assert the surviving state is consistent — the reader can still
parse it, or the write is absent, but never half-applied and silently accepted.

A process killed after the OS has accepted some but not all of a row's bytes leaves the
ledger with a trailing line that has no newline. `read_rows()` skips a malformed line by
design; the append path (`harness/ledger_io.write_row`, used by `closes` and
`ceremonies`) writes a newline first when the file does not end in one, so the next
row lands on its own line and only the in-flight row is lost.

**The mutation, run as the control.** The crash is simulated by writing a real
`json.dumps` row cut at half its length with the newline withheld — the shape a
`SIGKILL` mid-`write(2)` leaves; every other row comes from the real `propose()`. A
clean-recovery control (two properly terminated rows) runs first and must recover both,
or the comparator cannot tell a lost row from an absent one.

**Mutation that drives it red.** Against 9b02207, where `_append()` wrote
`json.dumps(row) + "\\n"` straight after the partial line, `read_rows()` returns only
`['pre-crash']`: the post-crash row merges into the unparseable line. Any truncation
point reproduces it; the missing separator is the defect, not an offset.
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
        # A writer killed after its last byte but before the newline leaves a complete
        # row; the fence must end that line, not merge the next row into it.
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "closes.jsonl"
            with ledger.open("a") as handle:
                handle.write(json.dumps({"event": "proposed", "ref": "r1",
                                          "thread_id": "unterminated", "scope": "qe"}))
            closes.propose(thread_id="after", scope="qe", basis="b",
                            disposition="settled", rationale="r",
                            proposed_by="qe-case", path=ledger)
            recovered = [row["thread_id"] for row in closes.read_rows(ledger)]
        if recovered == ["unterminated", "after"]:
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
        witness=f"recovered {recovered} after a partial or unterminated row",
        site="src/thalamus/harness/ledger_io.py:write_row",
    )


CASE = Case(
    name="ledger-append-survives-a-partial-write",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a crash mid-append must not swallow the next writer's row",
    run=run,
    issue=169,
    fixed=True,
)
