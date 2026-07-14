"""Graph memory schema definitions and YAML validation.

Two things to know before reading:

**The YAML surface and the graph shape are deliberately different.** The extraction
skill emits three ergonomic lists — `decisions`, `problems`, `solutions` — because that
is what a model fills in reliably. They are *subtypes of `Claim`* in the type system and
*one `Claim` label discriminated by `kind`* in the graph (docs/09 G1). Consumers depend
on the `Claim` label only, so a future expert adding `kind: literature/finding` breaks
nobody.

**Provenance is stamped, not asked for.** Every node in the *graph* carries a trust
tier, a source, and an ingestion timestamp — the contract obligation from docs/05,
enforced at write time. But a session extraction does not have to *say* so: its
provenance is derivable (tier-1, the agent's own lived experience, sourced to the
session). Feeds writing curated third-party content supply it explicitly instead. The
obligation is on the graph, not on the YAML.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Optional

from pydantic import BaseModel, Field

from thalamus.contract.ontology import MAIN_SCOPE


class Tier(IntEnum):
    """Origin tier. Provenance, not quality — a brilliant paper is tier 2 forever.

    The ordering is meaningful: effective trust is the *floor* over a node's
    DERIVED_FROM closure, which is what makes "distillation does not launder"
    computable rather than aspirational (docs/05).
    """

    OPERATOR = 0  # the human, directly: pins, manual notes, curation decisions
    FIRST_PARTY = 1  # the agent's own lived experience: sessions, episodes, verdicts
    CURATED = 2  # external content from operator-approved sources
    WILD = 3  # external content from unvetted sources


class Provenance(BaseModel):
    """Where a node came from. Required on every node in the graph."""

    tier: Tier = Tier.FIRST_PARTY
    source: str = Field(description="operator | session:<id> | feed:<name> | <url>")
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    derived_from: list[str] = Field(
        default_factory=list,
        description="Vertex IDs this was distilled from. Effective tier is the floor "
        "over the transitive closure: an agent's summary of a tier-2 paper is a tier-1 "
        "node whose effective trust is 2.",
    )


class Tool(str, Enum):
    CURSOR = "cursor"
    CLAUDE_CODE = "claude_code"


class ArtifactType(str, Enum):
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    MODULE = "module"
    DEPENDENCY = "dependency"
    CONFIG = "config"
    ENDPOINT = "endpoint"


class ProblemCategory(str, Enum):
    BUG = "bug"
    PERFORMANCE = "performance"
    DESIGN = "design"
    INTEGRATION = "integration"
    CONFIGURATION = "configuration"
    DEPENDENCY = "dependency"
    UNDERSTANDING = "understanding"


class ClaimKind(str, Enum):
    DECISION = "decision"
    PROBLEM = "problem"
    SOLUTION = "solution"


class Artifact(BaseModel):
    """A concrete thing in the operator's world: a file, class, module, dependency.

    **Global.** One vertex per identifier, shared across every scope — the join key
    between experts, and much of why the main plane is connective at all. Artifacts
    carry no scope. See contract/ontology.py.
    """

    identifier: str = Field(description="Unique path or qualified name")
    type: ArtifactType
    project: Optional[str] = None
    notes: Optional[str] = None
    provenance: Optional[Provenance] = None


class SourceKind(str, Enum):
    TRANSCRIPT = "transcript"


class Source(BaseModel):
    """Primary evidence, retained verbatim and content-addressed.

    A session transcript is a tier-1 Source; a paper will be a tier-2 Source. Same node
    type — they differ only by tier and locator.

    Source is what gives the provenance chain a **floor**. Without it, a tier-1 claim's
    `source` points at a Session whose stored content is a *summary* — a distillation of
    itself. docs/03's inspector ("pick any belief and walk to where it came from") has to
    terminate in evidence, not in another summary.

    The bytes live outside the graph, in a content-addressed archive; the node holds a
    pointer. Property graphs make poor blob stores, and the archive has to be immutable
    anyway — Claude Code rotates and compacts its own transcripts, so Thalamus must own
    the bytes rather than reference someone else's mutable file.
    """

    content_hash: str = Field(description="sha256 of the retained bytes — the node's identity")
    kind: SourceKind = SourceKind.TRANSCRIPT
    title: str = Field(description="Human-readable label")
    uri: str = Field(description="Where the retained bytes live, e.g. archive://<hash>")
    origin: Optional[str] = Field(None, description="Where it came from originally")
    byte_size: int = 0
    message_count: int = 0
    provenance: Optional[Provenance] = None


class Claim(BaseModel):
    """An assertion, with a provenance chain behind it.

    A Decision is an assertion with a rationale, made by the agent, inside an episode.
    A literature claim is an assertion with a citation, made by a source, inside an
    ingestion event. Same node, different provenance — which is what makes the trust
    model expressible, and what collapses contradiction detection into one mechanism
    instead of two (docs/09 G1).
    """

    kind: ClaimKind
    description: str = Field(description="The assertion itself")
    artifacts: list[str] = Field(default_factory=list, description="Artifact identifiers")
    provenance: Optional[Provenance] = None

    def content_id(self) -> str:
        """Stable, content-addressed identity.

        Replaces the old positional IDs (`decision:<session>:<index>`), under which a
        re-extraction with a reordered list silently overwrote *different* nodes, and no
        claim could ever be cited, superseded, or contradicted — fatal for a system whose
        headline demo is "walk from a belief to its source" (docs/09 G6).

        Note the consequence: the same claim asserted in two sessions now converges on
        **one** vertex with two CONTAINS edges. That is desirable — it is how "this keeps
        coming up" becomes a graph fact rather than a human impression, and it is exactly
        how Artifact has always behaved.
        """
        payload = self.model_dump(mode="json", exclude={"provenance", "artifacts"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class Decision(Claim):
    kind: ClaimKind = ClaimKind.DECISION
    rationale: str
    outcome: Optional[str] = None


class Problem(Claim):
    kind: ClaimKind = ClaimKind.PROBLEM
    category: ProblemCategory


class Solution(Claim):
    kind: ClaimKind = ClaimKind.SOLUTION
    approach: str
    worked: bool = True
    problem_ref: Optional[int] = Field(None, description="Index into problems list")


class Touch(BaseModel):
    """An artifact the session itself touched, with the evidence for it.

    Distinct from a Claim's `artifacts`: this is the *deterministic* layer, recovered
    exactly from tool-call records rather than inferred by a model. "This session edited
    this file, in these messages" is ground truth, and no LLM does it better.

    `anchors` are message UUIDs inside the session's Source. They are what let the
    provenance walk land on the precise evidence — the actual tool call — instead of
    handing the operator a 600 KB transcript and wishing them luck.
    """

    identifier: str
    anchors: list[str] = Field(default_factory=list, description="Message UUIDs in the Source")


class ThreadStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


class Thread(BaseModel):
    """An open thread of work — a continuation point, next step, unfinished inquiry.

    Threads persist across sessions until resolved, and they are the primary entrypoint
    into the graph. docs/01 generalizes exactly this: entrypoints are *how a graph makes
    itself legible*.
    """

    id: str = Field(description="Stable slug identifier (e.g. 'build-linking-workflow')")
    title: str = Field(description="Short actionable title")
    description: str = Field(description="What needs to happen, why it matters")
    status: ThreadStatus = ThreadStatus.OPEN
    artifacts: list[str] = Field(default_factory=list, description="Artifact identifiers")
    blocks: list[str] = Field(default_factory=list, description="Thread IDs this blocks")
    blocked_by: list[str] = Field(default_factory=list, description="Thread IDs blocking this")
    provenance: Optional[Provenance] = None


class ThreadRef(BaseModel):
    """Reference to an existing thread being continued or resolved in this session."""

    id: str = Field(description="Thread ID being referenced")
    status: ThreadStatus = Field(description="New status after this session's work")
    notes: Optional[str] = Field(None, description="What progress was made")


class SessionGraph(BaseModel):
    """A single session's extracted graph. This is what the extraction skill outputs."""

    session_id: str = Field(description="Unique session/conversation ID")
    timestamp: datetime = Field(default_factory=datetime.now)
    tool: Tool
    summary: str = Field(description="1-3 sentence summary of the session")

    scope: str = Field(
        default=MAIN_SCOPE,
        description="Which expert this session was pinned to. 'main' is the connective "
        "plane — a real scope like any other, distinguished topologically rather than "
        "structurally (docs/03).",
    )
    project: Optional[str] = Field(
        None,
        description="Primary project/repo. Orthogonal to scope: `project` is WHICH REPO, "
        "`scope` is WHICH EXPERT. A Thalamus session pinned to the agent-systems expert "
        "has both.",
    )

    artifacts: list[Artifact] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    problems: list[Problem] = Field(default_factory=list)
    solutions: list[Solution] = Field(default_factory=list)
    threads: list[Thread] = Field(default_factory=list, description="New threads opened here")
    thread_refs: list[ThreadRef] = Field(
        default_factory=list, description="Existing threads continued/resolved"
    )
    sources: list[Source] = Field(
        default_factory=list,
        description="Evidence this session was distilled from — normally its own transcript. "
        "The session gets a DERIVED_FROM edge to each, which is what gives its beliefs a "
        "provenance floor.",
    )
    touched: list[Touch] = Field(
        default_factory=list,
        description="Artifacts the session touched directly, recovered from tool-call records. "
        "The deterministic layer of the graph — exact, and free of model judgement.",
    )

    def claims(self) -> list[Claim]:
        """Every claim in the session, whatever its subtype."""
        return [*self.decisions, *self.problems, *self.solutions]

    def referenced_artifact_ids(self) -> set[str]:
        """Artifact identifiers something in this session points at."""
        referenced = {touch.identifier for touch in self.touched}
        for claim in self.claims():
            referenced.update(claim.artifacts)
        for thread in self.threads:
            referenced.update(thread.artifacts)
        return referenced

    def default_provenance(self) -> Provenance:
        """Provenance for nodes this session asserts without stating an origin.

        A session extraction is tier-1 by construction: the agent's own lived experience,
        sourced to the session that produced it.
        """
        return Provenance(
            tier=Tier.FIRST_PARTY,
            source=f"session:{self.session_id}",
            ingested_at=self.timestamp,
        )

    model_config = {
        "json_schema_extra": {
            "example": {
                "session_id": "abc123-def456",
                "timestamp": "2026-01-15T14:30:00",
                "tool": "claude_code",
                "scope": "main",
                "project": "thalamus",
                "summary": "Designed and scaffolded the graph memory substrate.",
                "artifacts": [
                    {"identifier": "src/thalamus/substrate/schema.py", "type": "file"},
                    {"identifier": "gremlinpython", "type": "dependency"},
                ],
                "decisions": [
                    {
                        "description": "Use TinkerGraph for storage",
                        "rationale": "Already have infra, real traversal semantics",
                        "outcome": "Proceeding with local Docker setup",
                        "artifacts": ["docker-compose.yml"],
                    }
                ],
                "problems": [],
                "solutions": [],
                "threads": [
                    {
                        "id": "build-linking-workflow",
                        "title": "Build cluster/summarization workflow",
                        "description": "Group related subgraphs behind summary nodes",
                        "status": "open",
                        "artifacts": ["src/thalamus/substrate/writer.py"],
                    }
                ],
                "thread_refs": [],
            }
        }
    }
