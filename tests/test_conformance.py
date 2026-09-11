"""
Federation-contract conformance tests.

Interfaces: thalamus.contract.conformance.check_session
Infrastructure: none
Scope: obligations are enforced at write time, not filtered at read time
"""

from datetime import datetime

import pytest

from thalamus.contract.conformance import (
    ContractViolation,
    check_session,
    prune_orphan_artifacts,
    write_session_checked,
)
from thalamus.substrate.schema import (
    Artifact,
    ArtifactType,
    Decision,
    Provenance,
    SessionGraph,
    Tier,
    Tool,
)


def _session(**overrides) -> SessionGraph:
    defaults = dict(
        session_id="s1",
        timestamp=datetime(2026, 1, 1),
        tool=Tool.CLAUDE_CODE,
        summary="A session.",
    )
    return SessionGraph(**{**defaults, **overrides})


def test_orphan_artifacts_are_rejected_not_quietly_dropped():
    """
    Scenario: An artifact is declared but never referenced

    Verifications:
    - the contract check reports the orphan by name
    """
    session = _session(
        artifacts=[Artifact(identifier="src/lonely.py", type=ArtifactType.FILE)],
    )

    issues = check_session(session)

    # Verifies: rejected at write time, with the offending node named
    assert any("src/lonely.py" in issue for issue in issues)


def test_a_fully_connected_session_satisfies_the_contract():
    """
    Scenario: Every declared artifact is referenced by a claim

    Verifications:
    - no issues are raised
    """
    session = _session(
        artifacts=[Artifact(identifier="src/used.py", type=ArtifactType.FILE)],
        decisions=[
            Decision(description="d", rationale="r", artifacts=["src/used.py"]),
        ],
    )

    # Verifies: a conformant subgraph passes cleanly
    assert check_session(session) == []


def test_provenance_without_a_source_is_rejected():
    """
    Scenario: A node supplies a provenance envelope with an empty source

    Verifications:
    - the contract refuses it — "no provenance, no write"
    """
    session = _session(
        artifacts=[
            Artifact(
                identifier="src/used.py",
                type=ArtifactType.FILE,
                provenance=Provenance(tier=Tier.CURATED, source=""),
            )
        ],
        decisions=[Decision(description="d", rationale="r", artifacts=["src/used.py"])],
    )

    issues = check_session(session)

    # Verifies: the gate fires at write time rather than being cleaned up later
    assert any("no provenance, no write" in issue for issue in issues)


def test_a_pinned_sessions_graph_is_legal_in_an_expert_scope():
    """
    Scenario: A whole session distilled into an expert scope (a pinned session —
    "the process is the pin")

    This was always legal — Session is generically scoped — but pinning makes it
    load-bearing: the SessionEnd hook now passes --scope, so expert-scoped episodic
    SessionGraphs must keep passing the write gate unchanged.
    """
    session = _session(
        scope="literature",
        artifacts=[Artifact(identifier="src/used.py", type=ArtifactType.FILE)],
        decisions=[
            Decision(description="d", rationale="r", artifacts=["src/used.py"]),
        ],
    )

    assert check_session(session) == []


def test_a_session_must_declare_a_scope():
    """
    Scenario: A session carries an empty scope

    Verifications:
    - the contract refuses it — every node belongs to exactly one scope
    """
    session = _session(scope="")

    # Verifies: scope is not optional, even though it defaults
    assert any("no scope" in issue for issue in check_session(session))


@pytest.mark.parametrize("scope", ["main", "literature"])
def test_prune_removes_only_unreferenced_artifacts(scope):
    """
    Scenario: Prepare a session for rendering, in any scope

    Verifications:
    - referenced artifacts survive, orphans do not
    """
    session = _session(
        scope=scope,
        artifacts=[
            Artifact(identifier="src/used.py", type=ArtifactType.FILE),
            Artifact(identifier="src/orphan.py", type=ArtifactType.FILE),
        ],
        decisions=[Decision(description="d", rationale="r", artifacts=["src/used.py"])],
    )

    pruned = prune_orphan_artifacts(session)

    # Verifies: pruning is by reachability, not by position or scope
    assert [a.identifier for a in pruned.artifacts] == ["src/used.py"]


def test_the_gated_write_path_refuses_a_session_the_contract_rejects():
    """
    Scenario: A session carrying an orphan artifact is offered to the gated writer

    Verifications:
    - the write is refused, and the exception carries the session id and the issues
    - nothing reached the writer

    The gate exists because the obligation used to be a caller convention, discharged
    unevenly: of three `write_session` call sites two checked, and the one that did
    not was `thalamus write`, whose input is an operator-supplied JSON file. It cannot
    live in `substrate/writer.py` — the substrate sits below the contract, and
    importing conformance there would invert the layering — so it sits one level up
    and callers use the door instead of remembering the check.
    """
    session = _session(
        artifacts=[Artifact(identifier="src/lonely.py", type=ArtifactType.FILE)],
    )

    def _explode(*_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("the writer was reached despite a contract violation")

    with pytest.raises(ContractViolation) as caught:
        write_session_checked(_explode, session)

    assert caught.value.session_id == "s1"
    assert any("src/lonely.py" in issue for issue in caught.value.issues)


def test_the_gated_write_path_passes_a_conforming_session_straight_through():
    """
    Scenario: A session that satisfies the contract

    Verifications:
    - the writer is called with the same graph and session, and its return is passed back

    The gate is a check plus a delegation, not a second write path — a fork here would
    be a second place for write semantics to drift.
    """
    session = _session()
    assert check_session(session) == []

    calls = []

    def _fake_writer(g, offered, *, gate):
        # The gate arrives as an argument rather than being applied before the call:
        # the door's job is to supply one, and the writer's job is to run it. Calling
        # it here is what makes the assertion below about refusal, not about ordering.
        gate(offered)
        calls.append((g, offered))
        return "scope:main:session:s1"

    import thalamus.substrate.writer as writer_module

    original = writer_module.write_session
    writer_module.write_session = _fake_writer
    try:
        result = write_session_checked("graph-handle", session)
    finally:
        writer_module.write_session = original

    assert result == "scope:main:session:s1"
    assert calls == [("graph-handle", session)]


def test_the_writer_will_not_write_without_being_handed_a_gate():
    """
    Scenario: A new write path calls the writer directly, the way the exchange
    path did for 102 tier-1 vertices

    Verifications:
    - every door that writes a contract-bearing subgraph refuses the call itself
      when no gate is named, rather than writing and leaving the check to an audit
    - the omission is a TypeError at the call, not a silently ungated write
    """
    import inspect

    from thalamus.substrate import writer as writer_module

    for name in ("write_session", "write_knowledge", "write_exchange", "close_exchange"):
        signature = inspect.signature(getattr(writer_module, name))
        gate = signature.parameters.get("gate")
        assert gate is not None, f"{name} takes no gate"
        assert gate.kind is inspect.Parameter.KEYWORD_ONLY, name
        assert gate.default is inspect.Parameter.empty, (
            f"{name}'s gate has a default, so omitting it is silent again"
        )


def test_the_exchange_protocol_refuses_an_answer_that_cites_nothing():
    """
    Scenario: Something closes an exchange as `answered` without citations —
    the write `audit_exchanges` indicts after the fact

    Verifications:
    - the refusal happens at the write, naming consult_answer as the only close path
    - a status the protocol does not know is refused too
    - the launcher's statusless updates (price, closed_by, fork_error) still pass:
      they update an exchange without answering it
    """
    from thalamus.contract.ontology import (
        ProtocolViolation,
        refuse_unless_exchange_protocol_holds,
    )

    vertex = "scope:main:exchange:abc123"

    with pytest.raises(ProtocolViolation) as answered_uncited:
        refuse_unless_exchange_protocol_holds(vertex, {"status": "answered"}, [])
    assert "consult_answer" in str(answered_uncited.value)

    with pytest.raises(ProtocolViolation):
        refuse_unless_exchange_protocol_holds(vertex, {"status": "closed"}, ["x"])

    refuse_unless_exchange_protocol_holds(vertex, {"status": "answered"}, ["scope:x:claim:1"])
    refuse_unless_exchange_protocol_holds(vertex, {"status": "open"}, [])
    for statusless in ({"fork_error": "boom"}, {"closed_by": "launcher"}, {"cost_usd": 0.4}):
        refuse_unless_exchange_protocol_holds(vertex, statusless, [])
