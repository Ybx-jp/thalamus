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
from thalamus.eval.rankers import RankerLedger
from thalamus.eval.traces import TraceEvent, load_events
from thalamus.harness.consultation import exchange_vid as _consultation_exchange_vid
from thalamus.substrate.reader import load_exchange
from thalamus.substrate.schema import Provenance, Tier
from thalamus.substrate.writer import _ensure_edge, close_exchange, write_trace

logger = logging.getLogger(__name__)

_PREFIX_TO_LABEL = {node.id_prefix: node.label for node in NODES_BY_LABEL.values()}


@dataclass
class SyncOutcome:
    written: int = 0
    attributed: int = 0
    used: int = 0
    ignored: int = 0
    empty_window: int = 0
    misses: int = 0
    rejected: int = 0
    legacy: int = 0
    dangling: int = 0
    pending: dict[str, int] = field(default_factory=dict)  # session_id -> trace count

    def summary(self) -> str:
        lines = [
            f"{self.written} traces landed "
            f"({self.misses} recall misses, {self.rejected} rejected/failed queries, "
            f"{self.dangling} dangling result nodes)",
            f"{self.attributed} returned nodes attributed: "
            f"{self.used} used, {self.ignored} ignored",
        ]
        if self.empty_window:
            lines.append(
                f"{self.empty_window} returned nodes unjudged — no agent output after "
                "the retrieval (not counted as ignored)"
            )
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
    rankers_base: Path | None = None,
    write: bool = True,
) -> SyncOutcome:
    """Sync every landable trace from the tap into the graph."""
    outcome = SyncOutcome()

    # Which ranker served each trace is a point-in-time question, answered from the
    # ledger the serving process wrote — never from the ranker installed right now,
    # which may be several dials removed from the one that produced these rows.
    ledger = RankerLedger.load(rankers_base)

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
            _land_event(g, event, session_vid, scope, transcript, write, outcome, ledger)

    return outcome


def _land_event(
    g: GraphTraversalSource,
    event: TraceEvent,
    session_vid: str,
    scope: str,
    transcript: bytes | None,
    write: bool,
    outcome: SyncOutcome,
    ledger: RankerLedger,
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
        outputs = outputs_after(transcript, event.ts)
        if not outputs.strip():
            # Nothing to judge against is not "ignored" — the two must never share a
            # number (lab/002). The edge records why it carries no verdict.
            outcome.empty_window += len(contents)
            for node_id in contents:
                returns[node_id] = {"unjudged": "no agent output after this retrieval"}
        else:
            for verdict in attribute(contents, outputs):
                returns[verdict.node_id] = {
                    "used": verdict.used,
                    "evidence": verdict.evidence,
                }
                outcome.attributed += 1
                if verdict.used:
                    outcome.used += 1
                else:
                    outcome.ignored += 1

    exchange_vid = _exchange_vid(g, event)

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
            # The rendered response *is* this retrieval's context-injection cost
            # (docs/04 layer 1b); recorded per trace so report can price verdicts.
            "injected_chars": len(event.tool_response),
            # Which ranking dials served this row. Traces older than the ledger read
            # `unknown` — the ranker of that era was never recorded, and borrowing the
            # oldest known fingerprint would invent the very attribution this exists
            # to make honest (lab/029).
            "ranker_config": ledger.at(event.ts),
            "tier": int(provenance.tier),
            "source": provenance.source,
            "ingested_at": provenance.ingested_at.isoformat(),
        }
        if exchange_vid:
            properties["exchange_id"] = exchange_vid
        write_trace(g, vid("Trace", event.trace_id(), scope), properties, session_vid, returns)
        if exchange_vid:
            # The CONSULTS edge lands here, not at mint time: the MCP server cannot
            # see its caller's session (lab/001), but the tap records the ticket, so
            # sync is where the consulting Session and its Exchange finally meet.
            _ensure_edge(g, session_vid, exchange_vid, "CONSULTS")
            _stamp_answering_context(g, exchange_vid, event)

    outcome.written += 1
    if event.is_miss():
        outcome.misses += 1
    if event.is_rejected():
        outcome.rejected += 1


def answering_context(agent_type: str | None, expert: str) -> str:
    """How independent the answer was from the session that asked for it.

    The consultation protocol says to spawn a subagent voicing the expert (docs/02),
    and the citation gate enforces that the answer rests on the expert's own memory.
    What the gate cannot see is *who assembled it*: a session that answers its own
    ticket inline produces a byte-identical Exchange record to one a subagent voiced,
    so "the expert said so" and "I said so under a ticket" were indistinguishable in
    the graph. Measured 2026-07-28: a subagent shares its parent's `session_id`, so
    the tap's agent fields are the only signal that separates them.

    - `voiced` — a subagent running the consulted expert's own agent definition.
    - `self` — the asking context answered its own ticket. Still validly cited, but
      the independence the protocol asks for was not obtained.
    - `agent:<type>` — some other subagent; independent of the main loop, but not
      the expert's persona.
    - `unknown` — the tap line predates the agent fields. Never collapsed into
      `self`: "we did not record it" is not "the main loop did it".
    """
    if agent_type is None:
        return "unknown"
    if not agent_type:
        return "self"
    return "voiced" if agent_type == f"thalamus-{expert}" else f"agent:{agent_type}"


def _stamp_answering_context(
    g: GraphTraversalSource, exchange_vid: str, event: TraceEvent
) -> None:
    """Record on the Exchange whether a subagent voiced the expert or the asker self-answered.

    Only the closing call carries this fact — recalls under the ticket may legitimately
    come from either context, and it is the *answer's* provenance that matters.
    """
    if event.tool != "consult_answer":
        return
    exchange = load_exchange(g, exchange_vid)
    if exchange is None:
        return
    close_exchange(
        g,
        exchange_vid,
        {
            "answered_from": answering_context(
                event.agent_type, exchange.get("expert") or ""
            ),
            "answered_by_agent_type": event.agent_type or "",
        },
        citation_refs=[],
    )


def _exchange_vid(g: GraphTraversalSource, event: TraceEvent) -> str | None:
    """The Exchange vertex behind this trace's ticket, if it was ever minted.

    A ticket the model invented names no vertex; merging a CONSULTS edge to it would
    500 the whole sync (the hallucinated-thread_ref lesson), so existence is checked
    here and a dangling ticket is simply not a consultation.
    """
    ticket = event.ticket()
    if not ticket:
        return None
    vertex_id = _consultation_exchange_vid(ticket)
    return vertex_id if _vertex_exists(g, vertex_id) else None


def _session_scope(
    g: GraphTraversalSource, session_id: str, events: list[TraceEvent]
) -> str | None:
    """Which scope this session's Session vertex lives in, or None if not yet distilled.

    Precedence: the tap-recorded pin (the hook inherits THALAMUS_SCOPE from the same
    process env the MCP server read — docs/07 "the process is the pin"), then the
    scope the returned vertex IDs carry, then the distilled Session vertex. Every
    candidate is validated against an existing Session vertex, so a wrong or stale
    hint falls through instead of landing traces in a scope the session never joined.
    """
    for candidate in (
        *(event.scope for event in events if event.scope),
        *(hint for event in events if (hint := event.scope_hint())),
    ):
        if _vertex_exists(g, vid("Session", session_id, candidate)):
            return candidate

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
