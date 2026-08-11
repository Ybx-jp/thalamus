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
