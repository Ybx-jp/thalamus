"""Bootstrap graph memory from retained session transcripts.

Two stages, and only one of them needs a model:

  Stage 1 (here)  — retain each transcript in the immutable archive, then derive Source,
                    Session, Artifact, and anchored TOUCHES edges from the tool-call
                    records. Exact, free, and instant.
  Stage 2 (later) — Claims and Threads, via the extraction skill. Needs judgement.

Stage 1 is not a stopgap. Because the transcripts are retained, stage 2 can be re-run at
any time — with a better skill, a better model, or a changed schema — and the graph
rebuilt from evidence. That is the property the archive buys: the graph is a materialized
view over an immutable log, not a lossy one-way distillation.

**Bootstrap is not an ingestion feed.** Feeds write only into an expert's *knowledge*
subgraph, never into episodic memory — but that rule is about untrusted third-party
content. This is tier-1: the agent's own history, which is episodic by definition.
Bootstrap is the session-stop distillation, applied retroactively in batch.

**Both harnesses reach stage 1**, and the seam is narrow by construction. The two
readers differ only in how facts are *obtained* — Claude Code reads cwd and times
out of the transcript, Cursor is handed them by discovery, because its rows carry
neither. Everything downstream is shared: one `TranscriptFacts` intermediate, one
archive that has no opinion about which harness wrote the bytes, and one graph
builder that Cursor's delegates to before re-stamping the tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from thalamus.contract.conformance import check_session
from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.harness import agents, cursor_transcripts, transcripts
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
        results.append(
            _bootstrap_one(
                path,
                transcripts.parse(path),
                transcripts.to_session_graph,
                archive_base=archive_base,
                scope=scope,
            )
        )
    return results


def bootstrap_cursor(
    sessions: list,
    *,
    archive_base: Path | None = None,
) -> list[BootstrapResult]:
    """The same stage 1, for Cursor sessions the two discovery surfaces found.

    Session-oriented rather than project-oriented because Cursor's discovery is:
    a `EndedSession` already carries the scope, the cwd and the end time, which
    for Claude Code are read out of the transcript itself. That asymmetry is why
    the reader cannot simply be swapped — `cursor_transcripts.parse` needs the
    session context handed to it — and it is also why nothing else here forks.
    Both readers produce the same `TranscriptFacts`, the archive is
    harness-agnostic, and `cursor_transcripts.to_session_graph` delegates to the
    builder above and re-stamps the tool.

    Each session's own resolved scope is used, never a caller-supplied default:
    a Cursor session is pinned by `THALAMUS_SCOPE` at launch, and overriding that
    in batch would file a pinned expert's history into the wrong subgraph. A
    session with no resolved scope must be claimed before it reaches this point
    (`cursor_transcripts.claim_unresolved`).
    """
    results: list[BootstrapResult] = []
    for session in sessions:
        cwd, started_at = cursor_transcripts.session_context(session.session_id)
        facts = cursor_transcripts.parse(
            session.transcript_path,
            session_id=session.session_id,
            cwd=cwd or session.cwd,
            started_at=started_at,
            ended_at=session.ended_at,
        )
        results.append(
            _bootstrap_one(
                session.transcript_path,
                facts,
                cursor_transcripts.to_session_graph,
                archive_base=archive_base,
                scope=session.scope,
            )
        )
    return results


def _bootstrap_one(
    path: Path,
    facts,
    to_session_graph,
    *,
    archive_base: Path | None,
    scope: str,
) -> BootstrapResult:
    """Retain the bytes, build the deterministic subgraph, check it.

    Takes the parsed facts and the builder rather than reading them off a module,
    because the two harnesses differ in how facts are *obtained* and in nothing
    after that. Retention is shared outright: the archive stores bytes and has no
    opinion about which harness wrote them.
    """
    # A transcript with no real exchange has nothing to remember. Writing it would add a
    # node the operator has to scroll past forever.
    if not facts.has_substance:
        return BootstrapResult(
            session=None, transcript=path, skipped="no substantive exchange — nothing to remember"
        )

    # An extraction sandbox is not a session (harness/agents.py): distilling one
    # writes memory about the act of remembering, and it is reachable here even
    # when the discovery surface that offered it did not recognise the project.
    if agents.is_sandbox_cwd(facts.cwd):
        return BootstrapResult(
            session=None, transcript=path, skipped="extraction sandbox — not a session"
        )

    entry, secrets = transcripts.retain(path, archive_base=archive_base)
    # The ingress evidence a Cursor session was judged against is not in `path`, so
    # retaining the transcript alone would leave the floor's verdict resting on bytes
    # the archive never saw.
    transcripts.retain_ingress_receipt(facts, archive_base=archive_base)
    session = to_session_graph(
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
