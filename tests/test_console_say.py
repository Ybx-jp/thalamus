"""Tap-to-listen: what gets selected to speak, and what happens when it can't.

The selection rule is the interesting half. "Read me the update" means the
assistant's latest turn — not the whole session, not the working that produced
it, and not a subagent narrating inside it. Getting that wrong is not a
cosmetic bug: a listener who asked for the last reply and got the last hour has
no way to skip, because audio has no scrollbar.
"""

from __future__ import annotations

import json

from thalamus.console import server, transcript as tr


def write_jsonl(path, records):
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def assistant(*blocks, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"content": list(blocks)}}


def user(text, sidechain=False):
    return {"type": "user", "isSidechain": sidechain, "message": {"content": text}}


def feed_for(tmp_path, records):
    path = tmp_path / "s.jsonl"
    write_jsonl(path, records)
    feed = tr.Feed(session_id="s", path=path, cwd="/repo")
    feed.refresh()
    return feed


# ---- selecting what to speak ----

class TestLatestTurnSelection:
    def test_takes_only_the_turn_after_the_last_user_message(self, tmp_path):
        feed = feed_for(tmp_path, [
            user("first ask"),
            assistant({"type": "text", "text": "An older reply."}),
            user("second ask"),
            assistant({"type": "text", "text": "The newest reply."}),
        ])
        assert feed.latest_turn_prose() == "The newest reply."

    def test_joins_several_prose_blocks_of_one_turn_in_order(self, tmp_path):
        feed = feed_for(tmp_path, [
            user("go"),
            assistant({"type": "text", "text": "First half."}),
            assistant({"type": "text", "text": "Second half."}),
        ])
        assert feed.latest_turn_prose() == "First half.\n\nSecond half."

    def test_leaves_out_tool_calls_and_their_results(self, tmp_path):
        feed = feed_for(tmp_path, [
            user("go"),
            assistant({"type": "text", "text": "Running it."},
                      {"type": "tool_use", "id": "t1", "name": "Bash",
                       "input": {"command": "pytest -q"}}),
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "940 passed"}]}},
        ])
        spoken = feed.latest_turn_prose()
        assert spoken == "Running it."
        assert "pytest" not in spoken
        assert "940 passed" not in spoken

    def test_leaves_out_a_subagents_narration(self, tmp_path):
        # A spawned agent's prose is in the same transcript but is not this
        # session talking, and the operator asked for one voice at a time.
        feed = feed_for(tmp_path, [
            user("go"),
            assistant({"type": "text", "text": "Delegating."}),
            assistant({"type": "text", "text": "I am the subagent."}, sidechain=True),
        ])
        assert feed.latest_turn_prose() == "Delegating."

    def test_a_tool_result_does_not_end_the_turn(self, tmp_path):
        # Tool results arrive as `user` records. Treating one as a turn boundary
        # would clip every reply at its first tool call.
        feed = feed_for(tmp_path, [
            user("go"),
            assistant({"type": "text", "text": "Before the call."},
                      {"type": "tool_use", "id": "t1", "name": "Bash",
                       "input": {"command": "ls"}}),
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}},
            assistant({"type": "text", "text": "After the call."}),
        ])
        assert feed.latest_turn_prose() == "Before the call.\n\nAfter the call."

    def test_a_session_with_nothing_said_yet_is_empty(self, tmp_path):
        feed = feed_for(tmp_path, [user("go")])
        assert feed.latest_turn_prose() == ""


class TestResumeCursor:
    """Where the second tap starts."""

    def test_a_first_listen_falls_back_to_the_latest_turn(self, tmp_path):
        # Not the whole session: a first tap on an hour-old window should not
        # start an hour ago, which is the complaint that produced this.
        feed = feed_for(tmp_path, [
            user("old ask"),
            assistant({"type": "text", "text": "Ancient history."}),
            user("new ask"),
            assistant({"type": "text", "text": "The current reply."}),
        ])
        text, _ = feed.prose_since(0)
        assert text == "The current reply."

    def test_resuming_skips_what_was_already_heard(self, tmp_path):
        feed = feed_for(tmp_path, [
            user("go"),
            assistant({"type": "text", "text": "First block."}),
            assistant({"type": "text", "text": "Second block."}),
        ])
        first = next(i for i in feed.items if i["kind"] == "prose")
        text, high = feed.prose_since(first["seq"])
        assert text == "Second block."
        assert high > first["seq"]

    def test_caught_up_yields_nothing(self, tmp_path):
        feed = feed_for(tmp_path, [
            user("go"),
            assistant({"type": "text", "text": "All of it."}),
        ])
        text, _ = feed.prose_since(feed.seq)
        assert text == ""

    def test_new_prose_after_catching_up_is_picked_up(self, tmp_path):
        path = tmp_path / "s.jsonl"
        write_jsonl(path, [user("go"), assistant({"type": "text", "text": "One."})])
        feed = tr.Feed(session_id="s", path=path, cwd="/repo")
        feed.refresh()
        _, high = feed.prose_since(0)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(assistant({"type": "text", "text": "Two."})) + "\n")
        feed.refresh()
        text, _ = feed.prose_since(high)
        assert text == "Two."

    def test_resume_still_excludes_subagent_narration(self, tmp_path):
        feed = feed_for(tmp_path, [
            user("go"),
            assistant({"type": "text", "text": "Mine."}),
            assistant({"type": "text", "text": "Not mine."}, sidechain=True),
        ])
        first = next(i for i in feed.items if i["kind"] == "prose")
        text, _ = feed.prose_since(first["seq"] - 1)
        assert "Not mine." not in text


class TestCursorCommit:
    """Generating audio is not hearing it."""

    def setup_method(self):
        server.SPOKEN_THROUGH.clear()
        server.SAY_PENDING.clear()

    def test_a_pending_utterance_does_not_move_the_cursor(self):
        server.say_pending("s", 40)
        assert server.say_cursor("s") == 0

    def test_acking_moves_it(self):
        server.say_pending("s", 40)
        assert server.say_commit("s") == 40
        assert server.say_cursor("s") == 40

    def test_stopping_early_replays_the_same_material(self):
        # No ack, so the next tap asks from the same place — which is the point.
        server.say_pending("s", 40)
        server.SAY_PENDING.pop("s")
        assert server.say_cursor("s") == 0

    def test_the_cursor_never_goes_backwards_on_a_late_ack(self):
        server.say_mark("s", 90)
        server.say_pending("s", 40)
        assert server.say_commit("s") == 90

    def test_marking_a_block_treats_everything_above_as_heard(self):
        server.say_mark("s", 25)
        assert server.say_cursor("s") == 25

    def test_marking_discards_an_utterance_in_flight(self):
        server.say_pending("s", 99)
        server.say_mark("s", 10)
        assert server.say_commit("s") == 10

    def test_cursors_are_per_session(self):
        server.say_mark("a", 10)
        server.say_mark("b", 20)
        assert (server.say_cursor("a"), server.say_cursor("b")) == (10, 20)


# ---- the contract, at the point audio would be produced ----

class TestSynthesisGate:
    def test_a_lost_protected_token_speaks_a_notice_instead(self, monkeypatch):
        """The failure mode this feature is built around.

        A summary that dropped a number must not be spoken. Substituting a
        notice is the only safe outcome: silence is ambiguous on a device the
        listener is not looking at, and the corrupted sentence is undetectable.
        """
        spoken = {}

        class Broken:
            @staticmethod
            def spoken_update(_raw):
                from thalamus.console.speech import ProtectedToken, SpokenUpdate
                lost = ProtectedToken("number", "17", ("17",))
                return SpokenUpdate(text="There are some citations.",
                                    protected=(lost,), missing=(lost,))

        monkeypatch.setattr(server, "speech_module", lambda: Broken)
        monkeypatch.setattr(server, "_post_to_voice", lambda text, timeout: (
            spoken.update(text=text) or (b"RIFF", None)))

        audio, err = server.synthesise_update("There are 17 citations.")
        assert err is None
        assert audio == b"RIFF"
        assert spoken["text"] == server.WITHHELD_NOTICE
        assert "17" not in spoken["text"]

    def test_a_faithful_update_is_spoken_as_transformed(self, monkeypatch):
        spoken = {}
        monkeypatch.setattr(server, "_post_to_voice", lambda text, timeout: (
            spoken.update(text=text) or (b"RIFF", None)))

        audio, err = server.synthesise_update(
            "Fixed `src/thalamus/console/server.py` — 17 citations, commit e08a09a.")
        assert err is None and audio == b"RIFF"
        assert "console server" in spoken["text"]
        assert "17" in spoken["text"]
        assert "slash" not in spoken["text"]

    def test_no_speech_module_is_reported_not_raised(self, monkeypatch):
        monkeypatch.setattr(server, "speech_module", lambda: None)
        audio, err = server.synthesise_update("anything")
        assert audio is None
        assert "unavailable" in err

    def test_an_unreachable_voice_service_is_an_error_not_a_crash(self, monkeypatch):
        monkeypatch.setattr(server, "VOICE_URL", "http://127.0.0.1:9")
        audio, err = server.synthesise_update("Say something.", timeout=1.0)
        assert audio is None
        assert err
