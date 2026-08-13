"""The Cursor distillation sweep, startable from the console.

A Claude Code session distills itself: SessionEnd launches `thalamus extract` detached
and `console/distill.py` reports how that went. A Cursor session cannot, and the reason
is in `harness/cursor_transcripts.py` — Cursor is not documented to flush its transcript
before firing the hook, so reading at sessionEnd races an async writer and can distill a
truncated session. Its hook therefore only logs a pointer, and the distillation is a
*later* sweep that somebody has to run.

Until this module, "somebody" meant a laptop. The gap that leaves is not that the sweep
is inconvenient: a Cursor session that ends and is never swept is a session whose memory
never exists, and nothing on the phone said so. So the console gets the count and the
button, on the same argument the spawn and restart buttons were built on — everything
here could be typed into a terminal, and this is the one-tap version.

**The survey is deliberately graph-free.** Whether a session was *already* extracted is
a question only the graph answers (`_session_has_claims`), and asking it per session
every time the panel opens would put a graph round-trip behind a gear tap. The sweep
already skips those and reports how many it skipped, so the panel shows what is on disk
and lets the run itself say what it did. A count that is cheap and slightly generous
beats one that is exact and makes the panel wait.

**The run is detached and its log is the state machine**, the same shape `distill.py`
reads for Claude Code — except this module launches the job itself, so it can write a
pidfile and ask the OS whether the process is alive instead of inferring liveness from
mtime. That is the one place the two differ, and it is a strictly better signal.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

LOG = Path.home() / ".thalamus" / "logs" / "cursor-sweep.log"
PIDFILE = Path.home() / ".thalamus" / "logs" / "cursor-sweep.pid"

# The line `thalamus extract` prints when it finishes. Matching the summary rather than
# the exit code is what lets a sweep started before this console process began still be
# reported correctly — the log outlives whoever launched it.
SUMMARY = re.compile(r"^(\d+) sessions?, ~(\d+) nodes; (\d+) skipped, (\d+) rejected")


def survey() -> dict:
    """What is on disk and routable, without touching the graph.

    `ready` is sessions a sweep would consider; `unresolved` is sessions found on the
    filesystem that no hook ever resolved a scope for, which the sweep refuses rather
    than defaulting into `main` — surfaced here because otherwise a session sits
    undistillable with nothing on the phone saying why.
    """
    try:
        from thalamus.harness import cursor_transcripts as ct
    except Exception:
        return {"ready": 0, "unresolved": 0, "available": False}
    try:
        found = [s for s in ct.discover() if s.exists]
        ready, refused = ct.claim_unresolved(found)
    except Exception:
        return {"ready": 0, "unresolved": 0, "available": False}
    return {"ready": len(ready), "unresolved": len(refused), "available": True}


def running() -> bool:
    """Is a sweep this console started still alive?

    Asks the OS rather than inferring from log mtime, which is available here only
    because this module is the one that launched it. A stale pidfile — console killed
    mid-sweep, machine rebooted — reads as not running and is cleared, since a pid that
    no longer exists cannot be the sweep.
    """
    try:
        pid = int(PIDFILE.read_text().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        PIDFILE.unlink(missing_ok=True)
        return False
    return True


def last_result() -> str:
    """The finished sweep's own summary line, or "" if it never got there.

    Read from the tail rather than remembered in memory: the console restarts, and the
    answer to "did last night's sweep work" has to survive that.
    """
    try:
        lines = LOG.read_text(errors="ignore").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        if SUMMARY.match(line.strip()):
            return line.strip()
    return ""


def status() -> dict:
    return {**survey(), "running": running(), "last": last_result()}


def start() -> tuple[bool, str]:
    """Launch the sweep detached. Returns (started, message).

    `--write` is passed, because a dry run from a phone is a button that costs money
    and changes nothing. The write path is the point: a swept session becomes memory.
    """
    if running():
        return False, "a sweep is already running"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "-m", "thalamus", "extract", "--harness", "cursor", "--write"]
    try:
        handle = LOG.open("a")
    except OSError as exc:
        return False, f"cannot write {LOG}: {exc}"
    try:
        # Detached: the sweep runs for minutes and must outlive both this request and
        # the console process itself, so it gets its own session and never inherits the
        # server's stdin.
        process = subprocess.Popen(
            argv, stdout=handle, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError as exc:
        handle.close()
        return False, f"cannot start the sweep: {exc}"
    finally:
        handle.close()
    PIDFILE.write_text(str(process.pid))
    return True, f"sweep started (pid {process.pid})"
