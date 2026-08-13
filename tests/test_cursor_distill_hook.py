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

    def test_the_settle_loop_outlasts_a_writer_still_appending(self, tmp_path):
        """The property the whole design rests on. A transcript still being written
        must not be read until it stops changing — reading early yields a truncated
        session, which is worse than no session because nothing can detect it.

        The loop is exercised directly rather than through the hook: the hook hands
        it to a detached shell whose completion nothing observes, and a test that
        waited on that would be testing `nohup`.
        """
        target = tmp_path / "settling.jsonl"
        target.write_text('{"n":0}\n')
        writer = subprocess.Popen(
            ["sh", "-c",
             f"for i in 1 2 3 4; do sleep 1; echo '{{\"n\":1}}' >> {target}; done"],
        )
        try:
            loop = subprocess.run(
                ["sh", "-c", f'''
                  last=''; stable=0; waited=0
                  while [ $waited -lt 60 ]; do
                    now=$(stat -c '%s:%Y' '{target}' 2>/dev/null || echo gone)
                    if [ "$now" = "$last" ]; then
                      stable=$((stable + 1)); [ $stable -ge 3 ] && break
                    else stable=0; fi
                    last="$now"; sleep 1; waited=$((waited + 1))
                  done
                  echo "$waited"
                '''],
                capture_output=True, text=True, timeout=90,
            )
        finally:
            writer.wait(timeout=30)

        waited = int(loop.stdout.strip())
        # It must not have stopped while the writer was still going, and it must not
        # have run to the cap either — a loop that never settles is a hang, not a wait.
        assert 4 <= waited < 60, f"settled after {waited}s"
        assert target.read_text().count("\n") == 5, "the loop settled on a partial file"
