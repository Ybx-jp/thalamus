"""Renderer-neutral graph models and pending-session conversion."""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from thalamus.substrate.schema import SessionGraph, ThreadStatus


class Expandable(BaseModel):
    incoming: bool = False
    outgoing: bool = False


class ViewNode(BaseModel):
    id: str
    kind: str
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)
    virtual: bool = False
    matched: bool = False
    expandable: Expandable = Field(default_factory=Expandable)
    finding_ids: list[str] = Field(default_factory=list)


class ViewEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: str
    properties: dict[str, Any] = Field(default_factory=dict)
    finding_ids: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    id: str
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ViewMetadata(BaseModel):
    mode: str
    visible_node_count: int
    visible_edge_count: int
    matching_node_count: int = 0
    truncated: bool = False
    time_range: dict[str, str] | None = None


class GraphView(BaseModel):
    nodes: list[ViewNode]
    edges: list[ViewEdge]
    findings: list[Finding]
    metadata: ViewMetadata


class NodeDetails(BaseModel):
    """Complete persisted-node data plus graph-wide relationship counts."""

    node: ViewNode
    incoming_count: int
    outgoing_count: int


def session_to_graph_view(session: SessionGraph) -> GraphView:
    """Convert a complete pending session into a renderer-neutral graph.

    Disconnected nodes and missing references remain visible so the preview
    exposes validation problems instead of hiding them.
    """
    nodes: dict[str, ViewNode] = {}
    edges: dict[str, ViewEdge] = {}
    findings: list[Finding] = []

    session_id = f"session:{session.session_id}"
    nodes[session_id] = ViewNode(
        id=session_id,
        kind="Session",
        label=session.summary,
        properties={
            "session_id": session.session_id,
            "timestamp": session.timestamp.isoformat(),
            "tool": session.tool.value,
            "project": session.project or "",
            "summary": session.summary,
        },
    )

    artifact_counts = Counter(artifact.identifier for artifact in session.artifacts)
    artifact_ids: set[str] = set()
    for artifact in session.artifacts:
        node_id = f"artifact:{artifact.identifier}"
        artifact_ids.add(artifact.identifier)
        nodes[node_id] = ViewNode(
            id=node_id,
            kind="Artifact",
            label=artifact.identifier,
            properties={
                "identifier": artifact.identifier,
                "type": artifact.type.value,
                "project": artifact.project or session.project or "",
                "notes": artifact.notes or "",
            },
        )
        if artifact_counts[artifact.identifier] > 1:
            _add_finding(
                findings,
                nodes,
                Finding(
                    id=f"duplicate-artifact:{artifact.identifier}",
                    severity="error",
                    code="duplicate_identifier",
                    message=f"Artifact identifier appears more than once: {artifact.identifier}",
                    node_ids=[node_id],
                    evidence={"count": artifact_counts[artifact.identifier]},
                ),
            )

    referenced_artifacts: set[str] = set()
    problem_ids: dict[int, str] = {}

    for index, decision in enumerate(session.decisions):
        node_id = f"decision:{session.session_id}:{index}"
        nodes[node_id] = ViewNode(
            id=node_id,
            kind="Decision",
            label=decision.description,
            properties=decision.model_dump(mode="json"),
        )
        _add_edge(edges, session_id, node_id, "CONTAINS")
        _add_artifact_edges(
            node_id, decision.artifacts, artifact_ids, referenced_artifacts, nodes, edges, findings
        )

    for index, problem in enumerate(session.problems):
        node_id = f"problem:{session.session_id}:{index}"
        problem_ids[index] = node_id
        nodes[node_id] = ViewNode(
            id=node_id,
            kind="Problem",
            label=problem.description,
            properties=problem.model_dump(mode="json"),
        )
        _add_edge(edges, session_id, node_id, "CONTAINS")
        _add_artifact_edges(
            node_id, problem.artifacts, artifact_ids, referenced_artifacts, nodes, edges, findings
        )

    for index, solution in enumerate(session.solutions):
        node_id = f"solution:{session.session_id}:{index}"
        nodes[node_id] = ViewNode(
            id=node_id,
            kind="Solution",
            label=solution.description,
            properties=solution.model_dump(mode="json"),
        )
        _add_edge(edges, session_id, node_id, "CONTAINS")
        if solution.problem_ref is not None:
            if solution.problem_ref in problem_ids:
                _add_edge(edges, problem_ids[solution.problem_ref], node_id, "SOLVED_BY")
            else:
                _add_missing_reference(
                    source_id=node_id,
                    reference_type="problem",
                    reference=str(solution.problem_ref),
                    relationship="SOLVED_BY",
                    nodes=nodes,
                    edges=edges,
                    findings=findings,
                )
        _add_artifact_edges(
            node_id, solution.artifacts, artifact_ids, referenced_artifacts, nodes, edges, findings
        )

    thread_ids = {thread.id for thread in session.threads}
    for thread in session.threads:
        node_id = f"thread:{thread.id}"
        nodes[node_id] = ViewNode(
            id=node_id,
            kind="Thread",
            label=thread.title,
            properties={
                **thread.model_dump(mode="json"),
                "project": session.project or "",
            },
        )
        _add_edge(edges, session_id, node_id, "SPAWNS")
        _add_artifact_edges(
            node_id, thread.artifacts, artifact_ids, referenced_artifacts, nodes, edges, findings
        )

    for thread in session.threads:
        source_id = f"thread:{thread.id}"
        for blocked_id in thread.blocks:
            _add_thread_relationship(
                source_id, blocked_id, thread_ids, "BLOCKS", nodes, edges, findings
            )
        for blocker_id in thread.blocked_by:
            _add_thread_relationship(
                f"thread:{blocker_id}", thread.id, thread_ids, "BLOCKS", nodes, edges, findings
            )

    for ref in session.thread_refs:
        node_id = f"thread:{ref.id}"
        if node_id not in nodes:
            nodes[node_id] = ViewNode(
                id=node_id,
                kind="Thread",
                label=ref.id,
                properties=ref.model_dump(mode="json"),
                virtual=True,
            )
        relationship = (
            "RESOLVES"
            if ref.status in (ThreadStatus.RESOLVED, ThreadStatus.ABANDONED)
            else "CONTINUES"
        )
        _add_edge(edges, session_id, node_id, relationship)

    for artifact_id in artifact_ids - referenced_artifacts:
        node_id = f"artifact:{artifact_id}"
        _add_finding(
            findings,
            nodes,
            Finding(
                id=f"orphan-artifact:{artifact_id}",
                severity="error",
                code="orphan_artifact",
                message=f"Artifact has no relationships: {artifact_id}",
                node_ids=[node_id],
            ),
        )

    timestamp = session.timestamp.isoformat()
    return GraphView(
        nodes=list(nodes.values()),
        edges=list(edges.values()),
        findings=findings,
        metadata=ViewMetadata(
            mode="session_preview",
            visible_node_count=len(nodes),
            visible_edge_count=len(edges),
            time_range={"minimum": timestamp, "maximum": timestamp},
        ),
    )


def _add_artifact_edges(
    source_id: str,
    references: list[str],
    artifact_ids: set[str],
    referenced_artifacts: set[str],
    nodes: dict[str, ViewNode],
    edges: dict[str, ViewEdge],
    findings: list[Finding],
) -> None:
    for artifact_id in references:
        if artifact_id in artifact_ids:
            referenced_artifacts.add(artifact_id)
            _add_edge(edges, source_id, f"artifact:{artifact_id}", "TOUCHES")
        else:
            _add_missing_reference(
                source_id=source_id,
                reference_type="artifact",
                reference=artifact_id,
                relationship="TOUCHES",
                nodes=nodes,
                edges=edges,
                findings=findings,
            )


def _add_thread_relationship(
    source_id: str,
    target_thread_id: str,
    local_thread_ids: set[str],
    relationship: str,
    nodes: dict[str, ViewNode],
    edges: dict[str, ViewEdge],
    findings: list[Finding],
) -> None:
    target_id = f"thread:{target_thread_id}"
    source_thread_id = source_id.removeprefix("thread:")
    if source_thread_id not in local_thread_ids:
        _ensure_external_thread(source_id, source_thread_id, nodes)
    if target_thread_id not in local_thread_ids:
        _ensure_external_thread(target_id, target_thread_id, nodes)
        finding_id = f"missing-thread:{source_thread_id}:{target_thread_id}"
        edge = _add_edge(edges, source_id, target_id, relationship)
        edge.finding_ids.append(finding_id)
        _add_finding(
            findings,
            nodes,
            Finding(
                id=finding_id,
                severity="warning",
                code="missing_thread_reference",
                message=(
                    f"Thread relationship references a thread outside this preview: "
                    f"{target_thread_id}"
                ),
                node_ids=[source_id, target_id],
                edge_ids=[edge.id],
            ),
        )
        return
    _add_edge(edges, source_id, target_id, relationship)


def _ensure_external_thread(
    node_id: str, thread_id: str, nodes: dict[str, ViewNode]
) -> None:
    if node_id not in nodes:
        nodes[node_id] = ViewNode(
            id=node_id,
            kind="Thread",
            label=thread_id,
            properties={"thread_id": thread_id},
            virtual=True,
        )


def _add_missing_reference(
    source_id: str,
    reference_type: str,
    reference: str,
    relationship: str,
    nodes: dict[str, ViewNode],
    edges: dict[str, ViewEdge],
    findings: list[Finding],
) -> None:
    target_id = f"missing:{reference_type}:{reference}"
    finding_id = f"missing-{reference_type}:{source_id}:{reference}"
    if target_id not in nodes:
        nodes[target_id] = ViewNode(
            id=target_id,
            kind="Missing",
            label=reference,
            properties={"reference_type": reference_type, "reference": reference},
            virtual=True,
        )
    edge = _add_edge(edges, source_id, target_id, relationship)
    edge.finding_ids.append(finding_id)
    _add_finding(
        findings,
        nodes,
        Finding(
            id=finding_id,
            severity="error",
            code=f"missing_{reference_type}_reference",
            message=f"{source_id} references missing {reference_type}: {reference}",
            node_ids=[source_id, target_id],
            edge_ids=[edge.id],
        ),
    )


def _add_edge(
    edges: dict[str, ViewEdge], source: str, target: str, kind: str
) -> ViewEdge:
    edge_id = f"{source}|{kind}|{target}"
    if edge_id not in edges:
        edges[edge_id] = ViewEdge(
            id=edge_id,
            source=source,
            target=target,
            kind=kind,
        )
    return edges[edge_id]


def _add_finding(
    findings: list[Finding], nodes: dict[str, ViewNode], finding: Finding
) -> None:
    if any(existing.id == finding.id for existing in findings):
        return
    findings.append(finding)
    for node_id in finding.node_ids:
        if node_id in nodes and finding.id not in nodes[node_id].finding_ids:
            nodes[node_id].finding_ids.append(finding.id)
