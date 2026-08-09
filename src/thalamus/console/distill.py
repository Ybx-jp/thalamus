"""Whether a session that ended is still distilling — derived from its log.

SessionEnd launches `thalamus extract` **detached** (`nohup … &` in
`hooks/claude-code/session-end.sh`), so the tmux window is gone long before the
distillation it triggered finishes. There is no lockfile, no pid file and no
status record anywhere; the single artifact is
`~/.thalamus/logs/session-end-<sid8>.log`, which the hook creates before
forking and the detached job appends to. That log is therefore the whole state
machine, and this module reads it as one:

    no summary line yet, recently touched   → distilling
    "N extracted, M skipped, 0 failed"      → done, drop it
    a ✗ line, "K failed", or no transcript  → error
    no summary line, log gone quiet         → error (the job died mid-flight)

**Only ledger-backed sessions count.** Subagents fire SessionEnd too, and each
one leaves a log that always ends in `No session matching …` because a subagent
has no transcript of its own — measured, and it is not a small effect: 1234 of
the 1826 logs on this box at the time of writing were subagent residue. What a
subagent never writes is a pin-ledger start record, so joining the logs against
`pins.jsonl` filters every one of them out, now and in future, without needing a
time horizon or a heuristic on the log body.

Errors persist until dismissed, per the operator's rule, so this owns a scrap of
state: `~/.thalamus/console/distill-dismissed.json`. Its `seeded_at` stamp is
the clean slate — every log already on disk the first time this runs counts as
dismissed, so the widget starts blank instead of opening on a pile of
archaeology. Both that stamp and a per-session dismissal are compared against
the log's *mtime*, which means a session that re-distills later and fails again
comes back on its own: the new write moves mtime past the dismissal.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

LOGS = Path.home() / ".thalamus" / "logs"
PINS = Path.home() / ".thalamus" / "pins" / "pins.jsonl"
STATE = Path.home() / ".thalamus" / "console" / "distill-dismissed.json"

# Bumped when the meaning of a `dismissed` value changes; an older file keeps its
# seed stamp and forgets its dismissals rather than misreading them.
STATE_V = 2

PREFIX = "session-end-"
SUFFIX = ".log"

# The line `thalamus extract` prints when it is done with every session it was
# given. Its presence is what separates "still running" from "finished", and the
# failure count in it is one of the two error signals.
SUMMARY_RE = re.compile(r"^(\d+) extracted, (\d+) skipped, (\d+) failed")

# The other error signal. `_cmd_extract` marks every per-session failure —
# extraction error, contract rejection, write failure — with this, and none of
# them set a non-zero exit code, so the log body is the only place they show up.
FAIL_MARK = "✗"

# Extraction with no transcript to read. For a real session this means the
# conversation was not distilled at all, which is exactly the silent loss this
# widget exists to make visible.
NO_TRANSCRIPT = "No session matching"

# How long a log may sit untouched with no summary line before the job behind it
# is presumed dead. Measured over 60 real distillations: p50 217s, max 255s;
# extract's own model-call timeout is 900s. 20 minutes clears both with room to
# spare, so anything past it died rather than ran long.
STALL_AFTER_S = 20 * 60

# Rescan floor. The client polls /api/panes about every 1.2s and several clients
# may poll at once; the scan is cheap (a scandir plus a read of whatever changed)
# but there is no reason to repeat it inside one poll interval.
SCAN_TTL_S = 1.0


# The line the hook writes before forking. A session distilled more than once —
# resumed, or re-extracted by hand — appends a second one, which is the only
# unambiguous "this ran again" marker in the file.
RUN_MARK = "distilling session "


def _runs(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith(RUN_MARK))


def _classify(text: str, mtime: float, now: float) -> tuple[str, str]:
    """(state, detail) for one log body. State is 'active', 'done' or 'error'."""
    summary = None
    fail_line = ""
    for line in text.splitlines():
        line = line.strip()
        got = SUMMARY_RE.match(line)
        if got:
            summary = got            # last one wins: a re-distill appends
        elif line.startswith(FAIL_MARK) and not fail_line:
            # `✗ <sid8>  extraction failed: …` — the row already names the
            # session, so only the reason is worth the width on a phone.
            fail_line = re.sub(r"^[0-9a-f]{8}\s+", "",
                               line.lstrip(FAIL_MARK).strip())

    if NO_TRANSCRIPT in text:
        return "error", "no transcript found — nothing was distilled"
    if summary is None:
        if now - mtime < STALL_AFTER_S:
            return "active", ""
        return "error", "stalled — the extract process stopped without finishing"
    if int(summary.group(3)) or fail_line:
        return "error", fail_line or f"{summary.group(3)} failed"
    return "done", ""


class DistillWatch:
    """The log directory, joined to the pin ledger, as a list of rows.

    Everything here is cached against (mtime, size) so a steady-state poll reads
    no file at all: the ledger is reparsed only when it grows, and a log is
    reread only when the detached job has actually written to it.
    """

    def __init__(self, logs: Path = LOGS, pins: Path = PINS, state: Path = STATE):
        self.logs, self.pins, self.state_path = logs, pins, state
        self._lock = threading.Lock()
        self._ledger: dict[str, dict] = {}
        self._ledger_sig: tuple = ()
        self._logs_cache: dict[str, tuple[float, int, str, str]] = {}
        self._rows: list[dict] = []
        self._scanned_at = 0.0
        self._state: dict | None = None

    # ---- the dismissal file -------------------------------------------------

    def _load_state(self) -> dict:
        if self._state is not None:
            return self._state
        try:
            got = json.loads(self.state_path.read_text())
            if not isinstance(got, dict):
                raise ValueError("not an object")
            got.setdefault("seeded_at", 0.0)
            got.setdefault("dismissed", {})
            # Dismissals used to be stamped with the log's mtime. Compared against
            # a run count those would hide a row forever, so an unversioned file
            # keeps its seed — the part that is still true — and drops the rest.
            if got.get("v") != STATE_V:
                got["v"], got["dismissed"] = STATE_V, {}
                self._write_state(got)
        except (OSError, ValueError):
            # First run (or a corrupt file, which is the same thing here): stamp
            # now and let every log that already exists fall behind the stamp.
            got = {"v": STATE_V, "seeded_at": time.time(), "dismissed": {}}
            self._write_state(got)
        self._state = got
        return got

    def _write_state(self, state: dict) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2))
            os.replace(tmp, self.state_path)
        except OSError:
            pass          # a widget is not worth failing a poll over

    def dismiss(self, session: str) -> bool:
        """Hide this session's error row until the session distills *again*.

        Keyed on the number of runs in the log rather than its mtime, because the
        hook appends `thalamus eval sync` output a few seconds behind extract's
        own summary: an mtime key would bounce a row that was dismissed inside
        that window straight back onto the list.
        """
        with self._lock:
            state = self._load_state()
            path = self.logs / f"{PREFIX}{session}{SUFFIX}"
            try:
                runs = _runs(path.read_text(errors="replace"))
            except OSError:
                return False
            state["dismissed"][session] = runs
            self._write_state(state)
            self._scanned_at = 0.0
            return True

    # ---- the ledger join ----------------------------------------------------

    def _ledger_rows(self) -> dict[str, dict]:
        try:
            st = self.pins.stat()
        except OSError:
            return {}
        sig = (st.st_mtime, st.st_size)
        if sig == self._ledger_sig:
            return self._ledger
        rows: dict[str, dict] = {}
        try:
            with self.pins.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    # 'engaged' rows are pin confirmations, not session starts,
                    # and carry none of the fields a row needs.
                    if rec.get("event") or not rec.get("session_id"):
                        continue
                    rows[rec["session_id"][:8]] = rec
        except OSError:
            return self._ledger
        self._ledger, self._ledger_sig = rows, sig
        return rows

    # ---- the scan -----------------------------------------------------------

    def rows(self) -> list[dict]:
        now = time.time()
        with self._lock:
            if now - self._scanned_at < SCAN_TTL_S:
                return self._rows
            self._scanned_at = now
            state = self._load_state()
            seeded_at = state.get("seeded_at", 0.0)
            dismissed = state.get("dismissed", {})
            ledger = self._ledger_rows()

            out, seen = [], set()
            try:
                entries = list(os.scandir(self.logs))
            except OSError:
                entries = []
            for entry in entries:
                name = entry.name
                if not (name.startswith(PREFIX) and name.endswith(SUFFIX)):
                    continue
                session = name[len(PREFIX):-len(SUFFIX)]
                pin = ledger.get(session)
                if pin is None:
                    continue          # a subagent's log; see the module docstring
                try:
                    st = entry.stat()
                except OSError:
                    continue
                seen.add(name)
                # The clean slate, applied before anything is read: a log that has
                # not been touched since this widget first ran is backlog.
                if st.st_mtime <= seeded_at:
                    continue

                cached = self._logs_cache.get(name)
                if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
                    kind, detail, runs = cached[2], cached[3], cached[4]
                    # 'active' is the one verdict that expires on the clock
                    # rather than on a write, so it is re-derived every scan.
                    if kind == "active" and now - st.st_mtime >= STALL_AFTER_S:
                        kind, detail = "error", ("stalled — the extract process "
                                                 "stopped without finishing")
                        self._logs_cache[name] = (st.st_mtime, st.st_size,
                                                  kind, detail, runs)
                else:
                    try:
                        text = (self.logs / name).read_text(errors="replace")
                    except OSError:
                        continue
                    kind, detail = _classify(text, st.st_mtime, now)
                    runs = _runs(text)
                    self._logs_cache[name] = (st.st_mtime, st.st_size,
                                              kind, detail, runs)

                if kind == "done":
                    continue
                if runs <= dismissed.get(session, 0):
                    continue
                cwd = pin.get("cwd", "") or ""
                out.append({
                    "session": session,
                    "scope": pin.get("scope", "") or "?",
                    "dir": os.path.basename(cwd.rstrip("/")) or cwd,
                    "state": kind,
                    "detail": detail,
                    "updated": st.st_mtime,
                    "age": max(0, int(now - st.st_mtime)),
                })

            for gone in set(self._logs_cache) - seen:
                del self._logs_cache[gone]

            # Distilling first (it is the transient one and the reason to look),
            # then errors; newest activity at the top within each group.
            out.sort(key=lambda r: (r["state"] != "active", -r["updated"]))
            self._rows = out
            return out
