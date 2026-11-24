"""`THALAMUS_PROJECT` must name the same project to the recall hook and to the write path.

Issue #360. The claude-code SessionStart hook resolves
`project="${THALAMUS_PROJECT:-$repo_name}"` and tells the agent to call
`memory_open_threads` and `memory_recall_by_project` with that value
(`src/thalamus/harness/hooks/claude-code/session-start.sh:86`). Distillation records
`Session.project` from `TranscriptFacts.project`, which is `basename(repo_root)` and reads
no override (`src/thalamus/harness/transcripts.py:130`). Recall filters on
`has("project", TextP.containing(project))` (`substrate/reader.py:941`, `:998`), so an
override that is not a substring of the checkout's directory name sends every
project-scoped recall to a name nothing was filed under.

**Both real surfaces run.** The hook script runs as a subprocess in a temp git repo
named `client-site`, with HOME a temp directory, and the project it names is read out of
the `additionalContext` it injects. The write side is the real parse path: a transcript
whose `cwd` is that repo goes through `transcripts.parse` and
`transcripts.to_session_graph`, with `THALAMUS_PROJECT` set in the process environment as
it is when `thalamus extract` runs, and `SessionGraph.project` is the value a Session
vertex would carry.

Assertion: with `THALAMUS_PROJECT=acme` the two projects are equal.

Control: with `THALAMUS_PROJECT` unset both resolve to `client-site`. A hook that names
nothing, or a parse that yields no project, would otherwise read as "disagree" or as a
pass for a reason that has nothing to do with the override.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_HOOK = (Path(__file__).resolve().parents[3] / "src" / "thalamus" / "harness" / "hooks"
         / "claude-code" / "session-start.sh")
_SITE = ("src/thalamus/harness/hooks/claude-code/session-start.sh:86 (recall key) / "
         "src/thalamus/harness/transcripts.py:130 (recorded project)")
_REPO_NAME = "client-site"
_OVERRIDE = "acme"
_SID = "0360a0d7-749b-7c3e-8a51-2f9d4e6b1a07"
_NAMED = re.compile(r'memory_open_threads with project="([^"]*)"')


def _hook_project(repo: Path, home: Path, override: str | None) -> tuple[str | None, str]:
    """The project the hook's injected context tells the agent to recall by."""
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if override is not None:
        env["THALAMUS_PROJECT"] = override
    payload = {"session_id": _SID, "cwd": str(repo), "source": "startup",
               "hook_event_name": "SessionStart"}
    try:
        done = subprocess.run(["bash", str(_HOOK)], input=json.dumps(payload), env=env,
                              cwd=home, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return None, "hook did not return within 30s"
    if done.returncode != 0:
        return None, f"hook exited {done.returncode}: {done.stderr[-200:]}"
    try:
        context = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError, TypeError):
        return None, f"hook stdout carried no additionalContext: {done.stdout[:200]!r}"
    named = _NAMED.search(context)
    if not named:
        return None, "additionalContext names no memory_open_threads project"
    return named.group(1), ""


def _extract_project(repo: Path, tmp: Path, override: str | None) -> str | None:
    """The project a distilled Session would carry, via the real parse path."""
    from thalamus.harness import transcripts  # noqa: PLC0415

    transcript = tmp / f"{_SID}.jsonl"
    records = [
        {"type": "user", "cwd": str(repo), "sessionId": _SID,
         "timestamp": "2026-10-18T10:00:00Z",
         "message": {"role": "user", "content": "hello"}},
        {"type": "assistant", "cwd": str(repo), "sessionId": _SID,
         "timestamp": "2026-10-18T10:00:01Z",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}},
    ]
    transcript.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

    saved = os.environ.get("THALAMUS_PROJECT")
    try:
        if override is None:
            os.environ.pop("THALAMUS_PROJECT", None)
        else:
            os.environ["THALAMUS_PROJECT"] = override
        facts = transcripts.parse(transcript)
        graph = transcripts.to_session_graph(
            facts, content_hash="0" * 64, uri=transcript.as_uri(),
            byte_size=transcript.stat().st_size)
    finally:
        if saved is None:
            os.environ.pop("THALAMUS_PROJECT", None)
        else:
            os.environ["THALAMUS_PROJECT"] = saved
    return graph.project


def _both(override: str | None) -> tuple[str | None, str | None, str]:
    tmp = Path(tempfile.mkdtemp(prefix="qe-360-"))
    try:
        repo, home = tmp / _REPO_NAME, tmp / "home"
        repo.mkdir()
        home.mkdir()
        init = subprocess.run(["git", "init", "-q", str(repo)], capture_output=True, text=True)
        if init.returncode != 0:
            return None, None, f"git init failed: {init.stderr[-200:]}"
        hook, err = _hook_project(repo, home, override)
        if err:
            return None, None, err
        return hook, _extract_project(repo, tmp, override), ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run() -> Finding | None:
    missing = [t for t in ("jq", "bash", "git") if shutil.which(t) is None]
    if missing:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=f"{', '.join(missing)} not on PATH, so the hook was not driven",
            witness=f"missing: {missing}", site=_SITE)

    # CONTROL: no override, both sides take the checkout's directory name.
    hook, written, err = _both(None)
    if err or hook != _REPO_NAME or written != _REPO_NAME:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="control failed: with THALAMUS_PROJECT unset the hook and the parse "
                    f"path should both resolve to {_REPO_NAME!r}, so the override "
                    "comparison below proves nothing",
            witness=f"hook={hook!r} extract={written!r} err={err!r}", site=_SITE)

    hook, written, err = _both(_OVERRIDE)
    if err:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the override run did not complete, so the two sides were not compared",
            witness=err, site=_SITE)
    if hook != written:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "with THALAMUS_PROJECT set, the SessionStart hook tells the agent to "
                "recall by one project and the write path files the session under "
                "another, so project-scoped recall misses the session it was told to "
                "look for"
            ),
            witness=(f"THALAMUS_PROJECT={_OVERRIDE!r} in a checkout named {_REPO_NAME!r}: "
                     f"hook names project={hook!r}, extract records project={written!r}"),
            site=_SITE)
    return None


CASE = Case(
    name="project-override-names-one-project-on-both-sides",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_JQ,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="THALAMUS_PROJECT must give the recall hook and the recorded Session the same project",
    run=run,
    issue=360,
    fixed=False,
)
