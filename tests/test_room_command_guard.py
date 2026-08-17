"""The room boundary on the command channel — the peer channel a tool matcher misses.

Interfaces: `hooks/claude-code/room-command-guard.sh` and its Cursor adapter, driven
as each harness drives them — JSON on stdin, exit 2 / `{"permission": "deny"}` to
block. Also `dispatch.authenticate`, which is the boundary the guard backs up.

Why this exists beside `test_room_guard.py`: `room-guard.sh` matches `SendMessage`,
which was the whole peer channel while peer messaging was a tool. `tmux send-keys` is
a measured delivery path into any pane on the box and `thalamus dispatch`
addresses a room by name from a shell — both Bash, neither visible to a tool-name
matcher, and on Cursor there is no `SendMessage` to match at all.
"""

import json
import subprocess
from pathlib import Path

import pytest

from thalamus.harness import dispatch

HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks"


def run_guard(command, home, room=None):
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin",
           "THALAMUS_SCOPE": "qe"}
    if room is not None:
        env["THALAMUS_ROOM"] = room
    payload = {"tool_name": "Bash", "tool_input": {"command": command},
               "session_id": "s1", "cwd": str(home)}
    return subprocess.run(
        [str(HOOKS / "claude-code" / "room-command-guard.sh")],
        input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=30,
    )


def run_cursor_guard(command, home, room=None):
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin",
           "THALAMUS_SCOPE": "qe"}
    if room is not None:
        env["THALAMUS_ROOM"] = room
    payload = {"command": command, "cwd": "", "workspace_roots": [str(home)],
               "conversation_id": "c1"}
    return subprocess.run(
        [str(HOOKS / "cursor" / "room-command-guard.sh")],
        input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=30,
    )


def rows(home):
    found = []
    for path in (home / ".thalamus" / "guards").glob("*.jsonl"):
        found += [json.loads(line) for line in path.read_text().splitlines() if line]
    return found


class TestOutsideARoom:
    def test_no_room_means_no_opinion(self, tmp_path):
        """Arming this changes nothing for every session that is not in a room."""
        assert run_guard("tmux send-keys -t %5 hi", tmp_path).returncode == 0

    def test_no_row_is_written_either(self, tmp_path):
        run_guard("thalamus dispatch beta 'hi'", tmp_path)
        assert rows(tmp_path) == []


class TestTheRawTransportIsClosed:
    def test_send_keys_is_blocked_from_inside_a_room(self, tmp_path):
        """
        Scenario: a member shells out to the transport dispatch itself delivers over

        Verification: blocked, and the refusal explains the difference rather than
        asserting one.

        This is the hole a tool-name matcher cannot see. `tmux send-keys` reaches any
        pane on the machine — a non-member's, another room's — with nothing in any
        ledger. It is not a different capability from dispatch; it is the same one
        with the pre-flight and the row removed, and the pre-flight is what refuses to
        type into a session holding an approval dialog.
        """
        r = run_guard("tmux send-keys -t %5 'hello'", tmp_path, room="alpha")
        assert r.returncode == 2
        assert "thalamus dispatch alpha" in r.stderr

    def test_the_block_is_recorded_as_a_room_boundary_event(self, tmp_path):
        run_guard("tmux send-keys -t %5 hi", tmp_path, room="alpha")
        row = rows(tmp_path)[0]
        assert row["guard"] == "room-boundary"
        assert (row["verdict"], row["branch"]) == ("block", "raw-transport")
        assert row["room"] == "alpha"

    @pytest.mark.parametrize(
        "command",
        ["/usr/bin/tmux send-keys -t %5 hi",
         '"$TMUX_BIN" send-keys -t %5 hi',
         "tmux paste-buffer -t %5"],
        ids=["absolute-path", "variable-binary", "paste-buffer"],
    )
    def test_the_verb_is_matched_not_the_binarys_spelling(self, command, tmp_path):
        """
        Verification: the block does not depend on `tmux` appearing literally.

        Unlike the addressing rules, this one has no second line behind it — a raw
        send never reaches `dispatch`, so nothing else can refuse it. A pattern keyed
        to one spelling of the binary would be a boundary that an absolute path walks
        through.
        """
        assert run_guard(command, tmp_path, room="alpha").returncode == 2

    def test_an_unrelated_tmux_command_is_untouched(self, tmp_path):
        """The guard names one verb, not the multiplexer. A member reading its own
        window list is not reaching anybody."""
        assert run_guard("tmux list-panes -a", tmp_path, room="alpha").returncode == 0


class TestAddressingARoomByName:
    def test_dispatching_to_your_own_room_passes(self, tmp_path):
        r = run_guard('thalamus dispatch alpha "hi"', tmp_path, room="alpha")
        assert r.returncode == 0
        assert rows(tmp_path)[0]["branch"] == "peer-command"

    def test_dispatching_to_another_room_is_blocked(self, tmp_path):
        r = run_guard('uv run thalamus dispatch beta "hi"', tmp_path, room="alpha")
        assert r.returncode == 2
        assert rows(tmp_path)[0]["branch"] == "outside-room"
        # Verifies: the block routes to the sanctioned cross-scope channel
        assert "consult_request" in r.stderr

    def test_a_flag_before_the_positional_does_not_defeat_it(self, tmp_path):
        """
        Verification: the own-room form still passes when a value-taking flag precedes
        the room.

        The matching rule is "does this command name my room", not "parse the
        positional" — `--to designer alpha` puts the room after a flag that consumes
        the next token, and a parser that got that wrong would refuse legitimate
        in-room traffic, which is the failure mode that teaches route-around.
        """
        r = run_guard('thalamus dispatch --to designer alpha "hi"', tmp_path,
                      room="alpha")
        assert r.returncode == 0

    def test_spawning_into_another_room_is_blocked(self, tmp_path):
        """A member placing a *new* session in a room it is not in reaches outside by
        creating rather than by messaging."""
        r = run_guard("thalamus spawn qe --room beta", tmp_path, room="alpha")
        assert r.returncode == 2

    def test_an_ordinary_command_is_untouched(self, tmp_path):
        assert run_guard("uv run pytest -q", tmp_path, room="alpha").returncode == 0


class TestTheCursorAdapter:
    """One boundary, two harness contracts — the shape `write-guard.sh` established."""

    def test_a_block_becomes_a_permission_deny_carrying_the_reason(self, tmp_path):
        r = run_cursor_guard("tmux send-keys -t %5 hi", tmp_path, room="alpha")
        assert r.returncode == 0, r.stderr
        verdict = json.loads(r.stdout)
        assert verdict["permission"] == "deny"
        # Both channels: the denial's tool result carries `user_message` and no
        # `agent_message` on this build, so a guard explaining itself only through the
        # documented agent channel blocks in silence.
        assert "thalamus dispatch" in verdict["agent_message"]
        assert verdict["user_message"] == verdict["agent_message"]

    def test_an_allowed_command_is_allowed(self, tmp_path):
        r = run_cursor_guard('thalamus dispatch alpha "hi"', tmp_path, room="alpha")
        assert json.loads(r.stdout)["permission"] == "allow"

    def test_outside_a_room_it_allows_without_an_opinion(self, tmp_path):
        r = run_cursor_guard("tmux send-keys -t %5 hi", tmp_path)
        assert json.loads(r.stdout)["permission"] == "allow"


class TestTheSenderIsEstablishedNotAsserted:
    """`dispatch.authenticate` — the boundary the guard above backs up.

    A guard over command strings can be evaded by a determined member (a variable, a
    here-doc). This check reads the calling process's own environment, which the
    caller cannot author, so it is the boundary and the guard is defence-in-depth.
    """

    def test_a_member_cannot_dispatch_into_another_room(self):
        with pytest.raises(dispatch.DispatchRefused, match="cannot dispatch into room"):
            dispatch.authenticate("beta", caller_room="alpha", caller_scope="qe")

    def test_the_operator_flag_is_the_named_exception(self):
        sender, authority = dispatch.authenticate(
            "beta", operator=True, caller_room="alpha", caller_scope="qe")
        assert (sender, authority) == ("qe", dispatch.SENDER_OPERATOR)

    def test_a_member_may_not_claim_another_scope(self):
        """
        Verification: inside a room, `--sender designer` from a `qe` session refuses.

        `eval/rooms.py` already declines a peer that parses but is not in the roster,
        on the grounds that the prefix alone is not membership. A sender nobody
        established is weaker provenance than the peer it already refuses, so
        admitting one would be inconsistent inside a single loop.
        """
        with pytest.raises(dispatch.DispatchRefused, match="pinned to `qe`"):
            dispatch.authenticate("alpha", "designer",
                                  caller_room="alpha", caller_scope="qe")

    def test_a_member_dispatching_to_its_own_room_is_authored_by_the_process(self):
        assert dispatch.authenticate("alpha", caller_room="alpha",
                                     caller_scope="qe") == ("qe", "process")

    def test_a_roomless_caller_is_the_operator(self):
        """The console server is long-lived and in no room; that is the broadcast
        path, and it stays open."""
        sender, authority = dispatch.authenticate(
            "alpha", "main", caller_room="", caller_scope="main")
        assert (sender, authority) == ("main", dispatch.SENDER_OPERATOR)


class TestPrecision:
    """The guard's false-positive rate is a security property, not an ergonomic one.

    Measured across three sessions on 2026-08-15: 8 false positives, 0 true ones. Every
    one was a path or a search pattern that happened to contain both `thalamus` and a
    verb, and every one was worked around within seconds with a glob or a here-doc. A
    member who has learned the rewrite has it ready for the case the guard exists to
    stop, so a guard that cries wolf is weaker than a quiet one, not safer.

    These are the eight, as issued.
    """

    @pytest.mark.parametrize("command", [
        # A path names both words and invokes nothing.
        "git add src/thalamus/console/static/app.js tests/js/roster.test.mjs",
        "sed -n '100,120p' src/thalamus/harness/dispatch.py",
        "grep -n 'caller_room' src/thalamus/harness/dispatch.py",
        "rg -n 'def dispatch\\(' -A 25 src/thalamus/harness/dispatch.py",
        "git diff -- src/thalamus/harness/dispatch.py",
        "git add src/thalamus/console/server.py docs/console.md",
        # Prose that mentions the tool and a verb, in a quoted argument.
        'gh pr create --body "thalamus console: roster sync stays idempotent"',
        # Asking what a verb does reaches no room — argparse exits before any argument.
        "thalamus dispatch --help",
        "uv run thalamus spawn -h",
    ])
    def test_naming_the_tool_is_not_invoking_it(self, command, tmp_path):
        assert run_guard(command, tmp_path, room="d4v2").returncode == 0, (
            f"false positive: {command!r} reaches no room")

    @pytest.mark.parametrize("command", [
        # The discriminator is what *follows* `thalamus`, so a path invocation is
        # still a real reach and must still be caught.
        '/home/op/.venv/bin/thalamus dispatch alpha "hello"',
        './.venv/bin/thalamus dispatch alpha "hello"',
        'uv run thalamus dispatch alpha "hello"',
        'THALAMUS_ROOM= thalamus dispatch alpha "hello"',
        "thalamus spawn qe --room alpha",
        # A flag taking a value must not let the room hide behind it.
        'thalamus dispatch --to qe alpha "hello"',
    ])
    def test_the_tightening_lets_no_real_reach_through(self, command, tmp_path):
        assert run_guard(command, tmp_path, room="d4v2").returncode == 2, (
            f"false negative: {command!r} addresses a room this session is not in")

    def test_a_help_flag_inside_a_message_buys_no_exemption(self, tmp_path):
        """The exemption is the shape of a help invocation, not the presence of a flag.

        `--help` inside a quoted positional is a word in a message: the shell passes it
        as part of one argv element and argparse never sees a flag, so a guard reading
        the raw string must not treat it as one.
        """
        result = run_guard('thalamus dispatch alpha "how do I use --help here"',
                           tmp_path, room="d4v2")
        assert result.returncode == 2
