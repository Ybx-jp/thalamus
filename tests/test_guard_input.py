"""
The shared stdin read every PreToolUse guard uses, and the one property it exists for.

Interfaces: src/thalamus/harness/hooks/claude-code/resolve-scope.sh
  (`thalamus_read_guard_input`), driven live through each guard that sources it.
Infrastructure: bash, a tmp_path `$HOME` so no guard's event log touches the live
instrument, and a stub `jq` on PATH for the missing-binary case. No graph, no tmux.
Scope: the *unreadable payload*, not any guard's verdict. Each guard's own decisions
are tested in its own file; what is asserted here is that none of them can be talked
past by handing it something it cannot parse.

A guard that examined the call and approved it and a guard that died before looking
are the same event from outside — exit 0, nothing on stderr — so an unreadable payload
would otherwise be one line past every boundary the roster draws.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks" / "claude-code"

BLOCK_EXIT = 2

# Every guard that gates a tool call. Observer hooks (the taps, the session-lifecycle
# pair) are deliberately absent: they decide nothing, so failing closed in one would
# block a call over a record nobody was going to read.
GUARDS = (
    "gremlin-guard.sh",
    "role-guard.sh",
    "room-guard.sh",
    "room-command-guard.sh",
    "write-guard.sh",
)

UNREADABLE = {
    "malformed": '{"tool_name": "Bash", broken',
    "empty": "",
    "not-an-object": "",  # replaced below; kept here so the ids read plainly
}
UNREADABLE["not-an-object"] = "just some text that is not JSON at all"


def run_guard(script: str, payload: str, home: Path, *, strip_jq: bool = False):
    env = dict(os.environ)
    env["HOME"] = str(home)
    # The sandbox makes every hook exit 0, which would mute the whole file.
    env.pop("THALAMUS_SANDBOX", None)
    if strip_jq:
        shadow = Path(tempfile.mkdtemp(prefix="guard-nojq-"))
        stub = shadow / "jq"
        # 127 is what a shell returns for a command it cannot find, so the guard sees
        # exactly what it would on a box without jq. Shadowing only `jq` and not
        # emptying PATH matters: removing bash and cat too would kill the script for a
        # reason that has nothing to do with the case.
        stub.write_text("#!/bin/sh\nexit 127\n", encoding="utf-8")
        stub.chmod(0o755)
        env["PATH"] = f"{shadow}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(
        ["bash", str(HOOKS / script)],
        input=payload, capture_output=True, text=True, env=env, timeout=30, check=False,
    )


@pytest.mark.parametrize("script", GUARDS)
@pytest.mark.parametrize("shape", sorted(UNREADABLE))
def test_a_guard_that_cannot_read_its_payload_blocks(script, shape, tmp_path):
    """Deny, not permit — and with the blocking code, not whatever the abort was.

    Under `set -euo pipefail` a jq failure aborts the script, and the abort code is 5
    (malformed) or 0 (empty, via each guard's `// empty` fallback). Neither is 2, so
    the call proceeded either way.
    """
    result = run_guard(script, UNREADABLE[shape], tmp_path)

    assert result.returncode == BLOCK_EXIT, result.stderr
    assert "could not read the tool call" in result.stderr


@pytest.mark.parametrize("script", GUARDS)
def test_a_guard_blocks_when_jq_is_gone(script, tmp_path):
    """`thalamus init` verifies jq once; nothing checks again, and PATH is mutable."""
    result = run_guard(script, '{"tool_name": "Bash", "tool_input": {}}',
                       tmp_path, strip_jq=True)

    assert result.returncode == BLOCK_EXIT, result.stderr
    assert "jq is not on PATH" in result.stderr


@pytest.mark.parametrize("script", GUARDS)
def test_a_readable_payload_the_guard_does_not_govern_is_untouched(script, tmp_path):
    """The control, and the reason failing closed is affordable.

    Blocking on an unreadable payload is only tolerable if a readable one outside the
    guard's subject still passes silently — otherwise the change reads as "block
    everything", which is the failure mode that teaches route-around. `Read` is
    governed by none of these five.
    """
    payload = '{"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}, "cwd": "/tmp"}'

    result = run_guard(script, payload, tmp_path)

    assert result.returncode == 0, result.stderr
