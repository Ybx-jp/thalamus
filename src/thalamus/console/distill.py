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
    a traceback, or a non-zero exit status  → error, naming the exception
    no summary line, log gone quiet         → stalled, then abandoned

A log holds one attempt per run mark and the last of them decides the row, so a
re-distill that succeeds clears a crash rather than inheriting it.

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

# The one thing a log cannot record: that no log was ever written. A forced close or
# a forced recycle kills the window without SessionEnd running, so `thalamus extract`
# never starts, no log file is created, and the scan below has nothing to classify —
# a distillation that never happened is invisible to a state machine whose only input
# is the artifact it would have produced. The console is the only witness, because it
# is the thing that did it, so it writes a row here at the moment it kills.
#
# Append-only JSONL, like the pin ledger and for the same reason: the writer is a
# worker thread racing a dying process, and appending a line is the one file
# operation that cannot leave a half-state behind for the reader.
KILLS = Path.home() / ".thalamus" / "console" / "distill-killed.jsonl"

# Bumped when the meaning of a `dismissed` value changes; an older file keeps its
# seed stamp and forgets its dismissals rather than misreading them.
STATE_V = 3

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

# What SessionEnd writes when the transcript is not on disk: it checks before
# launching `thalamus extract` and, for a session the pin ledger vouches for, records
# the absence and stops.
#
# That absence is not a loss, and this is the measurement (2026-09-01, two pinned
# `main` windows spawned for it). Claude Code creates the `.jsonl` at the first
# interaction, not at session start: a window spawned and left alone has none. Typing
# `/exit` is itself an interaction, so a window closed that way *does* leave a
# transcript, and extract reads it and reports `no substantive exchange` — which is
# why no console close reaches this line. Ending an untouched window by signal
# instead reproduced it exactly. So the file's absence is the evidence that there was
# no conversation, and the row belongs with the other clean ending below.
HOOK_NO_TRANSCRIPT = "no transcript at "

# The other clean ending, and the one that looks like a failure if you only know
# about the summary line. A session with no substantive exchange is named, found and
# deliberately not distilled — `cli.py:1767-1772` says so and exits 0 without ever
# printing a summary. Nothing was lost and nothing is running, so the row is `done`.
#
# Distinct from NO_TRANSCRIPT's "nothing distilled.", which is a session that could
# not be found at all. Measured on this box: of three rows the stall clock had
# marked, two were this — a job that finished its work correctly, reported as a
# process that died mid-flight, because the only completion signal recognised was a
# summary line it had no reason to print.
NOTHING_TO_DISTILL = "nothing to distill."

# How long a log may sit untouched with no summary line before the job behind it
# is presumed dead. Measured over 60 real distillations: p50 217s, max 255s;
# extract's own model-call timeout is 900s. 20 minutes clears both with room to
# spare, so anything past it died rather than ran long.
STALL_AFTER_S = 20 * 60

# When a stall stops being one. `stalled` holds steady geometry on the row because
# the process may still finish; that is true at half an hour and false at six days,
# where the same calm row reports work in progress that will never move again.
# Expressed as a multiple so it tracks the stall clock rather than drifting from it.
ABANDON_AFTER_S = 3 * STALL_AFTER_S

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


# What a crash leaves behind, and it is not a `✗`. `_cmd_extract` marks the failures it
# handles itself, but an exception escaping the command marks nothing and prints no
# summary: it writes a traceback and exits non-zero. session-end.sh checks that status
# and records it twice — a row in hook-failures.log, and this line in the log — so the
# log does say what happened. Nothing here read it. Measured on this box: all four
# crashed runs in the log directory were left to the stall clock, which called a
# process that died in its first seconds one that had gone quiet, then abandoned it.
# The codex hook runs extract with no status check and writes no such line, so the
# traceback is the only signal there; either one decides.
EXIT_RE = re.compile(r"^extract exited (\d+)\b")
TRACEBACK_MARK = "Traceback (most recent call last):"


def _last_run(text: str) -> str:
    """The log from its most recent run mark on.

    A log is a sequence of attempts rather than one state, so the attempt that decides
    the row is the latest one. Reading the whole body instead lets a failure that has
    since been superseded outlive the run that fixed it, and the dismissal machinery
    can only hide such a row, never correct it (A0156, cites-as-live).
    """
    lines = text.splitlines()
    cut = -1
    for i, line in enumerate(lines):
        if line.startswith(RUN_MARK):
            cut = i
    return text if cut < 0 else "\n".join(lines[cut:])


def _crash_detail(lines: list[str]) -> str:
    """The exception a traceback ended on — the whole of what a crash has to say.

    The frames in between are this repo's own file paths and say nothing on a phone.
    The last unindented line is the exception type and its message, which is what
    names the fault, and it is the last rather than the first because a chained
    traceback re-raises: the final exception is the one that reached the top.
    """
    starts = [i for i, line in enumerate(lines) if line.startswith(TRACEBACK_MARK)]
    if not starts:
        return ""
    last = ""
    for line in lines[starts[-1] + 1:]:
        if EXIT_RE.match(line):
            break
        if line and not line[0].isspace():
            last = line.strip()
    return last


# A `detail` is a log line and a log line has no length contract — a contract
# rejection or a write failure can run long. It reaches the operator verbatim, so
# the only safe way to bound it is to cut it and *say* that it was cut: a silently
# truncated string is an absence the reader cannot tell from a complete answer,
# which is the defect this module exists to remove, one field over.
DETAIL_MAX = 200


def _detail(text: str) -> tuple[str, bool]:
    """(detail, truncated) — one line, bounded, and honest about the bound."""
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    if len(first) <= DETAIL_MAX:
        return first, False
    return first[:DETAIL_MAX], True


def record_kill(session: str, scope: str, cwd: str, op: str,
                at: float | None = None, path: Path | None = None,
                project: str = "", repo_root: str = "") -> None:
    """Record that a window was killed with its distillation never started.

    Called by the console at the moment it forces — `respawn-window -k` or
    `kill-window` — because that is the only moment anything knows. `/exit` fires
    SessionEnd and SessionEnd is what launches `thalamus extract`; a window that
    dies without it leaves no log, and a scan over logs cannot report a log that was
    never created. Without this row a distillation that succeeded and one that never
    ran are the same pixels, which is the same absence-indistinguishable-from-a-
    negative this project has already ruled on twice.

    Failure to write is swallowed. This runs on the path that is already destroying
    something, and raising here would turn a lost distillation into a lost window.
    """
    path = path or KILLS
    # The row carries its own identity because by the time anyone reads it the
    # window is gone by construction — this is written *as* it is destroyed.
    row = {"session": (session or "")[:8], "scope": scope or "", "cwd": cwd or "",
           "project": project or "", "repo_root": repo_root or "",
           "op": op, "at": at if at is not None else time.time()}
    if not row["session"]:
        return          # nothing identifiable to report; a row keyed on "" is noise
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


# The three verdicts a log with no summary line passes through. They are a function
# of the clock and of nothing in the file, which is what makes them the one group
# that cannot be cached against the log's (mtime, size): a stalled log is by
# definition one nothing is writing to, so its cache entry stays valid for as long as
# the console runs — and the console runs as a systemd unit, so that is weeks. Read
# together here so the scan and the classifier cannot age a row differently.
CLOCK_STATES = frozenset({"active", "stalled", "abandoned"})


def _by_clock(idle: float) -> tuple[str, str]:
    """(state, detail) for a job that has written nothing for `idle` seconds."""
    if idle < STALL_AFTER_S:
        return "active", ""
    # Distinct from `error`, because the operator's next move differs: an error
    # is terminal and the answer is to rerun, while a stall is a process that is
    # still nominally running and may yet finish. Collapsing a live process into
    # a terminal word is the same defect this module's killed-window row exists
    # to fix, one state along.
    if idle < ABANDON_AFTER_S:
        return "stalled", "stalled — the extract process stopped without finishing"
    # "May yet finish" is true at half an hour and false at six days. Past the
    # abandonment threshold the row is a permanent steady state that reads as
    # work in progress, which is the meaningless silence this module exists to
    # remove, wearing a state word. Extraction is minutes of work: a process
    # silent for hours and then resuming is not a case worth encoding for.
    return "abandoned", "nothing has moved since the extract process went quiet"


def _classify(text: str, mtime: float, now: float) -> tuple[str, str]:
    """(state, detail) for one log body.

    State is 'active', 'done', 'stalled', 'abandoned' or 'error'. 'done' never
    reaches a client — a successful distillation is dropped rather than served, so
    the absence of a record is what says it worked.
    """
    text = _last_run(text)
    lines = text.splitlines()
    summary = None
    fail_line = ""
    exited = 0
    for raw in lines:
        line = raw.strip()
        got = SUMMARY_RE.match(line)
        got_exit = EXIT_RE.match(line)
        if got:
            summary = got            # last one wins: a re-distill appends
        elif got_exit:
            exited = int(got_exit.group(1))
        elif line.startswith(FAIL_MARK) and not fail_line:
            # `✗ <sid8>  extraction failed: …` — the row already names the
            # session, so only the reason is worth the width on a phone.
            fail_line = re.sub(r"^[0-9a-f]{8}\s+", "",
                               line.lstrip(FAIL_MARK).strip())

    if NO_TRANSCRIPT in text:
        return "error", "no transcript found — nothing was distilled"
    # A `✗` is an unambiguous per-session failure and none of them set a non-zero
    # exit code, so it is decided on its own rather than through the summary line —
    # a job that marks a failure and then dies before summarising has still failed,
    # and letting the stall clock reach it first would call that a hang.
    if fail_line:
        return "error", fail_line
    # Also before the stall clock, and for a sharper version of the same reason: a
    # crash and a slow run are the same log to a clock, and the clock reads a process
    # that died in two seconds as one that may yet finish. The exit status the hook
    # recorded settles it, or the traceback where the hook records none, and the row
    # then names the exception instead of ageing into "nothing has moved"
    # (A0155, cites-as-live).
    if exited or TRACEBACK_MARK in text:
        return "error", (_crash_detail(lines)
                         or f"extract exited {exited or 1} without distilling")
    # Checked before the stall clock: this job finished, it simply had nothing to
    # write, so ageing it into a failure would report loss where there was none. The
    # hook's own line is the same ending reached one step earlier — a session with no
    # interaction never had a transcript to read — and neither of them ever reaches a
    # summary line, so the stall clock is the only thing that would otherwise judge
    # them, and it would call both a process that died mid-flight.
    if NOTHING_TO_DISTILL in text or HOOK_NO_TRANSCRIPT in text:
        return "done", ""
    if summary is None:
        return _by_clock(now - mtime)
    if int(summary.group(3)) or fail_line:
        return "error", fail_line or f"{summary.group(3)} failed"
    return "done", ""


class DistillWatch:
    """The log directory, joined to the pin ledger, as a list of rows.

    Everything here is cached against (mtime, size) so a steady-state poll reads
    no file at all: the ledger is reparsed only when it grows, and a log is
    reread only when the detached job has actually written to it.
    """

    def __init__(self, logs: Path = LOGS, pins: Path = PINS, state: Path = STATE,
                 kills: Path = KILLS):
        self.logs, self.pins, self.state_path, self.kills = logs, pins, state, kills
        self._lock = threading.Lock()
        self._ledger: dict[str, dict] = {}
        self._ledger_sig: tuple = ()
        self._logs_cache: dict[str, tuple[float, int, str, str, int]] = {}
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
            # A separate keyspace from `dismissed`: one session can have both a
            # failed distillation and, later, a killed window, and a single map
            # would let an acknowledgement of one silently hide the other.
            got.setdefault("dismissed_kills", {})
            # Dismissals used to be stamped with the log's mtime. Compared against
            # a run count those would hide a row forever, so an unversioned file
            # keeps its seed — the part that is still true — and drops the rest.
            if got.get("v") != STATE_V:
                got["v"], got["dismissed"] = STATE_V, {}
                got["dismissed_kills"] = {}
                self._write_state(got)
        except (OSError, ValueError):
            # First run (or a corrupt file, which is the same thing here): stamp
            # now and let every log that already exists fall behind the stamp.
            got = {"v": STATE_V, "seeded_at": time.time(), "dismissed": {},
                   "dismissed_kills": {}}
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

        A killed-window row has no log to count runs in, so it is acknowledged by
        the stamp of the kill it names. Dismissal means "I saw this failure", never
        "stop telling me about this kind of failure": a second kill of the same
        session is a second event, carries a later stamp, and comes back. Silently
        converting one acknowledgement into permanent suppression would rebuild the
        silence this row exists to break.
        """
        with self._lock:
            state = self._load_state()
            kills = self._kill_rows()
            dismissed_any = False
            if session in kills:
                state["dismissed_kills"][session] = kills[session]["at"]
                dismissed_any = True
            path = self.logs / f"{PREFIX}{session}{SUFFIX}"
            try:
                runs = _runs(path.read_text(errors="replace"))
            except OSError:
                pass
            else:
                state["dismissed"][session] = runs
                dismissed_any = True
            if not dismissed_any:
                return False
            self._write_state(state)
            self._scanned_at = 0.0
            return True

    # ---- the killed-window ledger -------------------------------------------

    def _kill_rows(self) -> dict[str, dict]:
        """The latest kill per session. Last row wins, as the pin ledger does."""
        out: dict[str, dict] = {}
        try:
            text = self.kills.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return out
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            session = row.get("session")
            if not isinstance(row, dict) or not session:
                continue
            row.setdefault("at", 0.0)
            got = out.get(session)
            if got is None or row["at"] >= got["at"]:
                out[session] = row
        return out

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

            # `seen` is log filenames, for cache eviction. `seen_sessions` is the
            # sessions those logs belong to: a killed-window row is an assertion
            # that no log exists, so a log that does exist overrules it.
            out, seen, seen_sessions = [], set(), set()
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
                seen_sessions.add(session)
                cached = self._logs_cache.get(name)
                if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
                    kind, detail, runs = cached[2], cached[3], cached[4]
                    # The clock-derived verdicts expire on the clock rather than on a
                    # write, so they are re-derived every scan — all three of them,
                    # not just the first. Re-deriving only `active` froze a stalled
                    # row at `stalled` for the life of the process: the log it is
                    # derived from is one nothing is writing to, so the cache entry
                    # never invalidates, and `stalled` is the one state the roster
                    # draws without a dismiss control. A row that can never age and
                    # can never be cleared is the silence this module exists to
                    # break, wearing a state word.<!-- (A0155, cites-as-live) -->
                    if kind in CLOCK_STATES:
                        kind, detail = _by_clock(now - st.st_mtime)
                        if kind != cached[2]:
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

                # Seed away old terminal archaeology, not work that is running now.
                # The watcher is often first constructed after SessionEnd has already
                # created the log and entered a quiet model call. Hiding every file
                # older than `seeded_at` made that whole active phase invisible; a
                # successful run then disappeared without ever drawing a row.
                if st.st_mtime <= seeded_at and kind != "active":
                    continue

                if kind == "done":
                    continue
                # Membership, not a zero default: a log that never reached the run
                # mark — the no-transcript exit above is the whole of one — counts
                # zero runs, and `0 <= 0` would file every one of them as already
                # acknowledged. A row nobody dismissed would then be hidden by the
                # dismissal machinery, which is this module's own defect wearing its
                # own state file.
                if session in dismissed and runs <= dismissed[session]:
                    continue
                cwd = pin.get("cwd", "") or ""
                text_detail, truncated = _detail(detail)
                out.append({
                    "session": session,
                    "scope": pin.get("scope", "") or "?",
                    "dir": os.path.basename(cwd.rstrip("/")) or cwd,
                    # A record routinely outlives the window it came from — by the
                    # time a distillation fails, the session that triggered it has
                    # usually exited — so the record has to carry its own identity
                    # rather than borrowing the roster's. Same fields the row uses,
                    # from the same pin, so the two group the same way.
                    "project": pin.get("project", "") or "",
                    "repo_root": pin.get("repo_root", "") or "",
                    "state": kind,
                    "detail": text_detail,
                    "detail_truncated": truncated,
                    "updated": st.st_mtime,
                    "age": max(0, int(now - st.st_mtime)),
                })

            for gone in set(self._logs_cache) - seen:
                del self._logs_cache[gone]

            # The windows that were killed before SessionEnd could run. These have no
            # log by construction, so they are not in the scan above and cannot be:
            # the loop reads artifacts, and the whole point of this state is that no
            # artifact exists. A session that later distilled anyway — a race the
            # kill lost — is dropped, because the log is evidence and the kill row is
            # only an expectation.
            dismissed_kills = state.get("dismissed_kills", {})
            for session, row in self._kill_rows().items():
                if session in seen_sessions:
                    continue
                at = row.get("at", 0.0)
                if at <= seeded_at or at <= dismissed_kills.get(session, 0):
                    continue
                cwd = row.get("cwd", "") or ""
                out.append({
                    "session": session,
                    "scope": row.get("scope", "") or "?",
                    "dir": os.path.basename(cwd.rstrip("/")) or cwd,
                    "project": row.get("project", "") or "",
                    "repo_root": row.get("repo_root", "") or "",
                    "state": "unknown",
                    # No detail: the reason is structural and identical every time,
                    # so a per-row string would be the same sentence N times.
                    "detail": "",
                    "detail_truncated": False,
                    "op": row.get("op", ""),
                    "updated": at,
                    "age": max(0, int(now - at)),
                })

            # Distilling first (it is the transient one and the reason to look),
            # then everything terminal; newest activity at the top within each group.
            out.sort(key=lambda r: (r["state"] != "active", -r["updated"]))
            self._rows = out
            return out
