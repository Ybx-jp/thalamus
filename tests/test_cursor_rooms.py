"""Rooms on a harness that registers nothing.

Subject: the three mechanisms a Cursor room rests on — the boundary variable
(`pin._room_env`), the roster read off the control plane (`harness/panes.py`), and the
readiness verdict that decides whether `harness/dispatch.py` may type into a member.

Infrastructure: the screen fixtures below are **verbatim captures** from a live
interactive Cursor session driven in tmux on 2026-08-13 against build
2026.08.11-e8db854. They are quoted rather than invented because the branch
they exercise is the one that decides whether a dispatch approves a tool call nobody
saw: a hand-written approximation of a dialog would test the regex against itself.
"""

from __future__ import annotations

import pytest

from thalamus.harness import dispatch, pin
from thalamus.harness import panes as panes_mod

# --- captured screens -------------------------------------------------------------

# A member holding an approval dialog. The `→` marks the highlighted default, and it
# is `Run (once)` — so the Enter that follows a blind send runs the command. Measured:
# it did.
WAITING_SCREEN = """\
  $ uptime Waiting for approval...

────────────────────────────────────────────────────────────────────────────────
 $  uptime in .

 Run this command?
 Not in allowlist: uptime
  → Run (once) (y)
    Add Shell(uptime) to allowlist? (tab)
    Run Everything (shift+tab)
    Skip & tell the agent what to do instead (esc or n)
"""

# A member waiting for a prompt. Note the arrow: an idle composer draws one too, which
# is why the arrow alone cannot be the discriminator.
IDLE_SCREEN = """\
  → Plan, search, build anything


  Composer 2.5
  ~/code/thalamus ·
  worktree-cursor-rooms-tmux
"""

# A member that has just finished a turn — a second arrow-marked line with no hotkey.
FOLLOW_UP_SCREEN = """\
  Thirty is three tens, a round milestone, and a natural place to pause.

  → Add a follow-up

  Composer 2.5 · 9.6%
  ~/code/thalamus ·
"""

# Mid-turn. The footer carries the *selected model's* name, which is why readiness is
# never anchored to it: this capture says `Auto`, the ones above say `Composer 2.5`,
# and an operator switching models must not change who is addressable.
BUSY_SCREEN = """\
  Twenty-nine is prime and the last number before thirty.
  → Count slowly from 1 to 30, writing a short sentence about each number.
  2 tasks
  Auto · 9.7%                                  Auto-review
  ~/code/thalamus ·
"""


class TestTheBoundaryIsTheHarnesssOwnVariable:
    def test_each_harness_gets_the_config_root_it_actually_reads(self):
        """
        Scenario: the same room, entered on each harness

        Verification: the variable named is the one that harness resolves its config
        root from, and the paths do not collide.

        Handing a Cursor member `CLAUDE_CONFIG_DIR` fails silently and in the worst
        direction: the member reads its own default root, joins no room, shares the
        `chats/` store with every other session, and still reports as a member from
        every surface that reports one.
        """
        claude = dict(pin._room_env("alpha", "claude"))
        cursor = dict(pin._room_env("alpha", "cursor"))

        assert claude["THALAMUS_ROOM"] == cursor["THALAMUS_ROOM"] == "alpha"
        assert "CLAUDE_CONFIG_DIR" in claude and "CURSOR_CONFIG_DIR" not in claude
        assert "CURSOR_CONFIG_DIR" in cursor and "CLAUDE_CONFIG_DIR" not in cursor
        assert claude["CLAUDE_CONFIG_DIR"] != cursor["CURSOR_CONFIG_DIR"]

    def test_a_harness_with_no_declared_variable_is_refused(self):
        """A room that cannot be spelled is refused rather than launched unbounded."""
        with pytest.raises(ValueError, match="no config-root variable"):
            pin._room_env("alpha", "aider")

    def test_a_roomless_launch_clears_the_launched_harnesss_variable(self, monkeypatch):
        """
        Scenario: a roomless window opened in a tmux session that was created for a room

        Verification: the `env` prefix unsets the variable *that harness* reads.

        `new-session -e` stores its variables in the session environment and every
        later window inherits them, so silence is not the same as "no room". Clearing
        Claude Code's name in front of a Cursor binary clears nothing that binary
        reads — the leak this guards against, one harness over.
        """
        monkeypatch.delenv("CURSOR_CONFIG_DIR", raising=False)
        assert pin._room_clear("cursor") == [
            "env", "-u", "THALAMUS_ROOM", "-u", "CURSOR_CONFIG_DIR",
        ]

    def test_the_room_rides_the_argv_on_cursor_too(self):
        """
        Verification: the room is in the window's own command, not only its environment.

        `respawn-window` — the console's restart button — re-executes the argv with
        tmux's `-e` variables gone. The pin survives that on Cursor because the scope
        rides the argv; the room has to ride it for the same reason, or a phone tap
        turns a member into an outsider that still looks like a member.
        """
        argv = pin._with_room(["agent", "--trust"], "alpha", "cursor")
        assert argv[0] == "env"
        assert "THALAMUS_ROOM=alpha" in argv
        assert any(part.startswith("CURSOR_CONFIG_DIR=") for part in argv)


class TestReadinessIsReadFromTheScreen:
    """The branch that decides whether dispatch may type into somebody's session."""

    def test_an_approval_dialog_is_refused(self):
        assert panes_mod.classify(WAITING_SCREEN) == panes_mod.WAITING

    @pytest.mark.parametrize(
        "screen", [IDLE_SCREEN, FOLLOW_UP_SCREEN, BUSY_SCREEN],
        ids=["idle", "after-a-turn", "mid-turn"],
    )
    def test_a_working_member_is_deliverable(self, screen):
        """
        Verification: none of the three ready screens reads as a dialog.

        Two of them draw an arrow-marked line (`→ Plan, search, build anything`,
        `→ Add a follow-up`), which is why the discriminator is the *hotkey* rather
        than the arrow: matching the arrow alone would refuse every idle member in
        the room and report a working room as unreachable.
        """
        assert panes_mod.classify(screen) == panes_mod.DELIVERABLE

    def test_a_blank_screen_is_refused_rather_than_assumed_ready(self):
        """A pane that has not drawn yet is not a target. Fail closed."""
        assert panes_mod.classify("   \n\n  ") == panes_mod.UNREADABLE


class TestTheRosterIsTheControlPlane:
    def test_room_scope_and_harness_come_off_the_start_command(self):
        start = ("env THALAMUS_ROOM=alpha CURSOR_CONFIG_DIR=/rooms/alpha/cursor "
                 "env THALAMUS_SCOPE=qe agent --trust")
        assert panes_mod._assignment(start, "THALAMUS_ROOM") == "alpha"
        assert panes_mod.harness_of(start) == "cursor"

    def test_a_nested_env_prefix_still_resolves_the_binary(self):
        """`pin` wraps a roomless launch in `env -u …` and the Cursor pin carrier adds
        its own `env NAME=VALUE` inside that, so the reader loops rather than stripping
        one prefix."""
        start = "env -u THALAMUS_ROOM -u CURSOR_CONFIG_DIR env THALAMUS_SCOPE=qe agent"
        assert panes_mod.harness_of(start) == "cursor"
        assert panes_mod._assignment(start, "THALAMUS_ROOM") == ""

    def test_a_dead_pane_is_not_a_member(self, monkeypatch):
        """
        Verification: a pane whose process is gone leaves its start command behind and
        must not stay in the room.

        The start command is written by the launcher, not the session, so it outlives
        the process. Counting it would grow a room's membership every time a member
        exited, and `--partial`'s undelivered list would fill with sessions that ended
        hours ago.
        """
        alive = panes_mod.Pane("%1", "qe", "alpha", "qe", "cursor", "/w", dead=False)
        dead = panes_mod.Pane("%2", "designer", "alpha", "designer", "cursor", "/w",
                              dead=True)
        monkeypatch.setattr(panes_mod, "panes", lambda target=None: [alive, dead])
        assert [pane.pane_id for pane in panes_mod.room_panes("alpha")] == ["%1"]


class TestDispatchAddressesACursorMember:
    def _pane(self, scope="qe"):
        return panes_mod.Pane("%100", scope, "alpha", scope, "cursor", "/w", dead=False)

    def test_a_member_holding_a_dialog_refuses_the_whole_fanout(self, tmp_path):
        """
        Scenario: the room's only member is sitting on an approval prompt

        Verification: nothing is sent, and the refusal names the target and the reason.

        This is the measured hazard, not a defensive guess: a message sent into a pane
        showing `Run this command?` was discarded, and the Enter selected `Run (once)`
        and ran the command. The sender learns nothing and approves
        something.
        """
        sent = []
        with pytest.raises(dispatch.DispatchRefused, match="approval dialog"):
            dispatch.dispatch(
                "alpha", "hello",
                config_dir=tmp_path, pins_file=tmp_path / "pins.jsonl",
                guards_dir=tmp_path / "guards",
                room_panes=[self._pane()],
                status_fn=lambda pane: panes_mod.WAITING,
                sender_fn=lambda *a: sent.append(a) or "",
            )
        assert sent == []

    def test_a_ready_member_is_delivered_to_and_the_row_names_its_harness(self, tmp_path):
        """
        Verification: the send happens, and the row records which roster answered.

        The two rosters are not equally strong — a Claude Code target's status is the
        session's own report, a Cursor target's is a bracket our hooks wrote around the
        interval a modal can occupy — so a row that pooled them would let the weaker
        evidence be quoted with the stronger one's authority.
        """
        sent = []
        result = dispatch.dispatch(
            "alpha", "hello",
            config_dir=tmp_path, pins_file=tmp_path / "pins.jsonl",
            guards_dir=tmp_path / "guards",
            room_panes=[self._pane()],
            status_fn=lambda pane: panes_mod.DELIVERABLE,
            sender_fn=lambda pane, text, submit: sent.append((pane, text)) or "",
        )
        assert sent == [("%100", "hello")]
        assert result.performed == 1
        target = result.deliveries[0].target
        assert target.harness == "cursor"
        assert target.name == "alpha-qe"
        assert target.pane == "%100"

    def test_an_unreadable_screen_is_refused_like_an_unmeasured_status(self, tmp_path):
        """The rule Claude Code applies to a status outside its measured set, applied
        to a member whose readiness is unestablished: refuse rather than assume it is
        safe to type into."""
        with pytest.raises(dispatch.DispatchRefused, match="no readiness"):
            dispatch.dispatch(
                "alpha", "hello",
                config_dir=tmp_path, pins_file=tmp_path / "pins.jsonl",
                guards_dir=tmp_path / "guards",
                room_panes=[self._pane()],
                status_fn=lambda pane: panes_mod.UNREADABLE,
                sender_fn=lambda *a: "",
            )

    def test_scopes_restrict_a_cursor_fanout(self, tmp_path):
        sent = []
        dispatch.dispatch(
            "alpha", "hello", scopes=["qe"],
            config_dir=tmp_path, pins_file=tmp_path / "pins.jsonl",
            guards_dir=tmp_path / "guards",
            room_panes=[self._pane("qe"), self._pane("designer")],
            status_fn=lambda pane: panes_mod.DELIVERABLE,
            sender_fn=lambda pane, text, submit: sent.append(text) or "",
        )
        assert len(sent) == 1
