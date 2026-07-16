"""MCP server exposing graph memory recall tools.

**Scope is server-side, not a tool parameter.** docs/07 is explicit that "the model is
never trusted to self-limit its own retrieval scope", so the pinned expert comes from
THALAMUS_SCOPE — set by the session-start hook when the pin is resolved — and no tool
below accepts a scope argument. A model cannot widen its own view by asking nicely, and
`memorize` writes to the pinned scope regardless of what the extraction YAML claims.
"""

from __future__ import annotations

import logging
import os

import yaml
from fastmcp import FastMCP

from thalamus.substrate.reader import (
    recall,
    recall_by_artifact,
    recall_by_project,
    recall_open_threads,
    recall_recent,
    recall_thread,
)
from thalamus.substrate.schema import SessionGraph
from thalamus.contract.conformance import check_session, validate_connectivity
from thalamus.contract.manifest import available_scopes
from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.plane.mermaid import session_to_mermaid
from thalamus.substrate.writer import close_connection, connect, write_session

logger = logging.getLogger(__name__)

GRAPH_URL = os.environ.get("THALAMUS_GRAPH_URL", "ws://localhost:8182/gremlin")

# The session's pin. Resolved by the session-start hook, never by the model.
SCOPE = os.environ.get("THALAMUS_SCOPE", MAIN_SCOPE)

# Expert knowledge subgraphs recall may consult alongside the pinned scope's episodic
# memory. Server-side policy, same as SCOPE: derived from the expert manifests on
# disk (docs/08 — the literature consultant serves everything), never a tool
# parameter. Until M3 consultation tickets exist, every manifest-backed expert is
# consultable; the ticket protocol will narrow this to per-exchange grants.
KNOWLEDGE_SCOPES = [s for s in available_scopes() if s != SCOPE]

mcp = FastMCP("thalamus")


@mcp.tool
def memory_recall(query: str, limit: int = 5) -> str:
    """Search memory for relevant past sessions using natural language.
    Returns summaries of past coding sessions that match the query, plus any
    matching expert knowledge claims (quoted, cited, tier-labelled).
    """
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        results = recall(g, query, limit, SCOPE, knowledge_scopes=KNOWLEDGE_SCOPES)
        return _format_results(results)
    finally:
        _close(g)


@mcp.tool
def memory_recall_by_artifact(identifier: str, limit: int = 5) -> str:
    """Find past sessions that touched a specific file, class, module, or dependency.
    Use when you know the specific artifact you want context about.
    """
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        results = recall_by_artifact(g, identifier, limit, SCOPE)
        return _format_results(results)
    finally:
        _close(g)


@mcp.tool
def memory_recall_by_project(project: str, limit: int = 5) -> str:
    """Find recent sessions for a specific project/repository.
    Use when starting work on a project to get recent context.
    """
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        results = recall_by_project(g, project, limit, SCOPE)
        return _format_results(results)
    finally:
        _close(g)


@mcp.tool
def memory_recall_recent(limit: int = 5) -> str:
    """Return the most recent coding sessions from memory."""
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        results = recall_recent(g, limit, SCOPE)
        return _format_results(results)
    finally:
        _close(g)


@mcp.tool
def memory_open_threads(project: str = "", limit: int = 10) -> str:
    """Return open and in-progress threads for a project.
    Threads are active continuation points — unfinished work, next steps, and open questions.
    Use at session start to see what needs attention.
    """
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        results = recall_open_threads(g, project or None, limit, SCOPE)
        if not results:
            return "No open threads found."
        return "\n\n---\n\n".join(r.format() for r in results)
    finally:
        _close(g)


@mcp.tool
def memory_thread(thread_id: str) -> str:
    """Get details on a specific thread by its ID.
    Use to drill into a particular thread for full context.
    """
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        result = recall_thread(g, thread_id, SCOPE)
        if not result:
            return f"Thread `{thread_id}` not found."
        return result.format()
    finally:
        _close(g)


@mcp.tool
def memory_visualize(session_yaml: str) -> str:
    """Generate a Mermaid diagram from a session extraction for visual verification.
    Pass the output to Excalidraw create_from_mermaid to render the graph.
    Orphan nodes (no edges) are automatically pruned. Connectivity issues are reported.
    """
    try:
        data = yaml.safe_load(session_yaml)
    except yaml.YAMLError as e:
        return f"Invalid YAML: {e}"

    try:
        session = SessionGraph(**data)
    except Exception as e:
        return f"Schema validation failed: {e}"

    issues = validate_connectivity(session)
    mermaid = session_to_mermaid(session)

    if issues:
        warning = "CONNECTIVITY ISSUES (auto-pruned from diagram):\n"
        warning += "\n".join(f"  - {issue}" for issue in issues)
        warning += "\n\nFix these in the YAML before calling memorize.\n\n"
        return warning + mermaid

    return mermaid


@mcp.tool
def memorize(session_yaml: str) -> str:
    """Store a session extraction into graph memory.
    Accepts YAML conforming to the SessionGraph schema.
    Rejects sessions with orphan nodes — every artifact must have at least one edge.
    """
    try:
        data = yaml.safe_load(session_yaml)
    except yaml.YAMLError as e:
        return f"Invalid YAML: {e}"

    try:
        session = SessionGraph(**data)
    except Exception as e:
        return f"Schema validation failed: {e}"

    # The pin wins over whatever the extraction claims. Scope is not the model's to choose.
    session = session.model_copy(update={"scope": SCOPE})

    issues = check_session(session)
    if issues:
        msg = "REJECTED — the subgraph does not satisfy the federation contract:\n"
        msg += "\n".join(f"  - {issue}" for issue in issues)
        msg += "\n\nRemove orphan artifacts or add them to a decision/problem/solution/thread."
        return msg

    g = _connect()
    if isinstance(g, str):
        return g
    try:
        write_session(g, session)
        count = 1 + len(session.artifacts) + len(session.claims()) + len(session.threads)
        return (
            f"Memorized session `{session.session_id}` into scope `{SCOPE}` "
            f"({count} nodes written)"
        )
    except Exception as e:
        logger.exception("Failed to write session %s", session.session_id)
        return (
            f"Write failed: {e}\n"
            "Set THALAMUS_LOG_LEVEL=DEBUG and restart the MCP server for "
            "Gremlin bytecode and server stack traces."
        )
    finally:
        _close(g)


def _connect():
    try:
        return connect(GRAPH_URL)
    except Exception as e:
        return f"Failed to connect to graph at {GRAPH_URL}: {e}"


def _close(g):
    try:
        close_connection(g)
    except Exception as e:
        logger.warning("Failed to close Gremlin connection: %s", e)


def _format_results(results) -> str:
    if not results:
        return "No matching memories found."
    return "\n\n---\n\n".join(r.format() for r in results)


def main():
    log_level = os.environ.get("THALAMUS_LOG_LEVEL", "WARNING").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
