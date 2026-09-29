"""Each session a SessionEnd hook distills must get its own log file.

Issue #303. Both hooks name the per-session log
`~/.thalamus/logs/session-end-${session_id:0:8}.log`. Codex session ids are UUIDv7: the
first 8 hex digits are the high bits of a millisecond timestamp and hold for about 65
seconds, so two codex sessions started within a minute write one file, and nothing in it
says which lines belong to which session. (`cursor/distill.sh` names its log
`cursor-distill-${session_id:0:8}.log` with the same truncation; it is not driven here.)

**The real hook script runs, hermetically.** The hook detaches `uv run --project <repo>
thalamus extract ...` and `... eval sync --write`. A stub `uv` at the front of PATH
records its argv, prints it (so it lands in the log the hook redirects the detached block
into) and exits 0: no extract, no graph, no model call. HOME is a temp directory, so the
log directory, the pin ledger and the transcripts are the case's own. PATH still resolves
`jq`, `bash`, `nohup` and `sh` from the box. Every session gets a transcript file so the
hook reaches the distillation branch rather than the early "no transcript" exit.

Controls, each of which makes a clean result mean something:
- the stub actually ran: its record holds an `extract --session <full id>` line for every
  session driven, so an empty log directory cannot read as "no collision";
- two ids that differ within the first 8 characters get two files, so the assertion is
  capable of passing.

Repeat the mutation: change `${session_id:0:8}` to `${session_id}` in the log name of
both hooks and the case passes.
"""

from __future__ import annotations

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
        # CONTROL 1: distinct prefixes -> two files, and the stub is what ran.
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
    if not collisions:
        return None
    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "the SessionEnd hook keys its per-session log on the first 8 characters of the "
            "session id; UUIDv7 ids (codex) share those for about a minute, so two "
            "sessions write one log and neither's record is attributable"
        ),
        witness="; ".join(collisions),
        site="src/thalamus/harness/hooks/{claude-code,codex}/session-end.sh",
    )


CASE = Case(
    name="session-end-log-is-per-session",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_JQ,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="two sessions whose ids share their first 8 characters must not share a SessionEnd log",
    run=run,
    issue=303,
    fixed=False,
)
