"""The distillation widget's classifier.

What is being pinned down is the join and the state machine, not the rendering:
which `session-end-*.log` files count as a session at all (the subagent filter),
what each log body means, and the two ways a row stops being shown.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from thalamus.console.distill import STALL_AFTER_S, STATE_V, DistillWatch

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
    watch = DistillWatch(logs=logs, pins=pins, state=state)

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

    box = type("Box", (), {})()
    box.watch, box.pin, box.log, box.logs = watch, pin, log, logs
    return box


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


def test_a_distillation_that_went_quiet_is_an_error_not_a_forever_spinner(box):
    """The detached job can die without ever writing a summary. Nothing else
    notices, so an unfinished log that stops being written to is the signal."""
    box.pin("eeeeeeee")
    box.log("eeeeeeee", RUNNING, age_s=STALL_AFTER_S + 60)
    (row,) = box.watch.rows()
    assert row["state"] == "error"
    assert "stalled" in row["detail"]


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

    fresh = DistillWatch(logs=box.logs, pins=tmp_path / "pins.jsonl",
                         state=tmp_path / "dismissed.json")
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

    watch = DistillWatch(logs=logs, pins=pins, state=tmp_path / "dismissed.json")
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
