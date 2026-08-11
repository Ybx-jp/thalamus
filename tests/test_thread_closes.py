"""
Operator-approved thread closing — the ledger, the model, and the write.

Interfaces: thalamus.harness.closes, thalamus.substrate.schema.ThreadClose,
            thalamus.substrate.writer.write_thread_close
Infrastructure: tmp_path ledgers; a fake graph for the write
Scope: the propose/approve split, and what a close is incapable of claiming

Grounding: the propose-then-approve shape is `harness/quick.py`'s rule reused —
"The fork answers; it does not close. Acceptance is the launcher's, after the ledger
row is checked." The `Agent`-not-`Session` closer follows PROV-O's attribution-without-
activity pattern: ascribe to the agent when the generating activity is irrelevant.
"""

import pytest

from thalamus.harness import closes
from thalamus.substrate.schema import CloseDisposition, ThreadClose, ThreadStatus


def _ledger(tmp_path):
    return tmp_path / "closes.jsonl"


def _propose(path, thread_id="t1", scope="homelab", disposition="done"):
    return closes.propose(
        thread_id=thread_id,
        scope=scope,
        basis=f"scope:{scope}:session:s9",
        disposition=disposition,
        rationale="the work landed",
        proposed_by="main",
        path=path,
    )


def test_a_proposal_is_a_ledger_row_and_never_a_vertex(tmp_path):
    """
    Scenario: a session proposes closing a thread

    Verifications:
    - the proposal lands in the ledger
    - it shows up as pending, carrying the basis the proposer had in hand

    Proposals stay out of the graph deliberately. An open Thread is already served into
    every consultation brief and every `memory_open_threads` page, so a pending-close
    vertex would add a second population of half-real workitems to the exact surface
    this mechanism exists to clear.
    """
    path = _ledger(tmp_path)

    row = _propose(path)

    # Verifies: recorded, with a ref the operator can approve against
    assert row["event"] == closes.PROPOSED
    assert row["ref"]
    pending = closes.pending(path)
    assert [p["ref"] for p in pending] == [row["ref"]]
    assert pending[0]["basis"] == "scope:homelab:session:s9"


def test_an_approved_or_rejected_proposal_stops_being_pending(tmp_path):
    """
    Scenario: the operator works through the queue

    Verifications:
    - approving clears a proposal from pending
    - rejecting clears it too, and stays on the record

    A rejection is kept rather than deleted because it is the only negative evidence
    the basis-finders will ever get; precision cannot be measured from approvals alone.
    """
    path = _ledger(tmp_path)
    approved = _propose(path, thread_id="t1")
    rejected = _propose(path, thread_id="t2")

    closes.approve(approved["ref"], surface="cli", approver_evidence="cli:tty", path=path)
    closes.reject(rejected["ref"], reason="still open", path=path)

    # Verifies: the queue drains, and both outcomes survive in the ledger
    assert closes.pending(path) == []
    events = [row["event"] for row in closes.read_rows(path)]
    assert events.count(closes.REJECTED) == 1
    assert [row["ref"] for row in closes.approvals(path)] == [approved["ref"]]


def test_an_approval_must_name_a_real_proposal_and_a_known_surface(tmp_path):
    """
    Scenario: an approval arrives for nothing, or from nowhere

    Verifications:
    - approving an unknown ref is refused
    - an unknown surface is refused

    The surface is recorded rather than inferred because the three have genuinely
    different evidence available; collapsing them would make the weakest look like the
    strongest.
    """
    path = _ledger(tmp_path)
    proposal = _propose(path)

    # Verifies: no proposal, no approval
    with pytest.raises(ValueError, match="no proposal"):
        closes.approve("deadbeef", surface="cli", approver_evidence="cli:tty", path=path)

    # Verifies: the surface vocabulary is closed
    with pytest.raises(ValueError, match="unknown approval surface"):
        closes.approve(
            proposal["ref"], surface="telepathy", approver_evidence="x", path=path
        )


def test_the_close_record_cannot_claim_the_operator_was_authenticated():
    """
    Scenario: build the record a close writes

    Verifications:
    - there is no boolean saying approval happened
    - what is carried is the *kind* of evidence, and a pointer to it

    The console binds loopback with no authentication and does not pretend to; an
    in-session agent runs Bash at the operator's own uid. A close is therefore
    attributable and never authenticated, and the schema is deliberately incapable of
    asserting otherwise — forgery is caught by corroborating the ledger afterwards.
    """
    close = ThreadClose(
        thread_id="t1", scope="homelab",
        disposition=CloseDisposition.DONE,
        basis="scope:homelab:session:s9",
        surface="console", approval_ref="ref1",
        approver_evidence="console:req-42",
        closed_at="2026-08-11T00:00:00Z",
    )

    properties = close.edge_properties()

    # Verifies: no claim of authentication anywhere in the payload
    assert "approved" not in properties
    assert properties["approver_evidence"] == "console:req-42"
    assert properties["approval_ref"] == "ref1"
    # Verifies: absent optionals are omitted rather than written blank
    assert "on_behalf_of" not in properties
    assert "notes" not in properties


def test_status_is_derived_from_disposition_so_the_two_cannot_disagree():
    """
    Scenario: close a thread that was done, and one that was never work

    Verifications:
    - done/superseded resolve; never-work/abandoned are abandoned

    A thread marked `resolved` with disposition `never-work` is a contradiction a
    reader would have to arbitrate, so status is not separately settable. The
    distinction is load-bearing beyond tidiness: counting the weeks a probe's return
    value sat open as resolution latency measures nothing.
    """
    def close(disposition):
        return ThreadClose(
            thread_id="t1", disposition=disposition, basis="scope:main:session:s9",
            surface="cli", approval_ref="r", approver_evidence="cli:tty",
            closed_at="2026-08-11T00:00:00Z",
        ).status

    # Verifies: the mapping, both directions
    assert close(CloseDisposition.DONE) is ThreadStatus.RESOLVED
    assert close(CloseDisposition.SUPERSEDED) is ThreadStatus.RESOLVED
    assert close(CloseDisposition.NEVER_WORK) is ThreadStatus.ABANDONED
    assert close(CloseDisposition.ABANDONED) is ThreadStatus.ABANDONED


def test_closing_a_thread_that_does_not_exist_is_an_error_not_a_no_op():
    """
    Scenario: the operator approves a close naming a thread the graph does not hold

    Verifications:
    - the write raises rather than silently doing nothing

    A distilled `thread_ref` naming a missing thread is dropped, correctly: that is
    model output referencing memory never formed. This is the opposite case — an
    operator naming a specific thread — and reporting success for work not done is how
    a backlog looks drained while nothing moved.
    """
    from thalamus.substrate.writer import write_thread_close

    class MissingThread:
        def V(self, *_):
            return self

        def has_label(self, *_):
            return self

        def has_next(self):
            return False

    close = ThreadClose(
        thread_id="ghost", scope="homelab",
        disposition=CloseDisposition.DONE, basis="scope:homelab:session:s9",
        surface="cli", approval_ref="r", approver_evidence="cli:tty",
        closed_at="2026-08-11T00:00:00Z",
    )

    # Verifies: named, refused, and it says which thread
    with pytest.raises(ValueError, match="ghost"):
        write_thread_close(MissingThread(), close)
