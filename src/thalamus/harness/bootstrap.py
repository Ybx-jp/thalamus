"""Bootstrap graph memory from retained session transcripts.

Two stages, and only one of them needs a model:

  Stage 1 (here)  — retain each transcript in the immutable archive, then derive Source,
                    Session, Artifact, and anchored TOUCHES edges from the tool-call
                    records. Exact, free, and instant.
  Stage 2 (later) — Claims and Threads, via the extraction skill. Needs judgement.

Stage 1 is not a stopgap. Because the transcripts are retained, stage 2 can be re-run at
any time — with a better skill, a better model, or a changed schema — and the graph
rebuilt from evidence. That is the property the archive buys: the graph is a materialized
view over an immutable log, not a lossy one-way distillation (docs/04).

**Bootstrap is not an ingestion feed in the docs/06 sense.** docs/06 says feeds write only
into an expert's *knowledge* subgraph, never into episodic memory — but that rule is about
untrusted third-party content. This is tier-1: the agent's own history, which is episodic
by definition. Bootstrap is the session-stop distillation of docs/07, applied retroactively
in batch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from thalamus.contract.conformance import check_session
from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.harness import transcripts
from thalamus.substrate.schema import SessionGraph


@dataclass
class BootstrapResult:
    session: SessionGraph | None
    transcript: Path
    content_hash: str = ""
    already_archived: bool = False
    secrets: dict[str, int] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    skipped: str = ""


def bootstrap_project(
    project_dir: str,
    *,
    projects_dir: Path | None = None,
    archive_base: Path | None = None,
    scope: str = MAIN_SCOPE,
) -> list[BootstrapResult]:
    """Retain and deterministically extract every transcript in one project directory."""
    discovered = transcripts.discover(projects_dir)
    paths = discovered.get(project_dir, [])

    results: list[BootstrapResult] = []
    for path in paths:
        results.append(_bootstrap_one(path, archive_base=archive_base, scope=scope))
    return results


def _bootstrap_one(
    path: Path, *, archive_base: Path | None, scope: str
) -> BootstrapResult:
    facts = transcripts.parse(path)

    # A transcript with no real exchange has nothing to remember. Writing it would add a
    # node the operator has to scroll past forever.
    if not facts.has_substance:
        return BootstrapResult(
            session=None, transcript=path, skipped="no substantive exchange — nothing to remember"
        )

    entry, secrets = transcripts.retain(path, archive_base=archive_base)
    session = transcripts.to_session_graph(
        facts,
        content_hash=entry.content_hash,
        uri=entry.uri,
        byte_size=entry.byte_size,
        scope=scope,
    )

    return BootstrapResult(
        session=session,
        transcript=path,
        content_hash=entry.content_hash,
        already_archived=entry.already_present,
        secrets=secrets,
        issues=check_session(session),
    )
