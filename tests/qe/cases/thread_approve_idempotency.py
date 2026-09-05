"""`thalamus thread approve` run twice on the same ref must not duplicate the ledger row.

This is the idempotency shape of the qe charter's write-path gap (issue #76): a write
path re-run should produce one entry, not two. `closes.approve()`
(`src/thalamus/harness/closes.py:146`) is the ledger half of `thalamus thread approve` —
`_cmd_thread`'s `approve` branch (`src/thalamus/cli.py:3846`) calls it before the graph
write, exactly the ordering the module's own docstring cites as deliberate: "a close
whose ledger row is missing cannot be corroborated afterwards." The graph edge
(`write_thread_close`, needs a live Gremlin server on the property graph, `Substrate.
NEEDS_GRAPH`) is out of hermetic reach and not exercised here; the ledger write is pure
disk I/O behind a `path` parameter and needs nothing but a tmpdir.

**What `approve()` does not check.** `find_proposal()` matches a `ref` against its
original `PROPOSED` row and does not ask whether that ref has since been settled — the
same lookup a fresh approval and a second, redundant one both pass. So calling
`approve()` twice on one `ref` (a double-submitted command, a client retry after a
timeout, a second surface racing the same approval) appends two `APPROVED` rows to the
ledger for one decision. `thalamus thread audit`'s own comparison happens to dedupe on
`ref` via a Python `set` (`_agent_closes` vs `closes_mod.approvals()` in `cli.py`), so
the duplicate is invisible through that command specifically — but the ledger itself,
the artifact `audit` corroborates against and the one anything else would read directly,
now carries two approval events for a single approval.

**The control.** A single `approve()` call must produce exactly one row before the case
trusts a second call to mean anything — a comparator that already reads "1" as "2" would
call this case green for the wrong reason. That is asserted first and reported as
COLLAPSED_SENTINEL if it fails.

**Confirmed as a real defect, not asserted.** Filed as issue #170, tagged `issue=170,
fixed=False`, and pinned in `expectations.json`. Reproduction: run `closes.approve()`
twice against the same `ref` and the same ledger path; the row count for that ref goes
from 1 to 2. Repeat the mutation by calling `approve()` a third time — the count keeps
climbing with every call, confirming there is no idempotency check anywhere in the path,
not a boundary that happens to be off by one.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier


def run() -> Finding | None:
    from thalamus.harness import closes  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "closes.jsonl"

        row = closes.propose(
            thread_id="qe-idempotency-probe",
            scope="qe",
            basis="qe probe: not a real proposal",
            disposition="settled",
            rationale="exercised by tests/qe/cases/thread_approve_idempotency.py",
            proposed_by="qe-case",
            path=ledger,
        )
        ref = row["ref"]

        closes.approve(ref, surface="cli", approver_evidence="cli:tty", path=ledger)
        after_one = [a for a in closes.approvals(ledger) if a["ref"] == ref]

        # CONTROL: one approve() call must yield exactly one row. Without this, a
        # comparator that already miscounts a single approval as more than one would
        # call the second call's duplicate "expected" for the wrong reason.
        if len(after_one) != 1:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="a single approve() call did not produce exactly one ledger "
                        "row, so this case cannot tell a duplicate from the baseline",
                witness=f"rows for ref after 1 approve() call: {len(after_one)}",
                site="tests/qe/cases/thread_approve_idempotency.py",
            )

        closes.approve(ref, surface="cli", approver_evidence="cli:tty", path=ledger)
        after_two = [a for a in closes.approvals(ledger) if a["ref"] == ref]

        if len(after_two) == 1:
            return None

        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "closes.approve() has no guard against re-invocation on an already-"
                "approved ref: calling it a second time on the same ref appends a "
                "second APPROVED row instead of leaving the ledger unchanged"
            ),
            witness=(
                f"approvals for ref after 1st approve(): 1; after 2nd approve(): "
                f"{len(after_two)}"
            ),
            site="src/thalamus/harness/closes.py:approve",
        )


CASE = Case(
    name="thread-approve-is-idempotent",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="approving the same close ref twice must not duplicate the ledger row",
    run=run,
    issue=170,
    fixed=False,
)
