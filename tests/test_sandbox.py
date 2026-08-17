"""The extraction sandbox leaves no memory.

Interfaces: thalamus.harness.agents.sandbox_env / is_sandbox_cwd,
            thalamus.harness.extraction.run_extraction,
            thalamus.harness.transcripts.discover / is_sandbox_project,
            every hook script in harness/hooks/*/ driven live (bash).
Infrastructure: tmp_path as $HOME and as a synthetic ~/.claude/projects tree;
            subprocess.run patched for the CLI invocation; no live graph.
Scope: the three independent refusals that keep distillation from distilling
       itself — the marker the subprocess carries, the hooks that read it, and
       the transcript reader that recognises a sandbox from its cwd alone once
       the marker is gone.
"""

import json
import subprocess
from pathlib import Path

from thalamus.harness import extraction, transcripts
from thalamus.harness.agents import SANDBOX_ENV, is_sandbox_cwd

HOOKS_ROOT = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks"
# Sourced libraries, not hooks: nothing invokes them directly, so they carry no guard.
HOOK_LIBS = {"resolve-scope.sh", "spool.sh"}

_OK = json.dumps({"type": "result", "is_error": False, "result": "yaml", "duration_ms": 1})


def hook_scripts():
    return sorted(
        p for p in HOOKS_ROOT.glob("*/*.sh") if p.name not in HOOK_LIBS
    )


# ---------------------------------------------------------------------------
# The marker the subprocess carries
# ---------------------------------------------------------------------------


def test_the_headless_cli_runs_marked(monkeypatch):
    """
    Scenario: a session distills.

    Verification: the `claude -p` subprocess carries THALAMUS_SANDBOX. It is a
    full session to its own harness — transcript on disk, SessionEnd fired — so
    the marker is the only thing that tells the inherited hook suite it is
    machinery and not a conversation.
    """
    seen = {}

    def run(cmd, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout=_OK, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    extraction.run_extraction("prompt")
    assert seen["env"][SANDBOX_ENV] == "1"
    # The inherited environment survives: the CLI still needs the operator's own
    # PATH and credentials to run at all.
    assert "PATH" in seen["env"]


# ---------------------------------------------------------------------------
# The hooks that read it
# ---------------------------------------------------------------------------


def test_every_hook_declines_inside_a_sandbox(tmp_path):
    """
    Scenario: each hook fires inside a marked subprocess.

    Verification: it exits 0 and writes nothing — no stdout (no injected
    context), no ledger, no logs, no traces under $HOME. A sandbox is not a
    session, and the rule is uniform so no future hook has to rediscover it.
    """
    home = tmp_path / "home"
    home.mkdir()
    payload = json.dumps(
        {
            "session_id": "sandbox-session",
            "cwd": "/tmp/thalamus-extract-abc123",
            "transcript_path": "/dev/null",
            "hook_event_name": "SessionEnd",
            "tool_name": "mcp__thalamus__memory_recall",
            "tool_input": {"query": "anything"},
            "tool_response": {"stdout": "", "stderr": ""},
            "prompt": "hello",
        }
    )
    for script in hook_scripts():
        result = subprocess.run(
            [str(script)],
            input=payload,
            capture_output=True,
            text=True,
            env={
                "HOME": str(home),
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                SANDBOX_ENV: "1",
            },
            timeout=30,
        )
        assert result.returncode == 0, f"{script.name}: {result.stderr}"
        assert result.stdout.strip() == "", f"{script.name} injected context"
    assert list(home.iterdir()) == [], "a hook wrote under $HOME inside a sandbox"


def test_the_guard_is_wired_into_every_hook():
    """The guard is only a guard where it is called. A new hook that skips it
    reopens the loop for its own event, so the wiring is asserted per script
    rather than per code path."""
    for script in hook_scripts():
        assert "thalamus_sandbox_guard" in script.read_text(), f"{script.name} is unguarded"


def test_an_unmarked_session_still_gets_its_context(tmp_path):
    """The guard refuses sandboxes, not sessions: without the marker the
    SessionStart hook injects as before."""
    result = subprocess.run(
        [str(HOOKS_ROOT / "claude-code" / "session-start.sh")],
        input=json.dumps(
            {"session_id": "real-1", "cwd": "/home/user/code/proj", "source": "startup"}
        ),
        capture_output=True,
        text=True,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        timeout=30,
    )
    assert result.returncode == 0
    assert "memory_open_threads" in result.stdout


# ---------------------------------------------------------------------------
# The reader, once the marker is gone
# ---------------------------------------------------------------------------


def test_sandbox_transcripts_are_never_offered_for_extraction(tmp_path):
    """
    Scenario: a retroactive sweep (`thalamus bootstrap`, an explicit
    `thalamus extract -- <dir>`) reads ~/.claude/projects, where sandbox runs
    have left transcripts of their own.

    Verification: discovery withholds them. A transcript on disk carries no
    environment, so the marker cannot help here — the flattened cwd can.
    """
    projects = tmp_path / "projects"
    (projects / "-home-user-code-proj").mkdir(parents=True)
    (projects / "-home-user-code-proj" / "real.jsonl").write_text("{}\n")
    (projects / "-tmp-thalamus-extract-0a1yo40k").mkdir()
    (projects / "-tmp-thalamus-extract-0a1yo40k" / "sandbox.jsonl").write_text("{}\n")

    assert list(transcripts.discover(projects)) == ["-home-user-code-proj"]


def test_a_sandbox_cwd_is_recognised_wherever_tmpdir_points():
    """TMPDIR moves the sandbox, so the test is on the directory name, not on a
    `/tmp` prefix."""
    assert is_sandbox_cwd("/tmp/thalamus-extract-0a1yo40k")
    assert is_sandbox_cwd("/var/folders/xy/thalamus-extract-zz/inner")
    assert not is_sandbox_cwd("/home/user/code/thalamus")
    assert not is_sandbox_cwd("")
