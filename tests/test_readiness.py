"""The first-party readiness descriptor — what it refuses, and why absence is a refusal.

These tests encode the three conditions the design was accepted under (consultation
`d4c5982f12cf41ab`, `architect` scope): the default is inverted so absence refuses, the
coverage gap is real and the screen read is retained only in the direction it is sound,
and the bracket is closed only by the session that opened it.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from thalamus.harness import panes as panes_mod
from thalamus.harness import readiness

HOOKS = Path(__file__).resolve().parents[1] / "src/thalamus/harness/hooks/cursor"


def _pane(room="alpha", scope="qe", pane_id="%100"):
    return panes_mod.Pane(pane_id, scope, room, scope, "cursor", "/w", dead=False)


class TestAbsenceRefuses:
    """Condition 1: absence of a record is never read as "probably idle"."""

    def test_a_member_with_no_descriptor_is_unreadable(self, tmp_path):
        """
        Scenario: a Cursor member whose hook suite was never armed

        Verification: the verdict is `unreadable`, so dispatch refuses it.

        This is the member whose modals nothing would report, which makes it exactly
        the member that must not be typed into. Reading a missing file as idle would
        invert the one guarantee the descriptor exists to provide.
        """
        assert readiness.descriptor_status("alpha", "qe", root=tmp_path) == panes_mod.UNREADABLE

    @pytest.mark.parametrize(
        "content",
        ["", "not json at all", '{"phase": "pen', "[]", '"a string"', '{"phase": "moot"}'],
        ids=["empty", "garbage", "truncated", "array", "scalar", "unknown-phase"],
    )
    def test_every_way_a_record_can_fail_to_arrive_refuses(self, tmp_path, content):
        """A truncated write and an absent file are one outcome, deliberately: each is
        equally uninformative about whether a modal is up."""
        path = readiness.descriptor_path("alpha", "qe", root=tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text(content)
        assert readiness.descriptor_status("alpha", "qe", root=tmp_path) == panes_mod.UNREADABLE

    def test_an_unclosed_bracket_keeps_refusing(self, tmp_path):
        """A session killed while its modal was up leaves `pending` standing forever.

        That is the fail-closed direction and it is not a leak: the pane is either
        still holding that modal or it is gone, and `panes.room_panes` drops the gone
        ones by liveness before readiness is ever asked.
        """
        readiness.write_descriptor("alpha", "qe", readiness.PENDING,
                                   session_id="s1", root=tmp_path)
        assert readiness.descriptor_status("alpha", "qe", root=tmp_path) == panes_mod.WAITING


class TestTheBracket:
    def test_ready_then_pending_then_ready(self, tmp_path):
        """The interval a modal can occupy, delimited by two events we emit."""
        for phase, expected in (
            (readiness.READY, panes_mod.DELIVERABLE),
            (readiness.PENDING, panes_mod.WAITING),
            (readiness.READY, panes_mod.DELIVERABLE),
        ):
            readiness.write_descriptor("alpha", "qe", phase, session_id="s1", root=tmp_path)
            assert readiness.descriptor_status("alpha", "qe", root=tmp_path) == expected

    def test_a_foreign_session_cannot_close_a_bracket_it_did_not_open(self, tmp_path):
        """
        Scenario: a member runs `agent -p` from its own shell while holding a modal

        Verification: the child's `sessionStart` does not report the parent ready.

        The child inherits `THALAMUS_ROOM` and `THALAMUS_SCOPE`, so it writes to the
        same descriptor. Without this rule the bracket would be cleared by its own side
        effect, at the exact moment it is describing.
        """
        readiness.write_descriptor("alpha", "qe", readiness.PENDING,
                                   session_id="parent", root=tmp_path)
        readiness.write_descriptor("alpha", "qe", readiness.READY,
                                   session_id="child", root=tmp_path)
        assert readiness.descriptor_status("alpha", "qe", root=tmp_path) == panes_mod.WAITING

        readiness.write_descriptor("alpha", "qe", readiness.READY,
                                   session_id="parent", root=tmp_path)
        assert readiness.descriptor_status("alpha", "qe", root=tmp_path) == panes_mod.DELIVERABLE

    def test_a_roomless_session_writes_nothing(self, tmp_path):
        """Readiness is a room's question; a solo session has no dispatcher asking it."""
        assert readiness.write_descriptor("", "qe", readiness.READY, root=tmp_path) is None
        assert list(tmp_path.iterdir()) == []

    def test_members_of_one_room_do_not_share_a_descriptor(self, tmp_path):
        readiness.write_descriptor("alpha", "qe", readiness.PENDING, root=tmp_path)
        readiness.write_descriptor("alpha", "designer", readiness.READY, root=tmp_path)
        assert readiness.descriptor_status("alpha", "qe", root=tmp_path) == panes_mod.WAITING
        assert readiness.descriptor_status("alpha", "designer",
                                           root=tmp_path) == panes_mod.DELIVERABLE

    def test_the_write_is_atomic(self, tmp_path):
        """No reader ever sees a half-written object under the real path."""
        readiness.write_descriptor("alpha", "qe", readiness.READY, root=tmp_path)
        room_dir = tmp_path / "alpha"
        assert [p.name for p in room_dir.iterdir()] == ["qe.json"]
        assert json.loads((room_dir / "qe.json").read_text())["phase"] == readiness.READY


class TestTheScreenIsAPositiveOnlyFalsifier:
    """Condition 2: the bracket covers shell and MCP calls, and nothing else.

    The screen read is kept for part of that remainder, in the one direction it is
    sound — it may refuse, it may never permit.
    """

    def test_a_visible_modal_refuses_a_ready_descriptor(self, tmp_path):
        """
        Scenario: a workspace-trust dialog — outside the bracket — is on screen

        Verification: the send is refused anyway.

        This is the coverage gap being caught by the falsifier that covers part of it.
        A descriptor-only reading would deliver into this pane.
        """
        readiness.write_descriptor("alpha", "qe", readiness.READY, root=tmp_path)
        verdict = readiness.pane_status(
            _pane(), root=tmp_path, screen_fn=lambda _pane_id: panes_mod.WAITING,
        )
        assert verdict == panes_mod.WAITING

    def test_a_clean_screen_cannot_clear_a_pending_bracket(self, tmp_path):
        """The inversion that would reintroduce "did not see a modal, so send".

        `capture-pane` truncates to the visible height, so a modal below the fold reads
        as a clean screen. If a clean screen could upgrade a verdict, the descriptor
        would be decorative.
        """
        readiness.write_descriptor("alpha", "qe", readiness.PENDING, root=tmp_path)
        verdict = readiness.pane_status(
            _pane(), root=tmp_path, screen_fn=lambda _pane_id: panes_mod.DELIVERABLE,
        )
        assert verdict == panes_mod.WAITING

    def test_a_clean_screen_cannot_supply_a_missing_descriptor(self, tmp_path):
        """The same inversion in its other form: an unarmed member stays unaddressable
        however healthy its screen looks."""
        verdict = readiness.pane_status(
            _pane(), root=tmp_path, screen_fn=lambda _pane_id: panes_mod.DELIVERABLE,
        )
        assert verdict == panes_mod.UNREADABLE

    def test_both_signals_agreeing_is_the_only_way_to_be_deliverable(self, tmp_path):
        readiness.write_descriptor("alpha", "qe", readiness.READY, root=tmp_path)
        verdict = readiness.pane_status(
            _pane(), root=tmp_path, screen_fn=lambda _pane_id: panes_mod.DELIVERABLE,
        )
        assert verdict == panes_mod.DELIVERABLE


class TestTheHooksWriteWhatTheReaderReads:
    """The shell half and the Python half are two implementations of one format, which
    is exactly the pair that drifts. These drive the real scripts."""

    def _run(self, script, home, *, room="alpha", scope="qe", session="s1", payload=None):
        return subprocess.run(
            [str(HOOKS / script)],
            input=json.dumps(payload if payload is not None else {"session_id": session}),
            capture_output=True, text=True, timeout=15,
            env={
                "HOME": str(home), "PATH": "/usr/bin:/bin",
                "THALAMUS_ROOM": room, "THALAMUS_SCOPE": scope,
            },
        )

    def test_the_pending_hook_writes_a_descriptor_the_reader_calls_waiting(self, tmp_path):
        result = self._run("readiness-pending.sh", tmp_path)
        assert result.returncode == 0, result.stderr
        root = tmp_path / ".thalamus" / "readiness"
        assert readiness.descriptor_status("alpha", "qe", root=root) == panes_mod.WAITING

    def test_the_pending_hook_abstains_on_the_permission_decision(self, tmp_path):
        """It is wired to `beforeShellExecution` beside two guards that do decide. A
        hook that abstains has to say so in the vendor's vocabulary or it reads as a
        deny."""
        result = self._run("readiness-pending.sh", tmp_path)
        assert json.loads(result.stdout) == {"permission": "allow"}

    def test_the_ready_hook_closes_its_own_bracket(self, tmp_path):
        self._run("readiness-pending.sh", tmp_path, session="s1")
        self._run("readiness-ready.sh", tmp_path, session="s1")
        root = tmp_path / ".thalamus" / "readiness"
        assert readiness.descriptor_status("alpha", "qe", root=root) == panes_mod.DELIVERABLE

    def test_the_ready_hook_refuses_to_close_a_foreign_bracket(self, tmp_path):
        """The nested `agent -p` case, driven through the real scripts."""
        self._run("readiness-pending.sh", tmp_path, session="parent")
        self._run("readiness-ready.sh", tmp_path, session="child")
        root = tmp_path / ".thalamus" / "readiness"
        assert readiness.descriptor_status("alpha", "qe", root=root) == panes_mod.WAITING

    def test_a_background_agent_is_not_a_room_member(self, tmp_path):
        self._run("readiness-pending.sh", tmp_path, session="parent")
        self._run("readiness-ready.sh", tmp_path,
                  payload={"session_id": "bg", "is_background_agent": True})
        root = tmp_path / ".thalamus" / "readiness"
        assert readiness.descriptor_status("alpha", "qe", root=root) == panes_mod.WAITING

    def test_a_roomless_session_leaves_no_descriptor_behind(self, tmp_path):
        result = self._run("readiness-ready.sh", tmp_path, room="")
        assert result.returncode == 0, result.stderr
        assert not (tmp_path / ".thalamus" / "readiness").exists()


class TestTheRowTheRefusalNames:
    """`_cursor_targets` refuses by naming `room.peer_readiness`. A refusal that names
    a row nobody declared is worse than a vague one — it reads as citing a record."""

    def test_the_named_row_exists_for_both_harnesses(self):
        from thalamus.contract.rooms import ROOM_ROWS

        declared = {(r.component, r.harness) for r in ROOM_ROWS}
        assert ("room.peer_readiness", "cursor") in declared
        assert ("room.peer_readiness", "claude") in declared

    def test_the_cursor_row_states_its_coverage_gap(self):
        """Partial coverage on a safety gate is the shape that hides a failure. The row
        has to say what is bracketed, not merely that something is."""
        from thalamus.contract.rooms import ROOM_ROWS

        row = next(r for r in ROOM_ROWS
                   if r.component == "room.peer_readiness" and r.harness == "cursor")
        assert "shell and MCP" in row.note
        assert "outside the bracket" in row.note

    def test_delivery_cannot_outrank_readiness(self):
        """
        Scenario: someone promotes `room.peer_delivery` on a harness that cannot say
        whether a member is holding a modal

        Verification: the check drifts, naming the gate.

        This is the vacuous pass the row split was made to prevent: delivery gated on
        the *roster* passed the moment tmux supplied one, while the hazard it was
        protecting against was untouched.
        """
        from thalamus.contract import rooms
        from thalamus.contract.boundaries import Provision

        weakened = tuple(
            rooms.RoomRow(r.component, r.harness, Provision.ABSENT, r.evidence, r.note)
            if (r.component, r.harness) == ("room.peer_readiness", "cursor") else r
            for r in rooms.ROOM_ROWS
        )
        original = rooms.ROOM_ROWS
        rooms.ROOM_ROWS = weakened
        try:
            verdicts = {row.label: (outcome, detail)
                        for row, outcome, detail in rooms.check_rooms()}
        finally:
            rooms.ROOM_ROWS = original

        outcome, detail = verdicts["room.peer_delivery on cursor"]
        assert outcome == "drift"
        assert "room.peer_readiness" in detail

    def test_the_shipped_table_passes_its_own_gate(self):
        from thalamus.contract.rooms import check_rooms

        assert [r for r in check_rooms() if r[1] == "drift"] == []


class TestTheWiring:
    def test_both_halves_of_both_pairs_are_wired(self):
        """A bracket with only an opening event never reopens a member; one with only a
        closing event never refuses. Either half alone is worse than neither."""
        from thalamus.harness.install import CURSOR_HOOK_WIRING

        wiring = set(CURSOR_HOOK_WIRING)
        assert ("beforeShellExecution", "readiness-pending.sh") in wiring
        assert ("afterShellExecution", "readiness-ready.sh") in wiring
        assert ("beforeMCPExecution", "readiness-pending.sh") in wiring
        assert ("afterMCPExecution", "readiness-ready.sh") in wiring

    def test_the_resting_state_is_established_at_session_start(self):
        """Without this a freshly-launched member is unaddressable until it happens to
        run a shell command, which is a room that cannot start."""
        from thalamus.harness.install import CURSOR_HOOK_WIRING

        assert ("sessionStart", "readiness-ready.sh") in CURSOR_HOOK_WIRING
