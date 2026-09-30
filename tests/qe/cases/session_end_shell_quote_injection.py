"""A quote in a session id, scope or room must not run as shell in the SessionEnd hooks.

Issue #335, found by the qe red-team pass on #303. Each hook detaches distillation as
`nohup sh -c "..."`, a double-quoted block that splices shell variables in as
single-quoted words (`'$session_id'`, `'$scope'`, `'$room'`, ...). A value holding a
single quote closes the quoting and `sh` runs the remainder as commands, detached, under
the operator's account. `session_id` comes from the hook payload; `scope` and `room` come
from the pin ledger.

**The real hook scripts run, hermetically**, the way `session_end_log_per_session.py`
(#303) drives them: HOME is a temp directory, a stub `uv` is first on PATH (it records its
argv and exits 0, so no extract, graph or model call runs), and the session's transcript
file exists so the hook reaches the distillation branch. The hook's cwd is the case's temp
directory, and every injected command is `touch <bare name>`, so a marker can only land
inside that directory; nothing is ever written outside it.

Vectors driven: a hostile `session_id` through claude-code, codex and cursor
(`cursor/distill.sh`, which waits ~3 s for the transcript to settle); a hostile `scope`
and a hostile `room`, both through the pin ledger, on claude-code and codex (cursor reads
no room).

Assertion: no marker file exists anywhere under the temp directory after each run.

Control: the same run with a benign session id (and benign ledger row) reaches the stub,
which records `extract ... --session <id>` for that hook. Without it "no marker" would
also read as "nothing ran". A hook whose control fails is COLLAPSED_SENTINEL, not a pass.
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

_HOOKS = Path(__file__).resolve().parents[3] / "src" / "thalamus" / "harness" / "hooks"
_SITE = "tests/qe/cases/session_end_shell_quote_injection.py::_drive"

_STUB_UV = """#!/bin/sh
echo "stub-uv $*" >>"$STUB_RECORD"
exit 0
"""

_BENIGN_SID = "01a0d7d6-749b-7c3e-8a51-2f9d4e6b1a07"
_MARKER = "QE335_MARKER"
_SCRIPTS = {
    "claude-code": "session-end.sh",
    "codex": "session-end.sh",
    "cursor": "distill.sh",
}
# (hook, vector) pairs driven. scope/room reach the hook through the pin ledger.
_VECTORS = (
    ("claude-code", "session_id"), ("codex", "session_id"), ("cursor", "session_id"),
    ("claude-code", "scope"), ("codex", "scope"),
    ("claude-code", "room"), ("codex", "room"),
)


def _hostile() -> str:
    return f"q'; touch {_MARKER}; echo '"


def _drive(hook: str, vector: str | None) -> tuple[list[str], str, str]:
    """Run one hook once. vector=None is the benign control.

    Returns (marker files found anywhere under the temp dir, the stub's record, error).
    """
    tmp = Path(tempfile.mkdtemp(prefix="qe-335-"))
    try:
        home, bindir = tmp / "home", tmp / "bin"
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
        sid = _hostile() if vector == "session_id" else _BENIGN_SID
        scope = _hostile() if vector == "scope" else "qe-scope"
        room = _hostile() if vector == "room" else "qe-room"

        if hook == "claude-code":
            tdir = home / ".claude" / "projects" / "-tmp-qe335"
        elif hook == "codex":
            tdir = home / ".codex" / "sessions" / "2026" / "09" / "29"
        else:
            tdir = home / ".cursor" / "projects" / "p" / "agent-transcripts" / "s"
        tdir.mkdir(parents=True)
        transcript = tdir / (f"{sid}.jsonl" if hook == "claude-code" else "t.jsonl")
        transcript.write_text('{"type":"user"}\n')

        pins = home / ".thalamus" / "pins"
        pins.mkdir(parents=True)
        (pins / "pins.jsonl").write_text(json.dumps(
            {"session_id": sid, "scope": scope, "room": room, "cwd": "/tmp/qe335", "ts": "n"}
        ) + "\n")

        payload = {"session_id": sid, "transcript_path": str(transcript),
                   "cwd": "/tmp/qe335", "hook_event_name": "SessionEnd"}
        script = _HOOKS / hook / _SCRIPTS[hook]
        try:
            done = subprocess.run(["bash", str(script)], input=json.dumps(payload), env=env,
                                  cwd=tmp, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return [], "", f"{hook} hook did not return within 30s"
        if done.returncode != 0:
            return [], "", f"{hook} hook exited {done.returncode}: {done.stderr[-200:]}"

        # The detached block runs asynchronously (cursor settles ~3 s first). Wait for
        # the stub's extract line, or for a marker, up to a deadline.
        deadline = time.monotonic() + (10 if hook == "cursor" else 4)
        while time.monotonic() < deadline:
            if "extract" in record.read_text() or any(tmp.rglob(_MARKER + "*")):
                break
            time.sleep(0.05)
        time.sleep(0.5)
        markers = [str(p.relative_to(tmp)) for p in tmp.rglob(_MARKER + "*")]
        return markers, record.read_text(), ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run() -> Finding | None:
    if shutil.which("jq") is None or shutil.which("bash") is None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="jq or bash is missing, so the hooks were not driven",
            witness="jq/bash not on PATH", site=_SITE)

    # CONTROL, per hook: a benign id reaches the stub and leaves no marker.
    for hook in _SCRIPTS:
        markers, rec, err = _drive(hook, None)
        if err or markers or f"--session {_BENIGN_SID}" not in rec or "extract" not in rec:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=f"the {hook} hook driven with a benign session id did not reach the "
                        "stub uv's extract, so an absent marker below would not be evidence",
                witness=f"err={err!r} markers={markers} stub record={rec.strip()!r}",
                site=_SITE)

    fired: list[str] = []
    for hook, vector in _VECTORS:
        markers, _rec, err = _drive(hook, vector)
        if err:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=f"the {hook} hook did not run to completion with a hostile {vector}",
                witness=err, site=_SITE)
        if markers:
            fired.append(f"{hook}/{vector}: injected `touch` ran and created {markers}")
    if fired:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary="a single quote in a session id, scope or room closes the quoting in the "
                    "SessionEnd hook's `nohup sh -c \"...\"` block, and sh runs the rest of "
                    "the value as a command",
            witness="; ".join(fired),
            site="src/thalamus/harness/hooks/{claude-code,codex}/session-end.sh, "
                 "cursor/distill.sh")
    return None


CASE = Case(
    name="session-end-shell-quote-injection",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_JQ,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a quote in a session id, scope or room must not run as shell in a SessionEnd hook",
    run=run,
    issue=335,
    fixed=False,
)
