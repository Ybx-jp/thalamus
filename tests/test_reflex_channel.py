"""The agentic plan's channel: which model serves a job, and the claude channel's loop.

The loop is driven against a fake `claude` that speaks to the worker's socket the way
the relay does, so these tests reach no vendor and need no login. The relay itself is
driven in memory through FastMCP's client.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import socket
import sys
import threading
import time

import pytest

from thalamus.harness import agentic, reflex_channel
from thalamus.harness.agents import LOCAL_DEFAULT_MODEL, cli_for
from thalamus.harness.extraction import ExtractionError, StopLoop

FAKE_CLAUDE = """\
import json, os, socket, sys, time

argv = sys.argv[1:]
config = json.loads(argv[argv.index("--mcp-config") + 1])
workdir = config["mcpServers"]["reflex"]["args"][-1]
mode = os.environ.get("FAKE_MODE", "stop")
record = os.environ.get("FAKE_RECORD")
if record:
    with open(record, "w") as handle:
        json.dump({"argv": argv, "cwd": os.getcwd(),
                   "sandbox": os.environ.get("THALAMUS_SANDBOX"),
                   "stdin": sys.stdin.read()}, handle)


def call(name, args):
    with socket.socket(socket.AF_UNIX) as conn:
        conn.connect(os.path.join(workdir, "tools.sock"))
        conn.sendall(json.dumps({"name": name, "args": args}).encode() + b"\\n")
        data = b""
        while not data.endswith(b"\\n"):
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
    return json.loads(data)["content"]


def result(**fields):
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                      **fields}))


if mode == "hang":
    time.sleep(60)
if mode == "error":
    result(is_error=True, result="Not logged in")
    sys.exit(1)
if mode == "max_turns":
    result(subtype="error_max_turns", is_error=True, num_turns=12)
    sys.exit(1)
shown = call("lexical_by_kind", {"missing": "x", "query": "budget ceiling",
                                 "kind": "session"})
if mode == "answer":
    result(result=shown, num_turns=2)
    sys.exit(0)
call("stop", {"keep": ["R1.1"], "reason": "r"})
result(result="done", num_turns=3, duration_ms=10, duration_api_ms=8,
       total_cost_usd=0.001,
       usage={"input_tokens": 5, "output_tokens": 7, "cache_read_input_tokens": 100},
       modelUsage={"claude-haiku-5-5": {}}, permission_denials=[{"tool_name": "Bash"}],
       session_id="fake")
"""


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    path = tmp_path / "claude"
    path.write_text(f"#!{sys.executable}\n{FAKE_CLAUDE}")
    path.chmod(0o755)
    record = tmp_path / "record.json"
    monkeypatch.setenv("FAKE_RECORD", str(record))
    cli = dataclasses.replace(cli_for("claude"), binary=str(path))
    return cli, record


def _execute(calls):
    def execute(name, args):
        calls.append((name, args))
        if name == "stop":
            raise StopLoop
        return "R1.1 · session · tier 1 · 2026-09-12 · The reflex budget was set at 24k."
    return execute


def _loop(cli, calls, *, seconds=30.0, alive=None, cwd=""):
    return reflex_channel.run_loop(
        cli, "haiku", agentic.tool_schemas(), system="SYSTEM", prompt="the failure",
        execute=_execute(calls), deadline=time.monotonic() + seconds, max_turns=12,
        alive=alive, cwd=cwd,
    )


# --- choosing the channel ---------------------------------------------------------------


def test_the_default_channel_is_claude_with_haiku_and_runs_side_by_side():
    cli, model = reflex_channel.resolve()
    assert (cli.harness, model) == ("claude", "haiku")
    assert reflex_channel.concurrent()


def test_a_named_model_is_passed_through_whatever_it_is(monkeypatch):
    monkeypatch.setenv(reflex_channel.MODEL_ENV, "claude-sonnet-5-5")
    assert reflex_channel.resolve()[1] == "claude-sonnet-5-5"
    assert reflex_channel.resolve("opus")[1] == "opus"


def test_the_local_channel_is_the_servers_model_and_runs_alone(monkeypatch):
    monkeypatch.setenv(reflex_channel.CHANNEL_ENV, "local")
    cli, model = reflex_channel.resolve()
    assert (cli.harness, model) == ("local", LOCAL_DEFAULT_MODEL)
    assert not reflex_channel.concurrent()


def test_an_unknown_channel_is_refused_by_name(monkeypatch):
    monkeypatch.setenv(reflex_channel.CHANNEL_ENV, "gemini")
    with pytest.raises(reflex_channel.UnknownChannel, match="gemini"):
        reflex_channel.resolve()
    assert not reflex_channel.concurrent()


def test_the_command_fixes_the_sandbox_and_leaves_the_rest_to_claude(tmp_path):
    argv = reflex_channel.command(cli_for("claude"), "haiku", tmp_path, system="SYS",
                                  max_turns=12)
    assert argv[:6] == ["claude", "-p", "--model", "haiku", "--output-format", "json"]
    assert "--no-session-persistence" in argv
    assert argv[argv.index("--allowedTools") + 1] == "mcp__reflex__*"
    denied = argv[argv.index("--disallowedTools") + 1].split(",")
    assert {"Bash", "Edit", "Write", "WebFetch"} <= set(denied)
    assert argv[argv.index("--append-system-prompt") + 1].startswith("SYS")
    server = json.loads(argv[argv.index("--mcp-config") + 1])["mcpServers"]["reflex"]
    assert server["args"] == ["reflex", "--job-tools", str(tmp_path)]
    # Nothing that would replace the operator's own configuration.
    for flag in ("--bare", "--strict-mcp-config", "--setting-sources", "--tools",
                 "--system-prompt", "--permission-mode"):
        assert flag not in argv


# --- the loop ---------------------------------------------------------------------------


def test_a_run_relays_each_call_and_ends_on_the_stop(fake_claude, tmp_path):
    cli, record = fake_claude
    calls = []
    ran = _loop(cli, calls, cwd=str(tmp_path))
    assert ran.stopped == "stop_tool"
    assert [name for name, _ in calls] == ["lexical_by_kind", "stop"]
    assert calls[0][1]["query"] == "budget ceiling"
    assert ran.figures["num_turns"] == 3 and ran.figures["cost_usd"] == 0.001
    assert ran.figures["models"] == ["claude-haiku-5-5"]
    assert ran.figures["denied"] == ["Bash"]
    seen = json.loads(record.read_text())
    assert seen["sandbox"] == "1"
    assert seen["cwd"] == str(tmp_path)
    assert seen["stdin"] == "the failure"


def test_a_run_whose_cwd_is_gone_runs_in_its_own_directory(fake_claude, tmp_path):
    cli, record = fake_claude
    _loop(cli, [], cwd=str(tmp_path / "gone"))
    assert json.loads(record.read_text())["cwd"] != str(tmp_path / "gone")


def test_a_run_that_answers_without_stopping_is_no_tool_calls(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "answer")
    assert _loop(fake_claude[0], []).stopped == "no_tool_calls"


def test_a_run_its_turn_cap_ends_is_max_turns(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "max_turns")
    assert _loop(fake_claude[0], []).stopped == "max_turns"


def test_a_run_that_fails_raises_with_its_own_words(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "error")
    with pytest.raises(ExtractionError, match="Not logged in"):
        _loop(fake_claude[0], [])


def test_a_missing_binary_is_an_extraction_error(tmp_path):
    cli = dataclasses.replace(cli_for("claude"), binary=str(tmp_path / "nowhere"))
    with pytest.raises(ExtractionError, match="not on PATH"):
        _loop(cli, [])


def test_a_run_past_its_deadline_is_ended(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "hang")
    started = time.monotonic()
    assert _loop(fake_claude[0], [], seconds=1.0).stopped == "deadline"
    assert time.monotonic() - started < 10


def test_a_call_from_a_session_that_has_ended_runs_nothing(fake_claude):
    calls = []
    assert _loop(fake_claude[0], calls, alive=lambda: False).stopped == "session_end"
    assert calls == []


def test_pointwise_admission_is_refused_on_the_claude_channel(monkeypatch):
    monkeypatch.setenv(agentic.ADMISSION_ENV, "pointwise")
    with pytest.raises(ExtractionError, match="local channel only"):
        agentic.run(object(), cli=cli_for("claude"), model="haiku", anchors=[],
                    excerpt="", deadline=time.monotonic() + 1)


# --- the relay ----------------------------------------------------------------------------


def test_the_relay_offers_the_vocabulary_and_forwards_each_call(tmp_path):
    from fastmcp import Client

    (tmp_path / "tools.json").write_text(json.dumps(agentic.tool_schemas()))
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(tmp_path / "tools.sock"))
    listener.listen()
    received = []

    def worker():
        conn, _ = listener.accept()
        with conn:
            received.append(json.loads(conn.makefile().readline()))
            conn.sendall(json.dumps({"content": "R1.1 · a row"}).encode() + b"\n")

    thread = threading.Thread(target=worker)
    thread.start()

    async def drive():
        async with Client(reflex_channel.tool_server(tmp_path)) as client:
            names = {tool.name for tool in await client.list_tools()}
            answer = await client.call_tool("lexical_by_kind", {
                "missing": "x", "query": "budget", "kind": "session"})
            return names, answer

    names, answer = asyncio.run(drive())
    thread.join(5)
    listener.close()
    assert names == set(agentic.TOOLS) | {"stop"}
    assert received == [{"name": "lexical_by_kind",
                         "args": {"missing": "x", "query": "budget", "kind": "session"}}]
    assert answer.content[0].text == "R1.1 · a row"


def test_a_relay_whose_worker_is_gone_answers_with_an_error(tmp_path):
    from fastmcp import Client

    (tmp_path / "tools.json").write_text(json.dumps(agentic.tool_schemas()))

    async def drive():
        async with Client(reflex_channel.tool_server(tmp_path)) as client:
            return await client.call_tool("stop", {"keep": [], "reason": "r"},
                                          raise_on_error=False)

    answer = asyncio.run(drive())
    assert answer.is_error
    assert "no longer running" in answer.content[0].text
