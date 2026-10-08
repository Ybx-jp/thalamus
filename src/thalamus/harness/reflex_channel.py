"""The agentic plan's channel — which model serves a job, and the cloud channel's loop.

The plan (`harness/agentic.py`) runs on one of two channels, named after the
`agents.AGENT_CLIS` row that reaches the model. `claude`, the default, runs each job as
one `claude -p` with Haiku; `local` drives `ghoul` through ollama's `/api/chat`
(`extraction.run_tool_loop`). `THALAMUS_REFLEX_CHANNEL` picks one and
`THALAMUS_REFLEX_MODEL` names the model on it — any name the channel's CLI takes; with
none, `claude` gets `haiku` and `local` the server's own (`THALAMUS_LOCAL_MODEL`).

The local model serves one request at a time, so the local channel's worker takes a
global lock and runs every job in turn. The claude channel does not share a slot: every
trigger starts a worker, and the only limit is the queue's own, one job in flight per
`(session, agent)` key (`reflex_worker.claim_next`).

On the claude channel a job is one `claude -p` driving the same vocabulary the local
loop offers. The vocabulary reaches it as an MCP server, `thalamus reflex --job-tools`,
which `claude` spawns from `--mcp-config` and which only relays: each call crosses a
Unix socket back to the worker, which runs it on the job it holds — the same handles,
caps and stop log as the local loop, from the same `execute`. The `stop` call is the
answer; the worker replies to it, lets `claude` finish its turn, and reads the run's
figures from the JSON envelope. Everything about that `claude` but four settings is the
operator's own (`command`).
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from thalamus.harness.agents import (
    LOCAL_DEFAULT_MODEL,
    SANDBOX_TMP_PREFIX,
    AgentCLI,
    cli_for,
    sandbox_env,
)
from thalamus.harness.extraction import ExtractionError, StopLoop

CHANNEL_ENV = "THALAMUS_REFLEX_CHANNEL"
MODEL_ENV = "THALAMUS_REFLEX_MODEL"
# Each channel's model when `MODEL_ENV` names none.
CHANNELS = {
    # The default: Haiku through `claude -p`, jobs side by side, one in flight per
    # agent; `local` runs them one at a time under the worker's global lock
    # (A0222, cites-as-live).
    "claude": "haiku",
    "local": LOCAL_DEFAULT_MODEL,
}
DEFAULT_CHANNEL = "claude"

# The MCP server's name in `--mcp-config`, and so the prefix of every vocabulary tool
# as `claude` names it.
SERVER = "reflex"
DENIED_TOOLS = ("Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch")

# What the vocabulary's `stop` answers: the job is over, and one more turn is all the
# run needs to end.
STOPPED = "Stopped. The records you kept are what the agent will be shown; reply done."
# How long a `claude` that has called `stop` gets to finish its turn and print its
# envelope, inside the job's deadline, before it is ended without one.
STOP_GRACE_SECONDS = 15.0
# How often the worker asks whether the session is still live while `claude` thinks.
ALIVE_EVERY_SECONDS = 5.0
POLL_SECONDS = 0.2

# What the claude channel adds to the plan's prompt. Claude Code's own system prompt
# stays first; this tells it where its answer goes.
CHANNEL_PROMPT = (
    "\n\nYou are running headless as a background retriever. The `stop` tool is your "
    "answer: the records it keeps and its note are all that reaches the agent, and "
    "nothing you write outside it does. You may read files to understand the failure, "
    "but you cannot change them and you need not."
)


class UnknownChannel(ValueError):
    pass


def channel() -> str:
    value = os.environ.get(CHANNEL_ENV, "").strip() or DEFAULT_CHANNEL
    if value not in CHANNELS:
        raise UnknownChannel(
            f"{CHANNEL_ENV}={value!r} is not a reflex channel; "
            f"known: {', '.join(sorted(CHANNELS))}"
        )
    return value


def resolve(model: str = "") -> tuple[AgentCLI, str]:
    """The channel's CLI row and the model to ask it for."""
    name = channel()
    return cli_for(name), model or os.environ.get(MODEL_ENV, "").strip() or CHANNELS[name]


def concurrent() -> bool:
    """Whether jobs run side by side: true on every channel but the local one."""
    try:
        return channel() != "local"
    except UnknownChannel:
        return False


def searcher(cli: AgentCLI, model: str) -> str:
    """Who chose a digest's records, as its envelope names them to the agent."""
    if cli.transport == "subprocess":
        return f"a model ({model}, through {cli.display} -p)"
    return "a local model"


def thalamus_argv() -> list[str]:
    """The `thalamus` this process runs as, to start another of it."""
    binary = Path(sys.executable).parent / "thalamus"
    return [str(binary) if binary.exists() else "thalamus"]


@dataclass
class ClaudeLoop:
    # stop_tool | no_tool_calls | max_turns | deadline | session_end
    stopped: str
    # The run's own figures from its JSON envelope; empty when it was ended before
    # printing one.
    figures: dict = field(default_factory=dict)


def command(cli: AgentCLI, model: str, workdir: Path, *, system: str,
            max_turns: int) -> list[str]:
    """The job's `claude -p`, which is the operator's own Claude Code but for four settings.

    Settings, model aliases, MCP servers, hooks and permission mode load as they would
    for any `claude -p` run without `--bare` (A0220, cites-as-live), and this passes
    nothing that replaces them. What it fixes, each for a reason a setting cannot
    override (A0223, cites-as-live):

    - `THALAMUS_SANDBOX`, set by `run_loop` and inherited by every hook the run fires
      (A0192, cites-as-live), so each Thalamus hook declines: a reflex job is not a
      session to distil and does not fire the reflex.
    - `--no-session-persistence`, so the run leaves no transcript for a sweep to read
      (A0219, cites-as-live).
    - The vocabulary allowed by name, `mcp__reflex__*`: in a `-p` run a call that would
      prompt is denied, and the vocabulary is the job (A0221, cites-as-live).
    - `DENIED_TOOLS` denied by name, which holds in every permission mode. The job runs
      beside the agent it serves, in that agent's working directory, unseen: an edit
      there is a concurrent write into someone else's work, and a fetched page in its
      note would be web content delivered into the agent's context without the trust
      floor the transcript path enforces.
    """
    config = {"mcpServers": {SERVER: {
        "type": "stdio",
        "command": thalamus_argv()[0],
        "args": ["reflex", "--job-tools", str(workdir)],
    }}}
    return [
        *cli.argv(model),
        "--no-session-persistence",
        "--max-turns", str(max_turns),
        "--mcp-config", json.dumps(config),
        "--allowedTools", f"mcp__{SERVER}__*",
        "--disallowedTools", ",".join(DENIED_TOOLS),
        "--append-system-prompt", system + CHANNEL_PROMPT,
    ]


def _workdir() -> Path:
    # A Unix socket path is capped near 108 bytes, and a harness's TMPDIR can be most
    # of that on its own.
    base = Path(tempfile.gettempdir())
    if len(str(base)) > 60:
        base = Path("/tmp")
    return Path(tempfile.mkdtemp(prefix=SANDBOX_TMP_PREFIX, dir=base))


def run_loop(
    cli: AgentCLI,
    model: str,
    tools: list[dict],
    *,
    system: str,
    prompt: str,
    execute: Callable[[str, dict], str],
    deadline: float,
    max_turns: int,
    alive: Callable[[], bool] | None = None,
    cwd: str = "",
) -> ClaudeLoop:
    """Run one job as a `claude -p` whose vocabulary calls `execute` here.

    `tools` are the plan's function schemas, as the local loop takes them. `deadline`
    is a `time.monotonic()` instant; past it the run is ended. `cwd` is the agent's
    working directory, where `claude` runs when it still exists.
    """
    workdir = _workdir()
    (workdir / "tools.json").write_text(json.dumps(tools), encoding="utf-8")
    (workdir / "prompt").write_text(prompt, encoding="utf-8")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    proc = None
    stopped = ""
    try:
        listener.bind(str(workdir / "tools.sock"))
        listener.listen()
        listener.settimeout(POLL_SECONDS)
        with (workdir / "prompt").open("rb") as stdin, \
                (workdir / "stdout").open("wb") as stdout, \
                (workdir / "stderr").open("wb") as stderr:
            try:
                proc = subprocess.Popen(
                    command(cli, model, workdir, system=system, max_turns=max_turns),
                    stdin=stdin, stdout=stdout, stderr=stderr,
                    cwd=cwd if cwd and Path(cwd).is_dir() else workdir,
                    env=sandbox_env(), start_new_session=True,
                )
            except FileNotFoundError:
                raise ExtractionError(f"`{cli.binary}` is not on PATH") from None
        checked = time.monotonic()
        while proc.poll() is None:
            now = time.monotonic()
            if now >= deadline:
                stopped = "deadline"
                break
            if alive is not None and now - checked >= ALIVE_EVERY_SECONDS:
                checked = now
                if not alive():
                    stopped = "session_end"
                    break
            try:
                conn, _ = listener.accept()
            except TimeoutError:
                continue
            with conn:
                name, args = _request(conn)
                if alive is not None and not alive():
                    stopped = "session_end"
                    break
                try:
                    content = execute(name, args)
                except StopLoop:
                    content = STOPPED
                    stopped = "stop_tool"
                conn.sendall(json.dumps({"content": content}).encode() + b"\n")
            if stopped == "stop_tool":
                try:
                    proc.wait(timeout=max(0.0, min(STOP_GRACE_SECONDS,
                                                   deadline - time.monotonic())))
                except subprocess.TimeoutExpired:
                    pass
                break
        if proc.poll() is None:
            _end(proc)
        figures, subtype, error = _envelope(workdir)
        if stopped:
            return ClaudeLoop(stopped, figures)
        if subtype == "error_max_turns":
            return ClaudeLoop("max_turns", figures)
        if error or proc.returncode:
            tail = (workdir / "stderr").read_text(errors="replace")[-300:]
            raise ExtractionError(
                f"`{cli.binary} -p` exited {proc.returncode}: {error or tail or 'no output'}"
            )
        return ClaudeLoop("no_tool_calls", figures)
    finally:
        if proc is not None and proc.poll() is None:
            _end(proc)
        listener.close()
        shutil.rmtree(workdir, ignore_errors=True)


def _request(conn: socket.socket) -> tuple[str, dict]:
    conn.settimeout(10.0)
    data = b""
    while not data.endswith(b"\n"):
        chunk = conn.recv(65536)
        if not chunk:
            break
        data += chunk
    try:
        request = json.loads(data)
    except json.JSONDecodeError:
        return "", {}
    if not isinstance(request, dict):
        return "", {}
    args = request.get("args")
    return str(request.get("name") or ""), args if isinstance(args, dict) else {}


def _end(proc: subprocess.Popen) -> None:
    """End `claude` and whatever it started — the relay among them."""
    for sig, wait in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 3.0)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def _envelope(workdir: Path) -> tuple[dict, str, str]:
    """The run's figures, its subtype, and its error text when it reports one."""
    try:
        data = json.loads((workdir / "stdout").read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}, "", ""
    if not isinstance(data, dict):
        return {}, "", ""
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    figures = {
        "num_turns": data.get("num_turns"),
        "duration_ms": data.get("duration_ms"),
        "duration_api_ms": data.get("duration_api_ms"),
        "cost_usd": data.get("total_cost_usd"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_tokens": usage.get("cache_read_input_tokens"),
        "models": sorted(data.get("modelUsage") or {}),
        # The tools the run asked for and was refused — `DENIED_TOOLS` among them.
        "denied": [str(d.get("tool_name") or "") for d in data.get("permission_denials") or []
                   if isinstance(d, dict)],
        # The run's own id, which no transcript or hook record should carry.
        "session_id": data.get("session_id"),
    }
    subtype = str(data.get("subtype") or "")
    error = str(data.get("result") or data.get("errors") or "") if data.get("is_error") else ""
    return figures, subtype, error


def serve_tools(workdir: Path) -> None:
    """The MCP server `claude` starts, on stdio."""
    tool_server(workdir).run(show_banner=False)


def tool_server(workdir: Path):
    """The vocabulary in `workdir/tools.json` as a FastMCP server, each call relayed.

    Holds no job state. A call it cannot relay — the worker gone, the socket closed —
    answers as an error the model reads, and the worker's own clock ends the run.
    """
    from fastmcp import FastMCP
    from fastmcp.tools import Tool, ToolResult

    socket_path = str(workdir / "tools.sock")

    def relay(name: str, arguments: dict) -> str:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.connect(socket_path)
            conn.sendall(json.dumps({"name": name, "args": arguments}).encode() + b"\n")
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
        return str(json.loads(data).get("content") or "")

    class Relayed(Tool):
        async def run(self, arguments):
            import asyncio

            try:
                text = await asyncio.to_thread(relay, self.name, dict(arguments or {}))
            except (OSError, json.JSONDecodeError, AttributeError) as exc:
                return ToolResult(content=f"the job is no longer running ({exc})",
                                  is_error=True)
            return ToolResult(content=text)

    server = FastMCP(SERVER)
    schemas = json.loads((workdir / "tools.json").read_text(encoding="utf-8"))
    for schema in schemas:
        function = schema["function"]
        server.add_tool(Relayed(
            name=function["name"], description=function.get("description", ""),
            parameters=function["parameters"],
        ))
    return server
