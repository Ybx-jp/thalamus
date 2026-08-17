"""The distillation widget's classifier.

What is being pinned down is the join and the state machine, not the rendering:
which `session-end-*.log` files count as a session at all (the subagent filter),
what each log body means, and the two ways a row stops being shown.
"""

from __future__ import annotations

import json
import time

import pytest

from thalamus.console.distill import (
    ABANDON_AFTER_S, STALL_AFTER_S, STATE_V, DistillWatch, record_kill,
)

DONE = ("distilling session {sid} into scope {scope}\n"
        "1 sessions to extract (model: None)\n"
        "  + {sid}  18 claims  2 threads  0 refs  $0.33  Something happened\n"
        "\n1 extracted, 0 skipped, 0 failed; model cost $0.33\n")
FAILED = ("distilling session {sid} into scope {scope}\n"
          "  ✗ {sid}  extraction failed: 3 validation errors for SessionGraph\n"
          "0 extracted, 0 skipped, 1 failed; model cost $0.00\n")
RUNNING = "distilling session {sid} into scope {scope}\n"
NO_TX = ("distilling session {sid} into scope {scope}\n"
         "No session matching {sid}-a157-47ff-b8b2-f5ab under -home — nothing distilled.\n")


@pytest.fixture()
def box(tmp_path):
    """A watcher over throwaway logs/ledger/state, seeded as if freshly started."""
    logs = tmp_path / "logs"
    logs.mkdir()
    pins = tmp_path / "pins.jsonl"
    pins.write_text("")
    # A console that has already been up a while, so the clean-slate seed is behind
    # us and these logs read as new work. Seeding itself is tested separately.
    state = tmp_path / "dismissed.json"
    state.write_text(json.dumps({"v": STATE_V, "seeded_at": time.time() - 3600,
                                 "dismissed": {}}))
    kills = tmp_path / "killed.jsonl"
    watch = DistillWatch(logs=logs, pins=pins, state=state, kills=kills)

    def pin(sid, scope="homelab", cwd="/home/ybx/code/thalamus"):
        with pins.open("a") as fh:
            fh.write(json.dumps({"session_id": sid + "-rest", "scope": scope,
                                 "cwd": cwd, "tmux_pane": "%1", "ts": "now"}) + "\n")

    def log(sid, body, scope="homelab", age_s=0.0):
        path = logs / f"session-end-{sid}.log"
        path.write_text(body.format(sid=sid, scope=scope))
        if age_s:
            old = time.time() - age_s
            import os
            os.utime(path, (old, old))
        watch._scanned_at = 0.0        # the widget's 1s poll floor, not the test's
        return path

    def kill(sid, op="close", at=None, scope="homelab",
             cwd="/home/ybx/code/thalamus"):
        record_kill(sid, scope, cwd, op, at=at if at is not None else time.time(),
                    path=kills)
        watch._scanned_at = 0.0
        return kills

    box = type("Box", (), {})()
    box.watch, box.pin, box.log, box.logs = watch, pin, log, logs
    box.kill, box.kills = kill, kills
    return box


def test_a_killed_window_is_not_the_same_pixels_as_a_clean_distillation(box):
    """The gap this whole surface exists to close.

    A forced close kills the window before SessionEnd runs, so `thalamus extract`
    never starts and no log is ever created. The scan reads logs, and `done` rows
    are dropped on purpose — so a distillation that succeeded and one that never ran
    were both *nothing at all*. The row that succeeded is still silent; the one that
    never happened now has a state.
    """
    box.pin("cccccccc")
    box.log("cccccccc", DONE)
    assert box.watch.rows() == []          # success is still, deliberately, silent

    box.kill("dddddddd")

    (row,) = box.watch.rows()
    assert row["state"] == "unknown"
    assert row["session"] == "dddddddd"
    assert row["op"] == "close"


def test_a_record_names_itself_because_it_outlives_its_window(box):
    """The common case, not the awkward one.

    A record is read after the session that produced it has exited, so the roster
    usually holds no row to borrow identity from — measured live, every record on
    the box belonged to a departed window. A record that can say a distillation
    failed but not whose is a new absence in the surface built to remove absences,
    so it carries the same grouping fields the row does, from the same pin.
    """
    box.pin("aaaa7777", scope="literature", cwd="/home/ybx/code/thalamus/lab")
    box.log("aaaa7777", FAILED)

    (row,) = box.watch.rows()
    assert row["scope"] == "literature"
    assert row["session"] == "aaaa7777"
    assert "project" in row and "repo_root" in row


def test_a_killed_window_record_carries_its_own_grouping_keys(box):
    """The kill row is written *as* the window is destroyed, so it cannot look
    anything up later — whatever it fails to record is unrecoverable."""
    box.kill("aaaa8888", op="recycle", scope="qe")
    box.watch._scanned_at = 0.0
    from thalamus.console.distill import record_kill
    record_kill("aaaa9999", "designer", "/home/ybx/code/thalamus", "close",
                project="thalamus", repo_root="/home/ybx/code/thalamus",
                path=box.kills)
    box.watch._scanned_at = 0.0

    rows = {r["session"]: r for r in box.watch.rows()}
    assert rows["aaaa9999"]["project"] == "thalamus"
    assert rows["aaaa9999"]["repo_root"] == "/home/ybx/code/thalamus"
    assert rows["aaaa9999"]["scope"] == "designer"
    assert rows["aaaa8888"]["op"] == "recycle"


def test_a_killed_window_that_distilled_anyway_defers_to_its_log(box):
    """The kill row is an expectation; a log is evidence, and evidence wins.

    The graceful exit and the kill race each other, and the kill can lose — the
    session gets its SessionEnd in before the window dies. Reporting `unknown` then
    would be the console asserting a failure that did not happen.
    """
    box.pin("eeee1111")
    box.kill("eeee1111")
    box.log("eeee1111", FAILED)

    (row,) = box.watch.rows()
    assert row["state"] == "error"
    assert "validation errors" in row["detail"]


def test_dismissing_a_killed_window_does_not_suppress_the_next_kill(box):
    """Dismissal means "I saw this failure", never "stop telling me about these".

    Permanent suppression from one acknowledgement would rebuild the silence this
    row exists to break — the same failure one level up.
    """
    box.pin("ffff2222")
    box.kill("ffff2222", at=time.time() - 60)
    assert len(box.watch.rows()) == 1

    assert box.watch.dismiss("ffff2222") is True
    box.watch._scanned_at = 0.0
    assert box.watch.rows() == []

    box.kill("ffff2222", at=time.time())          # a second, later kill

    (row,) = box.watch.rows()
    assert row["state"] == "unknown"


def test_a_long_failure_detail_is_cut_and_says_so(box):
    """A silently truncated string is an absence the reader cannot detect.

    The detail reaches the operator verbatim, so the only honest way to bound it is
    to cut it and state that it was cut.
    """
    box.pin("aaaa3333")
    long_reason = "x" * 400
    box.log("aaaa3333", "distilling session {sid} into scope {scope}\n"
            f"  ✗ {{sid}}  extraction failed: {long_reason}\n"
            "0 extracted, 0 skipped, 1 failed\n")

    (row,) = box.watch.rows()
    assert row["detail_truncated"] is True
    assert len(row["detail"]) == 200


def test_an_ordinary_detail_is_not_marked_truncated(box):
    box.pin("bbbb4444")
    box.log("bbbb4444", FAILED)

    (row,) = box.watch.rows()
    assert row["detail_truncated"] is False
    assert row["detail"].endswith("SessionGraph")


def test_a_session_with_nothing_to_distill_finished_and_is_not_a_stall(box):
    """A clean ending that prints no summary line.

    `thalamus extract` exits 0 without a summary when a session had no substantive
    exchange — named, found, deliberately not distilled. The only completion signal
    the classifier otherwise knows is the summary line, so this log ages past the
    stall clock and reports a job that finished as a process that died mid-flight.

    Measured on the live box: two of the three rows the stall clock had marked were
    this. A channel meant to carry lost work must not spend its salience on work
    that was never at risk.
    """
    box.pin("bbbb5555")
    box.log("bbbb5555",
            "distilling session {sid} into scope {scope}\n"
            "{sid}: no substantive exchange (slash commands only, no tool use) "
            "— nothing to distill.\n",
            age_s=STALL_AFTER_S + 600)

    assert box.watch.rows() == []


def test_a_failure_still_wins_over_a_nothing_to_distill_line(box):
    """One session's clean skip must not launder another's failure.

    `extract` takes several sessions at once and writes one log, so the skip line
    and a `✗` line can share it. The failure is the load-bearing half.
    """
    box.pin("bbbb6666")
    box.log("bbbb6666",
            "distilling session {sid} into scope {scope}\n"
            "other111: no substantive exchange — nothing to distill.\n"
            "  ✗ {sid}  extraction failed: 3 validation errors for SessionGraph\n",
            age_s=STALL_AFTER_S + 600)

    (row,) = box.watch.rows()
    assert row["state"] == "error"
    assert "validation errors" in row["detail"]


def test_nothing_distilling_is_a_blank_list(box):
    assert box.watch.rows() == []


def test_a_session_with_no_summary_line_yet_is_distilling(box):
    box.pin("aaaaaaaa")
    box.log("aaaaaaaa", RUNNING)
    (row,) = box.watch.rows()
    assert row["state"] == "active"
    assert row["session"] == "aaaaaaaa"
    assert row["scope"] == "homelab"
    assert row["dir"] == "thalamus"


def test_a_clean_finish_drops_off_the_list(box):
    box.pin("bbbbbbbb")
    box.log("bbbbbbbb", DONE)
    assert box.watch.rows() == []


def test_a_failed_extraction_is_an_error_row_carrying_its_reason(box):
    box.pin("cccccccc")
    box.log("cccccccc", FAILED)
    (row,) = box.watch.rows()
    assert row["state"] == "error"
    assert "validation errors" in row["detail"]


def test_a_session_whose_transcript_was_never_found_is_an_error(box):
    box.pin("dddddddd")
    box.log("dddddddd", NO_TX)
    (row,) = box.watch.rows()
    assert row["state"] == "error"
    assert "no transcript" in row["detail"]


def test_a_distillation_that_went_quiet_is_stalled_not_a_forever_spinner(box):
    """The detached job can die without ever writing a summary. Nothing else
    notices, so an unfinished log that stops being written to is the signal.

    `stalled` and not `error`, because the operator's next move differs: an error is
    terminal and the answer is to rerun, while a stall is a process still nominally
    running that may yet finish. Drawing a live process in a terminal word is the
    same defect the killed-window row exists to fix, one state along.
    """
    box.pin("eeeeeeee")
    box.log("eeeeeeee", RUNNING, age_s=STALL_AFTER_S + 60)
    (row,) = box.watch.rows()
    assert row["state"] == "stalled"
    assert "stalled" in row["detail"]


def test_a_stall_that_never_moves_again_stops_being_called_a_stall(box):
    """`stalled` earns steady geometry on the row by promising it may yet finish.

    That promise is true at half an hour and false at six days. Measured on this box:
    a literature distillation had been `stalled` since 2026-08-09 and would have sat
    in a calm state word forever, reporting work in progress that will never move —
    the meaningless silence this module exists to remove, one state along.

    The threshold is a multiple of the stall clock rather than its own literal, so it
    cannot drift away from the constant it is defined against.
    """
    # An abandoned log is by definition older than the fixture's clean-slate seed,
    # which exists to stop a fresh console showing a backlog. The seed moves back so
    # the row can exist at all; moving the threshold instead would test a different
    # constant than the one that ships.
    box.watch.state_path.write_text(json.dumps(
        {"v": STATE_V, "seeded_at": time.time() - 10 * ABANDON_AFTER_S,
         "dismissed": {}}))
    box.watch._state = None

    box.pin("dddddddd")
    box.log("dddddddd", RUNNING, age_s=ABANDON_AFTER_S + 60)
    (row,) = box.watch.rows()
    assert row["state"] == "abandoned"

    # Still a stall right up to the line: the promotion must not eat the state it is
    # promoting from, or a job that dies at 21 minutes is drawn as one gone for days.
    box.watch.dismiss("dddddddd")
    box.pin("dddddddc")
    box.log("dddddddc", RUNNING, age_s=ABANDON_AFTER_S - 60)
    assert [r["state"] for r in box.watch.rows() if r["session"] == "dddddddc"] == ["stalled"]


def test_a_subagents_log_is_not_a_session(box):
    """Subagents fire SessionEnd and always fail with 'No session matching' — they
    have no transcript of their own — but they never write a pin-ledger row. That
    absence is the whole filter; without it the widget is ~2/3 noise."""
    box.log("ffffffff", NO_TX)          # note: no box.pin(...)
    assert box.watch.rows() == []


def test_dismissing_an_error_clears_it_and_the_dismissal_survives_a_restart(box, tmp_path):
    box.pin("11111111")
    box.log("11111111", FAILED)
    assert len(box.watch.rows()) == 1

    assert box.watch.dismiss("11111111") is True
    assert box.watch.rows() == []

    # `kills` too, not just the other three: left to its default it reads the real
    # killed-window ledger under ~/.thalamus on whatever box runs the suite, and one
    # genuine forced-kill record there fails this assertion with a row the test never
    # wrote.
    fresh = DistillWatch(logs=box.logs, pins=tmp_path / "pins.jsonl",
                         state=tmp_path / "dismissed.json", kills=box.kills)
    assert fresh.rows() == []


def test_a_dismissed_session_that_fails_again_comes_back(box):
    """Dismissal counts the runs in the log, so distilling the session a second
    time re-raises it rather than being swallowed by the earlier dismissal."""
    box.pin("22222222")
    path = box.log("22222222", FAILED)
    box.watch.dismiss("22222222")
    assert box.watch.rows() == []

    with path.open("a") as fh:                       # the session distills again
        fh.write(FAILED.format(sid="22222222", scope="homelab"))
    box.watch._scanned_at = 0.0
    assert len(box.watch.rows()) == 1


def test_a_dismissal_is_not_undone_by_the_eval_sync_that_trails_extract(box):
    """The hook runs `thalamus eval sync` into the same log a few seconds after
    extract's summary. Keyed on mtime, a dismissal made in that window would pop
    straight back; keyed on runs, those trailing lines are correctly ignored."""
    box.pin("66666666")
    path = box.log("66666666", FAILED)
    box.watch.dismiss("66666666")

    with path.open("a") as fh:
        fh.write("1107 traces landed (248 recall misses)\n"
                 "34 legacy traces skipped (pre-node-level rendering)\n")
    box.watch._scanned_at = 0.0
    assert box.watch.rows() == []


def test_the_backlog_on_disk_at_first_run_is_a_clean_slate(tmp_path):
    """Seeding stamps the moment the widget first ran; everything already on disk
    falls behind it. Otherwise the first open shows months of archaeology."""
    logs = tmp_path / "logs"
    logs.mkdir()
    pins = tmp_path / "pins.jsonl"
    with pins.open("w") as fh:
        for n in range(3):
            fh.write(json.dumps({"session_id": f"old{n}0000-rest", "scope": "main",
                                 "cwd": "/home/ybx/code/thalamus"}) + "\n")
    for n in range(3):
        (logs / f"session-end-old{n}0000.log").write_text(
            FAILED.format(sid=f"old{n}0000", scope="main"))

    watch = DistillWatch(logs=logs, pins=pins, state=tmp_path / "dismissed.json",
                         kills=tmp_path / "killed.jsonl")
    assert watch.rows() == []

    # ...but a distillation that happens after the seed is not swallowed by it.
    (logs / "session-end-new00000.log").write_text(
        FAILED.format(sid="new00000", scope="main"))
    with pins.open("a") as fh:
        fh.write(json.dumps({"session_id": "new00000-rest", "scope": "main",
                             "cwd": "/home/ybx/code/thalamus"}) + "\n")
    watch._scanned_at = 0.0
    assert [r["session"] for r in watch.rows()] == ["new00000"]


def test_distilling_sorts_above_errors(box):
    box.pin("33333333")
    box.pin("44444444")
    box.log("33333333", FAILED)
    box.log("44444444", RUNNING)
    assert [r["state"] for r in box.watch.rows()] == ["active", "error"]


def test_an_engaged_ledger_row_is_not_a_session_start(box):
    """pins.jsonl carries two shapes; only the start record has the fields a row
    needs, and an 'engaged' row alone must not resurrect a subagent's log."""
    with (box.watch.pins).open("a") as fh:
        fh.write(json.dumps({"event": "engaged", "session_id": "55555555-rest",
                             "scope": "homelab", "ts": "now"}) + "\n")
    box.log("55555555", NO_TX)
    assert box.watch.rows() == []
