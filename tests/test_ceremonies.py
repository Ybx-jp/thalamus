"""
Ceremony ledger tests (harness/ceremonies.py) — the first four lifecycle records.

Interfaces: thalamus.harness.ceremonies (start, end, skip, mint_deliverable,
record_revision, record_assignment, draw, next_index, audit, render)
Infrastructure: a tmp_path ledger; no graph, no network, no harness
Scope: the four records that make later analysis possible at all. Each test below is
anchored on what could NOT be reconstructed after the fact if the row were missing —
that is the standard that puts these four ahead of the rest of the lifecycle.
"""

import json

import pytest

from thalamus.harness import ceremonies


@pytest.fixture
def ledger(tmp_path):
    return tmp_path / "ceremonies.jsonl"


# --- 1. The occasion, written at start ----------------------------------------------


def test_an_aborted_ceremony_still_leaves_a_row(ledger):
    """
    Scenario: an occasion starts and nothing ever closes it — a crash, an abandoned
    ceremony, an interrupted room.

    Verification: the start row is on disk and the audit reports the occasion as
    unfinished rather than as absent. A ledger that wrote only on success could not
    tell an aborted ceremony from one that never ran, which is the whole reason the
    row is written at start.
    """
    row = ceremonies.start(
        "alpha", "review", participant_scopes=["homelab", "qe"], path=ledger
    )
    assert row["occasion_id"] == "alpha:review:1"
    assert row["ts_start"]
    assert "ts_end" not in row

    report = ceremonies.audit(path=ledger)
    assert report.unfinished == ("alpha:review:1",)
    assert report.occasions == 1
    # Unfinished is not a defect — an abort leaving a row is the designed behaviour.
    assert report.clean()


def test_end_appends_a_row_rather_than_mutating_the_start(ledger):
    """
    Scenario: an occasion is opened and later closed.

    Verification: the ledger holds two rows, the start row is byte-identical to what
    was written, and the pairing is by occasion_id. An in-place rewrite could lose the
    abort rows the ledger exists to keep.
    """
    ceremonies.start("alpha", "review", path=ledger)
    before = ledger.read_text()

    ceremonies.end("alpha:review:1", outcome="accepted", path=ledger)
    after = ledger.read_text()

    assert after.startswith(before)
    rows = ceremonies.read_rows(ledger)
    assert [row["event"] for row in rows] == ["start", "end"]
    assert rows[1]["occasion_id"] == "alpha:review:1"
    assert ceremonies.audit(path=ledger).unfinished == ()


def test_every_row_carries_an_event_so_one_ledger_can_hold_four_records(ledger):
    """
    Scenario: all four record kinds are written to one file.

    Verification: every row has an `event`, and filtering by it recovers each kind
    exactly. This is the pin ledger's defect inverted — there, `{event: "engaged"}`
    rows shared the file while carrying none of the launch fields, and last-row-wins
    read a correctly-launched fork as having met no obligation.
    """
    ceremonies.mint_deliverable("alpha", "The dispatch verb", path=ledger)
    ceremonies.record_assignment(
        "alpha", "review", ["alpha:the-dispatch-verb"], ["peer"], [1], 7, path=ledger
    )
    ceremonies.start("alpha", "review", path=ledger)
    ceremonies.skip("alpha", "retrospective", reason="one deliverable", path=ledger)

    raw = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert all(row.get("event") for row in raw)
    assert [row["event"] for row in raw] == [
        "deliverable", "assigned", "start", "skipped",
    ]


def test_an_unknown_ceremony_kind_is_refused(ledger):
    """
    Scenario: a caller opens a `standup`, which the lifecycle's filter cut.

    Verification: refused. A closed vocabulary is the point — an unrecognised kind is
    not a new ceremony, it is a silently forked occasion counter, and the lifecycle's
    discipline is that a ceremony must be paid for before it exists.
    """
    with pytest.raises(ValueError, match="unknown ceremony kind"):
        ceremonies.start("alpha", "standup", path=ledger)
    with pytest.raises(ValueError, match="unknown ceremony kind"):
        ceremonies.skip("alpha", "demo", path=ledger)


def test_occasions_number_per_room_and_kind(ledger):
    ceremonies.start("alpha", "review", path=ledger)
    ceremonies.start("alpha", "review", path=ledger)
    ceremonies.start("alpha", "acceptance", path=ledger)
    ceremonies.start("beta", "review", path=ledger)

    assert ceremonies.next_index("alpha", "review", path=ledger) == 3
    assert ceremonies.next_index("alpha", "acceptance", path=ledger) == 2
    assert ceremonies.next_index("beta", "review", path=ledger) == 2
    assert ceremonies.next_index("beta", "close", path=ledger) == 1


# --- 2. Non-occurrence ---------------------------------------------------------------


def test_a_skip_consumes_an_occasion_index(ledger):
    """
    Scenario: a room holds review 1, skips review 2, holds review 3.

    Verification: the third occasion is numbered 3, not 2. The counter numbers the
    moments the ceremony was *due*, so renumbering around a skip would erase the
    non-occurrence — and non-occurrence is the design's only naturally-occurring
    ablation.
    """
    ceremonies.start("alpha", "review", path=ledger)
    skipped = ceremonies.skip("alpha", "review", reason="nothing to review", path=ledger)
    third = ceremonies.start("alpha", "review", path=ledger)

    assert skipped["occasion_id"] == "alpha:review:2"
    assert third["occasion_id"] == "alpha:review:3"
    report = ceremonies.audit(path=ledger)
    assert report.skipped == 1
    assert report.occasions == 2


def test_a_skip_is_distinguishable_from_an_unlogged_ceremony(ledger):
    """
    Scenario: room alpha skips its retrospective and records it; room beta simply
    never holds one and records nothing.

    Verification: the ledger separates them. Without the skip row both rooms would
    read as "no retrospective" and the ablation would be unrecoverable.
    """
    ceremonies.skip("alpha", "retrospective", reason="cost", path=ledger)
    ceremonies.start("beta", "review", path=ledger)

    rows = ceremonies.read_rows(ledger)
    skips = [row for row in rows if row["event"] == "skipped"]
    assert len(skips) == 1
    assert skips[0]["room"] == "alpha"
    assert not [
        row for row in rows if row["event"] == "skipped" and row["room"] == "beta"
    ]


def test_a_closed_room_that_neither_held_nor_skipped_a_ceremony_is_named(ledger):
    """
    Scenario: room atlas as it actually ran (2026-08-11) — open, acceptance, close,
    and a recorded retrospective skip, while three review rounds happened and wrote
    nothing at all.

    Verification: the audit names `atlas:review` and is not clean. Every other finding
    reads rows that exist; the ledger had nothing to read here, so a room could hold
    the one ceremony the lifecycle calls measurable, log none of it, and still audit
    clean.
    """
    ceremonies.start("atlas", "open", path=ledger)
    ceremonies.start("atlas", "acceptance", path=ledger)
    ceremonies.skip("atlas", "retrospective", reason="cost", path=ledger)
    ceremonies.start("atlas", "close", path=ledger)

    report = ceremonies.audit(path=ledger)
    assert report.unaccounted == ("atlas:review",)
    assert not report.clean()


def test_a_room_still_open_is_not_asked_for_ceremonies_it_has_not_reached(ledger):
    """
    Scenario: a room has held its open ceremony and nothing else. It has not closed.

    Verification: nothing is reported unaccounted. Before close a missing ceremony is
    `not yet`, and an audit that demanded the full set from a live room would report
    every room mid-flight as defective — which is the reading that gets an instrument
    ignored.
    """
    ceremonies.start("alpha", "open", path=ledger)

    report = ceremonies.audit(path=ledger)
    assert report.unaccounted == ()
    assert report.clean()


def test_skipping_a_ceremony_discharges_the_obligation_to_account_for_it(ledger):
    """
    Scenario: a room skips every ceremony it does not hold, then closes.

    Verification: clean. The check asks the room to *say* what happened, not to hold
    every ceremony — a skip row is a complete answer, which is what keeps the design's
    one naturally-occurring ablation cheap to record rather than penalised.
    """
    ceremonies.start("alpha", "open", path=ledger)
    ceremonies.record_comparator("alpha", "solo", "sess-1", path=ledger)
    ceremonies.skip("alpha", "review", reason="single deliverable", path=ledger)
    ceremonies.skip("alpha", "acceptance", reason="no gate", path=ledger)
    ceremonies.skip("alpha", "retrospective", reason="cost", path=ledger)
    ceremonies.start("alpha", "close", path=ledger)

    report = ceremonies.audit(path=ledger)
    assert report.unaccounted == ()
    assert report.clean()


# --- 3. The stable deliverable id ----------------------------------------------------


def test_a_deliverable_id_survives_a_title_change(ledger):
    """
    Scenario: a deliverable is minted, revised twice, and its title drifts.

    Verification: both revisions resolve to the one id. Nothing in a finished graph
    tells you two artifacts at two times were one deliverable, so the id has to be
    minted once and carried — not derived from whatever the thing is called later.
    """
    minted = ceremonies.mint_deliverable(
        "alpha", "Dispatch verb", owner_scope="architect", path=ledger
    )
    assert minted["deliverable_id"] == "alpha:dispatch-verb"

    ceremonies.record_revision(
        minted["deliverable_id"], artifact="src/thalamus/cli.py@abc123", path=ledger
    )
    ceremonies.record_revision(
        minted["deliverable_id"], artifact="src/thalamus/cli.py@def456", path=ledger
    )

    held = ceremonies.deliverables("alpha", path=ledger)
    assert list(held) == ["alpha:dispatch-verb"]
    assert len(held["alpha:dispatch-verb"]) == 2
    assert [row["artifact"] for row in held["alpha:dispatch-verb"]] == [
        "src/thalamus/cli.py@abc123",
        "src/thalamus/cli.py@def456",
    ]


def test_minting_the_same_title_twice_makes_two_deliverables(ledger):
    """
    Scenario: two deliverables are minted under one title.

    Verification: distinct ids. A false merge is the error that cannot be detected
    later — the two revision histories would interleave beyond separation — so the
    collision takes a suffix rather than resolving to the existing id.
    """
    first = ceremonies.mint_deliverable("alpha", "The report", path=ledger)
    second = ceremonies.mint_deliverable("alpha", "The report", path=ledger)
    assert first["deliverable_id"] == "alpha:the-report"
    assert second["deliverable_id"] == "alpha:the-report-2"


def test_a_deliverable_id_used_but_never_minted_is_reported(ledger):
    """
    Scenario: an occasion names a deliverable that was never minted (a typo, or a
    ceremony run before planning).

    Verification: the audit names it. An unminted id has no revision history to carry
    anything across, so it is the one deliverable defect that silently produces an
    empty analysis rather than a wrong one.
    """
    ceremonies.start("alpha", "review", deliverable_ids=["alpha:ghost"], path=ledger)
    report = ceremonies.audit(path=ledger)
    assert report.unminted == ("alpha:ghost",)
    assert not report.clean()


# --- 4. The assignment, written before the ceremony runs ------------------------------


def test_the_draw_replays_from_its_seed(ledger):
    """
    Scenario: the same units, arms, counts and seed are dealt twice — once with the
    units in a different order.

    Verification: identical assignments. The deal has to depend on the *set* of units
    and the seed alone, or a replay of a recorded assignment could disagree with the
    original while looking faithful.
    """
    units = ["d1", "d2", "d3", "d4"]
    first = ceremonies.draw(units, ["peer", "solo"], [2, 2], 20260810)
    second = ceremonies.draw(list(reversed(units)), ["peer", "solo"], [2, 2], 20260810)
    assert first == second
    assert sorted(first) == units
    assert sum(1 for arm in first.values() if arm == "peer") == 2


def test_a_draw_that_does_not_deal_every_unit_is_refused():
    """
    Verification: refused. An undealt unit is not in the reference distribution, so an
    assignment that leaves one out has silently changed the space it claims to be
    drawn from.
    """
    with pytest.raises(ValueError, match="does not deal every unit"):
        ceremonies.draw(["d1", "d2", "d3"], ["peer", "solo"], [1, 1], 1)
    with pytest.raises(ValueError, match="must be distinct"):
        ceremonies.draw(["d1", "d1"], ["peer"], [2], 1)


def test_the_assignment_row_records_the_space_not_only_the_seed(ledger):
    """
    Scenario: four deliverables split 2/2 in one room.

    Verification: the row carries the eligible units as they stood, the arm sizes, the
    block, the procedure and the space — 6 assignments, so a floor of 1/6. A seed
    alone replays nothing: it only reconstructs a deal against the procedure that
    consumed it and the units that were eligible at the time.
    """
    row = ceremonies.record_assignment(
        "alpha", "review",
        ["d1", "d2", "d3", "d4"], ["peer", "solo"], [2, 2], 99,
        prereg_id="prereg-001", path=ledger,
    )
    assert row["units"] == ["d1", "d2", "d3", "d4"]
    assert row["counts"] == [2, 2]
    assert row["block"] == "alpha"
    assert row["procedure"] == ceremonies.PROCEDURE
    assert row["space"] == 6
    assert row["prereg_id"] == "prereg-001"
    assert ceremonies.assignment_space(4, (2, 2)) == 6


def test_an_arm_with_no_prior_assignment_is_reported(ledger):
    """
    Scenario: an occasion runs under arm `peer` with nothing ever assigned.

    Verification: the audit names it as unassigned. This is the sharp one — post-hoc
    assignment does not weaken the inference, it means the reference distribution does
    not exist, and no later care recovers it.
    """
    ceremonies.mint_deliverable("alpha", "d1", path=ledger)
    ceremonies.start(
        "alpha", "review", deliverable_ids=["alpha:d1"], arm="peer", path=ledger
    )
    report = ceremonies.audit(path=ledger)
    assert report.unassigned == ("alpha:review:1",)
    assert not report.clean()


def test_an_assignment_written_after_the_start_is_caught_by_position(ledger):
    """
    Scenario: the occasion starts, and only then is the assignment written.

    Verification: reported as a late assignment. Detection is by position in the file
    — the four record kinds share one ledger precisely so that "before" is answerable
    by order rather than by a second-resolution timestamp two writes can tie on.
    """
    ceremonies.mint_deliverable("alpha", "d1", path=ledger)
    ceremonies.start(
        "alpha", "review", deliverable_ids=["alpha:d1"], arm="peer", path=ledger
    )
    ceremonies.record_assignment(
        "alpha", "review", ["alpha:d1"], ["peer"], [1], 3, path=ledger
    )

    report = ceremonies.audit(path=ledger)
    assert report.late_assignments == ("alpha:review:1",)
    assert report.unassigned == ()
    assert not report.clean()


def test_a_realized_arm_contradicting_the_assignment_is_reported(ledger):
    """
    Scenario: `alpha:d1` is dealt to `solo`, and the occasion runs it as `peer`.

    Verification: the audit reports the mismatch. The start row does not default its
    arm from the assignment on purpose — copying one into the other would make a
    randomization that was not honoured unobservable from either record alone.
    """
    ceremonies.mint_deliverable("alpha", "d1", path=ledger)
    ceremonies.mint_deliverable("alpha", "d2", path=ledger)
    assignment = ceremonies.record_assignment(
        "alpha", "review", ["alpha:d1", "alpha:d2"], ["peer", "solo"], [1, 1], 5,
        path=ledger,
    )
    dealt_solo = [
        unit for unit, arm in assignment["assignment"].items() if arm == "solo"
    ][0]
    ceremonies.start(
        "alpha", "review", deliverable_ids=[dealt_solo], arm="peer", path=ledger
    )

    report = ceremonies.audit(path=ledger)
    assert report.arm_mismatches == ("alpha:review:1",)
    assert not report.clean()


def test_an_occasion_with_no_arm_is_not_an_experiment(ledger):
    """
    Scenario: an ordinary ceremony runs outside any ablation.

    Verification: no assignment is demanded of it. Requiring one would report every
    routine occasion as a defect and train the operator to ignore the audit — which
    would cost exactly the cases it exists for.
    """
    ceremonies.mint_deliverable("alpha", "d1", path=ledger)
    ceremonies.start("alpha", "review", deliverable_ids=["alpha:d1"], path=ledger)
    report = ceremonies.audit(path=ledger)
    assert report.unassigned == ()
    assert report.clean()


def test_a_redraw_supersedes_without_deleting_the_first(ledger):
    """
    Scenario: a block is assigned, then re-assigned under a different seed.

    Verification: both rows survive and the later one is last. A superseded draw is
    evidence about what the design did; dropping it would hide a re-randomization,
    which is the thing an audit most needs to be able to see.
    """
    ceremonies.record_assignment(
        "alpha", "review", ["d1", "d2"], ["peer", "solo"], [1, 1], 1, path=ledger
    )
    second = ceremonies.record_assignment(
        "alpha", "review", ["d1", "d2"], ["peer", "solo"], [1, 1], 2, path=ledger
    )
    assigned = [row for row in ceremonies.read_rows(ledger) if row["event"] == "assigned"]
    assert len(assigned) == 2
    assert [row["assignment_seed"] for row in assigned] == [1, 2]
    assert assigned[-1]["assignment"] == second["assignment"]


# --- 5-7. The forecast, its resolution, and the comparator ----------------------------


def test_a_commitment_is_resolvable_only_if_it_predicted_something(ledger):
    """
    Scenario: two commitments — one naming a predicted artifact and a horizon, one
    naming neither.

    Verification: both are recorded, and the fields that make a forecast resolvable
    are present on the row either way. The deliverables report is a forecast
    precisely so tooling can settle it later; a commitment carrying no
    prediction and no horizon is a sentence about intent, and the row has to show
    that rather than hide it behind a default.
    """
    ceremonies.mint_deliverable("alpha", "The verb", path=ledger)
    concrete = ceremonies.commit(
        "alpha", "alpha:the-verb", "the dispatch verb ships",
        predicted_artifact="src/thalamus/cli.py", resolve_by="2026-09-01", path=ledger,
    )
    vague = ceremonies.commit(
        "alpha", "alpha:the-verb", "things improve", path=ledger
    )

    assert concrete["predicted_artifact"] and concrete["resolve_by"]
    assert vague["predicted_artifact"] == "" and vague["resolve_by"] == ""


def test_a_resolution_without_evidence_is_refused(ledger):
    """
    Scenario: a resolution is written with an outcome but nothing to back it.

    Verification: refused. An unevidenced resolution is a self-report wearing a
    measurement's shape, which is strictly worse than an unresolved commitment —
    the latter is visibly open, the former reads as settled.
    """
    with pytest.raises(ValueError, match="evidence"):
        ceremonies.resolve(
            "alpha:the-verb", "appeared", resolver="ci", evidence="  ", path=ledger
        )
    with pytest.raises(ValueError, match="resolver"):
        ceremonies.resolve(
            "alpha:the-verb", "appeared", resolver="", evidence="commit abc", path=ledger
        )
    with pytest.raises(ValueError, match="outcome"):
        ceremonies.resolve(
            "alpha:the-verb", "went well", resolver="ci", evidence="commit abc", path=ledger
        )


def test_a_member_resolving_its_own_rooms_forecast_is_named(ledger):
    """
    Scenario: `qe` sits in room alpha and later resolves one of alpha's commitments.

    Verification: the audit names it. Nothing can stop a member running the verb, so
    the design's "written by tooling and never by a member" is enforced by being
    checkable — the forecast's entire value is that the forecaster does not control
    the resolution, and a member-written resolution voids the result rather than
    merely blemishing the record.
    """
    ceremonies.start("alpha", "open", participant_scopes=["qe", "designer"], path=ledger)
    ceremonies.mint_deliverable("alpha", "The verb", path=ledger)
    ceremonies.commit("alpha", "alpha:the-verb", "ships", path=ledger)
    ceremonies.resolve(
        "alpha:the-verb", "appeared", resolver="qe", evidence="commit abc",
        room="alpha", path=ledger,
    )

    report = ceremonies.audit(path=ledger)
    assert report.member_resolutions == ("alpha:the-verb by `qe`",)
    assert not report.clean()


def test_a_resolution_by_tooling_is_clean(ledger):
    """
    Scenario: the same commitment, resolved by a job that was never in the room.

    Verification: clean. The check discriminates on who resolved it, not on the fact
    that a resolution happened — otherwise it would penalise exactly the behaviour
    item 6 asks for.
    """
    ceremonies.start("alpha", "open", participant_scopes=["qe"], path=ledger)
    ceremonies.record_comparator("alpha", "solo", "sess-1", path=ledger)
    ceremonies.mint_deliverable("alpha", "The verb", path=ledger)
    ceremonies.commit("alpha", "alpha:the-verb", "ships", path=ledger)
    ceremonies.start("alpha", "close", path=ledger)
    ceremonies.skip("alpha", "review", path=ledger)
    ceremonies.skip("alpha", "acceptance", path=ledger)
    ceremonies.skip("alpha", "retrospective", path=ledger)
    ceremonies.resolve(
        "alpha:the-verb", "appeared", resolver="resolve-commitments.py",
        evidence="commit abc", room="alpha", path=ledger,
    )

    report = ceremonies.audit(path=ledger)
    assert report.member_resolutions == ()
    assert report.clean()


def test_a_comparator_named_after_the_room_closed_is_named(ledger):
    """
    Scenario: a room closes, and only then is an out-of-room comparator identified.

    Verification: the audit reports it as late, by file position — the same mechanism
    item 4 uses for assignments, and for the same reason. A comparator chosen once
    the outcomes are visible has absorbed them, so lateness here is not untidiness,
    it is the comparison being dead.
    """
    ceremonies.start("alpha", "open", path=ledger)
    ceremonies.start("alpha", "close", path=ledger)
    ceremonies.record_comparator("alpha", "ticket", "ticket-7", path=ledger)

    report = ceremonies.audit(path=ledger)
    assert report.late_comparators == ("alpha",)
    assert report.uncompared == ()


def test_a_closed_room_that_never_named_a_comparator_is_named(ledger):
    """
    Scenario: a room runs and closes without ever identifying what it will be read
    against.

    Verification: reported. Nothing later supplies this — the arms are solo, ticket
    and room, and a room with no out-of-room unit is an arm with no contrast.
    """
    ceremonies.start("alpha", "open", path=ledger)
    ceremonies.start("alpha", "close", path=ledger)

    assert ceremonies.audit(path=ledger).uncompared == ("alpha",)


def test_a_room_cannot_be_its_own_comparator(ledger):
    """
    Scenario: someone names the `room` arm as the comparator.

    Verification: refused. `room` is the treatment, so accepting it would record a
    contrast of the treatment against itself in the field built to prevent exactly
    that.
    """
    with pytest.raises(ValueError, match="cannot compare against itself"):
        ceremonies.record_comparator("alpha", "room", "alpha", path=ledger)


def test_outstanding_lists_commitments_no_resolution_has_settled(ledger):
    """
    Scenario: two commitments, one resolved.

    Verification: only the unresolved one is outstanding, and it is *not* an audit
    finding. An open forecast is the ordinary state of a horizon that has not
    arrived; treating it as a defect would push rooms toward resolving early, which
    is the one thing the forecaster must not control.
    """
    ceremonies.mint_deliverable("alpha", "One", path=ledger)
    ceremonies.mint_deliverable("alpha", "Two", path=ledger)
    ceremonies.commit("alpha", "alpha:one", "lands", path=ledger)
    ceremonies.commit("alpha", "alpha:two", "lands", path=ledger)
    ceremonies.resolve(
        "alpha:one", "appeared", resolver="ci", evidence="commit abc", path=ledger
    )

    open_rows = ceremonies.outstanding(path=ledger)
    assert [row["deliverable_id"] for row in open_rows] == ["alpha:two"]
    # An open commitment is not a defect: the audit stays clean while it waits.
    assert ceremonies.audit(path=ledger).clean()


def test_a_commitment_on_an_unminted_deliverable_is_reported(ledger):
    """
    Scenario: a commitment names a deliverable id that was never minted.

    Verification: the existing unminted check catches it. A forecast about something
    with no stable identity cannot be resolved against anything later, which is the
    same loss item 3 exists to prevent.
    """
    ceremonies.commit("alpha", "alpha:ghost", "lands", path=ledger)
    assert ceremonies.audit(path=ledger).unminted == ("alpha:ghost",)


# --- Acknowledgement: the exit code, and nothing else ---------------------------------


@pytest.fixture
def acks(tmp_path):
    return tmp_path / "acknowledged.jsonl"


def _room_missing_review_and_comparator(ledger):
    ceremonies.start("alpha", "open", path=ledger)
    ceremonies.skip("alpha", "acceptance", path=ledger)
    ceremonies.skip("alpha", "retrospective", path=ledger)
    ceremonies.start("alpha", "close", path=ledger)


def test_acknowledging_discharges_the_exit_code_but_not_the_finding(ledger, acks):
    """
    Scenario: a permanent, understood finding is acknowledged.

    Verification: `unacknowledged()` empties while `clean()` stays False and the
    finding is still printed with its reason. The ledger is evidence; the way to stop
    an audit failing must never be to make it stop saying what happened. Only the
    caller's gate policy moves.
    """
    _room_missing_review_and_comparator(ledger)
    ceremonies.acknowledge(
        "unaccounted:alpha:review", reason="ran before the ledger took reviews",
        ledger=ledger, path=acks,
    )
    ceremonies.acknowledge(
        "uncompared:alpha", reason="predates the pre-registration",
        ledger=ledger, path=acks,
    )

    seen = ceremonies.load_acknowledged(acks)
    report = ceremonies.audit(path=ledger)

    assert report.unacknowledged(seen) == ()
    assert not report.clean()
    note = report.note(seen)
    assert "alpha:review" in note
    assert "ran before the ledger took reviews" in note


def test_an_acknowledgement_names_one_finding_and_a_new_one_still_fails(ledger, acks):
    """
    Scenario: alpha's findings are acknowledged, then room beta closes with the same
    two defects.

    Verification: beta's findings are unacknowledged and the gate fails again. This is
    the property the whole mechanism rests on — an acknowledgement that generalised to
    a category would turn one read finding into a permanently silenced class, which is
    how a suppression file becomes the reason nobody sees the next real defect.
    """
    _room_missing_review_and_comparator(ledger)
    ceremonies.acknowledge(
        "unaccounted:alpha:review", reason="understood", ledger=ledger, path=acks
    )
    ceremonies.acknowledge(
        "uncompared:alpha", reason="understood", ledger=ledger, path=acks
    )
    assert ceremonies.audit(path=ledger).unacknowledged(
        ceremonies.load_acknowledged(acks)
    ) == ()

    ceremonies.start("beta", "open", path=ledger)
    ceremonies.skip("beta", "acceptance", path=ledger)
    ceremonies.skip("beta", "retrospective", path=ledger)
    ceremonies.start("beta", "close", path=ledger)

    still_open = ceremonies.audit(path=ledger).unacknowledged(
        ceremonies.load_acknowledged(acks)
    )
    assert ("unaccounted", "beta:review") in still_open
    assert ("uncompared", "beta") in still_open


def test_a_finding_cannot_be_acknowledged_before_it_exists(ledger, acks):
    """
    Scenario: an acknowledgement is written for a finding the ledger does not report.

    Verification: refused. Acknowledging ahead of the defect would pre-approve a class
    of failure, which inverts the mechanism — it exists to retire a finding someone has
    read, never to arrange in advance that nobody has to.
    """
    _room_missing_review_and_comparator(ledger)
    with pytest.raises(ValueError, match="not a current finding"):
        ceremonies.acknowledge(
            "unaccounted:gamma:review", reason="pre-approving", ledger=ledger, path=acks
        )
    with pytest.raises(ValueError, match="reason"):
        ceremonies.acknowledge(
            "uncompared:alpha", reason="   ", ledger=ledger, path=acks
        )


def test_categories_keep_two_findings_about_one_room_apart(ledger, acks):
    """
    Scenario: room alpha carries both an unaccounted ceremony and a missing comparator,
    and only the comparator one is acknowledged.

    Verification: the ceremony finding still fails. The category is part of the key
    precisely because both findings can name the same room, and a key of `alpha` alone
    would retire a finding nobody read.
    """
    _room_missing_review_and_comparator(ledger)
    ceremonies.acknowledge(
        "uncompared:alpha", reason="understood", ledger=ledger, path=acks
    )

    still_open = ceremonies.audit(path=ledger).unacknowledged(
        ceremonies.load_acknowledged(acks)
    )
    assert still_open == (("unaccounted", "alpha:review"),)


# --- The ledger as a whole ------------------------------------------------------------


def test_an_empty_ledger_says_what_is_lost_rather_than_nothing(ledger):
    text = ceremonies.render(path=ledger)
    assert "empty" in text
    assert "cannot be recovered" in text
    assert ceremonies.audit(path=ledger).occasions == 0


def test_render_shows_occasions_skips_and_deliverables(ledger):
    ceremonies.mint_deliverable("alpha", "Dispatch verb", path=ledger)
    ceremonies.record_revision("alpha:dispatch-verb", artifact="cli.py", path=ledger)
    ceremonies.start(
        "alpha", "review",
        participant_scopes=["qe", "architect"],
        deliverable_ids=["alpha:dispatch-verb"],
        path=ledger,
    )
    ceremonies.end("alpha:review:1", outcome="accepted", path=ledger)
    ceremonies.skip("alpha", "retrospective", reason="single deliverable", path=ledger)

    text = ceremonies.render(path=ledger)
    assert "room `alpha`" in text
    assert "alpha:review:1" in text
    assert "SKIPPED — single deliverable" in text
    assert "1 revision(s)" in text
    assert "UNFINISHED" not in text
    assert "clean" in text


def test_a_malformed_line_does_not_take_the_ledger_with_it(ledger):
    """
    Scenario: a truncated write leaves half a JSON object in the file.

    Verification: the surrounding rows still read. An append-only capture ledger whose
    reader dies on one bad line would lose every occasion recorded after the first
    interrupted write — the failure mode it was built to survive.
    """
    ceremonies.start("alpha", "review", path=ledger)
    with ledger.open("a") as handle:
        handle.write('{"event": "start", "room": "alpha"\n')
    ceremonies.start("alpha", "acceptance", path=ledger)

    rows = ceremonies.read_rows(ledger)
    assert len(rows) == 2
    assert [row["occasion_id"] for row in rows] == [
        "alpha:review:1", "alpha:acceptance:1",
    ]


def test_an_end_for_an_occasion_that_never_started_is_reported(ledger):
    ceremonies.end("alpha:review:9", path=ledger)
    report = ceremonies.audit(path=ledger)
    assert report.orphan_ends == ("alpha:review:9",)
    assert not report.clean()
