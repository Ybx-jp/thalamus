"""Query and retrieve memory from the graph."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from gremlin_python.process.graph_traversal import GraphTraversalSource
from gremlin_python.process.traversal import Order, P, T, TextP

logger = logging.getLogger(__name__)


@dataclass
class MemoryResult:
    """A single memory retrieval result."""

    session_id: str
    summary: str
    timestamp: str
    tool: str
    project: str
    details: list[dict] = field(default_factory=list)
    relevance: str = ""

    def format(self) -> str:
        lines = [
            f"## [{self.tool}] {self.project or 'unknown project'} — {self.timestamp[:10]}",
            f"**Summary:** {self.summary}",
        ]
        if self.relevance:
            lines.append(f"**Match:** {self.relevance}")
        if self.details:
            lines.append("")
            for detail in self.details:
                label = detail.get("label", "")
                desc = detail.get("description", "")
                lines.append(f"- **{label}**: {desc}")
        return "\n".join(lines)


@dataclass
class ThreadResult:
    """A thread retrieval result."""

    thread_id: str
    title: str
    description: str
    status: str
    project: str
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


def recall(g: GraphTraversalSource, query: str, limit: int = 5) -> list[MemoryResult]:
    """Natural language recall — search session summaries and node descriptions.

    Uses text containment matching on summaries, decisions, problems, and solutions.
    Returns the most relevant sessions with their subgraph details.
    """
    keywords = _extract_keywords(query)
    if not keywords:
        return recall_recent(g, limit)

    matched_session_ids: dict[str, float] = {}

    for keyword in keywords:
        # Search session summaries
        sessions = (
            g.V()
            .has_label("Session")
            .has("summary", TextP.containing(keyword))
            .value_map("session_id", "summary", "timestamp", "tool", "project")
            .to_list()
        )
        for s in sessions:
            sid = _first(s.get("session_id"))
            matched_session_ids[sid] = matched_session_ids.get(sid, 0) + 2.0

        # Search decision/problem/solution descriptions
        for label in ("Decision", "Problem", "Solution"):
            nodes = (
                g.V()
                .has_label(label)
                .has("description", TextP.containing(keyword))
                .in_e("CONTAINS")
                .out_v()
                .has_label("Session")
                .value_map("session_id")
                .to_list()
            )
            for n in nodes:
                sid = _first(n.get("session_id"))
                matched_session_ids[sid] = matched_session_ids.get(sid, 0) + 1.0

    ranked = sorted(matched_session_ids.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [_load_session_result(g, sid, f"matched on: {', '.join(keywords)}") for sid, _ in ranked]


def recall_by_artifact(
    g: GraphTraversalSource, identifier: str, limit: int = 5
) -> list[MemoryResult]:
    """Find sessions that touched a specific artifact."""
    sessions = (
        g.V()
        .has_label("Artifact")
        .has("identifier", TextP.containing(identifier))
        .in_e("TOUCHES")
        .out_v()
        .in_e("CONTAINS")
        .out_v()
        .has_label("Session")
        .dedup()
        .value_map("session_id")
        .limit(limit)
        .to_list()
    )

    return [
        _load_session_result(g, _first(s.get("session_id")), f"touches: {identifier}")
        for s in sessions
    ]


def recall_by_project(
    g: GraphTraversalSource, project: str, limit: int = 5
) -> list[MemoryResult]:
    """Find recent sessions for a specific project."""
    sessions = (
        g.V()
        .has_label("Session")
        .has("project", TextP.containing(project))
        .order()
        .by("timestamp", Order.desc)
        .limit(limit)
        .value_map("session_id", "summary", "timestamp", "tool", "project")
        .to_list()
    )

    return [
        MemoryResult(
            session_id=_first(s.get("session_id")),
            summary=_first(s.get("summary")),
            timestamp=_first(s.get("timestamp")),
            tool=_first(s.get("tool")),
            project=_first(s.get("project")),
            relevance=f"project: {project}",
        )
        for s in sessions
    ]


def recall_recent(g: GraphTraversalSource, limit: int = 5) -> list[MemoryResult]:
    """Return the most recent sessions."""
    sessions = (
        g.V()
        .has_label("Session")
        .order()
        .by("timestamp", Order.desc)
        .limit(limit)
        .value_map("session_id", "summary", "timestamp", "tool", "project")
        .to_list()
    )

    return [
        MemoryResult(
            session_id=_first(s.get("session_id")),
            summary=_first(s.get("summary")),
            timestamp=_first(s.get("timestamp")),
            tool=_first(s.get("tool")),
            project=_first(s.get("project")),
        )
        for s in sessions
    ]


def recall_open_threads(
    g: GraphTraversalSource, project: str | None = None, limit: int = 10
) -> list[ThreadResult]:
    """Return open/in-progress threads, optionally filtered by project.

    These are the active continuation points — what should be worked on next.
    """
    query = g.V().has_label("Thread").has("status", P.within("open", "in_progress"))

    if project:
        query = query.has("project", TextP.containing(project))

    threads = query.order().by("status", Order.asc).limit(limit).value_map(
        "thread_id", "title", "description", "status", "project"
    ).to_list()

    results = []
    for t in threads:
        tid = _first(t.get("thread_id"))
        vid = f"thread:{tid}"

        # Find the session that spawned this thread
        spawned = (
            g.V(vid).in_e("SPAWNS").out_v().has_label("Session")
            .value_map("session_id", "timestamp").limit(1).to_list()
        )
        spawned_by = ""
        if spawned:
            spawned_by = f"{_first(spawned[0].get('session_id'))} ({_first(spawned[0].get('timestamp'))[:10]})"

        # Find the most recent session that touched this thread (CONTINUES or RESOLVES)
        recent = (
            g.V(vid).in_e("CONTINUES", "SPAWNS").out_v().has_label("Session")
            .order().by("timestamp", Order.desc)
            .value_map("session_id", "timestamp").limit(1).to_list()
        )
        last_session = ""
        if recent:
            last_session = f"{_first(recent[0].get('session_id'))} ({_first(recent[0].get('timestamp'))[:10]})"

        results.append(ThreadResult(
            thread_id=tid,
            title=_first(t.get("title")),
            description=_first(t.get("description")),
            status=_first(t.get("status")),
            project=_first(t.get("project")),
            spawned_by=spawned_by,
            last_session=last_session,
        ))

    return results


def recall_thread(g: GraphTraversalSource, thread_id: str) -> ThreadResult | None:
    """Load a single thread by ID with its lineage."""
    vid = f"thread:{thread_id}"

    data = g.V(vid).has_label("Thread").value_map(
        "thread_id", "title", "description", "status", "project"
    ).to_list()

    if not data:
        return None

    t = data[0]

    spawned = (
        g.V(vid).in_e("SPAWNS").out_v().has_label("Session")
        .value_map("session_id", "timestamp").limit(1).to_list()
    )
    spawned_by = ""
    if spawned:
        spawned_by = f"{_first(spawned[0].get('session_id'))} ({_first(spawned[0].get('timestamp'))[:10]})"

    recent = (
        g.V(vid).in_e("CONTINUES", "SPAWNS").out_v().has_label("Session")
        .order().by("timestamp", Order.desc)
        .value_map("session_id", "timestamp").limit(1).to_list()
    )
    last_session = ""
    if recent:
        last_session = f"{_first(recent[0].get('session_id'))} ({_first(recent[0].get('timestamp'))[:10]})"

    return ThreadResult(
        thread_id=_first(t.get("thread_id")),
        title=_first(t.get("title")),
        description=_first(t.get("description")),
        status=_first(t.get("status")),
        project=_first(t.get("project")),
        spawned_by=spawned_by,
        last_session=last_session,
    )


def _load_session_result(
    g: GraphTraversalSource, session_id: str, relevance: str
) -> MemoryResult:
    """Load full session details from graph."""
    session_data = (
        g.V()
        .has_label("Session")
        .has("session_id", session_id)
        .value_map("session_id", "summary", "timestamp", "tool", "project")
        .to_list()
    )

    if not session_data:
        return MemoryResult(
            session_id=session_id,
            summary="(session not found)",
            timestamp="",
            tool="",
            project="",
            relevance=relevance,
        )

    s = session_data[0]
    vid = f"session:{session_id}"

    # Load contained nodes
    children = (
        g.V(vid)
        .out("CONTAINS")
        .value_map(True)
        .to_list()
    )

    details = []
    for child in children:
        label = child.get(T.label, "") if hasattr(child, "get") else ""
        # value_map(True) returns label under T.label key
        if isinstance(child, dict):
            label = child.get("label", [label])[0] if "label" not in child else label
            desc = _first(child.get("description"))
            if desc:
                details.append({"label": label, "description": desc})

    return MemoryResult(
        session_id=_first(s.get("session_id")),
        summary=_first(s.get("summary")),
        timestamp=_first(s.get("timestamp")),
        tool=_first(s.get("tool")),
        project=_first(s.get("project")),
        details=details,
        relevance=relevance,
    )


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
    """Extract first value from Gremlin value_map list, or return as string."""
    if isinstance(val, list):
        return str(val[0]) if val else ""
    return str(val) if val is not None else ""
