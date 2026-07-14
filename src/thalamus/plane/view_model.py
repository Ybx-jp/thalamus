"""Renderer-neutral graph models and pending-session conversion.

Node and edge *kinds* are free-form strings here and on the TypeScript side, so the
transport was always ontology-neutral. What was not neutral were the hardcoded type
registries; those now come from contract/ontology.py, so a new node type does not need
a change in this file.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from thalamus.contract.ontology import vid
from thalamus.substrate.schema import Claim, SessionGraph, ThreadStatus


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

    Disconnected nodes and missing references remain visible, so the preview exposes
    validation problems instead of hiding them.
    """
    nodes: dict[str, ViewNode] = {}
    edges: dict[str, ViewEdge] = {}
    findings: list[Finding] = []
    scope = session.scope

    session_id = vid("Session", session.session_id, scope)
    provenance = session.default_provenance()
    nodes[session_id] = ViewNode(
        id=session_id,
        kind="Session",
        label=session.summary,
        properties={
            "session_id": session.session_id,
            "timestamp": session.timestamp.isoformat(),
            "tool": session.tool.value,
            "scope": scope,
            "project": session.project or "",
            "summary": session.summary,
            "tier": int(provenance.tier),
            "source": provenance.source,
        },
    )

    for source in session.sources:
        node_id = vid("Source", source.content_hash, scope)
        source_provenance = source.provenance or provenance
        nodes[node_id] = ViewNode(
            id=node_id,
            kind="Source",
            label=source.title,
            properties={
                **source.model_dump(mode="json", exclude={"provenance"}),
                "scope": scope,
                "tier": int(source_provenance.tier),
            },
        )
        # The edge that gives every belief in this session a provenance floor.
        _add_edge(edges, session_id, node_id, "DERIVED_FROM")

    artifact_counts = Counter(artifact.identifier for artifact in session.artifacts)
    artifact_ids: set[str] = set()
    for artifact in session.artifacts:
        node_id = vid("Artifact", artifact.identifier)  # global: no scope segment
        artifact_ids.add(artifact.identifier)
        artifact_provenance = artifact.provenance or provenance
        nodes[node_id] = ViewNode(
            id=node_id,
            kind="Artifact",
            label=artifact.identifier,
            properties={
                "identifier": artifact.identifier,
                "type": artifact.type.value,
                "project": artifact.project or session.project or "",
                "notes": artifact.notes or "",
                "tier": int(artifact_provenance.tier),
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

    # The deterministic layer: Session -> Artifact, anchored to the tool calls that did it.
    for touch in session.touched:
        if touch.identifier not in artifact_ids:
            _add_missing_reference(
                source_id=session_id,
                reference_type="artifact",
                reference=touch.identifier,
                relationship="TOUCHES",
                nodes=nodes,
                edges=edges,
                findings=findings,
            )
            continue
        referenced_artifacts.add(touch.identifier)
        edge = _add_edge(edges, session_id, vid("Artifact", touch.identifier), "TOUCHES")
        edge.properties["anchors"] = touch.anchors

    for claim in session.claims():
        node_id = _claim_id(claim, scope)
        claim_provenance = claim.provenance or provenance
        nodes[node_id] = ViewNode(
            id=node_id,
            kind="Claim",
            label=claim.description,
            properties={
                **claim.model_dump(mode="json", exclude={"provenance"}),
                "scope": scope,
                "tier": int(claim_provenance.tier),
            },
        )
        _add_edge(edges, session_id, node_id, "CONTAINS")
        _add_artifact_edges(
            node_id, claim.artifacts, artifact_ids, referenced_artifacts, nodes, edges, findings
        )

    for solution in session.solutions:
        if solution.problem_ref is None:
            continue
        if 0 <= solution.problem_ref < len(session.problems):
            problem = session.problems[solution.problem_ref]
            _add_edge(edges, _claim_id(problem, scope), _claim_id(solution, scope), "SOLVED_BY")
        else:
            _add_missing_reference(
                source_id=_claim_id(solution, scope),
                reference_type="problem",
                reference=str(solution.problem_ref),
                relationship="SOLVED_BY",
                nodes=nodes,
                edges=edges,
                findings=findings,
            )

    thread_ids = {thread.id for thread in session.threads}
    for thread in session.threads:
        node_id = vid("Thread", thread.id, scope)
        thread_provenance = thread.provenance or provenance
        nodes[node_id] = ViewNode(
            id=node_id,
            kind="Thread",
            label=thread.title,
            properties={
                **thread.model_dump(mode="json", exclude={"provenance"}),
                "scope": scope,
                "project": session.project or "",
                "tier": int(thread_provenance.tier),
            },
        )
        _add_edge(edges, session_id, node_id, "SPAWNS")
        _add_artifact_edges(
            node_id, thread.artifacts, artifact_ids, referenced_artifacts, nodes, edges, findings
        )

    for thread in session.threads:
        source_id = vid("Thread", thread.id, scope)
        for blocked_id in thread.blocks:
            _add_thread_relationship(
                source_id, blocked_id, thread_ids, scope, "BLOCKS", nodes, edges, findings
            )
        for blocker_id in thread.blocked_by:
            _add_thread_relationship(
                vid("Thread", blocker_id, scope),
                thread.id,
                thread_ids,
                scope,
                "BLOCKS",
                nodes,
                edges,
                findings,
            )

    for ref in session.thread_refs:
        node_id = vid("Thread", ref.id, scope)
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
        node_id = vid("Artifact", artifact_id)
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


def _claim_id(claim: Claim, scope: str) -> str:
    return vid("Claim", claim.content_id(), scope)


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
            _add_edge(edges, source_id, vid("Artifact", artifact_id), "TOUCHES")
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
    scope: str,
    relationship: str,
    nodes: dict[str, ViewNode],
    edges: dict[str, ViewEdge],
    findings: list[Finding],
) -> None:
    target_id = vid("Thread", target_thread_id, scope)
    source_thread_id = source_id.rsplit(":", 1)[-1]
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
                    "Thread relationship references a thread outside this preview: "
                    f"{target_thread_id}"
                ),
                node_ids=[source_id, target_id],
                edge_ids=[edge.id],
            ),
        )
        return
    _add_edge(edges, source_id, target_id, relationship)


def _ensure_external_thread(node_id: str, thread_id: str, nodes: dict[str, ViewNode]) -> None:
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


def _add_edge(edges: dict[str, ViewEdge], source: str, target: str, kind: str) -> ViewEdge:
    edge_id = f"{source}|{kind}|{target}"
    if edge_id not in edges:
        edges[edge_id] = ViewEdge(id=edge_id, source=source, target=target, kind=kind)
    return edges[edge_id]


def _add_finding(findings: list[Finding], nodes: dict[str, ViewNode], finding: Finding) -> None:
    if any(existing.id == finding.id for existing in findings):
        return
    findings.append(finding)
    for node_id in finding.node_ids:
        if node_id in nodes and finding.id not in nodes[node_id].finding_ids:
            nodes[node_id].finding_ids.append(finding.id)
