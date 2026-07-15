"""Read the retrieval-trace tap into typed events.

The PostToolUse hook (harness/hooks/claude-code/post-tool-use.sh) appends one JSON line
per thalamus tool call to ~/.thalamus/traces/<YYYY-MM>.jsonl. The hook is a tap, not a
judge — it records the call verbatim and nothing else. This module is where raw lines
become retrieval events: which session asked, what it asked, and which graph nodes came
back.

Node identity is recovered from the response text itself. The reader renders every
result's vertex ID inline (docs/09 G5), so the verbatim `tool_response` in the trace
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

logger = logging.getLogger(__name__)

TRACES_DIR = Path.home() / ".thalamus" / "traces"

# The tap matcher is mcp__thalamus__.*, so memorize/visualize calls land in the JSONL
# too. Only these read memory; only these are retrieval events.
RETRIEVAL_TOOLS = frozenset(
    {
        "memory_recall",
        "memory_recall_by_artifact",
        "memory_recall_by_project",
        "memory_recall_recent",
        "memory_open_threads",
        "memory_thread",
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
    r"^(No matching memories found\.|No open threads found\.|Thread `[^`]*` not found\.)$"
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
        for key in ("query", "identifier", "project", "thread_id"):
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

    def is_legacy(self) -> bool:
        """A non-empty response with no vertex IDs: recorded before node-level rendering."""
        return (
            bool(self.tool_response.strip())
            and not self.is_miss()
            and not self.returned_node_ids()
        )

    def scope_hint(self) -> str | None:
        """The scope encoded in the returned vertex IDs, if any came back."""
        for node_id in self.returned_node_ids():
            return node_id.split(":", 2)[1]
        return None


def load_events(base: Path | None = None) -> list[TraceEvent]:
    """Parse every monthly tap file into retrieval events, oldest first."""
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
                if event.tool in RETRIEVAL_TOOLS:
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

    return TraceEvent(
        ts=ts,
        session_id=session_id,
        cwd=record.get("cwd") or "",
        tool=tool,
        tool_input=tool_input if isinstance(tool_input, dict) else {},
        tool_response=tool_response if isinstance(tool_response, str) else "",
    )
