"""
The Cursor auto-distillation hook (harness/hooks/cursor/distill.sh).

Interfaces: the script, driven over its real stdin contract. Infrastructure: tmp
HOME so nothing reads or writes the operator's ledgers; no Cursor, no graph, and
no `thalamus extract` — the hook's job ends at launching one, so what is tested is
every decision it makes *before* that, plus the settle loop it makes them with.

Scope: the two failure modes that would be silent in production. A hook that
distills too early writes a truncated session, which is a corrupted memory rather
than a missing one and nothing downstream can tell the difference. A hook that
raises, or that runs long enough to be cancelled, distills nothing and says so
nowhere. So the cases here are: it exits quietly and cheaply when there is nothing
to do, it never blocks the harness, and its settle loop waits out a writer that is
still appending.
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "src/thalamus/harness/hooks/cursor/distill.sh"


def run(payload: dict, home: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    environ = {**os.environ, "HOME": str(home)}
    environ.pop("THALAMUS_SANDBOX", None)
    environ.update(env or {})
    return subprocess.run(
        [str(HOOK)], input=json.dumps(payload), text=True,
        capture_output=True, env=environ, timeout=30,
    )


def logs(home: Path) -> list[Path]:
    return sorted((home / ".thalamus" / "logs").glob("cursor-distill-*.log"))


def _stub_uv(tmp_path: Path, records: Path, counting: Path | None = None) -> str:
    """A `uv` on PATH that records the handoff instead of running an extraction.

    The detached shell execs `uv` the instant its settle loop breaks, so this is where
    the loop's decision becomes observable from a test. It writes its own argv, or —
    given `counting` — the line count of that file at the moment it ran, which is what
    the extractor would have been reading.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "uv"
    body = (f'wc -l < "{counting}" | tr -d " \\n" > "{records}"'
            if counting else f'echo "$@" > "{records}"')
    stub.write_text(f"#!/bin/sh\n{body}\nexit 0\n")
    stub.chmod(0o755)
    return f"{bin_dir}:{os.environ['PATH']}"


def _wait_for(path: Path, timeout: float) -> None:
    """Block until the detached shell has written `path`. Fails loudly rather than
    letting a test that observed nothing read as a test that observed success."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.read_text().strip():
            return
        time.sleep(0.2)
    raise AssertionError(f"{path.name} was never written — the handoff never happened")


@pytest.fixture
def home(tmp_path):
    (tmp_path / ".thalamus" / "logs").mkdir(parents=True)
    return tmp_path


class TestItNeverBlocksTheHarness:
    def test_the_hook_returns_immediately(self, home, tmp_path):
        """A sessionEnd hook still running when the process exits is cancelled —
        that is how the Claude Code side once lost a fork's staging. Everything
        that costs time has to be detached, so the hook itself must return in
        well under the settle window it schedules."""
        transcript = tmp_path / "t.jsonl"
        transcript.write_text('{"role":"user","message":{"content":"hi"}}\n')
        start = time.monotonic()
        result = run({"session_id": "sess-quick", "transcript_path": str(transcript)}, home)
        assert result.returncode == 0
        assert time.monotonic() - start < 2.0, "the hook waited instead of detaching"

    def test_a_session_with_no_transcript_costs_nothing(self, home):
        """`transcript_path` is null for a session that completed no turn. There is
        nothing to distill and never will be, so it exits without scheduling a
        model call — and without an error, since this is the ordinary case."""
        result = run({"session_id": "sess-empty", "transcript_path": None}, home)
        assert result.returncode == 0
        assert logs(home) == [], "a turnless session must not schedule a distillation"

    def test_a_payload_with_no_session_is_not_an_error(self, home):
        assert run({}, home).returncode == 0
        assert logs(home) == []

    def test_an_extraction_sandbox_is_refused(self, home, tmp_path):
        """Thalamus distills by running headless `agent -p`, which is itself a
        Cursor session that fires sessionEnd. Unguarded, the hook that makes memory
        fires inside the machinery that makes memory."""
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")
        result = run({"session_id": "sess-sandbox", "transcript_path": str(transcript)},
                     home, env={"THALAMUS_SANDBOX": "1"})
        assert result.returncode == 0
        assert logs(home) == []


class TestItWaitsForTheTranscript:
    def test_it_schedules_a_wait_rather_than_reading_at_once(self, home, tmp_path):
        """The log line is written before the detached block starts, so its
        presence is the evidence that a distillation was scheduled at all."""
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")
        run({"session_id": "sess-abcdefgh", "transcript_path": str(transcript)}, home)
        written = logs(home)
        assert len(written) == 1
        assert written[0].name == "cursor-distill-sess-abc.log"
        assert "waiting for" in written[0].read_text()

    def test_the_settle_loop_outlasts_a_writer_still_appending(self, home, tmp_path):
        """The property the whole design rests on. A transcript still being written
        must not be read until it stops changing — reading early yields a truncated
        session, which is a corrupted memory rather than a missing one, and nothing
        downstream can tell the difference.

        The hook's own loop is what runs. Waiting on `nohup` is not the obstacle it
        looks like: the detached shell's handoff is observable, because the very next
        thing it does is exec `uv`. A stub `uv` on PATH records how much of the
        transcript existed at that moment, which is the property stated directly —
        not "the loop waited about long enough" but "what the extractor was handed
        was whole" (#224).
        """
        target = tmp_path / "settling.jsonl"
        target.write_text('{"n":0}\n')
        handoff = tmp_path / "handoff"
        path = _stub_uv(tmp_path, records=handoff, counting=target)

        writer = subprocess.Popen(
            ["sh", "-c",
             f"for i in 1 2 3 4; do sleep 1; echo '{{\"n\":1}}' >> {target}; done"],
        )
        try:
            result = run({"session_id": "sess-settling", "transcript_path": str(target)},
                         home, env={"PATH": path})
            assert result.returncode == 0
            _wait_for(handoff, timeout=60)
        finally:
            writer.wait(timeout=30)

        assert target.read_text().count("\n") == 5, "the writer did not finish"
        assert handoff.read_text().strip() == "5", (
            "the extractor was handed a transcript that was still being written")

        (log,) = logs(home)
        settled = re.search(r"settled after (\d+)s", log.read_text())
        assert settled, f"the loop never reported settling: {log.read_text()!r}"
        # It must not have stopped while the writer was still going, and it must not
        # have run to the cap either — a loop that never settles is a hang, not a wait.
        assert 4 <= int(settled.group(1)) < 120

    def test_the_extractor_is_launched_with_the_session_and_scope_the_hook_resolved(
            self, home, tmp_path):
        """The control for the test above, and the handoff itself.

        "The transcript was whole when `uv` ran" says nothing if `uv` runs for some
        other reason, or with arguments that name a different session. A settle loop
        that ended in no extraction at all would satisfy every timing assertion there
        and distil nothing.
        """
        target = tmp_path / "quiet.jsonl"
        target.write_text('{"n":0}\n')
        argv = tmp_path / "argv"
        path = _stub_uv(tmp_path, records=argv)

        run({"session_id": "sess-abcdefgh", "transcript_path": str(target)},
            home, env={"PATH": path, "THALAMUS_SCOPE": "homelab"})
        _wait_for(argv, timeout=60)

        launched = argv.read_text()
        assert "thalamus extract" in launched
        assert "--harness cursor" in launched
        assert "--session sess-abcdefgh" in launched
        assert "--scope homelab" in launched
        assert "--write" in launched
