"""Land the trace tap in the graph: Trace nodes, RETURNS edges, verdicts.

A trace can only land once its session has been distilled — the QUERIES edge needs the
Session vertex, and attribution needs the retained transcript behind it (Session
-[DERIVED_FROM]-> Source -> archive). Traces from sessions that have not been distilled
yet stay in the tap, reported as pending; the tap is append-only and sync is
content-addressed, so nothing is lost by waiting and nothing duplicates on re-run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from gremlin_python.process.graph_traversal import GraphTraversalSource, __
from gremlin_python.process.traversal import Order

from thalamus.archive import read_archived
from thalamus.contract.ontology import NODES_BY_LABEL, vid
from thalamus.eval.attribution import attribute, outputs_after
from thalamus.eval.traces import TraceEvent, load_events
from thalamus.substrate.schema import Provenance, Tier
from thalamus.substrate.writer import write_trace

logger = logging.getLogger(__name__)

_PREFIX_TO_LABEL = {node.id_prefix: node.label for node in NODES_BY_LABEL.values()}


@dataclass
class SyncOutcome:
    written: int = 0
    attributed: int = 0
    used: int = 0
    ignored: int = 0
    misses: int = 0
    legacy: int = 0
    dangling: int = 0
    pending: dict[str, int] = field(default_factory=dict)  # session_id -> trace count

    def summary(self) -> str:
        lines = [
            f"{self.written} traces landed "
            f"({self.misses} recall misses, {self.dangling} dangling result nodes)",
            f"{self.attributed} returned nodes attributed: "
            f"{self.used} used, {self.ignored} ignored",
        ]
        if self.legacy:
            lines.append(f"{self.legacy} legacy traces skipped (pre-node-level rendering)")
        if self.pending:
            total = sum(self.pending.values())
            names = ", ".join(sid[:8] for sid in sorted(self.pending))
            lines.append(
                f"{total} traces pending from {len(self.pending)} undistilled "
                f"session(s): {names}"
            )
        return "\n".join(lines)


def sync(
    g: GraphTraversalSource,
    *,
    traces_base: Path | None = None,
    write: bool = True,
) -> SyncOutcome:
    """Sync every landable trace from the tap into the graph."""
    outcome = SyncOutcome()

    by_session: dict[str, list[TraceEvent]] = {}
    for event in load_events(traces_base):
        by_session.setdefault(event.session_id, []).append(event)

    for session_id, events in sorted(by_session.items()):
        scope = _session_scope(g, session_id, events)
        if scope is None:
            outcome.pending[session_id] = len(events)
            continue

        session_vid = vid("Session", session_id, scope)
        transcript = _retained_transcript(g, session_vid)

        for event in events:
            _land_event(g, event, session_vid, scope, transcript, write, outcome)

    return outcome


def _land_event(
    g: GraphTraversalSource,
    event: TraceEvent,
    session_vid: str,
    scope: str,
    transcript: bytes | None,
    write: bool,
    outcome: SyncOutcome,
) -> None:
    if event.is_legacy():
        outcome.legacy += 1
        return

    returned_ids = event.returned_node_ids()

    # Only nodes still present in the graph can carry a RETURNS edge; the rest are
    # counted, because "retrieval showed the agent something that no longer exists"
    # is itself a finding.
    contents: dict[str, str] = {}
    for node_id in returned_ids:
        text = _node_text(g, node_id)
        if text is None:
            outcome.dangling += 1
        else:
            contents[node_id] = text

    returns: dict[str, dict[str, object] | None] = {nid: None for nid in contents}
    if transcript is not None and contents:
        verdicts = attribute(contents, outputs_after(transcript, event.ts))
        for verdict in verdicts:
            returns[verdict.node_id] = {
                "used": verdict.used,
                "evidence": verdict.evidence,
            }
            outcome.attributed += 1
            if verdict.used:
                outcome.used += 1
            else:
                outcome.ignored += 1

    if write:
        provenance = Provenance(
            tier=Tier.FIRST_PARTY,
            source=f"session:{event.session_id}",
            ingested_at=event.ts,
        )
        properties = {
            "query": event.query_text(),
            "tool": event.tool,
            "ts": event.ts.isoformat(),
            "session_id": event.session_id,
            "scope": scope,
            "returned_count": len(returned_ids),
            "tier": int(provenance.tier),
            "source": provenance.source,
            "ingested_at": provenance.ingested_at.isoformat(),
        }
        write_trace(g, vid("Trace", event.trace_id(), scope), properties, session_vid, returns)

    outcome.written += 1
    if event.is_miss():
        outcome.misses += 1


def _session_scope(
    g: GraphTraversalSource, session_id: str, events: list[TraceEvent]
) -> str | None:
    """Which scope this session's Session vertex lives in, or None if not yet distilled.

    The tap does not record the pin (the hook runs outside the MCP server's process),
    but the returned vertex IDs carry it, and failing that the distilled Session vertex
    is the authority.
    """
    for event in events:
        hint = event.scope_hint()
        if hint and _vertex_exists(g, vid("Session", session_id, hint)):
            return hint

    try:
        rows = (
            g.V()
            .has_label("Session")
            .has("session_id", session_id)
            .value_map("scope")
            .limit(1)
            .to_list()
        )
    except Exception:
        return None
    if not rows:
        return None
    scope = rows[0].get("scope")
    return scope[0] if isinstance(scope, list) and scope else None


def _retained_transcript(g: GraphTraversalSource, session_vid: str) -> bytes | None:
    """The archived transcript behind this session, for attribution.

    A session distilled while still open accumulates several Source snapshots (docs/10,
    lab/002); the SUPERSEDES lineage marks the current head, and attribution against
    anything else silently under-counts usage. The head is the snapshot with no
    incoming SUPERSEDES edge; ordering by ingested_at breaks ties on graphs written
    before the lineage existed, where every snapshot still looks like a head.
    """
    try:
        rows = (
            g.V(session_vid)
            .out("DERIVED_FROM")
            .has_label("Source")
            .not_(__.in_e("SUPERSEDES"))
            .order()
            .by("ingested_at", Order.desc)
            .value_map("content_hash")
            .limit(1)
            .to_list()
        )
    except Exception:
        return None
    if not rows:
        return None
    content_hash = rows[0].get("content_hash")
    if isinstance(content_hash, list):
        content_hash = content_hash[0] if content_hash else None
    if not content_hash:
        return None
    try:
        return read_archived(str(content_hash), suffix=".jsonl")
    except FileNotFoundError:
        logger.warning("Archive missing for %s (%s)", session_vid, content_hash)
        return None


def _node_text(g: GraphTraversalSource, node_id: str) -> str | None:
    """The retrievable text of a node — what attribution matches against."""
    try:
        rows = g.V(node_id).value_map("summary", "description", "title").limit(1).to_list()
    except Exception:
        return None
    if not rows:
        return None
    parts = []
    for key in ("title", "summary", "description"):
        value = rows[0].get(key)
        if isinstance(value, list) and value:
            parts.append(str(value[0]))
    return " ".join(parts)


def _vertex_exists(g: GraphTraversalSource, vertex_id: str) -> bool:
    try:
        return g.V(vertex_id).has_next()
    except Exception:
        return False
