"""Bounded persisted-graph queries for the local memory viewer."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote

from gremlin_python.process.graph_traversal import GraphTraversalSource, __
from gremlin_python.process.traversal import Order, P, T

from thalamus.plane.view_model import (
    Expandable,
    GraphView,
    NodeDetails,
    ViewEdge,
    ViewMetadata,
    ViewNode,
)

DEFAULT_OVERVIEW_LIMIT = 100
DEFAULT_PER_PROJECT_SESSION_LIMIT = 5
DEFAULT_ACTIVE_THREAD_LIMIT = 25
MAX_OVERVIEW_SOURCE_SESSIONS = 10_000
MAX_EXPANSION_NODES = 100
MAX_EXPANSION_EDGES = 200

_EXPANDABLE_KINDS = {"Session", "Artifact", "Decision", "Problem", "Solution", "Thread"}
_NODE_LABEL_PROPERTIES = {
    "Session": "summary",
    "Artifact": "identifier",
    "Decision": "description",
    "Problem": "description",
    "Solution": "description",
    "Thread": "title",
}


def persisted_overview(
    g: GraphTraversalSource,
    *,
    project: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    per_project_session_limit: int = DEFAULT_PER_PROJECT_SESSION_LIMIT,
    total_limit: int = DEFAULT_OVERVIEW_LIMIT,
) -> GraphView:
    """Return virtual project aggregates, recent sessions, and active threads.

    The source traversal is capped before data reaches Python.  The returned graph
    is separately capped so the browser never receives an unbounded overview.
    """
    session_query = _filtered_sessions(g, project=project, start=start, end=end)
    session_maps = (
        session_query.order()
        .by("timestamp", Order.desc)
        .limit(MAX_OVERVIEW_SOURCE_SESSIONS + 1)
        .value_map(True)
        .to_list()
    )
    source_truncated = len(session_maps) > MAX_OVERVIEW_SOURCE_SESSIONS
    if source_truncated:
        session_maps = session_maps[:MAX_OVERVIEW_SOURCE_SESSIONS]

    sessions_by_project: dict[str, list[ViewNode]] = defaultdict(list)
    for session_map in session_maps:
        session = node_from_value_map(session_map)
        sessions_by_project[_project_name(session)].append(session)

    nodes: dict[str, ViewNode] = {}
    edges: dict[str, ViewEdge] = {}
    overview_truncated = source_truncated
    for project_name, sessions in sorted(sessions_by_project.items()):
        if len(nodes) >= total_limit:
            overview_truncated = True
            break
        _add_project_node(nodes, project_name, session_count=len(sessions))

    active_threads = _active_threads(g, project=project)
    for thread in active_threads:
        if len(nodes) >= total_limit:
            overview_truncated = True
            break
        thread_project = _project_name(thread)
        if _project_id(thread_project) not in nodes:
            _add_project_node(nodes, thread_project, session_count=len(sessions_by_project[thread_project]))
        if len(nodes) >= total_limit:
            overview_truncated = True
            break
        nodes[thread.id] = thread
        _add_edge(edges, _project_id(thread_project), thread.id, "PROJECT_CONTAINS", virtual=True)

    for project_name, sessions in sorted(sessions_by_project.items()):
        for session in sessions[:per_project_session_limit]:
            if len(nodes) >= total_limit:
                overview_truncated = True
                break
            nodes[session.id] = session
            _add_edge(edges, _project_id(project_name), session.id, "PROJECT_CONTAINS", virtual=True)
        if len(nodes) >= total_limit:
            break

    timestamps = [
        str(session.properties["timestamp"])
        for sessions in sessions_by_project.values()
        for session in sessions
        if session.properties.get("timestamp")
    ]
    return GraphView(
        nodes=list(nodes.values()),
        edges=list(edges.values()),
        findings=[],
        metadata=ViewMetadata(
            mode="overview",
            visible_node_count=len(nodes),
            visible_edge_count=len(edges),
            matching_node_count=len(session_maps),
            truncated=overview_truncated,
            time_range=_time_range(timestamps),
        ),
    )


def expand_subgraph(
    g: GraphTraversalSource,
    *,
    root_ids: list[str],
    direction: Literal["incoming", "outgoing", "both"] = "both",
    visible_node_ids: set[str] | None = None,
    visible_edge_ids: set[str] | None = None,
    node_limit: int = MAX_EXPANSION_NODES,
    edge_limit: int = MAX_EXPANSION_EDGES,
) -> GraphView:
    """Load new one-hop neighbors of visible persisted nodes with explicit caps."""
    known_nodes = visible_node_ids or set()
    known_edges = visible_edge_ids or set()
    nodes: dict[str, ViewNode] = {}
    edges: dict[str, ViewEdge] = {}
    truncated = False

    for root_id in root_ids:
        directions = []
        if direction in {"outgoing", "both"}:
            directions.append("outgoing")
        if direction in {"incoming", "both"}:
            directions.append("incoming")

        for traversal_direction in directions:
            pairs = _neighbor_pairs(g, root_id, traversal_direction, edge_limit + 1)
            if len(pairs) > edge_limit:
                truncated = True
                pairs = pairs[:edge_limit]
            for pair in pairs:
                edge_map = pair["edge"]
                neighbor = node_from_value_map(pair["node"])
                if traversal_direction == "outgoing":
                    source, target = root_id, neighbor.id
                else:
                    source, target = neighbor.id, root_id
                edge = edge_from_value_map(edge_map, source=source, target=target)

                if edge.id not in known_edges:
                    if len(edges) >= edge_limit:
                        truncated = True
                        continue
                    edges[edge.id] = edge
                if neighbor.id not in known_nodes:
                    if len(nodes) >= node_limit:
                        truncated = True
                        continue
                    nodes[neighbor.id] = neighbor

    return GraphView(
        nodes=list(nodes.values()),
        edges=list(edges.values()),
        findings=[],
        metadata=ViewMetadata(
            mode="expansion",
            visible_node_count=len(nodes),
            visible_edge_count=len(edges),
            matching_node_count=len(nodes),
            truncated=truncated,
        ),
    )


def persisted_node_details(g: GraphTraversalSource, node_id: str) -> NodeDetails | None:
    """Load one persisted node and its graph-wide incoming and outgoing counts."""
    value_maps = g.V(node_id).limit(1).value_map(True).to_list()
    if not value_maps:
        return None
    incoming_counts = g.V(node_id).in_e().count().to_list()
    outgoing_counts = g.V(node_id).out_e().count().to_list()
    return NodeDetails(
        node=node_from_value_map(value_maps[0]),
        incoming_count=int(incoming_counts[0]) if incoming_counts else 0,
        outgoing_count=int(outgoing_counts[0]) if outgoing_counts else 0,
    )


def node_from_value_map(value_map: dict[Any, Any]) -> ViewNode:
    """Convert Gremlin ``value_map(True)`` output into a canonical view node."""
    element_id = _string_value(_element_value(value_map, T.id, "id"))
    kind = _string_value(_element_value(value_map, T.label, "label"))
    properties = {
        _property_key(key): _scalar(value)
        for key, value in value_map.items()
        if key not in {T.id, T.label, "id", "label"}
    }
    label_property = _NODE_LABEL_PROPERTIES.get(kind, "id")
    label = str(properties.get(label_property) or element_id)
    return ViewNode(
        id=element_id,
        kind=kind,
        label=label,
        properties=properties,
        expandable=Expandable(incoming=kind in _EXPANDABLE_KINDS, outgoing=kind in _EXPANDABLE_KINDS),
    )


def edge_from_value_map(value_map: dict[Any, Any], *, source: str, target: str) -> ViewEdge:
    """Convert a Gremlin edge map into the canonical deterministic edge form."""
    kind = _string_value(_element_value(value_map, T.label, "label"))
    properties = {
        _property_key(key): _scalar(value)
        for key, value in value_map.items()
        if key not in {T.id, T.label, "id", "label"}
    }
    return ViewEdge(id=f"{source}|{kind}|{target}", source=source, target=target, kind=kind, properties=properties)


def _filtered_sessions(
    g: GraphTraversalSource,
    *,
    project: str | None,
    start: datetime | None,
    end: datetime | None,
):
    query = g.V().has_label("Session")
    if project:
        query = query.has("project", project)
    if start:
        query = query.has("timestamp", P.gte(start.isoformat()))
    if end:
        query = query.has("timestamp", P.lte(end.isoformat()))
    return query


def _active_threads(g: GraphTraversalSource, *, project: str | None) -> list[ViewNode]:
    query = g.V().has_label("Thread").has("status", P.within("open", "in_progress"))
    if project:
        query = query.has("project", project)
    return [
        node_from_value_map(value_map)
        for value_map in query.order()
        .by("status", Order.asc)
        .limit(DEFAULT_ACTIVE_THREAD_LIMIT)
        .value_map(True)
        .to_list()
    ]


def _neighbor_pairs(
    g: GraphTraversalSource,
    root_id: str,
    direction: Literal["incoming", "outgoing"],
    limit: int,
) -> list[dict[str, dict[Any, Any]]]:
    if direction == "outgoing":
        traversal = g.V(root_id).out_e().as_("edge").in_v().as_("node")
    else:
        traversal = g.V(root_id).in_e().as_("edge").out_v().as_("node")
    return traversal.select("edge", "node").by(__.value_map(True)).by(__.value_map(True)).limit(limit).to_list()


def _add_project_node(nodes: dict[str, ViewNode], project: str, *, session_count: int) -> None:
    project_id = _project_id(project)
    if project_id not in nodes:
        nodes[project_id] = ViewNode(
            id=project_id,
            kind="Project",
            label=project,
            properties={"project": project, "session_count": session_count},
            virtual=True,
        )


def _add_edge(
    edges: dict[str, ViewEdge], source: str, target: str, kind: str, *, virtual: bool = False
) -> None:
    edge_id = f"{source}|{kind}|{target}"
    if edge_id not in edges:
        edges[edge_id] = ViewEdge(
            id=edge_id,
            source=source,
            target=target,
            kind=kind,
            properties={"virtual": True} if virtual else {},
        )


def _project_name(node: ViewNode) -> str:
    return str(node.properties.get("project") or "(unassigned)")


def _project_id(project: str) -> str:
    return f"project:{quote(project, safe='')}"


def _time_range(timestamps: list[str]) -> dict[str, str] | None:
    if not timestamps:
        return None
    return {"minimum": min(timestamps), "maximum": max(timestamps)}


def _element_value(value_map: dict[Any, Any], token: T, string_key: str) -> Any:
    return value_map.get(token, value_map.get(string_key, value_map.get(str(token))))


def _property_key(key: Any) -> str:
    return str(key)


def _scalar(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if len(value) == 1 else value
    return value


def _string_value(value: Any) -> str:
    scalar = _scalar(value)
    return str(scalar) if scalar is not None else ""
