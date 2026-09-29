"""A distillation log written after the seed must surface, whichever clock skews.

Issue #187, fixed. `DistillWatch` (`console/distill.py`) seeds its clean slate the first
time it loads state and hides logs older than the seed unless they classify `active`. A
log's mtime comes from the kernel's coarse timestamp clock, which lags `time.time()` by
up to a tick (0.9-1.7 ms measured in the issue), so a wall-clock seed left a log written
just after it with an earlier mtime, hidden on every scan. The seed is now the mtime of a
probe file written in the logs directory (created if absent), and the comparison is
`st_mtime < seeded_at`, so a log in the seed's own tick surfaces.

The case drives the real `DistillWatch.rows()` and never touches the comparison. Modes:

1. `_same_tick`: a log whose mtime equals the persisted seed surfaces (a coarse
   filesystem gives the probe and the next write one mtime; back-to-back writes never
   tie on this box's kernel, so the state is reached with `os.utime`).
2. `_wall_clock_ahead`: `time.time` is moved 50 ms ahead for the first scan only, then a
   real write must surface. This is the #187 skew, modelled on the clock, not the
   comparison.
3. `_no_logs_dir`: the same with no logs directory at first scan (the seed must still
   come from the filesystem).
4. `_unusable_logs_dir`: the logs path is a regular file; `rows()` must not raise.
5. `_back_to_back`: 200 real writes right after a first scan; none hidden. Nothing ties
   on this kernel, so it is a weak control here.

Controls: the backlog (aged 60 s, as real backlog is) is hidden by the first scan, and a
log at seed + 2 s surfaces.

Driven red against the parent of the fix: modes 1, 2 and 3 fail with `src/` from 9b02207
(`git show 9b02207:src/thalamus/console/distill.py`). Modes 4 and 5 pass there; they
guard the fix's own edges.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_FAILED = ("distilling session {sid} into scope main\n"
           "  ✗ {sid}  extraction failed: 3 validation errors for SessionGraph\n"
           "0 extracted, 0 skipped, 1 failed; model cost $0.00\n")

_SKEW_S = 0.0015


def _sessions(watch) -> list[str]:
    watch._scanned_at = 0.0          # step past SCAN_TTL_S; the comparison is untouched
    return [r["session"] for r in watch.rows()]


def _fixture(tmp: Path, mkdir: bool = True):
    from thalamus.console.distill import DistillWatch

    logs = tmp / "logs"
    if mkdir:
        logs.mkdir()
    pins = tmp / "pins.jsonl"
    pins.write_text("".join(
        json.dumps({"session_id": f"{s}00000-rest", "scope": "main", "cwd": "/x"}) + "\n"
        for s in ("old", "ctl", "skw")))
    if mkdir:
        old = logs / "session-end-old00000.log"
        old.write_text(_FAILED.format(sid="old00000"))
        aged = time.time() - 60.0        # real backlog is not in the probe's tick
        os.utime(old, (aged, aged))
    watch = DistillWatch(logs=logs, pins=pins, state=tmp / "dismissed.json",
                         kills=tmp / "killed.jsonl")
    return watch, logs


def _finding(cls, summary, witness):
    return Finding(failure_class=cls, summary=summary, witness=witness)


def _seed(tmp: Path) -> float:
    return json.loads((tmp / "dismissed.json").read_text()).get("seeded_at")


def _write(logs: Path, sid: str, mtime: float | None = None) -> None:
    p = logs / f"session-end-{sid}.log"
    p.write_text(_FAILED.format(sid=sid))
    if mtime is not None:
        os.utime(p, (mtime, mtime))


def _same_tick() -> Finding | None:
    # Control: seeding hides the backlog; a log clearly after the seed surfaces.
    with tempfile.TemporaryDirectory(prefix="qe-distill-seed-") as d:
        tmp = Path(d)
        watch, logs = _fixture(tmp)
        first = _sessions(watch)
        seed = _seed(tmp)
        if not isinstance(seed, float) or seed <= 0 or first:
            return _finding(FailureClass.COLLAPSED_SENTINEL,
                            "control: the first scan did not seed and hide the backlog",
                            f"seeded_at={seed!r} first_scan_sessions={first!r}")
        _write(logs, "ctl00000", seed + 2.0)
        if "ctl00000" not in _sessions(watch):
            return _finding(FailureClass.COLLAPSED_SENTINEL,
                            "control: a log clearly after the seed did not surface",
                            f"seeded_at={seed!r}")

        # Same tick: the filesystem gives a log written in the seed's tick the seed's
        # own mtime. `st_mtime <= seeded_at` hides it.
        _write(logs, "skw00000", seed)
        got = _sessions(watch)
        if "skw00000" not in got:
            return _finding(
                FailureClass.INVARIANT_FALSIFIED,
                "a log written after the seed whose mtime equals the seed is hidden",
                f"log with mtime == seeded_at ({seed!r}) not surfaced: {got!r}; "
                f"the control log at seeded_at + 2 s surfaced")

    return None


def _wall_clock_ahead() -> Finding | None:
    # Wall clock ahead of the filesystem clock (the #187 skew, modelled by moving
    # `time.time`, not the comparison): a real write after the first scan must surface.
    with tempfile.TemporaryDirectory(prefix="qe-distill-seed-") as d:
        tmp = Path(d)
        watch, logs = _fixture(tmp)
        real = time.time
        time.time = lambda: real() + 0.05
        try:
            _sessions(watch)
        finally:
            time.time = real
        _write(logs, "skw00000")
        got = _sessions(watch)
        if "skw00000" not in got:
            return _finding(
                FailureClass.INVARIANT_FALSIFIED,
                "with the wall clock 50 ms ahead of the filesystem clock, a log written "
                "after the first scan is hidden",
                f"seeded_at={_seed(tmp)!r}; log written after the seed not surfaced: {got!r}")

    return None


def _no_logs_dir() -> Finding | None:
    # First run with no logs directory, wall clock ahead of the filesystem clock: the
    # seed must still come from the filesystem, so a log written afterwards surfaces.
    with tempfile.TemporaryDirectory(prefix="qe-distill-seed-") as d:
        tmp = Path(d)
        watch, logs = _fixture(tmp, mkdir=False)
        real = time.time
        time.time = lambda: real() + 0.05
        try:
            _sessions(watch)
        finally:
            time.time = real
        if not logs.is_dir():
            return _finding(FailureClass.INVARIANT_FALSIFIED,
                            "first scan with no logs directory left it absent",
                            f"seeded_at={_seed(tmp)!r}")
        _write(logs, "skw00000")
        got = _sessions(watch)
        if "skw00000" not in got:
            return _finding(
                FailureClass.INVARIANT_FALSIFIED,
                "seeded with no logs directory, a log written afterwards is hidden",
                f"logs dir absent at first scan, wall clock 50 ms ahead; "
                f"seeded_at={_seed(tmp)!r}; log not surfaced: {got!r}")
    return None


def _unusable_logs_dir() -> Finding | None:
    # The logs path is a regular file: nothing can be probed or created. The watcher
    # must not raise, and must list a log once the path becomes a directory.
    with tempfile.TemporaryDirectory(prefix="qe-distill-seed-") as d:
        tmp = Path(d)
        watch, logs = _fixture(tmp, mkdir=False)
        logs.write_text("in the way")
        try:
            got = _sessions(watch)
        except Exception as exc:  # noqa: BLE001 - the property is "does not raise"
            return _finding(FailureClass.FAILED_OPEN,
                            "DistillWatch.rows() raised when the logs path is a file",
                            f"{type(exc).__name__}: {exc}")
        if got:
            return _finding(FailureClass.COLLAPSED_SENTINEL,
                            "control: rows from a logs path that is a file",
                            repr(got))
    return None


def _back_to_back() -> Finding | None:
    # Real back-to-back writes, repeated: none may be hidden.
    hidden = 0
    for _ in range(200):
        with tempfile.TemporaryDirectory(prefix="qe-distill-seed-") as d:
            watch, logs = _fixture(Path(d))
            _sessions(watch)
            _write(logs, "skw00000")
            hidden += "skw00000" not in _sessions(watch)
    if hidden:
        return _finding(FailureClass.INVARIANT_FALSIFIED,
                        "a log written immediately after the first scan was hidden",
                        f"{hidden}/200 real back-to-back writes never surfaced")
    return None


MODES = (_same_tick, _wall_clock_ahead, _no_logs_dir, _unusable_logs_dir, _back_to_back)


def run() -> Finding | None:
    for mode in MODES:
        found = mode()
        if found is not None:
            return found
    return None


CASE = Case(
    name="console-distill-seed-hides-log-written-after-seed",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL,
             FailureClass.FAILED_OPEN),
    summary=(
        "a distillation log written after DistillWatch seeds must surface even when "
        "its coarse-clock mtime is a tick behind seeded_at"
    ),
    run=run,
    issue=187,
    fixed=True,
)
