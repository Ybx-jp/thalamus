"""MCP server exposing graph memory recall and consultation tools.

**Scope is server-side, not a tool parameter.** docs/07 is explicit that "the model is
never trusted to self-limit its own retrieval scope", so the pinned expert comes from
THALAMUS_SCOPE — set by the session-start hook when the pin is resolved — and no tool
below accepts a scope argument. A model cannot widen its own view by asking nicely, and
`memorize` writes to the pinned scope regardless of what the extraction YAML claims.

The one sanctioned way across a scope boundary is a **consultation ticket** (docs/02):
`consult_request` mints it server-side — which IS opening the exchange record in the
graph — and the recall tools accept it as the `ticket` parameter, resolving the granted
scope from the ticket's own Exchange vertex, never from model input. An invented or
burned ticket grants nothing.
"""

from __future__ import annotations

import logging
import os

import yaml
from fastmcp import FastMCP

from thalamus.harness import consultation
from thalamus.harness.extraction import apply_ingress_floor
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
# parameter. This ambient surface covers *knowledge* claims only; an expert's
# episodic memory is reachable solely through a consultation ticket, which grants
# the consulted scope per-exchange (docs/02).
KNOWLEDGE_SCOPES = [s for s in available_scopes() if s != SCOPE]

mcp = FastMCP("thalamus")


def _granted_scope(g, ticket: str) -> tuple[str, list[str]] | str:
    """Resolve which scope a call may read: the pin, or an open ticket's grant.

    Returns (scope, knowledge_scopes), or an error string. A ticket grants the
    consulted scope's episodic AND knowledge memory (the expert answers from its own
    whole memory) but no ambient view of *other* experts — grants are per-exchange,
    not transitive. Failing closed on a bad ticket matters: silently falling back to
    the pinned scope would let a stale ticket masquerade as a successful consultation.
    """
    if not ticket:
        return SCOPE, KNOWLEDGE_SCOPES
    granted = consultation.ticket_scope(g, ticket)
    if granted is None:
        return (
            f"Ticket `{ticket}` grants nothing: it was never minted or is already "
            "burned. Mint a consultation with consult_request."
        )
    return granted, []


@mcp.tool
def memory_recall(query: str, limit: int = 5, ticket: str = "") -> str:
    """Search memory for relevant past sessions using natural language.
    Returns summaries of past coding sessions that match the query, plus any
    matching expert knowledge claims (quoted, cited, tier-labelled).
    Under a consultation ticket, searches the consulted expert's memory instead.
    """
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        grant = _granted_scope(g, ticket)
        if isinstance(grant, str):
            return grant
        scope, knowledge_scopes = grant
        results = recall(g, query, limit, scope, knowledge_scopes=knowledge_scopes)
        return _format_results(results)
    finally:
        _close(g)


@mcp.tool
def memory_recall_by_artifact(identifier: str, limit: int = 5, ticket: str = "") -> str:
    """Find past sessions that touched a specific file, class, module, or dependency.
    Use when you know the specific artifact you want context about.
    """
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        grant = _granted_scope(g, ticket)
        if isinstance(grant, str):
            return grant
        results = recall_by_artifact(g, identifier, limit, grant[0])
        return _format_results(results)
    finally:
        _close(g)


@mcp.tool
def memory_recall_by_project(project: str, limit: int = 5, ticket: str = "") -> str:
    """Find recent sessions for a specific project/repository.
    Use when starting work on a project to get recent context.
    """
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        grant = _granted_scope(g, ticket)
        if isinstance(grant, str):
            return grant
        results = recall_by_project(g, project, limit, grant[0])
        return _format_results(results)
    finally:
        _close(g)


@mcp.tool
def memory_recall_recent(limit: int = 5, ticket: str = "") -> str:
    """Return the most recent coding sessions from memory."""
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        grant = _granted_scope(g, ticket)
        if isinstance(grant, str):
            return grant
        results = recall_recent(g, limit, grant[0])
        return _format_results(results)
    finally:
        _close(g)


@mcp.tool
def memory_open_threads(project: str = "", limit: int = 10, ticket: str = "") -> str:
    """Return open and in-progress threads for a project.
    Threads are active continuation points — unfinished work, next steps, and open questions.
    Use at session start to see what needs attention.
    """
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        grant = _granted_scope(g, ticket)
        if isinstance(grant, str):
            return grant
        results = recall_open_threads(g, project or None, limit, grant[0])
        if not results:
            return "No open threads found."
        return "\n\n---\n\n".join(r.format() for r in results)
    finally:
        _close(g)


@mcp.tool
def memory_thread(thread_id: str, ticket: str = "") -> str:
    """Get details on a specific thread by its ID.
    Use to drill into a particular thread for full context.
    """
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        grant = _granted_scope(g, ticket)
        if isinstance(grant, str):
            return grant
        result = recall_thread(g, thread_id, grant[0])
        if not result:
            return f"Thread `{thread_id}` not found."
        return result.format()
    finally:
        _close(g)


@mcp.tool
def consult_request(expert: str, question: str) -> str:
    """Consult another expert: mint a single-use consultation ticket, which IS opening
    the exchange record in the graph (docs/02 — the mint is the write).
    Returns the ticket, a server-assembled brief of the expert's own memory, and the
    protocol to follow: spawn a subagent voicing the expert, let it recall with the
    ticket, and have it close the exchange with consult_answer. The expert answers
    with data and citations, never directives.
    """
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        return consultation.consult_request(g, expert, question, SCOPE)
    finally:
        _close(g)


@mcp.tool
def consult_answer(ticket: str, answer: str) -> str:
    """Close a consultation exchange with the expert's answer — the only close path.
    Citations are validated server-side: every backticked vertex ID in the answer must
    resolve inside the consulted scope, and an answer with no valid citations is
    rejected (the ticket stays open). Success records the answer and burns the ticket.
    """
    g = _connect()
    if isinstance(g, str):
        return g
    try:
        return consultation.consult_answer(g, ticket, answer)
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

    # Honor external-origin marks with tier-2 provenance (docs/05). No transcript is
    # available live, so only explicit marks apply here; the mechanical echo floor
    # runs when SessionEnd re-extracts against the retained transcript.
    session = apply_ingress_floor(session, [])

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
