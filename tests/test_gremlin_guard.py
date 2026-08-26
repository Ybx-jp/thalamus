"""
Terminal-step guard decision tests.

Interfaces: src/thalamus/harness/hooks/claude-code/gremlin-guard.sh, driven
live (bash) with synthetic PreToolUse payloads.
Infrastructure: tmp_path as $HOME so the guard's event log is sandboxed; no
live graph.
Scope: the guard's *verdict*, which had no test until a v4 false positive
blocked a command that built no traversal at all. The guard's subject is a
traversal that was built and never terminated; these tests pin both halves —
that it still blocks a doomed traversal, and that it declines commands where
there is no traversal to be lazy about. False positives are the failure mode
that matters: they teach agents to route around the guard.
"""

import json
import subprocess
from pathlib import Path


GUARD = (
    Path(__file__).resolve().parents[1]
    / "src" / "thalamus" / "harness" / "hooks" / "claude-code" / "gremlin-guard.sh"
)

BLOCK_EXIT = 2


def run_guard(command, home):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "session_id": "guard-sess-1",
        "cwd": "/home/user/code/thalamus",
    }
    return subprocess.run(
        [str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        timeout=30,
    )


def events(home):
    directory = Path(home) / ".thalamus" / "guards"
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.jsonl")):
        out += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return out


def verdict_of(home):
    recorded = events(home)
    assert len(recorded) == 1, f"expected exactly one event, got {recorded}"
    return recorded[0]["verdict"], recorded[0]["branch"]


class TestBlocksDoomedTraversals:
    """The guard's reason to exist: a traversal built and never iterated."""

    def test_traversal_without_terminal_step_is_blocked(self, tmp_path):
        result = run_guard(
            "python -c \"from thalamus.substrate.reader import x; "
            "g.V().has_label('Session').values('id')\"",
            tmp_path,
        )
        assert result.returncode == BLOCK_EXIT
        assert "Blocked:" in result.stderr and "Traversals are lazy" in result.stderr
        assert verdict_of(tmp_path) == ("block", "none")

    def test_write_traversal_without_iterate_is_blocked(self, tmp_path):
        result = run_guard(
            "python -c \"from thalamus.substrate.writer import w; "
            "g.addV('Claim').property('id', 'c1')\"",
            tmp_path,
        )
        assert result.returncode == BLOCK_EXIT
        assert verdict_of(tmp_path) == ("block", "none")


class TestPassesRealTraversals:
    def test_terminated_traversal_passes_on_the_terminal_branch(self, tmp_path):
        result = run_guard(
            "python -c \"from thalamus.substrate.reader import x; "
            "print(g.V().has_label('Session').count().next())\"",
            tmp_path,
        )
        assert result.returncode == 0
        assert verdict_of(tmp_path) == ("pass", "terminal")

    def test_commit_message_describing_the_guard_is_prose_not_code(self, tmp_path):
        """A commit that documents this guard quotes `.V(` and names the
        import, so it clears the no-traversal gate — but `git commit` executes
        no python. Measured false positive on the v5 amendment itself."""
        result = run_guard(
            "git commit -m 'guard: no source step (.V( / .addV() means no "
            "traversal was built; from thalamus.substrate import is not a query'",
            tmp_path,
        )
        assert result.returncode == 0
        assert verdict_of(tmp_path) == ("pass", "textedit")

    def test_text_command_quoting_traversal_syntax_stays_textedit(self, tmp_path):
        """A text tool may legitimately quote `.V(`, so it survives the
        no-traversal gate and must still be excused as code manipulation."""
        result = run_guard(
            "grep -rn 'from thalamus.substrate import\\|g.V(' src/",
            tmp_path,
        )
        assert result.returncode == 0
        assert verdict_of(tmp_path) == ("pass", "textedit")


class TestNoTraversalIsNotTheGuardsBusiness:
    """The v4 false positive: the trigger matches imports and connection setup,
    which are not traversals. Regression cases, each one a command that names a
    marker while building nothing lazy."""

    def test_importing_a_module_constant_is_not_a_traversal(self, tmp_path):
        """Verbatim shape of the command guard v4 blocked."""
        result = run_guard(
            "python -c \"from thalamus.substrate.snapshot import "
            "DEFAULT_SNAPSHOT_PATH as p; import os; print(os.path.getsize(p))\"",
            tmp_path,
        )
        assert result.returncode == 0
        assert verdict_of(tmp_path) == ("pass", "no-traversal")

    def test_house_writer_call_is_not_a_traversal(self, tmp_path):
        result = run_guard(
            "python -c \"from thalamus.substrate.writer import write_knowledge; "
            "write_knowledge(graph, batch)\"",
            tmp_path,
        )
        assert result.returncode == 0
        assert verdict_of(tmp_path) == ("pass", "no-traversal")

    def test_connection_setup_alone_is_not_a_traversal(self, tmp_path):
        result = run_guard(
            "python -c \"from gremlin_python.driver.driver_remote_connection "
            "import DriverRemoteConnection; print(DriverRemoteConnection)\"",
            tmp_path,
        )
        assert result.returncode == 0
        assert verdict_of(tmp_path) == ("pass", "no-traversal")


class TestScopeAndSchema:
    def test_command_without_markers_is_never_touched(self, tmp_path):
        result = run_guard("ls -la", tmp_path)
        assert result.returncode == 0
        assert events(tmp_path) == [], "a non-gremlin command must not log an event"

    def test_events_carry_the_current_guard_version(self, tmp_path):
        """The version keeps the event stream interpretable across amendments,
        so a branch added in v5 must not be read as a v4 record."""
        run_guard(
            "python -c \"from thalamus.substrate.snapshot import P; print(P)\"",
            tmp_path,
        )
        assert events(tmp_path)[0]["guard_version"] == 5


class TestAPayloadTheGuardCannotRead:
    """Past the `Bash` gate, an absent command is drift and not an empty call.

    This hook's matcher is `Bash`, and Claude Code does not raise a Bash event
    without `tool_input.command` — so a read that comes back empty means the payload
    is not the shape this guard was written against. It used to `exit 0` on that,
    which is indistinguishable from having looked and approved.
    """

    def _run_raw(self, stdin, home):
        return subprocess.run(
            [str(GUARD)], input=stdin, capture_output=True, text=True, timeout=30,
            env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        )

    def test_a_field_that_moved_blocks(self, tmp_path):
        result = self._run_raw(json.dumps({
            "tool_name": "Bash",
            "tool_input": {"shell_command": "g.V().has_label('Session')"},
            "session_id": "s1", "cwd": "/tmp"}), tmp_path)

        assert result.returncode == BLOCK_EXIT
        assert "no tool_input.command" in result.stderr
        assert "gremlin-guard.sh" in result.stderr

    def test_a_non_bash_tool_is_still_none_of_its_business(self, tmp_path):
        """The gate before the read, and the reason the rule is not general: on a
        matcher that is not `Bash` a call legitimately carries no command, and
        denying there would block every tool this guard was never wired to."""
        result = self._run_raw(json.dumps({
            "tool_name": "Read", "tool_input": {"file_path": "/tmp/x"},
            "session_id": "s1", "cwd": "/tmp"}), tmp_path)

        assert result.returncode == 0
