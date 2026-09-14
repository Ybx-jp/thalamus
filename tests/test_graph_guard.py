"""Graph-access guard decision tests.

Interfaces: src/thalamus/harness/hooks/claude-code/graph-guard.sh, driven live
(bash) with synthetic PreToolUse payloads.
Infrastructure: tmp_path as $HOME so the guard's event log is sandboxed; the
pin arrives by env and by payload `agent_type`, never from a live session. No
live graph — the guard decides on the command text and never connects.
Scope: the guard's *verdict*. The boundary it draws is that outside `main` the
graph is reached through the MCP tools, so the two halves that must both hold
are that an expert pin's inline connection is refused and that `main`'s is not:
"everything is refused" and "the boundary holds" are indistinguishable without
the second. False positives are the failure mode that matters — they teach
agents to route around the guard — so the text-command branch is pinned here
too.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

GUARD = (
    Path(__file__).resolve().parents[1]
    / "src" / "thalamus" / "harness" / "hooks" / "claude-code" / "graph-guard.sh"
)

BLOCK_EXIT = 2

CONNECT = (
    "python -c \"from thalamus.substrate.writer import connect; "
    "g = connect(); print(g.V().has_label('Session').count().next())\""
)


def run_guard(command, home, *, scope="main", agent_type="", tool_name="Bash",
              cwd="/home/user/code/thalamus"):
    payload = {
        "tool_name": tool_name,
        "tool_input": {"command": command},
        "session_id": "graph-guard-sess-1",
        "cwd": cwd,
    }
    if agent_type:
        payload["agent_type"] = agent_type
    return subprocess.run(
        [str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin",
             "THALAMUS_SCOPE": scope},
        timeout=30,
        check=False,
    )


def events(home):
    directory = Path(home) / ".thalamus" / "guards"
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.jsonl")):
        out += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return out


def only_event(home):
    recorded = events(home)
    assert len(recorded) == 1, f"expected exactly one event, got {recorded}"
    return recorded[0]


class TestAnExpertPinDoesNotOpenItsOwnConnection:
    """The boundary: `connect()` applies no scope filter, so outside `main` the
    graph is reached through the tools that do."""

    def test_the_documented_connect_idiom_is_blocked(self, tmp_path):
        result = run_guard(CONNECT, tmp_path, scope="literature")
        assert result.returncode == BLOCK_EXIT
        assert "Blocked:" in result.stderr
        assert "memory_recall" in result.stderr, "a block must name what to use instead"
        event = only_event(tmp_path)
        assert (event["verdict"], event["branch"]) == ("block", "direct")
        assert event["scope"] == "literature"

    def test_the_gremlin_client_reached_without_the_house_module_is_blocked(self, tmp_path):
        result = run_guard(
            "python -c \"from gremlin_python.driver.driver_remote_connection import "
            "DriverRemoteConnection; c = DriverRemoteConnection('ws://x/gremlin', 'g')\"",
            tmp_path,
            scope="qe",
        )
        assert result.returncode == BLOCK_EXIT
        assert only_event(tmp_path)["branch"] == "direct"

    def test_the_endpoint_reached_with_no_python_at_all_is_blocked(self, tmp_path):
        result = run_guard("curl -s http://localhost:8182/gremlin", tmp_path, scope="qe")
        assert result.returncode == BLOCK_EXIT
        assert only_event(tmp_path)["branch"] == "direct"

    def test_a_subagent_is_gated_on_its_own_pin_not_its_launchers(self, tmp_path):
        """The payload's `agent_type` outranks the launcher's env, so a `main`
        session spawning an expert does not lend it `main`'s reach."""
        result = run_guard(CONNECT, tmp_path, scope="main", agent_type="thalamus-qe")
        assert result.returncode == BLOCK_EXIT
        assert only_event(tmp_path)["scope"] == "qe"

    def test_a_text_command_prefix_does_not_launder_the_connection(self, tmp_path):
        """The pass branch asks whether anything is invoked that could open a
        socket, not whether the command looks like text — otherwise `ls;` in
        front of the traversal is the whole route around."""
        result = run_guard(f"ls src/thalamus; {CONNECT}", tmp_path, scope="qe")
        assert result.returncode == BLOCK_EXIT
        assert only_event(tmp_path)["branch"] == "direct"

    def test_a_script_file_is_read_rather_than_trusted(self, tmp_path):
        """Writing the traversal to a file and running it is two ordinary calls,
        and was a live bypass: the heredoc passes as text and the run names no
        marker. The file a command names is read."""
        script = tmp_path / "q.py"
        script.write_text(
            "from thalamus.substrate.writer import connect\n"
            "print(connect().V().count().next())\n"
        )
        result = run_guard(f"python {script}", tmp_path, scope="qe")
        assert result.returncode == BLOCK_EXIT
        assert only_event(tmp_path)["branch"] == "script"

    def test_a_relative_script_resolves_against_the_calls_cwd(self, tmp_path):
        (tmp_path / "q.py").write_text("import gremlin_python\n")
        result = run_guard("python q.py", tmp_path, scope="qe", cwd=str(tmp_path))
        assert result.returncode == BLOCK_EXIT
        assert only_event(tmp_path)["branch"] == "script"

    def test_an_environment_prefix_is_still_an_invocation(self, tmp_path):
        result = run_guard(f"THALAMUS_SCOPE=main {CONNECT}", tmp_path, scope="qe")
        assert result.returncode == BLOCK_EXIT
        assert only_event(tmp_path)["branch"] == "direct"

    def test_a_house_entrypoint_does_not_launder_a_connection_beside_it(self, tmp_path):
        """The entrypoint pass strikes the entrypoint out and judges what is left,
        rather than returning on the first thing it recognises."""
        result = run_guard(f"{CONNECT}; thalamus status", tmp_path, scope="qe")
        assert result.returncode == BLOCK_EXIT
        assert only_event(tmp_path)["branch"] == "direct"

    def test_an_unpinned_subagent_falls_through_to_the_launchers_pin(self, tmp_path):
        """`general-purpose` matches no manifest, so it inherits the pin it was
        spawned under — otherwise "spawn a general-purpose subagent to run the
        traversal" is a one-line route around the boundary."""
        result = run_guard(
            CONNECT, tmp_path, scope="literature", agent_type="general-purpose",
        )
        assert result.returncode == BLOCK_EXIT
        assert only_event(tmp_path)["scope"] == "literature"


class TestTheDiscriminationControls:
    """Without these the file asserts that the guard refuses things, not that it
    draws the boundary it claims to."""

    def test_main_runs_the_same_command_unimpeded(self, tmp_path):
        result = run_guard(CONNECT, tmp_path, scope="main")
        assert result.returncode == 0
        assert result.stderr == ""
        assert only_event(tmp_path)["branch"] == "main"

    def test_an_unmarked_command_is_never_this_guards_business(self, tmp_path):
        result = run_guard("uv run pytest tests/test_uses.py -n 0", tmp_path, scope="qe")
        assert result.returncode == 0
        assert events(tmp_path) == [], (
            "the ledger records this boundary's decisions, not every Bash call"
        )

    def test_a_house_entrypoint_carrying_a_marker_passes(self, tmp_path):
        """A suite run and the CLI reach the graph on the session's behalf; each
        has its own confinement question and this guard does not answer it."""
        result = run_guard(
            "uv run pytest --pyargs thalamus.substrate -n 0", tmp_path, scope="qe",
        )
        assert result.returncode == 0
        assert only_event(tmp_path)["branch"] == "entrypoint"

    def test_the_suite_run_spelt_through_the_interpreter_passes(self, tmp_path):
        """`python -m pytest <file>` names a test file that imports the graph
        client, and a pin runs it as ordinary work."""
        (tmp_path / "test_writer.py").write_text(
            "from thalamus.substrate.writer import connect\n"
        )
        result = run_guard(
            f"python -m pytest {tmp_path / 'test_writer.py'} -n 0",
            tmp_path,
            scope="qe",
        )
        assert result.returncode == 0
        assert only_event(tmp_path)["branch"] == "entrypoint"

    def test_a_script_that_never_names_the_client_is_untouched(self, tmp_path):
        """The control for the file read: it is the file's content that decides,
        not the fact that a `.py` argument was named."""
        (tmp_path / "build.py").write_text("print('hello')\n")
        result = run_guard(f"python {tmp_path / 'build.py'}", tmp_path, scope="qe")
        assert result.returncode == 0
        assert events(tmp_path) == []

    def test_a_path_qualified_interpreter_is_still_an_invocation(self, tmp_path):
        result = run_guard(f".venv/bin/{CONNECT}", tmp_path, scope="qe")
        assert result.returncode == BLOCK_EXIT
        assert only_event(tmp_path)["branch"] == "direct"

    def test_a_non_bash_tool_is_untouched(self, tmp_path):
        result = run_guard(CONNECT, tmp_path, scope="qe", tool_name="Read")
        assert result.returncode == 0
        assert events(tmp_path) == []


class TestMarkersCarriedAsDataAreNotAConnection:
    """Reading, searching and committing code that names the graph client is how
    one works on it. Both other Bash guards tripped on exactly this."""

    def test_grepping_for_the_idiom_passes(self, tmp_path):
        result = run_guard(
            "grep -rn 'from thalamus.substrate.writer import connect' src/",
            tmp_path,
            scope="architect",
        )
        assert result.returncode == 0
        assert only_event(tmp_path)["branch"] == "textedit"

    def test_a_commit_message_naming_the_module_passes(self, tmp_path):
        result = run_guard(
            "git commit -m 'Confine thalamus.substrate reads to the MCP surface'",
            tmp_path,
            scope="architect",
        )
        assert result.returncode == 0
        assert only_event(tmp_path)["branch"] == "textedit"

    def test_a_commit_message_naming_the_interpreter_too_passes(self, tmp_path):
        """The anchor is what keeps prose out of the invocation branch: a message
        says `python` mid-sentence, never after a `;`."""
        result = run_guard(
            "git commit -m 'Block inline python that imports thalamus.substrate'",
            tmp_path,
            scope="architect",
        )
        assert result.returncode == 0
        assert only_event(tmp_path)["branch"] == "textedit"

    def test_reading_the_connecting_module_passes(self, tmp_path):
        result = run_guard(
            "sed -n '90,120p' src/thalamus/substrate/writer.py; "
            "echo 'thalamus.substrate read'",
            tmp_path,
            scope="architect",
        )
        assert result.returncode == 0
        assert only_event(tmp_path)["branch"] == "textedit"


class TestTheLedgerRowIsReadable:
    def test_rows_carry_the_guard_name_and_version(self, tmp_path):
        run_guard(CONNECT, tmp_path, scope="literature")
        event = only_event(tmp_path)
        assert event["guard"] == "graph-access"
        assert event["guard_version"] == 1
        assert event["tool"] == "Bash"
        assert event["command_hash"], "a row without a join key cannot be followed"
