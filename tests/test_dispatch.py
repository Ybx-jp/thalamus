"""
Dispatch tests (harness/dispatch.py) — delivery mechanics.

Interfaces: thalamus.harness.dispatch (preflight, announcement, dispatch, ledger_panes)
Infrastructure: tmp_path config dir + pin ledger + guard dir; tmux is never invoked —
the live pane set is injected and the send is a recording fake
Scope: the refusals. Every test here is anchored on something that costs more than a
failed send if it goes wrong: approving an unseen permission prompt, making a member's
silence uninterpretable, or letting an operator broadcast count as collaboration.
"""

import json

import pytest

from thalamus.harness import dispatch


def _descriptor(sessions_dir, scope, session_id, pid, status, updated_at=1000):
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / f"{pid}.json").write_text(json.dumps({
        "sessionId": session_id,
        "pid": pid,
        "cwd": "/home/ybx/code/thalamus",
        "agent": f"thalamus-{scope}",
        "name": f"alpha-{scope}",
        "status": status,
        "updatedAt": updated_at,
    }))


@pytest.fixture
def room(tmp_path, monkeypatch):
    """A room config dir, a pin ledger placing each member on a pane, and no tmux.

    `procStart` is left out of the descriptors so `quick.live_sessions` skips the
    /proc check — these sessions are fixtures, not processes.
    """
    config = tmp_path / "room"
    pins = tmp_path / "pins.jsonl"
    guards = tmp_path / "guards"

    _descriptor(config / "sessions", "qe", "sid-qe", 101, "idle")
    _descriptor(config / "sessions", "architect", "sid-arch", 102, "busy")

    pins.write_text("\n".join(json.dumps(row) for row in [
        {"session_id": "sid-qe", "scope": "qe", "room": "alpha", "tmux_pane": "%11"},
        {"session_id": "sid-arch", "scope": "architect", "room": "alpha",
         "tmux_pane": "%12"},
        # An `event` row sharing the ledger, carrying no launch facts. A reader that
        # let this win would lose the pane for sid-qe entirely.
        {"session_id": "sid-qe", "event": "engaged"},
    ]))

    return {
        "config_dir": config, "pins_file": pins, "guards_dir": guards,
        "panes": {"%11", "%12"},
    }


def _sends(record):
    def send(pane, text, submit):
        record.append((pane, text, submit))
        return ""
    return send


# --- The refusal the whole verb exists for -------------------------------------------


def test_a_waiting_target_is_refused_and_never_written_to(room, tmp_path):
    """
    Scenario: one member is sitting on a permission prompt (`waiting`).

    Verification: refused, nothing sent. This is the one that costs more than a failed
    message — text into a `waiting` window is discarded and the following Enter
    actuates the highlighted default, which approves a tool call the sender cannot
    see. A dispatch that "handled `waiting` carefully" would still approve it.
    """
    _descriptor(room["config_dir"] / "sessions", "homelab", "sid-home", 103, "waiting")
    room["pins_file"].write_text(
        room["pins_file"].read_text()
        + "\n" + json.dumps({"session_id": "sid-home", "scope": "homelab",
                             "room": "alpha", "tmux_pane": "%13"})
    )
    room["panes"].add("%13")

    sent = []
    with pytest.raises(dispatch.DispatchRefused, match="waiting"):
        dispatch.dispatch("alpha", "ping", sender="main", sender_fn=_sends(sent), **room)
    assert sent == []


def test_preflight_names_the_waiting_target_without_touching_it(room):
    _descriptor(room["config_dir"] / "sessions", "homelab", "sid-home", 103, "waiting")
    room["pins_file"].write_text(
        room["pins_file"].read_text()
        + "\n" + json.dumps({"session_id": "sid-home", "scope": "homelab",
                             "room": "alpha", "tmux_pane": "%13"})
    )
    room["panes"].add("%13")

    targets = dispatch.preflight(
        "alpha", config_dir=room["config_dir"], pins_file=room["pins_file"],
        panes=room["panes"],
    )
    waiting = [t for t in targets if t.scope == "homelab"][0]
    assert not waiting.deliverable
    assert "actuate the highlighted default" in waiting.refusal
    assert [t.deliverable for t in targets if t.scope != "homelab"] == [True, True]


def test_an_unmeasured_status_is_refused_rather_than_assumed_idle(room):
    """
    Scenario: a descriptor reports a status outside the measured set.

    Verification: refused. The measurement covers idle, busy and waiting; treating an
    unknown fourth as idle is assuming the one thing that has always been fatal here.
    """
    _descriptor(room["config_dir"] / "sessions", "designer", "sid-des", 104, "compacting")
    room["pins_file"].write_text(
        room["pins_file"].read_text()
        + "\n" + json.dumps({"session_id": "sid-des", "scope": "designer",
                             "room": "alpha", "tmux_pane": "%14"})
    )
    room["panes"].add("%14")

    targets = dispatch.preflight(
        "alpha", config_dir=room["config_dir"], pins_file=room["pins_file"],
        panes=room["panes"],
    )
    unknown = [t for t in targets if t.scope == "designer"][0]
    assert not unknown.deliverable
    assert "outside the measured set" in unknown.refusal


# --- Delivery on the two statuses that take it ----------------------------------------


def test_idle_and_busy_both_take_delivery(room):
    """
    Verification: both are delivered to, text first and Enter second. `busy` is not
    refused — the message queues and is processed as the next turn, which is delivery
    and not a failure.
    """
    sent = []
    result = dispatch.dispatch(
        "alpha", "the announcement", sender="main", sender_fn=_sends(sent), **room
    )
    assert result.performed == 2
    assert sorted(pane for pane, _text, _submit in sent) == ["%11", "%12"]
    assert all(text == "the announcement" for _pane, text, _submit in sent)
    assert all(submit for _pane, _text, submit in sent)


def test_no_submit_types_without_the_enter(room):
    sent = []
    dispatch.dispatch(
        "alpha", "draft", sender="main", submit=False, sender_fn=_sends(sent), **room
    )
    assert all(submit is False for _pane, _text, submit in sent)


# --- The partial fan-out, and why it is not the default -------------------------------


def test_one_undeliverable_target_refuses_the_whole_fanout(room):
    """
    Scenario: two members are reachable, one is `waiting`.

    Verification: nobody is sent to. A partial announcement makes a member's silence
    ambiguous — it can no longer separate "this expert declined" from "this expert was
    never asked" — and Contract Net treats a decline and a timeout as different states
    carrying different information.
    """
    _descriptor(room["config_dir"] / "sessions", "homelab", "sid-home", 103, "waiting")
    room["pins_file"].write_text(
        room["pins_file"].read_text()
        + "\n" + json.dumps({"session_id": "sid-home", "scope": "homelab",
                             "room": "alpha", "tmux_pane": "%13"})
    )
    room["panes"].add("%13")

    sent = []
    with pytest.raises(dispatch.DispatchRefused, match="whole fan-out"):
        dispatch.dispatch("alpha", "ping", sender="main", sender_fn=_sends(sent), **room)
    assert sent == []


def test_partial_delivers_and_records_who_missed_it(room):
    """
    Verification: the reachable members get it, and every row carries the undelivered
    names. Recording them is what keeps the later reading honest — without it, a
    partial broadcast's timeouts are uninterpretable.
    """
    _descriptor(room["config_dir"] / "sessions", "homelab", "sid-home", 103, "waiting")
    room["pins_file"].write_text(
        room["pins_file"].read_text()
        + "\n" + json.dumps({"session_id": "sid-home", "scope": "homelab",
                             "room": "alpha", "tmux_pane": "%13"})
    )
    room["panes"].add("%13")

    sent = []
    result = dispatch.dispatch(
        "alpha", "ping", sender="main", partial=True, sender_fn=_sends(sent), **room
    )
    assert result.performed == 2
    assert result.undelivered == ("alpha-homelab",)
    assert "must not be read as a timeout" in result.note()

    rows = [
        json.loads(line)
        for path in room["guards_dir"].glob("*.jsonl")
        for line in path.read_text().splitlines()
    ]
    assert len(rows) == 3
    assert all(row["undelivered"] == ["alpha-homelab"] for row in rows)


# --- The two rosters must agree -------------------------------------------------------


def test_a_member_the_pin_ledger_cannot_place_is_refused(room):
    """
    Scenario: a live descriptor with no pin-ledger row, so no pane resolves.

    Verification: refused rather than guessed. Guessing a pane sends the room's
    message into a stranger's window.
    """
    _descriptor(room["config_dir"] / "sessions", "teacher", "sid-teach", 105, "idle")
    targets = dispatch.preflight(
        "alpha", config_dir=room["config_dir"], pins_file=room["pins_file"],
        panes=room["panes"],
    )
    orphan = [t for t in targets if t.scope == "teacher"][0]
    assert not orphan.deliverable
    assert "absent from the pin ledger" in orphan.refusal


def test_a_pane_tmux_does_not_have_is_refused(room):
    """
    Scenario: the pin ledger claims a pane that is no longer live.

    Verification: refused as a roster disagreement. Dispatch refuses rather than
    guesses where the window list and the descriptor roster disagree, and
    a recycled pane id belonging to something else is the case that makes it matter.
    """
    room["panes"] = {"%11"}
    targets = dispatch.preflight(
        "alpha", config_dir=room["config_dir"], pins_file=room["pins_file"],
        panes=room["panes"],
    )
    stale = [t for t in targets if t.scope == "architect"][0]
    assert not stale.deliverable
    assert "tmux does not have" in stale.refusal


def test_an_event_row_does_not_hide_a_members_pane(room):
    """
    Verification: sid-qe still resolves to %11 despite a later `event` row for the same
    session carrying no pane. Letting a lifecycle row win is the pin-ledger defect that
    once read a correctly-launched fork as having met no obligation.
    """
    panes = dispatch.ledger_panes(room["pins_file"])
    assert panes == {"sid-qe": "%11", "sid-arch": "%12"}


# --- The rows are stimulus, not collaboration -----------------------------------------


def test_rows_carry_a_guard_name_the_room_topology_check_excludes_by_construction(room):
    """
    Verification: rows are written under `guard: "dispatch"`, distinct from
    `"room-boundary"` — the guard name `thalamus-eval`'s room-manipulation check
    (`room_topologies`, split out of this repo) filters on to drop exactly these rows.
    A broadcast is the stimulus, not the collaboration, and folding operator sends into
    a room's edge count would let a room pass its own manipulation check on operator
    action alone.

    The exclusion itself (`room_topologies` producing empty edges / not-occurred for
    these rows) is verified in `thalamus-eval`'s own `tests/test_rooms.py`, which
    depends on this repo but not vice versa; this test only owns the guard name
    contract on the dispatch side of that boundary.
    """
    dispatch.dispatch("alpha", "ping", sender="main", sender_fn=_sends([]), **room)
    rows = [
        json.loads(line)
        for path in room["guards_dir"].glob("*.jsonl")
        for line in path.read_text().splitlines()
    ]
    assert rows and all(row["guard"] == dispatch.DISPATCH_GUARD for row in rows)
    assert all(row["guard"] != "room-boundary" for row in rows)


def test_rows_record_the_preflight_status_and_the_fanout(room):
    dispatch.dispatch("alpha", "ping", sender="main", sender_fn=_sends([]), **room)
    rows = [
        json.loads(line)
        for path in room["guards_dir"].glob("*.jsonl")
        for line in path.read_text().splitlines()
    ]
    by_target = {row["target"]: row for row in rows}
    assert by_target["alpha-qe"]["preflight_status"] == "idle"
    assert by_target["alpha-architect"]["preflight_status"] == "busy"
    assert all(row["fanout"] == 2 for row in rows)
    assert all(row["via"] == dispatch.VIA_TMUX for row in rows)
    assert all(row["dispatch_id"] == rows[0]["dispatch_id"] for row in rows)


# --- Dry run, and the empty cases -----------------------------------------------------


def test_dry_run_sends_nothing_and_writes_nothing(room):
    sent = []
    result = dispatch.dispatch(
        "alpha", "ping", sender="main", dry_run=True, sender_fn=_sends(sent), **room
    )
    assert sent == []
    assert result.performed == 0
    # Unconditional: a dry run must leave the guard dir with no rows in it, and
    # `is_dir()` guarding this assertion would let it pass vacuously by never running.
    written = list(room["guards_dir"].glob("*.jsonl")) if room["guards_dir"].is_dir() else []
    assert written == []
    assert "dry run, nothing sent" in result.note()


def test_an_empty_message_is_refused(room):
    with pytest.raises(dispatch.DispatchRefused, match="empty message"):
        dispatch.dispatch("alpha", "   ", sender="main", **room)


def test_a_room_with_no_live_members_is_refused(tmp_path):
    with pytest.raises(dispatch.DispatchRefused, match="no live members"):
        dispatch.dispatch(
            "ghost", "ping", sender="main",
            config_dir=tmp_path / "empty", pins_file=tmp_path / "pins.jsonl",
            guards_dir=tmp_path / "guards", panes=set(),
        )


def test_scopes_restrict_the_fanout(room):
    sent = []
    result = dispatch.dispatch(
        "alpha", "ping", sender="main", scopes=["qe"], sender_fn=_sends(sent), **room
    )
    assert result.performed == 1
    assert [pane for pane, _text, _submit in sent] == ["%11"]


# --- The announcement format ----------------------------------------------------------


def test_an_announcement_missing_a_slot_is_refused():
    """
    Verification: refused, naming the missing slots. Contract Net's four are mandatory
    together — the format's economy is that a member reads eligibility and stops, and a
    blank slot makes it process the whole message to discover the message is not for it.
    """
    with pytest.raises(dispatch.DispatchRefused, match="eligibility, bid"):
        dispatch.announcement("ship the verb", "", "", "2026-08-11T06:00Z")


def test_an_announcement_carries_four_slots_and_a_legal_decline():
    text = dispatch.announcement(
        "Ship the dispatch verb",
        "any scope holding the harness write boundary",
        "one paragraph naming what you would build first",
        "2026-08-11T06:00Z",
        sender="main",
    )
    for slot in ("task:", "eligibility:", "bid:", "expires:"):
        assert slot in text
    assert "decline is a protocol-legal reply" in text
    # The third state has to be named, or silence gets read as a decline.
    assert "timeout" in text
