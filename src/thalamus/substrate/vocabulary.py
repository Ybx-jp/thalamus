"""The retrieval vocabulary — fixed, read-only graph primitives a planner composes.

A model never writes Gremlin. It chooses among these calls, and the code runs them:
each primitive is one parameterized traversal with its scope passed in as a plain
argument, the contract `recall()` keeps. The memory reflex's compiler
(`harness/retrieval.py`) validates a planner's calls against this vocabulary and caps
them per job; `harness/mcp_server.py` exposes the same primitives to Claude and to
expert pins, with the scope set server-side from the pin or a ticket.

**Every primitive returns rows, never renderings.** A `Row` is one line — vertex id,
kind, tier, date and the node's own first sentence — which is what a planner needs to
decide its next call and nothing more. The full rendering of a node is `resolve`,
through the reader's own formatters.

**Confinement is applied to what comes back, not only to where a walk starts.**
Artifacts and Entities are global, so a walk through one reaches every scope's nodes;
`rows_for` is the one gate every primitive's output passes, and it keeps a node only
when this scope may read it: a Session, a Thread and a session-contained Claim in the
scope itself, a knowledge Claim (contained by no Session) or a Chunk in the scope or in
`knowledge_scopes` — the same line `recall()` draws (A0171, cites-as-live).

The relations `expand_one_hop` walks are the edges the graph holds, one relation per
populated edge family. Counted on 2026-09-24: `TOUCHES` 17,557 (10,414 from episodic
claims), `ABOUT` 68,365 (none from an episodic claim), `SOLVED_BY` 2,144, `USES` 745,
`SPAWNS`/`CONTINUES`/`RESOLVES` 1,366, `CONTAINS` 7,524.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from gremlin_python.process.graph_traversal import GraphTraversalSource, __
from gremlin_python.process.traversal import Order, P, T

from thalamus.contract.ontology import MAIN_SCOPE, scope_of
from thalamus.substrate.reader import (
    _MATCH_FLOOR,
    _extract_keywords,
    _first,
    _first_int,
    _keyword_predicate,
    _load_chunk_result,
    _load_knowledge_result,
    _load_session_result,
    _ranked,
    recall_open_threads,
    recall_thread,
    sessions_touching,
)
from thalamus.substrate.schema import Tier, is_rejected_kind

# What `lexical_by_kind` can search. The three episodic claim kinds are the ones
# distillation writes; `external` is a knowledge claim, contained by no session.
KINDS = ("session", "decision", "problem", "solution", "thread", "chunk", "external")
EPISODIC_CLAIM_KINDS = ("decision", "problem", "solution")

# relation -> the edge labels it walks, both directions unless the tuple says out/in.
RELATIONS: dict[str, tuple[str, ...]] = {
    # Anything else that touched one of this node's artifacts.
    "same_file": ("TOUCHES",),
    # Knowledge claims and chunks about one of this node's entities. Episodic claims
    # carry no ABOUT edge, so from one this returns nothing.
    "same_entity": ("ABOUT",),
    # The session that holds this claim and its other claims; from a session, its claims.
    "same_episode": ("CONTAINS",),
    # A problem's solutions, or a solution's problem.
    "resolved_by": ("SOLVED_BY",),
    # What a claim reasoned with, or the claims that reasoned with this one.
    "uses": ("USES",),
    # A session's threads, or a thread's sessions.
    "threads": ("SPAWNS", "CONTINUES", "RESOLVES"),
}

# Edges whose far end is a global hub, crossed to reach the nodes on its other side.
_THROUGH_HUB = {"TOUCHES", "ABOUT"}

# How many neighbours a hop reads before confinement and the caller's limit cut them.
# An Entity can carry thousands of ABOUT edges; the walk stops reading here rather than
# materialising all of them to keep a handful.
_HOP_WINDOW = 200

# A row's summary: the node's own first sentence, cut here.
_SUMMARY_CHARS = 160

_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


@dataclass(frozen=True)
class Row:
    """One node as a planner sees it."""

    vid: str
    kind: str
    tier: int
    date: str
    summary: str

    def line(self, handle: str = "") -> str:
        """`handle · kind · tier N · date · summary`; the vertex id when no handle."""
        name = handle or f"`{self.vid}`"
        date = f" · {self.date}" if self.date else ""
        return f"{name} · {self.kind} · tier {self.tier}{date} · {self.summary}"


def _summary(text: str) -> str:
    text = " ".join(text.split())
    first = _SENTENCE_END.split(text, maxsplit=1)[0]
    if len(first) > _SUMMARY_CHARS:
        return first[: _SUMMARY_CHARS - 1].rstrip() + "…"
    return first


def rows_for(
    g: GraphTraversalSource,
    vids: list[str],
    scope: str = MAIN_SCOPE,
    knowledge_scopes: list[str] | None = None,
) -> list[Row]:
    """The readable subset of `vids` as rows, in the order given.

    The confinement gate: every primitive's output passes through here.
    """
    if not vids:
        return []
    readable_knowledge = {scope, *(knowledge_scopes or [])}
    records = (
        g.V(*vids)
        .project("id", "label", "props", "session_ts")
        .by(T.id)
        .by(T.label)
        .by(__.value_map("kind", "tier", "summary", "description", "title", "text",
                         "timestamp", "ingested_at"))
        .by(__.in_("CONTAINS").has_label("Session").values("timestamp").fold())
        .to_list()
    )
    by_id = {str(record["id"]): record for record in records}
    rows = []
    for node_id in dict.fromkeys(vids):
        record = by_id.get(node_id)
        if record is None:
            continue
        row = _row(node_id, record, scope, readable_knowledge)
        if row is not None:
            rows.append(row)
    return rows


def _row(node_id: str, record: dict, scope: str, readable_knowledge: set[str]) -> Row | None:
    label = str(record["label"])
    props = record["props"]
    node_scope = scope_of(node_id)
    contained = bool(record["session_ts"])

    if label in ("Session", "Thread") or (label == "Claim" and contained):
        if node_scope != scope:
            return None
    elif label in ("Claim", "Chunk"):
        if node_scope not in readable_knowledge:
            return None
    else:
        # Artifacts, Entities, Sources, Traces, Exchanges: walked through or read by
        # their own tools, never a result row.
        return None

    if label == "Session":
        kind, text, date = "session", _first(props.get("summary")), _first(props.get("timestamp"))
    elif label == "Thread":
        kind = "thread"
        text = _first(props.get("title")) or _first(props.get("description"))
        date = _first(props.get("ingested_at"))
    elif label == "Chunk":
        kind, text, date = "chunk", _first(props.get("text")), _first(props.get("ingested_at"))
    elif contained:
        claim_kind = _first(props.get("kind"))
        kind = "rejected" if is_rejected_kind(claim_kind) else claim_kind
        text, date = _first(props.get("description")), str(record["session_ts"][0])
    else:
        kind, text = "external", _first(props.get("description"))
        date = _first(props.get("ingested_at"))

    default_tier = Tier.FIRST_PARTY if label in ("Session", "Thread") or contained else Tier.CURATED
    return Row(
        vid=node_id,
        kind=kind,
        tier=_first_int(props.get("tier"), int(default_tier)),
        date=date[:10],
        summary=_summary(text),
    )


def lexical_by_kind(
    g: GraphTraversalSource,
    query: str,
    kind: str,
    limit: int = 5,
    scope: str = MAIN_SCOPE,
    knowledge_scopes: list[str] | None = None,
) -> list[Row]:
    """Nodes of one kind ranked by keyword hits, under `recall()`'s predicate and floor."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; one of {', '.join(KINDS)}")
    keywords = _extract_keywords(query)
    if not keywords:
        return []
    claim_scopes = [scope, *(s for s in knowledge_scopes or [] if s != scope)]

    scores: dict[str, float] = {}
    hits: dict[str, set[str]] = {}
    for keyword in keywords:
        predicate = _keyword_predicate(keyword)
        if kind == "session":
            walk = g.V().has_label("Session").has("scope", scope).has("summary", predicate)
        elif kind in EPISODIC_CLAIM_KINDS:
            walk = (
                g.V().has_label("Claim").has("scope", scope).has("kind", kind)
                .has("description", predicate).where(__.in_e("CONTAINS"))
            )
        elif kind == "thread":
            walk = (
                g.V().has_label("Thread").has("scope", scope)
                .or_(__.has("title", predicate), __.has("description", predicate))
            )
        elif kind == "chunk":
            walk = (
                g.V().has_label("Chunk").has("scope", P.within(claim_scopes))
                .has("text", predicate)
            )
        else:
            walk = (
                g.V().has_label("Claim").has("scope", P.within(claim_scopes))
                .has("description", predicate).not_(__.in_e("CONTAINS"))
            )
        for node_id in walk.id_().to_list():
            key = str(node_id)
            scores[key] = scores.get(key, 0) + 1
            hits.setdefault(key, set()).add(keyword)

    floor = min(_MATCH_FLOOR, len(keywords))
    ranked = [node_id for node_id, _ in _ranked(scores, hits, floor, query)]
    return rows_for(g, ranked[: limit * 2], scope, knowledge_scopes)[:limit]


def expand_one_hop(
    g: GraphTraversalSource,
    node_id: str,
    relation: str,
    limit: int = 5,
    scope: str = MAIN_SCOPE,
    knowledge_scopes: list[str] | None = None,
) -> list[Row]:
    """The readable neighbours of one readable node over one relation."""
    if relation not in RELATIONS:
        raise ValueError(f"unknown relation {relation!r}; one of {', '.join(RELATIONS)}")
    if not rows_for(g, [node_id], scope, knowledge_scopes):
        return []

    labels = RELATIONS[relation]
    if labels[0] in _THROUGH_HUB:
        walk = g.V(node_id).out(*labels).in_(*labels)
    elif relation == "same_episode":
        walk = g.V(node_id).union(
            __.out("CONTAINS"),
            __.in_("CONTAINS"),
            __.in_("CONTAINS").out("CONTAINS"),
        )
    else:
        walk = g.V(node_id).both(*labels)
    neighbours = (
        walk.has(T.id, P.neq(node_id)).dedup().limit(_HOP_WINDOW).id_().to_list()
    )
    rows = rows_for(g, [str(n) for n in neighbours], scope, knowledge_scopes)
    rows.sort(key=lambda row: row.date, reverse=True)
    return rows[:limit]


def session_claims(
    g: GraphTraversalSource,
    node_id: str,
    kinds: list[str] | None = None,
    limit: int = 8,
    scope: str = MAIN_SCOPE,
) -> list[Row]:
    """A readable session's claims of the given kinds (default: all three episodic)."""
    wanted = list(kinds or EPISODIC_CLAIM_KINDS)
    unknown = [kind for kind in wanted if kind not in EPISODIC_CLAIM_KINDS]
    if unknown:
        raise ValueError(
            f"unknown claim kind(s) {', '.join(unknown)}; one of {', '.join(EPISODIC_CLAIM_KINDS)}"
        )
    session = rows_for(g, [node_id], scope)
    if not session or session[0].kind != "session":
        return []
    claims = (
        g.V(node_id).out("CONTAINS").has("kind", P.within(wanted))
        .order().by("ingested_at", Order.asc).limit(limit).id_().to_list()
    )
    return rows_for(g, [str(c) for c in claims], scope)


def chunks_near_source(
    g: GraphTraversalSource,
    node_id: str,
    limit: int = 3,
    scope: str = MAIN_SCOPE,
    knowledge_scopes: list[str] | None = None,
) -> list[Row]:
    """Passages behind a readable claim or chunk.

    From a claim: the chunks its citation was found in (`ANCHORS`), or failing those
    the opening chunks of the Source it was derived from. From a chunk: the passages
    either side of it in the document.
    """
    start = rows_for(g, [node_id], scope, knowledge_scopes)
    if not start:
        return []
    if start[0].kind == "chunk":
        found = g.V(node_id).both("ADJACENT_IN_TEXT").id_().to_list()
    else:
        found = g.V(node_id).out("ANCHORS").limit(limit).id_().to_list()
        if not found:
            found = (
                g.V(node_id).out("DERIVED_FROM").has_label("Source")
                .in_("DERIVED_FROM").has_label("Chunk")
                .order().by("ordinal", Order.asc).limit(limit).id_().to_list()
            )
    return rows_for(g, [str(f) for f in found], scope, knowledge_scopes)[:limit]


def by_path(
    g: GraphTraversalSource, path: str, limit: int = 5, scope: str = MAIN_SCOPE
) -> list[Row]:
    """Sessions that touched a file, under any spelling of it (`recall_by_artifact`'s walk)."""
    session_vids = sessions_touching(g, path, limit, scope)
    return rows_for(g, session_vids, scope)


def threads_by_topic(
    g: GraphTraversalSource, topic: str, limit: int = 5, scope: str = MAIN_SCOPE
) -> list[Row]:
    """Open threads ranked against a topic (`recall_open_threads`' ranking), held to
    `recall()`'s match floor.

    `recall_open_threads` orders by overlap but keeps every row to fill its page, so on
    its own it answers any topic with `limit` threads; replayed over 40 real reflex
    anchor sets it returned five rows for all 40. A planner reads a full page as five
    matches, so rows under the floor are dropped here.
    """
    keywords = _extract_keywords(topic)
    if not keywords:
        return []
    floor = min(_MATCH_FLOOR, len(keywords))
    threads = [
        thread for thread in recall_open_threads(g, limit=limit, scope=scope, topic=topic)
        if thread.node_id and sum(
            1 for keyword in keywords
            if keyword in f"{thread.thread_id} {thread.title} {thread.description}".lower()
        ) >= floor
    ]
    return rows_for(g, [t.node_id for t in threads], scope)


def resolve(
    g: GraphTraversalSource,
    node_id: str,
    scope: str = MAIN_SCOPE,
    knowledge_scopes: list[str] | None = None,
):
    """One readable node rendered in full, or None when this scope may not read it.

    Scope-checked before anything is loaded, so an id from another scope renders
    nothing rather than a partial record.
    """
    rows = rows_for(g, [node_id], scope, knowledge_scopes)
    if not rows:
        return None
    kind = rows[0].kind
    if kind == "session":
        session_id = node_id.split(":", 3)[3]
        return _load_session_result(g, session_id, "", scope)
    if kind == "thread":
        return recall_thread(g, node_id.split(":", 3)[3], scope)
    if kind == "chunk":
        return _load_chunk_result(g, node_id)
    if kind == "external":
        return _load_knowledge_result(g, node_id)
    sessions = g.V(node_id).in_("CONTAINS").has_label("Session").values("session_id").to_list()
    if not sessions:
        return None
    return _load_session_result(g, str(sessions[0]), "", scope, claim_vid=node_id)
