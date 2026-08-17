"""Read the retrieval-trace tap into typed events.

The PostToolUse hook (harness/hooks/claude-code/post-tool-use.sh) appends one JSON line
per thalamus tool call to ~/.thalamus/traces/<YYYY-MM>.jsonl. The hook is a tap, not a
judge — it records the call verbatim and nothing else. This module is where raw lines
become retrieval events: which session asked, what it asked, and which graph nodes came
back.

Node identity is recovered from the response text itself. The reader renders every
result's vertex ID inline, so the verbatim `tool_response` in the trace
*contains* the node-level answer — the tap needs no schema of its own and never lags
the reader. A trace whose response carries no vertex IDs predates that rendering and is
reported as legacy rather than silently miscounted as a retrieval miss.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from thalamus.contract.ontology import CORE_NODES
from thalamus.substrate.query import backtick_vids

logger = logging.getLogger(__name__)

TRACES_DIR = Path.home() / ".thalamus" / "traces"

# The tap matcher is mcp__thalamus__.*, so consultation calls land in the JSONL too
# — as do `memorize` and `visualize` records retained from before those tools were
# retired.
# Only these read memory; only these are retrieval events. memory_query and
# bash_gremlin (the ad-hoc Bash tap, gremlin-tap.sh) are retrieval surfaces like
# any recall — one priced surface, not a parallel metric.
RETRIEVAL_TOOLS = frozenset(
    {
        "memory_recall",
        "memory_recall_by_artifact",
        "memory_recall_by_project",
        "memory_recall_recent",
        "memory_open_threads",
        "memory_open_problems",
        "memory_thread",
        "memory_query",
        # A ranked query over answered exchanges, so it is retrieval in the shape
        # the eval loop measures — unlike memory_consultations, which serves a
        # fixed list and rank-orders nothing. Whether pointing a session at a
        # settled design prevents rework is exactly a used-vs-ignored question.
        "memory_exchanges",
        "bash_gremlin",
    }
)

_TOOL_PREFIX = "mcp__thalamus__"

# Scoped vertex IDs as the reader renders them: backticked, `scope:<scope>:<prefix>:<local>`.
# The prefix alternation derives from the ontology, so a new node type is extractable the
# day it exists. Requiring the backticks keeps prose that merely resembles an ID out.
_SCOPED_PREFIXES = "|".join(
    sorted(re.escape(node.id_prefix) for node in CORE_NODES if node.scoped)
)
_VID_RE = re.compile(rf"`(scope:[^:`\s]+:(?:{_SCOPED_PREFIXES}):[^`]+)`")

# Every empty-result message the recall tools produce. A miss is a real event — "the
# graph had nothing" is exactly the signal that grades recall — so these are recorded
# with zero returned nodes rather than dropped.
_MISS_RE = re.compile(
    r"^(No matching memories found\.|No open threads found\.|Thread `[^`]*` not found\."
    r"|Query returned no results\.)$"
)

# memory_query's guard rejections and server-side failures (substrate/query.py).
# A rejected query is neither a miss ("the graph had nothing") nor a legacy line —
# it is its own event class, priced for its injection cost and counted by
# `thalamus eval gremlin`.
_REJECTED_RE = re.compile(r"^(Rejected:|Query (?:failed:|must be a traversal)|Query exceeds )")

# The Bash tap records on marker presence alone (the tap stays dumb), but marker
# traffic is dominated by non-queries — sed refactors, heredoc rewrites (8/8
# flagged archive commands were wrappers or text edits). Only commands that
# actually reach for a connection or a house retrieval wrapper are retrieval
# events; the rest would pollute the priced surface and the reuse arms
# (verification consultation 8f6ad2d6f4024b2c).
_BASH_QUERY_RE = re.compile(
    r"connect\(|with_remote\(|DriverRemoteConnection\(|Client\(|run_query\(|recall\("
)


@dataclass
class TraceEvent:
    """One memory-tool call, as the tap recorded it."""

    ts: datetime
    session_id: str
    cwd: str
    tool: str  # short name, e.g. "memory_recall"
    tool_input: dict = field(default_factory=dict)
    tool_response: str = ""
    # The pin the tap recorded ("the process is the pin"). Empty on lines
    # written before the hook carried it; sync validates it like any other hint.
    scope: str = ""
    # Which agent context made the call. A subagent's calls carry the harness's
    # agent id and type; the main loop's carry neither, so **empty means the session
    # itself called** (measured 2026-07-28 — a subagent shares its parent's
    # session_id, so this is the only field that separates them). `None` means the
    # tap line predates these fields, which is a different fact from "the main loop
    # called" and must never collapse into it.
    agent_id: str | None = None
    agent_type: str | None = None

    def trace_id(self) -> str:
        """Content-addressed identity, so re-syncing the tap converges instead of duplicating."""
        payload = json.dumps(
            {
                "session_id": self.session_id,
                "ts": self.ts.isoformat(),
                "tool": self.tool,
                "input": self.tool_input,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def query_text(self) -> str:
        """The human-readable question this retrieval asked — the Trace node's label."""
        for key in ("query", "identifier", "project", "thread_id", "command"):
            value = self.tool_input.get(key)
            if value:
                return f"{self.tool}: {value}"
        return self.tool

    def returned_node_ids(self) -> list[str]:
        """Vertex IDs of every node this retrieval put into context, in render order."""
        seen: dict[str, None] = {}
        for match in _VID_RE.findall(self.tool_response):
            seen.setdefault(match)
        return list(seen)

    def is_miss(self) -> bool:
        return bool(_MISS_RE.match(self.tool_response.strip()))

    def is_rejected(self) -> bool:
        """A memory_query the guard refused or the server failed — never reached data."""
        return bool(_REJECTED_RE.match(self.tool_response.strip()))

    def ticket(self) -> str:
        """The consultation ticket this call carried, if it ran under one.

        This is how a consultation gets attributed to its session: the MCP server
        cannot see its caller, but the tap records the tool input verbatim, so the
        ticket in a recall's input is the join key between the session and the
        Exchange vertex the ticket names.
        """
        value = self.tool_input.get("ticket")
        return value if isinstance(value, str) else ""

    def is_legacy(self) -> bool:
        """A non-empty response with no vertex IDs: recorded before node-level rendering.

        bash_gremlin traces are never legacy — raw gremlin output legitimately
        carries no vertex IDs (aggregates, counts) and the surface postdates
        node-level rendering entirely. Rejections are their own class.
        """
        return (
            self.tool != "bash_gremlin"
            and bool(self.tool_response.strip())
            and not self.is_miss()
            and not self.is_rejected()
            and not self.returned_node_ids()
        )

    def scope_hint(self) -> str | None:
        """The scope encoded in the returned vertex IDs, if any came back."""
        for node_id in self.returned_node_ids():
            return node_id.split(":", 2)[1]
        return None


def load_events(
    base: Path | None = None, tools: frozenset[str] | None = RETRIEVAL_TOOLS
) -> list[TraceEvent]:
    """Parse every monthly tap file into typed events, oldest first.

    Defaults to retrieval events only — the eval loop's layer 1. Pass `tools=None`
    to get every thalamus tool call in the tap (cost accounting wants consultation
    traffic too, not just reads).
    """
    directory = base or TRACES_DIR
    if not directory.is_dir():
        return []

    events: list[TraceEvent] = []
    for path in sorted(directory.glob("*.jsonl")):
        with path.open(errors="ignore") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                event = _parse_line(line)
                if event is None:
                    logger.warning("Unparseable trace line %s:%d", path.name, line_number)
                    continue
                if event.tool == "bash_gremlin" and not _BASH_QUERY_RE.search(
                    str(event.tool_input.get("command", ""))
                ):
                    continue
                if tools is None or event.tool in tools:
                    events.append(event)

    events.sort(key=lambda e: e.ts)
    return events


def _parse_line(line: str) -> TraceEvent | None:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict):
        return None

    try:
        ts = datetime.fromisoformat(str(record.get("ts", "")).replace("Z", "+00:00"))
    except ValueError:
        return None

    session_id = record.get("session_id") or ""
    tool_name = record.get("tool_name") or ""
    if not session_id or not tool_name:
        return None

    tool = tool_name.removeprefix(_TOOL_PREFIX)
    tool_input = record.get("tool_input")
    tool_response = record.get("tool_response")

    # Claude Code wraps MCP results as [{type: "text", text: ...}]; the hook may have
    # recorded either that structure or the bare string, depending on harness version.
    if isinstance(tool_response, list):
        tool_response = "\n".join(
            block.get("text", "")
            for block in tool_response
            if isinstance(block, dict) and block.get("type") == "text"
        )
    elif isinstance(tool_response, dict):
        tool_response = json.dumps(tool_response)

    # The thalamus MCP server itself returns {"result": <rendered text>}, and the tap
    # records that envelope (sometimes JSON-encoded into a string). Unwrap it so the
    # response the parser judges is the text the model actually saw — the anchored
    # miss patterns can never match inside an envelope. Measured, not hypothetical:
    # the first real miss in the tap (a pinned session with no open threads)
    # was misclassified as a legacy trace because of exactly this.
    if isinstance(tool_response, str) and tool_response.lstrip().startswith("{"):
        try:
            envelope = json.loads(tool_response)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(envelope, dict) and isinstance(envelope.get("result"), str):
                tool_response = envelope["result"]

    if not isinstance(tool_response, str):
        tool_response = ""
    if tool == "bash_gremlin":
        # Raw gremlin-python output carries bare vertex IDs; the RETURNS extractor
        # requires backticks. One rendering rule, applied at read time.
        tool_response = backtick_vids(tool_response)

    return TraceEvent(
        ts=ts,
        session_id=session_id,
        cwd=record.get("cwd") or "",
        tool=tool,
        tool_input=tool_input if isinstance(tool_input, dict) else {},
        tool_response=tool_response,
        scope=record.get("scope") or "",
        agent_id=record.get("agent_id"),
        agent_type=record.get("agent_type"),
    )
