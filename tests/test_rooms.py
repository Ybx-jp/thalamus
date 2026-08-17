"""
Room manipulation-check tests (eval/rooms.py).

Interfaces: thalamus.eval.rooms (peer_scope, room_members, room_topologies, render)
Infrastructure: tmp_path pin/guard JSONL ledgers; no live graph, no tmux
Scope: whether the room *treatment* occurred — the check that separates "rooms did
not help" from "the room never happened". Not an outcome: nothing here grades a
room, and the tests assert that a failed check reads as an exclusion rather than a
result.
"""

import json

from thalamus.eval.rooms import peer_scope, room_members, room_topologies, render


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def _pins(tmp_path, rows):
    path = tmp_path / "pins" / "pins.jsonl"
    _write_jsonl(path, rows)
    return path


def _guards(tmp_path, rows):
    directory = tmp_path / "guards"
    _write_jsonl(directory / "2026-08.jsonl", rows)
    return directory


def _send(room, scope, target, branch="roommate", verdict="pass"):
    return {
        "ts": "2026-08-08T12:00:00Z", "session_id": f"s-{scope}", "scope": scope,
        "room": room, "guard": "room-boundary", "branch": branch,
        "verdict": verdict, "target": target,
    }


def test_peer_scope_normalizes_both_target_forms():
    """
    Scenario: SendMessage wants a disambiguating ` [ref]` on first contact, so the
    same peer is named two ways across a room's history.

    Verification: both normalize to one scope, and a name outside the room resolves
    to nothing rather than to a bogus member.
    """
    assert peer_scope("alpha-homelab", "alpha") == "homelab"
    assert peer_scope("alpha-homelab [a1b2c3d4]", "alpha") == "homelab"
    # Verifies: another room's member is not this room's peer
    assert peer_scope("beta-homelab", "alpha") == ""
    # Verifies: an unprefixed outsider name resolves to nothing
    assert peer_scope("some-outsider", "alpha") == ""


def test_a_room_nobody_messaged_fails_the_check(tmp_path):
    """
    Scenario: two sessions launched into a room and neither ever sent to the other.

    Verification: the check fails. This is the case the module exists for — the arm
    is a pair of solo sessions wearing a room label, and counting it as a room arm
    would let "the room never happened" masquerade as "rooms do not help".
    """
    pins = _pins(tmp_path, [
        {"session_id": "s1", "scope": "main", "room": "quiet"},
        {"session_id": "s2", "scope": "homelab", "room": "quiet"},
    ])
    topologies = room_topologies(pins_file=pins, guards_base=tmp_path / "absent")

    assert len(topologies) == 1
    quiet = topologies[0]
    # Verifies: the room is known from the pin ledger despite zero guard rows
    assert quiet.members == ("homelab", "main")
    assert not quiet.occurred
    assert quiet.density == 0.0
    assert "TREATMENT DID NOT OCCUR" in quiet.note()


def test_a_room_is_driven_from_the_pin_ledger_not_the_guard_ledger(tmp_path):
    """
    Verification: a room that produced no guard row at all is still enumerated. If
    the realized edges drove enumeration, the silent room — the only one the check
    can fail — would be invisible, and the check would report success on every room
    it could see.
    """
    pins = _pins(tmp_path, [
        {"session_id": "s1", "scope": "main", "room": "silent"},
        {"session_id": "s2", "scope": "teacher", "room": "silent"},
    ])
    guards = _guards(tmp_path, [_send("other", "main", "other-teacher")])
    rooms = {t.room for t in room_topologies(pins_file=pins, guards_base=guards)}
    assert rooms == {"silent"}


def test_treatment_occurred_counts_sends_and_direction(tmp_path):
    """
    Scenario: main sends to homelab twice (once with a ref suffix), homelab never
    replies, and one send to an outsider is refused.

    Verification: the check passes on one directed edge, the repeat is counted as
    volume rather than a second pair, the pair is not reciprocated, and the refusal
    is kept separately as evidence of attempted reach.
    """
    pins = _pins(tmp_path, [
        {"session_id": "s1", "scope": "main", "room": "alpha"},
        {"session_id": "s2", "scope": "homelab", "room": "alpha"},
    ])
    guards = _guards(tmp_path, [
        _send("alpha", "main", "alpha-homelab"),
        _send("alpha", "main", "alpha-homelab [a1b2c3d4]"),
        _send("alpha", "main", "beta-homelab", branch="outside-room", verdict="block"),
    ])
    alpha = room_topologies(pins_file=pins, guards_base=guards)[0]

    assert alpha.occurred
    assert alpha.edges == (("main", "homelab", 2),)
    assert alpha.sends == 2
    # Verifies: a one-way pair is a broadcast, not the exchange the room is for
    assert alpha.reciprocated == 0
    assert alpha.density == 1.0
    # Verifies: a blocked send is evidence of trying, never a realized edge
    assert alpha.blocked == 1


def test_reciprocation_needs_both_directions(tmp_path):
    """
    Verification: a pair counts as reciprocated only when each sent to the other,
    and it is counted once rather than once per direction.
    """
    pins = _pins(tmp_path, [
        {"session_id": "s1", "scope": "main", "room": "alpha"},
        {"session_id": "s2", "scope": "homelab", "room": "alpha"},
    ])
    guards = _guards(tmp_path, [
        _send("alpha", "main", "alpha-homelab"),
        _send("alpha", "homelab", "alpha-main"),
    ])
    alpha = room_topologies(pins_file=pins, guards_base=guards)[0]
    assert alpha.reciprocated == 1


def test_a_self_send_is_dropped_without_claiming_an_undercount(tmp_path):
    """
    Scenario: a member's target resolves to its own scope — observed live in room
    `alpha`, where main sent to `alpha-main`.

    Verification: it is excluded from the graph but counted apart from `unresolved`.
    The two license opposite readings: a self-send is understood and correctly
    dropped, while an unparsed target means the edge list is missing something, so
    conflating them raises a lower-bound caveat the data does not support.
    """
    pins = _pins(tmp_path, [
        {"session_id": "s1", "scope": "main", "room": "alpha"},
        {"session_id": "s2", "scope": "homelab", "room": "alpha"},
    ])
    guards = _guards(tmp_path, [
        _send("alpha", "main", "alpha-main"),
        _send("alpha", "main", "alpha-nonmember-typo-"),
    ])
    alpha = room_topologies(pins_file=pins, guards_base=guards)[0]

    assert alpha.self_sends == 1
    # Verifies: a target that parses but names no member is unresolved, not an edge —
    # the prefix alone is not membership, and a phantom peer would add a node the
    # roster never had to a graph whose density denominator comes from the roster
    assert alpha.edges == ()
    assert alpha.unresolved == 1


def test_a_room_of_one_is_not_a_room(tmp_path):
    """
    Scenario: a single session launched into a room — a real run took this shape and
    carried no in-room control of its own.

    Verification: reported as NOT A ROOM rather than as a room that failed to
    collaborate. No pair could have collaborated, so the failure is in the roster
    and never reaches the question the check is asking.
    """
    pins = _pins(tmp_path, [{"session_id": "s1", "scope": "main", "room": "solo"}])
    solo = room_topologies(pins_file=pins, guards_base=tmp_path / "absent")[0]

    assert not solo.occurred
    assert solo.density == 0.0
    assert "NOT A ROOM" in solo.note()


def test_other_guards_sharing_the_ledger_are_not_room_edges(tmp_path):
    """
    Verification: the guard ledger directory is shared, so rows written by another
    guard must not become room edges. A terminal-step row carries no room and no
    target; counting it would manufacture collaboration out of unrelated tooling.
    """
    pins = _pins(tmp_path, [
        {"session_id": "s1", "scope": "main", "room": "alpha"},
        {"session_id": "s2", "scope": "homelab", "room": "alpha"},
    ])
    guards = _guards(tmp_path, [
        {"ts": "2026-08-08T12:00:00Z", "session_id": "s1", "scope": "main",
         "guard": "terminal-step", "verdict": "pass", "branch": "terminal"},
    ])
    alpha = room_topologies(pins_file=pins, guards_base=guards)[0]
    assert not alpha.occurred


def test_render_gates_the_campaign_on_the_roll_up(tmp_path):
    """
    Verification: the roll-up names how many rooms the treatment landed in and says
    the rest are excluded *before* analysis. Dropping arms after seeing outcomes is
    the peeking failure this line is meant to avoid, so the instruction has to travel
    with the number.
    """
    pins = _pins(tmp_path, [
        {"session_id": "s1", "scope": "main", "room": "alpha"},
        {"session_id": "s2", "scope": "homelab", "room": "alpha"},
        {"session_id": "s3", "scope": "main", "room": "quiet"},
        {"session_id": "s4", "scope": "teacher", "room": "quiet"},
    ])
    guards = _guards(tmp_path, [_send("alpha", "main", "alpha-homelab")])
    text = render(room_topologies(pins_file=pins, guards_base=guards))

    assert "treatment occurred in 1/2 room(s)" in text
    assert "before analysis" in text


def test_no_rooms_reads_as_uninterpretable_not_as_zero(tmp_path):
    """
    Verification: an empty pin ledger says a room arm cannot be interpreted yet,
    rather than rendering an empty table that reads like a measured null.
    """
    text = render(room_topologies(
        pins_file=tmp_path / "pins" / "pins.jsonl", guards_base=tmp_path / "absent"
    ))
    assert "none in the pin ledger" in text


def test_room_members_dedupes_relaunches(tmp_path):
    """
    Verification: a scope relaunched into the same room is one member, not two —
    otherwise a restarted window would inflate the nominal graph and deflate density
    against a denominator that never existed.
    """
    pins = _pins(tmp_path, [
        {"session_id": "s1", "scope": "main", "room": "alpha"},
        {"session_id": "s2", "scope": "main", "room": "alpha"},
        {"session_id": "s3", "scope": "homelab", "room": "alpha"},
        {"session_id": "s4", "scope": "main", "room": ""},
    ])
    members = room_members(pins)
    assert members == {"alpha": {"main", "homelab"}}
