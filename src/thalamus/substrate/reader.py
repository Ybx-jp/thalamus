"""Query and retrieve memory from the graph.

Every read is **scoped**. A session is pinned to one scope, and the server — not the
model — decides what that scope can see: docs/07 is explicit that "the model is never
trusted to self-limit its own retrieval scope". The `scope` parameter threaded through
this module is where that enforcement lives.

Results are rendered as **data with provenance**, never as text positioned to be read as
instructions (docs/05, informs-never-instructs). Today everything in the graph is tier-1
— the agent's own history — so the exposure is small. The moment a feed writes tier-2
content, this formatter is the injection surface, which is why the tier travels with the
content rather than being dropped on the floor at render time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from gremlin_python.process.graph_traversal import GraphTraversalSource
from gremlin_python.process.traversal import Order, P, T, TextP

from thalamus.contract.ontology import MAIN_SCOPE, vid
from thalamus.substrate.schema import Tier

logger = logging.getLogger(__name__)

_TIER_NAMES = {
    0: "operator",
    1: "first-party",
    2: "curated third-party",
    3: "wild",
}


def _tier_label(tier: object) -> str:
    try:
        value = int(tier)
    except (TypeError, ValueError):
        value = int(Tier.FIRST_PARTY)
    return f"tier {value} · {_TIER_NAMES.get(value, 'unknown')}"


@dataclass
class MemoryResult:
    """A single memory retrieval result."""

    session_id: str
    summary: str
    timestamp: str
    tool: str
    project: str
    scope: str = MAIN_SCOPE
    tier: int = int(Tier.FIRST_PARTY)
    node_id: str = ""
    details: list[dict] = field(default_factory=list)
    relevance: str = ""

    def format(self) -> str:
        lines = [
            f"## Recalled memory [{_tier_label(self.tier)}]",
            f"**Session:** [{self.tool}] {self.project or 'unknown project'} — "
            f"{self.timestamp[:10]} (scope: {self.scope})",
            f"**Summary:** {self.summary}",
        ]
        if self.relevance:
            lines.append(f"**Match:** {self.relevance}")
        if self.details:
            lines.append("")
            for detail in self.details:
                kind = detail.get("kind") or detail.get("label", "")
                desc = detail.get("description", "")
                lines.append(f"- **{kind}**: {desc}")
        return "\n".join(lines)


@dataclass
class ThreadResult:
    """A thread retrieval result."""

    thread_id: str
    title: str
    description: str
    status: str
    project: str
    scope: str = MAIN_SCOPE
    spawned_by: str = ""
    last_session: str = ""

    def format(self) -> str:
        status_icon = {"open": "○", "in_progress": "◐", "resolved": "●", "abandoned": "✗"}.get(
            self.status, "?"
        )
        lines = [
            f"## {status_icon} [{self.status}] {self.title}",
            f"**ID:** `{self.thread_id}`",
            f"**Description:** {self.description}",
        ]
        if self.project:
            lines.append(f"**Project:** {self.project}")
        if self.spawned_by:
            lines.append(f"**Opened in:** {self.spawned_by}")
        if self.last_session:
            lines.append(f"**Last touched:** {self.last_session}")
        return "\n".join(lines)


def recall(
    g: GraphTraversalSource, query: str, limit: int = 5, scope: str = MAIN_SCOPE
) -> list[MemoryResult]:
    """Natural language recall — search session summaries and claim descriptions.

    Uses text containment matching. Claims are searched by label, not by subtype: a
    single `hasLabel("Claim")` covers decisions, problems, solutions, and anything an
    expert adds later, which is the point of the unified Claim (docs/09 G1).
    """
    keywords = _extract_keywords(query)
    if not keywords:
        return recall_recent(g, limit, scope)

    matched_session_ids: dict[str, float] = {}

    for keyword in keywords:
        sessions = (
            g.V()
            .has_label("Session")
            .has("scope", scope)
            .has("summary", TextP.containing(keyword))
            .value_map("session_id")
            .to_list()
        )
        for session in sessions:
            session_id = _first(session.get("session_id"))
            matched_session_ids[session_id] = matched_session_ids.get(session_id, 0) + 2.0

        claims = (
            g.V()
            .has_label("Claim")
            .has("scope", scope)
            .has("description", TextP.containing(keyword))
            .in_e("CONTAINS")
            .out_v()
            .has_label("Session")
            .value_map("session_id")
            .to_list()
        )
        for claim in claims:
            session_id = _first(claim.get("session_id"))
            matched_session_ids[session_id] = matched_session_ids.get(session_id, 0) + 1.0

    ranked = sorted(matched_session_ids.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [
        _load_session_result(g, session_id, f"matched on: {', '.join(keywords)}", scope)
        for session_id, _ in ranked
    ]


def recall_by_artifact(
    g: GraphTraversalSource, identifier: str, limit: int = 5, scope: str = MAIN_SCOPE
) -> list[MemoryResult]:
    """Find sessions that touched a specific artifact.

    Artifacts are global — the same vertex is reachable from every scope — so the scope
    filter is applied to the *sessions*, not to the artifact. This is the join key doing
    its job: a shared artifact is a shared vocabulary, not a channel between experts.
    """
    sessions = (
        g.V()
        .has_label("Artifact")
        .has("identifier", TextP.containing(identifier))
        .in_e("TOUCHES")
        .out_v()
        .in_e("CONTAINS")
        .out_v()
        .has_label("Session")
        .has("scope", scope)
        .dedup()
        .value_map("session_id")
        .limit(limit)
        .to_list()
    )

    return [
        _load_session_result(g, _first(s.get("session_id")), f"touches: {identifier}", scope)
        for s in sessions
    ]


def recall_by_project(
    g: GraphTraversalSource, project: str, limit: int = 5, scope: str = MAIN_SCOPE
) -> list[MemoryResult]:
    """Find recent sessions for a specific project.

    `project` and `scope` are orthogonal axes — which repo, versus which expert — so this
    filters on both.
    """
    sessions = (
        g.V()
        .has_label("Session")
        .has("scope", scope)
        .has("project", TextP.containing(project))
        .order()
        .by("timestamp", Order.desc)
        .limit(limit)
        .value_map("session_id", "summary", "timestamp", "tool", "project", "scope", "tier")
        .to_list()
    )

    return [_session_result(s, relevance=f"project: {project}") for s in sessions]


def recall_recent(
    g: GraphTraversalSource, limit: int = 5, scope: str = MAIN_SCOPE
) -> list[MemoryResult]:
    """Return the most recent sessions in scope."""
    sessions = (
        g.V()
        .has_label("Session")
        .has("scope", scope)
        .order()
        .by("timestamp", Order.desc)
        .limit(limit)
        .value_map("session_id", "summary", "timestamp", "tool", "project", "scope", "tier")
        .to_list()
    )

    return [_session_result(s) for s in sessions]


def recall_open_threads(
    g: GraphTraversalSource,
    project: str | None = None,
    limit: int = 10,
    scope: str = MAIN_SCOPE,
) -> list[ThreadResult]:
    """Return open/in-progress threads — the active continuation points."""
    query = (
        g.V()
        .has_label("Thread")
        .has("scope", scope)
        .has("status", P.within("open", "in_progress"))
    )

    if project:
        query = query.has("project", TextP.containing(project))

    threads = (
        query.order()
        .by("status", Order.asc)
        .limit(limit)
        .value_map("thread_id", "title", "description", "status", "project", "scope")
        .to_list()
    )

    return [_thread_result(g, thread, scope) for thread in threads]


def recall_thread(
    g: GraphTraversalSource, thread_id: str, scope: str = MAIN_SCOPE
) -> ThreadResult | None:
    """Load a single thread by ID with its lineage."""
    thread_vid = vid("Thread", thread_id, scope)

    data = (
        g.V(thread_vid)
        .has_label("Thread")
        .value_map("thread_id", "title", "description", "status", "project", "scope")
        .to_list()
    )
    if not data:
        return None

    return _thread_result(g, data[0], scope)


def _thread_result(g: GraphTraversalSource, thread: dict, scope: str) -> ThreadResult:
    thread_id = _first(thread.get("thread_id"))
    thread_vid = vid("Thread", thread_id, scope)

    spawned = (
        g.V(thread_vid)
        .in_e("SPAWNS")
        .out_v()
        .has_label("Session")
        .value_map("session_id", "timestamp")
        .limit(1)
        .to_list()
    )
    recent = (
        g.V(thread_vid)
        .in_e("CONTINUES", "SPAWNS")
        .out_v()
        .has_label("Session")
        .order()
        .by("timestamp", Order.desc)
        .value_map("session_id", "timestamp")
        .limit(1)
        .to_list()
    )

    return ThreadResult(
        thread_id=thread_id,
        title=_first(thread.get("title")),
        description=_first(thread.get("description")),
        status=_first(thread.get("status")),
        project=_first(thread.get("project")),
        scope=_first(thread.get("scope")) or scope,
        spawned_by=_session_stamp(spawned),
        last_session=_session_stamp(recent),
    )


def _session_stamp(rows: list[dict]) -> str:
    if not rows:
        return ""
    session_id = _first(rows[0].get("session_id"))
    timestamp = _first(rows[0].get("timestamp"))
    return f"{session_id} ({timestamp[:10]})"


def _session_result(session: dict, relevance: str = "", details: list[dict] | None = None):
    return MemoryResult(
        session_id=_first(session.get("session_id")),
        summary=_first(session.get("summary")),
        timestamp=_first(session.get("timestamp")),
        tool=_first(session.get("tool")),
        project=_first(session.get("project")),
        scope=_first(session.get("scope")) or MAIN_SCOPE,
        tier=_first_int(session.get("tier"), int(Tier.FIRST_PARTY)),
        node_id=vid(
            "Session",
            _first(session.get("session_id")),
            _first(session.get("scope")) or MAIN_SCOPE,
        ),
        details=details or [],
        relevance=relevance,
    )


def _load_session_result(
    g: GraphTraversalSource, session_id: str, relevance: str, scope: str
) -> MemoryResult:
    """Load full session details from the graph."""
    session_data = (
        g.V()
        .has_label("Session")
        .has("scope", scope)
        .has("session_id", session_id)
        .value_map("session_id", "summary", "timestamp", "tool", "project", "scope", "tier")
        .to_list()
    )

    if not session_data:
        return MemoryResult(
            session_id=session_id,
            summary="(session not found)",
            timestamp="",
            tool="",
            project="",
            scope=scope,
            relevance=relevance,
        )

    session_vid = vid("Session", session_id, scope)
    children = g.V(session_vid).out("CONTAINS").value_map(True).to_list()

    details = []
    for child in children:
        if not isinstance(child, dict):
            continue
        description = _first(child.get("description"))
        if not description:
            continue
        details.append(
            {
                "kind": _first(child.get("kind")) or _first(child.get(T.label)),
                "description": description,
                "tier": _first_int(child.get("tier"), int(Tier.FIRST_PARTY)),
            }
        )

    return _session_result(session_data[0], relevance=relevance, details=details)


def _extract_keywords(query: str) -> list[str]:
    """Extract meaningful keywords from a natural language query.

    Simple heuristic: split on whitespace, drop stopwords and short tokens.
    """
    stopwords = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "about", "into", "through", "during", "before", "after", "above",
        "below", "between", "under", "again", "further", "then", "once",
        "what", "which", "who", "whom", "this", "that", "these", "those",
        "i", "me", "my", "we", "our", "you", "your", "it", "its", "how",
        "when", "where", "why", "all", "any", "both", "each", "few", "more",
        "most", "other", "some", "such", "no", "not", "only", "same", "so",
        "than", "too", "very", "just", "know", "work", "thing", "things",
    }
    tokens = query.lower().split()
    return [t for t in tokens if len(t) > 2 and t not in stopwords]


def _first(val) -> str:
    """Extract the first value from a Gremlin value_map list, or stringify."""
    if isinstance(val, list):
        return str(val[0]) if val else ""
    return str(val) if val is not None else ""


def _first_int(val, default: int) -> int:
    text = _first(val)
    try:
        return int(text)
    except (TypeError, ValueError):
        return default
