"""
Self-write guard decision tests.

Interfaces: src/thalamus/harness/hooks/claude-code/write-guard.sh, driven live
(bash) with synthetic PreToolUse payloads.
Infrastructure: tmp_path as $HOME so the guard's event log is sandboxed; no live
graph.
Scope: the guard's *verdict*. Its subject is a session writing its own memory —
`thalamus write` and `thalamus extract --write`, both of which the decision keeps
as operator actions from outside a session. The boundary lived in prose until a
session read "`thalamus write` keeps the hand-authored path" as a general
permission and wrote itself a Thread mid-flight.

The failure mode that matters is a false positive: it teaches agents to route
around the guard, and route-around costs more than a gap. So the
maintenance commands that also take `--write`, the ingest path, and the in-session
close verb all have to pass, and so does prose that merely names the command.
"""

import json
import subprocess
from pathlib import Path

GUARD = (
    Path(__file__).resolve().parents[1]
    / "src" / "thalamus" / "harness" / "hooks" / "claude-code" / "write-guard.sh"
)

BLOCK_EXIT = 2


def run_guard(command, home, *, raw=None):
    payload = raw if raw is not None else json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "session_id": "wg-sess-1",
        "cwd": "/home/user/code/thalamus",
    })
    return subprocess.run(
        [str(GUARD)],
        input=payload,
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        timeout=30,
    )


def test_a_session_may_not_write_its_own_memory(tmp_path):
    """
    Scenario: `thalamus write` and `thalamus extract --write`, from inside a session

    Both are the decision's subject, and both survive as operator actions from a
    plain terminal where no hook fires. The reason has to name what to do instead —
    a block with no route forward is a stall.
    """
    for command in (
        "uv run thalamus write /tmp/session.yaml",
        "uv run thalamus extract --session abc --force --write",
    ):
        result = run_guard(command, tmp_path)
        assert result.returncode == BLOCK_EXIT, command
        assert "writes memory from inside a session" in result.stderr
        assert "thread propose" in result.stderr


def test_the_commands_that_merely_share_the_flag_are_untouched(tmp_path):
    """
    Scenario: maintenance commands taking `--write`, the ingest path, and the
    in-session close verb

    None of these is a session distilling itself. `repair-projects` and
    `derive-artifact-paths` operate over the whole graph, `ingest` carries
    third-party documents behind its own allowlist, and closing a thread is
    explicitly an in-session verb with operator approval (2026-08-11) — blocking it
    would invert that decision.
    """
    for command in (
        "uv run thalamus repair-projects --write",
        "uv run thalamus derive-artifact-paths --write",
        "uv run thalamus ingest https://example.com/paper --write",
        "uv run thalamus thread approve 1a2b3c",
        "uv run thalamus contract check",
        "ls -la",
    ):
        assert run_guard(command, tmp_path).returncode == 0, command


def test_prose_that_names_the_command_is_not_the_command(tmp_path):
    """
    Scenario: a commit message describing this very boundary

    This project already paid for this class on the gremlin guard, whose amendment
    tripped on the commit message explaining the amendment. The residual — a real
    write chained after a `git commit` — is accepted knowingly on the same trade.
    """
    for command in (
        'git commit -m "Block thalamus write from inside a session"',
        "echo thalamus write is blocked",
    ):
        assert run_guard(command, tmp_path).returncode == 0, command


def test_an_unparseable_payload_still_blocks(tmp_path):
    """
    Scenario: a payload the guard cannot read as JSON

    Deliberately the opposite posture from the other guards, and the reason is the
    consequence rather than the likelihood. `guards-fail-closed-on-unparseable-input`
    is an open qe finding against them: they permit when jq is missing or the JSON is
    malformed, so the guard is absent exactly when something unusual is happening.
    They can afford it because their failure is a bad edit; this one's failure is a
    graph write that distillation then duplicates. So the raw payload is searched when
    the structured read fails.
    """
    result = run_guard(None, tmp_path, raw="not json at all: thalamus write /tmp/x.yaml")

    assert result.returncode == BLOCK_EXIT
    assert "writes memory from inside a session" in result.stderr


def test_an_empty_payload_is_not_a_write(tmp_path):
    """Failing closed must not mean blocking everything: no command, nothing to block."""
    assert run_guard(None, tmp_path, raw="").returncode == 0
