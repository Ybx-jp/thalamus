"""A distillation log written just after the seed must not be hidden by it.

Issue #187: `DistillWatch` (`console/distill.py`) stamps `seeded_at = time.time()` the
first time it loads state, then drops any log with `st_mtime <= seeded_at` unless it
classifies `active`. A file's mtime comes from the kernel's coarse timestamp clock,
which lags `CLOCK_REALTIME` by up to one timer tick (0.9-1.7 ms measured in the issue),
so a SessionEnd log written *after* the seed can carry an mtime *before* it. The row is
then dropped on every scan, not just the first.

The dev test for the property (`test_console_distill.py::test_the_backlog_on_disk_at_
first_run_is_a_clean_slate`) is timing-dependent: it passes or fails on the gap between
the seed and its next write. This case removes the timing. It drives the real
`DistillWatch.rows()`, reads the `seeded_at` the watcher actually persisted, and writes
the log with `os.utime` set to `seeded_at - 1.5 ms`, the kernel-plausible value for a
file created right after the seed. The comparison in `rows()` is neither mocked nor
patched.

Controls: (1) the seed must be a real positive number and the pre-seed backlog must be
hidden (the seeding works at all); (2) the same log with an mtime clearly after the seed
(+2 s) must surface, so a miss is attributable to the mtime and not to the fixture (pin
ledger, log name, failure text).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_FAILED = ("distilling session {sid} into scope main\n"
           "  ✗ {sid}  extraction failed: 3 validation errors for SessionGraph\n"
           "0 extracted, 0 skipped, 1 failed; model cost $0.00\n")

_SKEW_S = 0.0015


def _sessions(watch) -> list[str]:
    watch._scanned_at = 0.0          # step past SCAN_TTL_S; the comparison is untouched
    return [r["session"] for r in watch.rows()]


def _fixture(tmp: Path):
    from thalamus.console.distill import DistillWatch

    logs = tmp / "logs"
    logs.mkdir()
    pins = tmp / "pins.jsonl"
    pins.write_text("".join(
        json.dumps({"session_id": f"{s}00000-rest", "scope": "main", "cwd": "/x"}) + "\n"
        for s in ("old", "ctl", "skw")))
    (logs / "session-end-old00000.log").write_text(_FAILED.format(sid="old00000"))
    watch = DistillWatch(logs=logs, pins=pins, state=tmp / "dismissed.json",
                         kills=tmp / "killed.jsonl")
    return watch, logs


def run() -> Finding | None:
    with tempfile.TemporaryDirectory(prefix="qe-distill-seed-") as d:
        watch, logs = _fixture(Path(d))
        first = _sessions(watch)
        seeded_at = json.loads((Path(d) / "dismissed.json").read_text()).get("seeded_at")
        if not isinstance(seeded_at, float) or seeded_at <= 0 or first:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="control: the first scan did not seed and hide the backlog",
                witness=f"seeded_at={seeded_at!r} first_scan_sessions={first!r}",
            )

        ctl = logs / "session-end-ctl00000.log"
        ctl.write_text(_FAILED.format(sid="ctl00000"))
        os.utime(ctl, (seeded_at + 2.0, seeded_at + 2.0))
        got = _sessions(watch)
        if "ctl00000" not in got:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="control: a log with an mtime clearly after the seed did not surface",
                witness=f"sessions={got!r}",
            )

        skw = logs / "session-end-skw00000.log"
        skw.write_text(_FAILED.format(sid="skw00000"))
        mtime = seeded_at - _SKEW_S
        os.utime(skw, (mtime, mtime))
        scans = [_sessions(watch) for _ in range(3)]
        if any("skw00000" in s for s in scans):
            return None
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "a SessionEnd log written after the seed, with the mtime the kernel's "
                "coarse clock gives it, is hidden on every scan"
            ),
            witness=(
                f"log session-end-skw00000.log written after seed with mtime = "
                f"seeded_at - {_SKEW_S * 1000:.1f} ms never surfaced in "
                f"{len(scans)} consecutive scans: {scans!r}; the control log with "
                f"mtime = seeded_at + 2 s surfaced"
            ),
        )


CASE = Case(
    name="console-distill-seed-hides-log-written-after-seed",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary=(
        "a distillation log written after DistillWatch seeds must surface even when "
        "its coarse-clock mtime is a tick behind seeded_at"
    ),
    run=run,
    issue=187,
    fixed=False,
)
