"""
Independent-grounding tests: which asserting sessions count as separate witnesses.

Interfaces: thalamus.substrate.witnesses
Infrastructure: none — pure functions over recorded launcher facts
Scope: the asymmetry docs/09 §Scope settles. A fork collapses because the
dependence is recorded; a room does not, because a room is not an event. Both
halves are tested as decisions, since either one implemented by symmetry with the
other is a bug the graph cannot show you afterwards.
"""

from thalamus.substrate.witnesses import Witness, corroboration


def test_uncorrelated_sessions_are_each_their_own_grounding():
    """The ordinary case, and the one that must stay silent: three sessions that
    independently asserted something are three witnesses, and a reader is told
    nothing extra because there is nothing to warn about."""
    result = corroboration([Witness("a"), Witness("b"), Witness("c")])

    assert result.asserted == 3
    assert result.independent == 3
    assert result.correlated is False
    assert result.note() == ""


def test_a_fork_collapses_into_its_parent():
    """
    Scenario: a session forked from another, and both assert the same claim

    Verifications:
    - both readings are kept: 2 asserted, 1 independent
    - the reader is told which of the two numbers to trust

    A fork inherits its parent's context rather than reaching its own conclusions,
    so it is a mapping over the parent's material: its agreement corroborates
    nothing. This is the one collapse the schema can justify, because the
    dependence was recorded by the launcher and not inferred afterwards.
    """
    result = corroboration([Witness("parent"), Witness("child", forked_from="parent")])

    assert (result.asserted, result.independent) == (2, 1)
    assert result.correlated is True
    assert "1 independent grounding" in result.note()
    assert "corroborate nothing" in result.note()


def test_a_fork_chain_collapses_to_one_root():
    """Transitive: a fork of a fork is still one grounding, not two."""
    result = corroboration([
        Witness("a"),
        Witness("b", forked_from="a"),
        Witness("c", forked_from="b"),
    ])

    assert (result.asserted, result.independent) == (3, 1)


def test_a_fork_whose_parent_is_absent_stands_alone():
    """
    Scenario: a session forked from one that never asserted this claim

    Verifications:
    - it counts as its own grounding

    Collapsing here would assert a dependence between two witnesses on the strength
    of a third that made no claim at all — an inference, where every other input to
    this function is a record. A gap in the chain costs a collapse rather than
    inventing one.
    """
    result = corroboration([Witness("a"), Witness("b", forked_from="not-a-witness")])

    assert (result.asserted, result.independent) == (2, 2)
    assert result.correlated is False


def test_a_room_is_flagged_and_never_collapsed():
    """
    Scenario: two sessions in one room both assert the same claim

    Verifications:
    - the count is NOT reduced
    - the room is named so a reader can discount it

    docs/09 closes this deliberately: a room hosts many turns, so it is not an event
    identifier, and collapsing by it would trade a false-count error for a
    false-collapse error. Membership makes correlation plausible where a fork parent
    makes it certain — so the room is flagged and left counted.
    """
    result = corroboration([Witness("a", room="alpha"), Witness("b", room="alpha")])

    assert (result.asserted, result.independent) == (2, 2)
    assert result.rooms == ("alpha",)
    assert result.correlated is True
    assert "shared room `alpha`" in result.note()


def test_one_session_alone_in_a_room_is_not_correlated():
    """A room with a single witness correlates nothing — there is no second
    assertion for it to be correlated *with*, and flagging it would train a reader
    to ignore the flag."""
    result = corroboration([Witness("a", room="alpha"), Witness("b")])

    assert result.rooms == ()
    assert result.correlated is False


def test_both_axes_at_once_are_reported_together():
    """A fork inside a room: the collapse and the flag are independent findings and
    both reach the reader."""
    result = corroboration([
        Witness("a", room="alpha"),
        Witness("b", room="alpha", forked_from="a"),
        Witness("c", room="alpha"),
    ])

    assert (result.asserted, result.independent) == (3, 2)
    assert result.rooms == ("alpha",)
    note = result.note()
    assert "2 independent groundings" in note and "shared room `alpha`" in note


def test_a_corrupted_parent_cycle_terminates():
    """A launcher cannot produce a cycle (a fork's parent always predates it), so
    this is a hand-edited or corrupted ledger — which must not become an infinite
    loop inside a recall the operator is waiting on."""
    result = corroboration([
        Witness("a", forked_from="b"),
        Witness("b", forked_from="a"),
    ])

    assert result.asserted == 2
    assert result.independent >= 1
