"""Each session a SessionEnd hook distills gets its own log, and the readers keep them apart.

Issue #303. The hooks name the per-session log `~/.thalamus/logs/session-end-<session id>.log`
(`cursor/distill.sh`: `cursor-distill-<session id>.log`). Codex session ids are UUIDv7: the
first 8 hex digits are the high bits of a millisecond timestamp and hold for about 65
seconds, so a name built from those 8 characters was shared by two codex sessions started
within a minute, and nothing in the file said which lines belonged to which session.

**The real hook script runs, hermetically.** The hook detaches `uv run --project <repo>
thalamus <verb> ...` twice (the extract, then the eval sync). A stub `uv` at the front of
PATH records its argv, prints it (so it lands in the log the hook redirects the detached
block into) and exits 0: no extract, no graph, no model call. HOME is a temp directory,
so the log directory, the pin ledger and the transcripts are the case's own. PATH still
resolves `jq`, `bash`, `nohup` and `sh` from the box. Every session gets a transcript file
so the hook reaches the distillation branch rather than the early "no transcript" exit.

Checked, in order:
1. Two shared-prefix ids get two log files from each hook, each holding one header naming
   its own full id.
2. The console widget (`console/distill.DistillWatch`) over those two sessions' failed
   logs shows two rows, each joined to its own pin (scope); dismissing one leaves the
   other; a kill row for one session does not hide the other's log row.
3. A hostile session id (`../../x`, `a/b`, `..`, spaces) never puts a file outside
   `~/.thalamus/logs`: a path separator makes the hook fail to open its log and distill
   nothing, and the rest name a file inside the log directory.
4. `status.last_distillation` picks the newest log across the legacy 8-character and the
   full-id name shapes.

Controls, each of which makes a clean result mean something: the stub's record holds an
`extract --session <full id>` line for every session driven (an empty log directory cannot
read as "no collision"); two ids differing within the first 8 characters get two files;
the widget is first shown a single session, which must produce its one row.

Known residual, not asserted: a legacy 8-character log left on disk from before the name
changed joins the ledger by prefix, to the latest session with that prefix. It can show
beside a full-id row for the same prefix, and its prefix hides a kill row for a sibling
session that has no log.

Drive it red: in both hooks change the log name back to `${session_id:0:8}`. The case
fails at check 1 (run against the parent commit e62ebec to confirm).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_ROOT = Path(__file__).resolve().parents[3]
_HOOKS = _ROOT / "src" / "thalamus" / "harness" / "hooks"
_SITE = "tests/qe/cases/session_end_log_per_session.py::_drive"

# Real-shaped UUIDv7s: version nibble 7, variant 8-b. The first pair share their first 8
# hex digits, as two codex sessions started within one ~65 s window do.
_SHARED = ("01a0d7d6-749b-7c3e-8a51-2f9d4e6b1a07", "01a0d7d6-7f21-7b90-9c44-0e8d3a5f6b12")
_DISTINCT = ("01a0d7d6-749b-7c3e-8a51-2f9d4e6b1a07", "01a0d8e1-3c02-7a15-b2d8-6b1f0c9e4d33")

_FAILED = (
    "distilling session {sid} into scope s\n"
    "  ✗ {sid}  extraction failed: boom\n"
    "0 extracted, 0 skipped, 1 failed; model cost $0.00\n"
)

_STUB_UV = """#!/bin/sh
echo "stub-uv $*" >>"$STUB_RECORD"
echo "stub-uv $*"
exit 0
"""


def _drive(harness: str, ids: tuple[str, str]) -> tuple[dict[str, str], str, str]:
    """Run the real `harness` SessionEnd hook once per id under a temp HOME.

    Returns ({log filename: content}, the stub's record, an error string).
    """
    tmp = Path(tempfile.mkdtemp(prefix="qe-303-"))
    try:
        home = tmp / "home"
        bindir = tmp / "bin"
        home.mkdir()
        bindir.mkdir()
        record = tmp / "record"
        record.write_text("")
        uv = bindir / "uv"
        uv.write_text(_STUB_UV)
        uv.chmod(0o755)
        env = {
            "HOME": str(home),
            "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "STUB_RECORD": str(record),
        }
        script = _HOOKS / harness / "session-end.sh"
        for n, sid in enumerate(ids, start=1):
            if harness == "claude-code":
                tdir = home / ".claude" / "projects" / "-tmp-qe303"
                tdir.mkdir(parents=True, exist_ok=True)
                transcript = tdir / f"{sid}.jsonl"
            else:
                tdir = home / ".codex" / "sessions" / "2026" / "09" / "25"
                tdir.mkdir(parents=True, exist_ok=True)
                transcript = tdir / f"rollout-2026-09-25T00-00-00-{sid}.jsonl"
            transcript.write_text('{"type":"user"}\n')
            payload = (
                f'{{"session_id":"{sid}","transcript_path":"{transcript}",'
                f'"cwd":"/tmp/qe303","hook_event_name":"SessionEnd","reason":"other"}}'
            )
            try:
                done = subprocess.run(
                    ["bash", str(script)], input=payload, env=env, cwd=tmp,
                    capture_output=True, text=True, timeout=30,
                )
            except subprocess.TimeoutExpired:
                return {}, "", f"{harness} hook did not return within 30s"
            if done.returncode != 0:
                return {}, "", f"{harness} hook exited {done.returncode}: {done.stderr[-200:]}"
            # The detached block runs two stub calls (extract, eval sync); wait for both
            # before the next session so the sessions do not race on the record.
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if len(record.read_text().splitlines()) >= 2 * n:
                    break
                time.sleep(0.05)
        time.sleep(0.2)
        logs_dir = home / ".thalamus" / "logs"
        logs = {p.name: p.read_text() for p in sorted(logs_dir.glob("session-end-*.log"))}
        return logs, record.read_text(), ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _stub_ran(record: str, ids: tuple[str, str]) -> bool:
    return all("extract --harness" in record and f"--session {sid}" in record for sid in ids)


def _widget_keeps_sessions_apart() -> Finding | None:
    from thalamus.console.distill import STATE_V, DistillWatch, record_kill  # noqa: PLC0415

    a, b = _SHARED
    with tempfile.TemporaryDirectory(prefix="qe-303w-") as raw:
        tmp = Path(raw)
        logs = tmp / "logs"
        logs.mkdir()
        pins = tmp / "pins.jsonl"
        pins.write_text("".join(
            json.dumps({"session_id": sid, "scope": scope, "cwd": "/x", "ts": "n"}) + "\n"
            for sid, scope in ((a, "scope-a"), (b, "scope-b"))))
        state = tmp / "state.json"
        state.write_text(json.dumps({"v": STATE_V, "seeded_at": time.time() - 3600,
                                     "dismissed": {}, "dismissed_kills": {}}))
        kills = tmp / "kills.jsonl"
        watch = DistillWatch(logs=logs, pins=pins, state=state, kills=kills)

        def rows() -> dict[str, str]:
            watch._scanned_at = 0.0
            return {r["session"]: r["scope"] for r in watch.rows()}

        # CONTROL: one session shows one row, joined to its own pin.
        (logs / f"session-end-{a}.log").write_text(_FAILED.format(sid=a))
        one = rows()
        if one != {a: "scope-a"}:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the widget did not show a single failed session as one row joined "
                        "to its pin, so the two-session checks below prove nothing",
                witness=f"rows={one}", site="src/thalamus/console/distill.py::rows")
        (logs / f"session-end-{b}.log").write_text(_FAILED.format(sid=b))
        got = rows()
        if got != {a: "scope-a", b: "scope-b"}:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary="two sessions sharing an 8-character id prefix are not two widget "
                        "rows each joined to its own pin",
                witness=f"rows={got}", site="src/thalamus/console/distill.py::rows")
        watch.dismiss(a)
        got = rows()
        if got != {b: "scope-b"}:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary="dismissing one shared-prefix session did not leave exactly the other",
                witness=f"rows after dismissing {a}: {got}",
                site="src/thalamus/console/distill.py::dismiss")
        # A kill row for a session with no log must not hide its sibling's log row.
        c = "01a0d7d6-7000-7c00-8000-000000000003"
        record_kill(c, "scope-c", "/x", "close", at=time.time(), path=kills)
        got = rows()
        if got.get(b) != "scope-b" or c not in got:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary="a kill row for one shared-prefix session hid, or was hidden by, "
                        "a sibling's log row",
                witness=f"rows={got}", site="src/thalamus/console/distill.py::rows")
    return None


def _hostile_ids_stay_in_the_log_dir() -> Finding | None:
    tmp = Path(tempfile.mkdtemp(prefix="qe-303h-"))
    try:
        for harness in ("codex", "claude-code"):
            for n, sid in enumerate(("../../escape", "a/b", "..", "x y")):
                root = tmp / f"{harness}-{n}"
                home = root / "home"
                bindir = root / "bin"
                home.mkdir(parents=True)
                bindir.mkdir()
                uv = bindir / "uv"
                uv.write_text(_STUB_UV)
                uv.chmod(0o755)
                record = root / "record"
                record.write_text("")
                if harness == "codex":
                    transcript = home / "t.jsonl"
                else:
                    tdir = home / ".claude" / "projects" / "-p"
                    tdir.mkdir(parents=True)
                    transcript = tdir / f"{Path(sid).name}.jsonl"
                transcript.write_text("{}\n")
                payload = json.dumps({"session_id": sid, "transcript_path": str(transcript),
                                      "cwd": "/tmp/x", "hook_event_name": "SessionEnd"})
                env = {"HOME": str(home), "STUB_RECORD": str(record),
                       "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"}
                subprocess.run(["bash", str(_HOOKS / harness / "session-end.sh")],
                               input=payload, env=env, cwd=root, capture_output=True,
                               text=True, timeout=30)
                time.sleep(0.4)
                logs_dir = home / ".thalamus" / "logs"
                stray = [
                    str(p.relative_to(root)) for p in root.rglob("*")
                    if p.is_file() and logs_dir not in p.parents
                    and p not in (transcript, record, uv)
                ]
                if stray:
                    return Finding(
                        failure_class=FailureClass.INVARIANT_FALSIFIED,
                        summary="a crafted session_id in a SessionEnd payload wrote a file "
                                "outside ~/.thalamus/logs",
                        witness=f"hook={harness} session_id={sid!r} stray files={stray}",
                        site=f"src/thalamus/harness/hooks/{harness}/session-end.sh",
                    )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return None


def _status_picks_newest_across_name_shapes() -> Finding | None:
    from thalamus.harness import status  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="qe-303s-") as raw:
        d = Path(raw)
        legacy = d / "session-end-01a0d7d6.log"
        full = d / f"session-end-{_SHARED[0]}.log"
        legacy.write_text("legacy\n")
        full.write_text("full\n")
        now = time.time()
        original = status.LOG_DIR
        status.LOG_DIR = d
        try:
            os.utime(legacy, (now - 100, now - 100))
            os.utime(full, (now - 50, now - 50))
            first = status.last_distillation()
            os.utime(legacy, (now + 10, now + 10))
            second = status.last_distillation()
        finally:
            status.LOG_DIR = original
    if not first or first[1] != "full" or not second or second[1] != "legacy":
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary="status.last_distillation does not pick the newest log across the "
                    "legacy 8-character and full-id name shapes",
            witness=f"full newer -> {first}; legacy newer -> {second}",
            site="src/thalamus/harness/status.py::SESSION_LOG",
        )
    return None


def run() -> Finding | None:
    if shutil.which("jq") is None or shutil.which("bash") is None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="jq or bash is missing, so the hooks were not driven",
            witness="jq/bash not on PATH",
            site=_SITE,
        )
    collisions: list[str] = []
    for harness in ("claude-code", "codex"):
        # CONTROL: distinct prefixes -> two files, and the stub is what ran.
        logs, record, err = _drive(harness, _DISTINCT)
        if err or not _stub_ran(record, _DISTINCT) or len(logs) != 2:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    f"the {harness} hook driven with two ids that differ in their first 8 "
                    "characters did not yield two logs and two stub extracts, so a "
                    "collision verdict below would not be evidence"
                ),
                witness=f"err={err!r} logs={sorted(logs)} stub record={record.strip()!r}",
                site=_SITE,
            )
        logs, record, err = _drive(harness, _SHARED)
        if err or not _stub_ran(record, _SHARED):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=f"the {harness} hook did not run the stub uv for both shared-prefix "
                        "sessions, so the log count says nothing",
                witness=f"err={err!r} stub record={record.strip()!r}",
                site=_SITE,
            )
        if len(logs) < len(_SHARED):
            headers = sum(t.count("distilling session") for t in logs.values())
            collisions.append(
                f"hook={harness}: {len(_SHARED)} sessions sharing id prefix "
                f"{_SHARED[0][:8]} wrote {len(logs)} log file(s) {sorted(logs)} holding "
                f"{headers} 'distilling session' header(s)"
            )
        else:
            for sid in _SHARED:
                text = next((t for name, t in logs.items() if sid in name), "")
                if text.count("distilling session") != 1 or f"distilling session {sid}" not in text:
                    collisions.append(
                        f"hook={harness}: log for {sid} does not carry one header naming "
                        f"its full id: {text[:120]!r}"
                    )
    if collisions:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "the SessionEnd hook keys its per-session log on the first 8 characters of "
                "the session id; UUIDv7 ids (codex) share those for about a minute, so two "
                "sessions write one log and neither's record is attributable"
            ),
            witness="; ".join(collisions),
            site="src/thalamus/harness/hooks/{claude-code,codex}/session-end.sh",
        )
    for check in (
        _widget_keeps_sessions_apart,
        _hostile_ids_stay_in_the_log_dir,
        _status_picks_newest_across_name_shapes,
    ):
        finding = check()
        if finding is not None:
            return finding
    return None


CASE = Case(
    name="session-end-log-is-per-session",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_JQ,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="two sessions whose ids share their first 8 characters must not share a SessionEnd log",
    run=run,
    issue=303,
    fixed=True,
)
