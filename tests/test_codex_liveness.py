"""
Codex live status — the liveness half of a console row for the harness that
publishes no session descriptor.

Interfaces: `harness/codex_transcripts.live_status` / `rollout_path`, and
`console/server._attach_codex_activity`.
Infrastructure: synthetic rollouts in tmp_path, shaped per codex's measured record
grammar (codex-cli 0.148.0, 2026-08-22 — seven rollouts on the operator's box, TUI
and `exec`, read for their turn-boundary rows). No live codex, no tmux, no graph.
Scope: what the record supports and what it does not. Claude Code answers "what is
this session doing" from a descriptor its runtime writes; codex writes none, and its
hook table has no turn-*end* event to synthesize one from. The turn boundaries in its
rollout are the substitute, and the load-bearing property under test is the one that
makes the substitute safe: a session that cannot be read renders as unread, never as
rest.
"""

import json
from datetime import datetime, timezone

import pytest

from thalamus.harness import codex_transcripts as ct
from thalamus.console import server


def meta(originator="codex-tui", source="cli"):
    return {"type": "session_meta",
            "payload": {"originator": originator, "source": source,
                        "cli_version": "0.148.0"}}


def event(kind, ts="2026-08-21T22:56:54.393Z"):
    return {"type": "event_msg", "timestamp": ts, "payload": {"type": kind}}


def rollout(path, *records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


class TestLiveStatus:
    def test_a_finished_turn_reads_idle(self, tmp_path):
        path = rollout(tmp_path / "r.jsonl", meta(),
                       event("task_started", "2026-08-21T22:56:00.000Z"),
                       event("task_complete", "2026-08-21T22:56:54.393Z"))
        status, since = ct.live_status(path)
        assert status == ct.CODEX_IDLE
        assert since.isoformat() == "2026-08-21T22:56:54.393000+00:00"

    def test_a_turn_in_flight_reads_busy(self, tmp_path):
        path = rollout(tmp_path / "r.jsonl", meta(),
                       event("task_started", "2026-08-21T22:56:00.000Z"))
        status, since = ct.live_status(path)
        assert status == ct.CODEX_BUSY
        assert since.isoformat() == "2026-08-21T22:56:00+00:00"

    def test_the_last_boundary_wins_across_many_turns(self, tmp_path):
        """Three turns, the third still running. A reader taking the first boundary,
        or counting them, would call this idle."""
        path = rollout(tmp_path / "r.jsonl", meta(),
                       event("task_started"), event("task_complete"),
                       event("task_started"), event("task_complete"),
                       event("task_started", "2026-08-21T23:10:00.000Z"))
        assert ct.live_status(path)[0] == ct.CODEX_BUSY

    def test_a_rollout_with_no_boundary_is_unknown_not_idle(self, tmp_path):
        """The load-bearing refusal. A session whose turn boundaries are not in reach
        is one we could not read, and rendering that as `idle` would state rest on
        exactly the evidence that says nothing — the inversion the readiness design
        exists to refuse."""
        path = rollout(tmp_path / "r.jsonl", meta(), {"type": "response_item"})
        assert ct.live_status(path) == (ct.CODEX_UNKNOWN, None)

    def test_a_missing_rollout_is_unknown(self, tmp_path):
        assert ct.live_status(tmp_path / "nope.jsonl") == (ct.CODEX_UNKNOWN, None)

    def test_a_boundary_past_the_tail_window_is_unknown(self, tmp_path):
        """Bounding the read is a real limit and it degrades to `unknown`, not to a
        guess. A turn longer than the window is indistinguishable from no record."""
        path = rollout(tmp_path / "r.jsonl", meta(), event("task_started"),
                       *[{"type": "response_item", "payload": {"pad": "x" * 400}}
                         for _ in range(200)])
        assert ct.live_status(path, tail_bytes=2048)[0] == ct.CODEX_UNKNOWN
        assert ct.live_status(path)[0] == ct.CODEX_BUSY

    def test_a_tool_heavy_turn_stays_in_reach_by_default(self, tmp_path):
        """The console's old 256 KiB tail lost `task_started` mid-turn, so active
        Codex sessions usually rendered as "not in reach" while doing real work."""
        path = rollout(tmp_path / "r.jsonl", meta(), event("task_started"),
                       {"type": "response_item", "payload": {"pad": "z" * (2 * 1024 * 1024)}})
        assert ct.live_status(path)[0] == ct.CODEX_BUSY

    def test_the_partial_first_line_of_a_tail_read_is_not_parsed(self, tmp_path):
        """Seeking into the middle of the file lands mid-record. That fragment is
        dropped rather than parsed, so a half-written row cannot decode as a
        boundary."""
        path = rollout(tmp_path / "r.jsonl", meta(),
                       event("task_complete", "2026-08-21T22:00:00.000Z"),
                       *[{"type": "response_item", "payload": {"pad": "y" * 200}}
                         for _ in range(40)],
                       event("task_started", "2026-08-21T23:00:00.000Z"))
        assert ct.live_status(path, tail_bytes=1024)[0] == ct.CODEX_BUSY

    def test_the_word_task_complete_in_message_text_is_not_a_boundary(self, tmp_path):
        """The substring scan is a filter over the tail, never the decision — a
        session discussing `task_complete` must not read as having finished one."""
        path = rollout(tmp_path / "r.jsonl", meta(),
                       event("task_started", "2026-08-21T22:00:00.000Z"),
                       {"type": "response_item", "timestamp": "2026-08-21T22:30:00.000Z",
                        "payload": {"type": "message",
                                    "text": "the rollout writes task_complete at the end"}})
        assert ct.live_status(path)[0] == ct.CODEX_BUSY

    def test_the_vocabulary_is_dispatchs_and_not_a_second_one(self):
        """Spelled in `codex_transcripts` rather than imported, because `dispatch`
        pulls in half the harness and this module is on the extraction path. This is
        what keeps the duplication from drifting."""
        dispatch = pytest.importorskip("thalamus.harness.dispatch")
        assert (ct.CODEX_IDLE, ct.CODEX_BUSY) == (dispatch.IDLE_STATUS,
                                                  dispatch.BUSY_STATUS)
        assert ct.CODEX_UNKNOWN not in dispatch.DELIVERABLE_STATUSES


class TestRolloutPath:
    def test_a_session_is_found_by_id_under_the_date_layout(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODEX_HOME", str(tmp_path))
        day = tmp_path / "sessions" / "2026" / "08" / "21"
        day.mkdir(parents=True)
        sid = "01a02689-38cf-7a62-8efd-cb1786b223cc"
        rollout(day / f"rollout-2026-08-21T15-55-22-{sid}.jsonl", meta())
        assert ct.rollout_path(sid).name.endswith(f"{sid}.jsonl")

    def test_an_unknown_id_resolves_to_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODEX_HOME", str(tmp_path))
        (tmp_path / "sessions").mkdir()
        assert ct.rollout_path("no-such-session") is None
        assert ct.rollout_path("") is None


class TestTheConsoleRow:
    """`_attach_codex_activity` fills only what the rollout supports."""

    def setup_method(self):
        server._CODEX_ROLLOUTS.clear()

    def window(self, **over):
        w = {"harness": "codex", "session_id": "s1", "observed": False,
             "blocked": None, "blocked_since": None, "activity": "",
             "activity_since": None}
        w.update(over)
        return w

    def test_a_busy_codex_row_is_observed_and_carries_a_clock(self, tmp_path, monkeypatch):
        path = rollout(tmp_path / "r.jsonl", meta(),
                       event("task_started", "2026-08-21T22:56:00.000Z"))
        monkeypatch.setattr(ct, "rollout_path", lambda sid, home=None: path)
        rows = [self.window()]

        server._attach_codex_activity(rows)

        assert rows[0]["observed"] is True
        assert rows[0]["activity"] == "busy"
        # Epoch seconds on the wire, milliseconds nowhere — the same idiom `started`
        # and the lifecycle stamps already speak. Derived rather than spelled: a
        # hardcoded epoch tests the arithmetic of whoever wrote the test.
        expected = datetime(2026, 8, 21, 22, 56, tzinfo=timezone.utc).timestamp()
        assert rows[0]["activity_since"] == expected

    def test_an_idle_codex_row_carries_no_clock(self, tmp_path, monkeypatch):
        """Only `busy` is worth a clock — an elapsed on every idle row is motion on
        most rows at once, which costs the loud channel what it is worth."""
        path = rollout(tmp_path / "r.jsonl", meta(), event("task_complete"))
        monkeypatch.setattr(ct, "rollout_path", lambda sid, home=None: path)
        rows = [self.window()]

        server._attach_codex_activity(rows)

        assert (rows[0]["observed"], rows[0]["activity"]) == (True, "idle")
        assert rows[0]["activity_since"] is None

    def test_blocked_stays_none_on_an_observed_codex_row(self, tmp_path, monkeypatch):
        """The rollout says when a turn began and ended and nothing about an approval
        prompt inside one, so `blocked` here means *not known*. It must not be filled
        with False, which is the "not stuck" claim on no evidence."""
        path = rollout(tmp_path / "r.jsonl", meta(), event("task_complete"))
        monkeypatch.setattr(ct, "rollout_path", lambda sid, home=None: path)
        rows = [self.window()]

        server._attach_codex_activity(rows)

        assert rows[0]["blocked"] is None
        assert rows[0]["blocked_since"] is None

    def test_an_unreadable_row_stays_unobserved(self, tmp_path, monkeypatch):
        """Which is what draws `not in reach` — correct here, because it is true."""
        monkeypatch.setattr(ct, "rollout_path", lambda sid, home=None: None)
        rows = [self.window()]

        server._attach_codex_activity(rows)

        assert rows[0]["observed"] is False
        assert rows[0]["activity"] == ""

    def test_a_window_with_no_session_id_stays_unobserved(self, tmp_path, monkeypatch):
        """Codex's SessionStart fires at the first submitted turn, so a spawned window
        nobody has typed into has no ledger row and no id to join on."""
        monkeypatch.setattr(ct, "rollout_path",
                            lambda sid, home=None: pytest.fail("should not be asked"))
        rows = [self.window(session_id="")]

        server._attach_codex_activity(rows)

        assert rows[0]["observed"] is False

    def test_rows_of_other_harnesses_are_left_alone(self, tmp_path, monkeypatch):
        """Claude Code has a descriptor and `attach_blocked` reads it; a rollout read
        here would be a second answer to a question already owned elsewhere."""
        monkeypatch.setattr(ct, "rollout_path",
                            lambda sid, home=None: pytest.fail("should not be asked"))
        rows = [self.window(harness="claude"), self.window(harness="agent")]

        server._attach_codex_activity(rows)

        assert [r["observed"] for r in rows] == [False, False]
