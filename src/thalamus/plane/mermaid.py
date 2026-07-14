"""Convert SessionGraph to Mermaid for visual verification.

Superseded for interactive use by the Cytoscape viewer in this package; retained
because the `memory_visualize` MCP tool still renders pending extractions with it.
"""

from __future__ import annotations

import re

from thalamus.contract.conformance import prune_orphan_artifacts
from thalamus.substrate.schema import SessionGraph

MAX_LABEL_LEN = 60


def session_to_mermaid(session: SessionGraph) -> str:
    """Convert a SessionGraph to a Mermaid graph TD diagram string.

    Uses subgraphs for labeled zones by node type and filters out
    orphan nodes (those with zero edges).
    """
    session = prune_orphan_artifacts(session)

    edges: list[str] = []
    artifact_index: dict[str, str] = {}
    thread_index: dict[str, str] = {}

    # Build artifact index
    for i, artifact in enumerate(session.artifacts):
        artifact_index[artifact.identifier] = f"A{i}"

    # Build thread index
    for i, thread in enumerate(session.threads):
        thread_index[thread.id] = f"T{i}"

    # Collect all edges first so we can determine which artifacts are referenced
    referenced_artifacts: set[str] = set()

    # Session -> Thread edges (SPAWNS)
    for i, thread in enumerate(session.threads):
        edges.append(f"    S0 -->|SPAWNS| T{i}")
        for artifact_id in thread.artifacts:
            if artifact_id in artifact_index:
                referenced_artifacts.add(artifact_id)
                edges.append(f"    T{i} -->|TOUCHES| {artifact_index[artifact_id]}")
        for blocked_id in thread.blocks:
            if blocked_id in thread_index:
                edges.append(f"    T{i} -->|BLOCKS| {thread_index[blocked_id]}")

    # Session -> ThreadRef edges (CONTINUES/RESOLVES)
    for i, ref in enumerate(session.thread_refs):
        edge_label = "RESOLVES" if ref.status.value in ("resolved", "abandoned") else "CONTINUES"
        edges.append(f"    S0 -->|{edge_label}| TR{i}")

    # Session -> Decision edges
    for i, decision in enumerate(session.decisions):
        edges.append(f"    S0 -->|CONTAINS| D{i}")
        for artifact_id in decision.artifacts:
            if artifact_id in artifact_index:
                referenced_artifacts.add(artifact_id)
                edges.append(f"    D{i} -->|TOUCHES| {artifact_index[artifact_id]}")

    # Session -> Problem edges
    for i, problem in enumerate(session.problems):
        edges.append(f"    S0 -->|CONTAINS| P{i}")
        for artifact_id in problem.artifacts:
            if artifact_id in artifact_index:
                referenced_artifacts.add(artifact_id)
                edges.append(f"    P{i} -->|TOUCHES| {artifact_index[artifact_id]}")

    # Session -> Solution edges
    for i, solution in enumerate(session.solutions):
        edges.append(f"    S0 -->|CONTAINS| Sol{i}")
        if solution.problem_ref is not None and 0 <= solution.problem_ref < len(session.problems):
            edges.append(f"    P{solution.problem_ref} -->|SOLVED_BY| Sol{i}")
        for artifact_id in solution.artifacts:
            if artifact_id in artifact_index:
                referenced_artifacts.add(artifact_id)
                edges.append(f"    Sol{i} -->|TOUCHES| {artifact_index[artifact_id]}")

    # Build the diagram with subgraph zones
    lines: list[str] = ["graph TD"]

    # Session zone (always exactly one node)
    session_label = _truncate(f"{session.session_id}\\n{session.summary}")
    lines.append('    subgraph session [Session]')
    lines.append(f'        S0["{session_label}"]')
    lines.append("    end")

    # Threads zone
    if session.threads or session.thread_refs:
        lines.append("    subgraph threads [Threads]")
        for i, thread in enumerate(session.threads):
            label = _truncate(f"({thread.status.value}) {thread.title}")
            lines.append(f'        T{i}["{label}"]')
        for i, ref in enumerate(session.thread_refs):
            label = _truncate(f"({ref.status.value}) {ref.id}")
            lines.append(f'        TR{i}["{label}"]')
        lines.append("    end")

    # Decisions zone
    if session.decisions:
        lines.append("    subgraph decisions [Decisions]")
        for i, decision in enumerate(session.decisions):
            label = _truncate(decision.description)
            lines.append(f'        D{i}["{label}"]')
        lines.append("    end")

    # Problems & Solutions zone
    if session.problems or session.solutions:
        lines.append("    subgraph problems_solutions [Problems and Solutions]")
        for i, problem in enumerate(session.problems):
            label = _truncate(f"({problem.category.value}) {problem.description}")
            lines.append(f'        P{i}["{label}"]')
        for i, solution in enumerate(session.solutions):
            label = _truncate(solution.description)
            lines.append(f'        Sol{i}["{label}"]')
        lines.append("    end")

    # Artifacts zone (only artifacts that have at least one edge)
    linked_artifacts = [
        (i, a) for i, a in enumerate(session.artifacts)
        if a.identifier in referenced_artifacts
    ]
    if linked_artifacts:
        lines.append("    subgraph artifacts [Artifacts]")
        for i, artifact in linked_artifacts:
            label = _truncate(f"({artifact.type.value}) {artifact.identifier}")
            lines.append(f'        A{i}["{label}"]')
        lines.append("    end")

    lines.append("")
    lines.extend(edges)
    return "\n".join(lines)




def _truncate(text: str, max_len: int = MAX_LABEL_LEN) -> str:
    """Truncate and escape text for Mermaid node labels."""
    escaped = _escape_mermaid(text.replace("\n", " "))
    if len(escaped) <= max_len:
        return escaped
    return escaped[: max_len - 3] + "..."


def _escape_mermaid(text: str) -> str:
    """Escape characters that break Mermaid quoted labels."""
    text = text.replace('"', "'")
    text = text.replace("[", "(").replace("]", ")")
    text = re.sub(r"[<>]", "", text)
    return text
