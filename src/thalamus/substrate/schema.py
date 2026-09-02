"""Graph memory schema definitions and YAML validation.

Two things to know before reading:

**The YAML surface and the graph shape are deliberately different.** The extraction
skill emits three ergonomic lists — `decisions`, `problems`, `solutions` — because that
is what a model fills in reliably. They are *subtypes of `Claim`* in the type system and
*one `Claim` label discriminated by `kind`* in the graph. Consumers depend
on the `Claim` label only, so a future expert adding `kind: literature/finding` breaks
nobody.

**Provenance is stamped, not asked for.** Every node in the *graph* carries a trust
tier, a source, and an ingestion timestamp — the contract obligation,
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

from pydantic import BaseModel, Field, field_validator

from thalamus.contract.ontology import MAIN_SCOPE


class Tier(IntEnum):
    """Origin tier. Provenance, not quality — a brilliant paper is tier 2 forever.

    The ordering is meaningful: effective trust is the *floor* over a node's
    DERIVED_FROM closure, which is what makes "distillation does not launder"
    computable rather than aspirational.
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


def _normalized(description: str) -> str:
    """The hashing form of a claim's description: whitespace collapsed, one trailing
    period dropped. Deliberately conservative — no casefolding, no stemming; anything
    smarter is semantic matching, which is a different (parked) mechanism."""
    return " ".join(description.split()).rstrip(".")


class ProjectEvidence(str, Enum):
    """How a session's `project` was reached — the value's own provenance.

    `project` answers two questions that want different standards of proof. As the
    **anchor** an absolute path is cut against, a wrong value does not fail to merge,
    it splits one file into two identities (`substrate/artifact_audit.py`), so only a
    proven value may be used. As a **recall key** — "show me my thalamus work" — an
    absent value simply loses the session, and a plausible one is better than none.
    One property served both, and nothing recorded which kind of claim it was.

    That gap is not hypothetical: re-anchoring the graph had to leave four sessions
    alone because a value `basename(cwd)` could not have produced is indistinguishable
    from a deliberate `THALAMUS_PROJECT` override, and there was no way to ask.

    Members are only the kinds something actually writes. A vocabulary carrying states
    no code path produces is a distinction the system cannot record, and adding one
    here later is a line of code.
    """

    # The session's working directory resolved to a checkout at extraction time.
    CWD = "cwd"
    # Every repo file the session touched sat in one checkout. Tool-call inputs, so
    # this is recorded evidence rather than a reading of what the session was about.
    TOUCH = "touch"


class Tool(str, Enum):
    CURSOR = "cursor"
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"


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
    ARTICLE = "article"


class Source(BaseModel):
    """Primary evidence, retained verbatim and content-addressed.

    A session transcript is a tier-1 Source; a paper will be a tier-2 Source. Same node
    type — they differ only by tier and locator.

    Source is what gives the provenance chain a **floor**. Without it, a tier-1 claim's
    `source` points at a Session whose stored content is a *summary* — a distillation of
    itself. The inspector ("pick any belief and walk to where it came from") has to
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
    instead of two.

    `kind` is a string, not the enum: core kinds come from ClaimKind, and experts add
    namespaced extensions (`literature/finding`) without touching core — consumers
    depend on the `Claim` label, never on the kind list.
    """

    kind: str
    description: str = Field(description="The assertion itself")
    artifacts: list[str] = Field(default_factory=list, description="Artifact identifiers")
    provenance: Optional[Provenance] = None
    external: bool = Field(
        False,
        description="The claim's substance rests on content the transcript fetched from "
        "outside (web pages, search results). Marked by the extractor and/or forced by "
        "the mechanical ingress floor; the write path answers it with tier-2 provenance "
        "— transcript-mediated content keeps third-party trust.",
    )

    @field_validator("kind", mode="before")
    @classmethod
    def _kind_to_plain_string(cls, value):
        """Accept ClaimKind members but store the bare value — graph properties and
        content hashes must never depend on Python enum identity."""
        return value.value if isinstance(value, Enum) else value

    def content_id(self) -> str:
        """Stable, content-addressed identity: **(kind, normalized description) only.**

        Replaces the old positional IDs (`decision:<session>:<index>`), under which a
        re-extraction with a reordered list silently overwrote *different* nodes, and no
        claim could ever be cited, superseded, or contradicted — fatal for a system whose
        headline demo is "walk from a belief to its source".

        The identity deliberately excludes the secondary fields (rationale, outcome,
        approach, citation …). The first design hashed all of them — "substance is part
        of identity" — and the first full-corpus measurement returned the verdict:
        convergence fired **zero** times across 1,089 claims, because two
        sessions never reproduce a rationale byte-for-byte. An identity function that
        never converges has no identity function. So the assertion is the identity and
        the supporting fields are properties, latest-write-wins — re-asserting a claim
        with a fresh rationale updates the node rather than forking it, and "this keeps
        coming up" becomes the graph fact it was always meant to be (two CONTAINS edges,
        exactly how Artifact has always behaved). Decision log 2026-07-15.
        """
        payload = {"kind": self.kind, "description": _normalized(self.description)}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


_REFERENCES_DESCRIPTION = (
    "Vertex IDs of the knowledge items this claim reasoned with — a literature claim "
    "or passage the session recalled and used as grounds. Each becomes a `USES` edge "
    "with role `reason`; relationships are edges, never list-valued properties."
)


class Decision(Claim):
    kind: str = ClaimKind.DECISION.value
    rationale: str
    outcome: Optional[str] = None
    references: list[str] = Field(default_factory=list, description=_REFERENCES_DESCRIPTION)


class Problem(Claim):
    kind: str = ClaimKind.PROBLEM.value
    category: ProblemCategory


class Solution(Claim):
    kind: str = ClaimKind.SOLUTION.value
    approach: str
    worked: bool = True
    problem_ref: Optional[int] = Field(None, description="Index into problems list")
    references: list[str] = Field(default_factory=list, description=_REFERENCES_DESCRIPTION)


class LiteratureClaim(Claim):
    """An assertion made by an external source — the knowledge half of G1.

    Tier 2 by construction: it records what a source *asserts*, not what the agent
    believes. The citation is the claim's own anchor into its Source, the same job
    message-UUID anchors do for transcripts.
    """

    kind: str = "literature/finding"
    citation: Optional[str] = Field(
        None, description="Short verbatim quote or section reference inside the source"
    )
    locator: Optional[str] = Field(None, description="Page, anchor, or section id")
    about: list[str] = Field(
        default_factory=list, description="Entity names this claim is about"
    )


class Entity(BaseModel):
    """A domain concept in an expert's knowledge subgraph: a technique, a system,
    a recurring idea. Scoped — each expert names its own world; convergence across
    experts happens through claims and artifacts, not shared entities.
    """

    name: str = Field(description="Canonical name — the node's identity within its scope")
    kind: str = Field("concept", description="concept | technique | system | <extension>")
    description: Optional[str] = None
    provenance: Optional[Provenance] = None

    def slug(self) -> str:
        """Vertex-ID segment: lowercase, hyphenated, stable across mentions."""
        return "-".join("".join(c if c.isalnum() else " " for c in self.name.lower()).split())


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
    into the graph. The federation contract generalizes exactly this: entrypoints are
    *how a graph makes itself legible*.
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


class CloseDisposition(str, Enum):
    """Why a thread closed, as a closed set — the stratification variable.

    Without it, resolution latency conflates "the work got done" with "this was never
    work", and the two have nothing to do with each other. `never_work` is the one that
    matters most here: a thread minted from a probe's return value was born wrong, and
    counting the weeks it sat open as latency measures nothing.
    """

    DONE = "done"
    SUPERSEDED = "superseded"
    NEVER_WORK = "never-work"
    ABANDONED = "abandoned"


class ThreadClose(BaseModel):
    """One operator-authorized close of a thread, written by an Agent, not a Session.

    The evidence rides on the edge. `basis` is the vertex the close rests on and is
    mandatory — an uncited close is a status flip with a name on it, and `audit_edges`
    rejects it. For a thread that was *born* wrong the basis is its own spawning
    session: unciteable-for-resolution is not unciteable.

    **A close is attributable, never authenticated, and this schema is deliberately
    incapable of claiming otherwise.** There is no `approved: bool`. The console has no
    authentication and does not pretend to; an in-session agent runs Bash at the
    operator's own uid and can read any secret the operator could. So what is recorded
    is *what kind of evidence exists* that the operator approved — `approver_evidence`
    — and a pointer to it. A forged approval is caught by corroborating the ledger
    afterwards, not prevented at the write.
    """

    thread_id: str = Field(description="Thread ID being closed, unqualified")
    scope: str = Field(default=MAIN_SCOPE, description="Scope the thread lives in")
    disposition: CloseDisposition = Field(description="Why it closed")
    basis: str = Field(
        description="Vertex ID this close rests on. Must resolve in the thread's own "
        "scope, or be global"
    )
    agent: str = Field(default="operator", description="Identity that closed it")
    role: str = Field(
        default="approver",
        description="What the agent did — PROV-O's prov:hadRole on the association",
    )
    on_behalf_of: Optional[str] = Field(
        None, description="Session that proposed this close, if one did"
    )
    surface: str = Field(description="Where approval was given: cli | console | session")
    approval_ref: str = Field(description="Ledger row this close was approved in")
    approver_evidence: str = Field(
        description="What kind of evidence exists that the operator approved — "
        "`cli:tty`, `console:<request-id>`, `session:<id>`. Never a bare assertion."
    )
    closed_at: str = Field(description="ISO-8601 timestamp of the approval")
    notes: Optional[str] = Field(None, description="Why, in the operator's words")

    @property
    def status(self) -> ThreadStatus:
        """The terminal status, derived rather than set.

        Two fields that can disagree will, and a thread marked `resolved` with
        disposition `never-work` is a contradiction a reader has to arbitrate. Work
        that got done or was overtaken is `resolved`; a thread that was never work, or
        that is being dropped undone, is `abandoned`.
        """
        if self.disposition in (CloseDisposition.NEVER_WORK, CloseDisposition.ABANDONED):
            return ThreadStatus.ABANDONED
        return ThreadStatus.RESOLVED

    def edge_properties(self) -> dict[str, object]:
        """The RESOLVES edge's payload. Absent optionals are omitted, never written
        empty — a property that is present and blank reads as an answered question."""
        properties: dict[str, object] = {
            "basis": self.basis,
            "role": self.role,
            "surface": self.surface,
            "approval_ref": self.approval_ref,
            "approver_evidence": self.approver_evidence,
            "closed_at": self.closed_at,
            "disposition": self.disposition.value,
        }
        if self.on_behalf_of:
            properties["on_behalf_of"] = self.on_behalf_of
        if self.notes:
            properties["notes"] = self.notes
        return properties


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
        "structurally.",
    )
    project: Optional[str] = Field(
        None,
        description="Primary project/repo. Orthogonal to scope: `project` is WHICH REPO, "
        "`scope` is WHICH EXPERT. A Thalamus session pinned to the agent-systems expert "
        "has both. Derived from `repo_root`'s basename, and absent when the session ran "
        "outside a checkout — a directory name is not a project.",
    )
    cwd: str = Field(
        default="",
        description="The directory the session started in, kept rather than consumed. "
        "`project` used to be this path's basename and nothing else survived, so a "
        "session's location was unrecoverable once the derivation proved wrong.",
    )
    repo_root: str = Field(
        default="",
        description="The checkout containing `cwd`, resolved at extraction time and "
        "stored because it is not re-derivable later: directories move and are deleted, "
        "and a path that resolves to no repo today may have had one when it was touched. "
        "Empty when the session ran outside a repo, which is a state and not a gap. This "
        "is the anchor a repo-relative path is cut against.",
    )
    project_evidence: Optional[ProjectEvidence] = Field(
        None,
        description="How `project` was reached, so a consumer can hold it to the "
        "standard its own use needs. Absent when there is no project to justify, and on "
        "sessions written before the field existed — absent means unknown, never proven.",
    )
    room: str = Field(
        default="",
        description="The collaboration this session witnessed, empty when it worked alone. "
        "A third orthogonal axis: `project` is WHICH REPO, `scope` is WHICH EXPERT, `room` "
        "is WHICH EVENT. Sessions sharing a room distilled one conversation, so their "
        "claims are correlated — a convergence count that treats them as distinct "
        "witnesses reads one event as N-fold agreement. Recorded at write time because "
        "the correlation is undetectable afterwards: nothing in a finished graph "
        "distinguishes three sessions that agreed from three that were in the room "
        "together.",
    )
    forked_from: str = Field(
        default="",
        description="The session this one was forked from (`claude --resume <id> "
        "--fork-session`), empty when it started cold. Where `room` says these sessions "
        "witnessed one event, this says **this session derives from that one** — the "
        "fork inherited the parent's context rather than reaching its own conclusions "
        "from scratch. That makes it a mapping over the parent's material and not an "
        "independent witness, so its agreement corroborates nothing. Unlike room "
        "membership the dependence here is exact rather than circumstantial, which is "
        "the whole reason it is worth a field of its own.",
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
                        "rationale": "Runs anywhere, real traversal semantics",
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


class Chunk(BaseModel):
    """A verbatim slice of a retained Source, co-indexed into retrieval.

    Tier 2 always: this is third-party source text, never a belief the agent formed, so
    it informs and never instructs. It carries no judgement and no
    interpretation — the whole point is that nothing was decided about it at write time,
    which is what an extracted claim cannot say. Where a claim is what the extractor
    chose to record, a chunk is what the document said.

    Identity is content-addressed on (source hash, ordinal): re-ingesting an unchanged
    document converges onto the same vertices, and a changed one mints a new Source and
    therefore a new chunk set, so versions never blend.
    """

    text: str = Field(description="The verbatim slice, exactly as the source had it")
    ordinal: int = Field(description="0-based position in document order")
    start: int = Field(description="Character offset of the slice within the Source text")
    end: int = Field(description="Character offset of the slice's end")
    about: list[str] = Field(
        default_factory=list,
        description="Entity names this chunk mentions. Chunk-to-chunk 'mentions' is a "
        "2-hop walk through these shared entities rather than a direct edge — entities "
        "are already deduped, so co-reachability costs no quadratic edge set.",
    )
    provenance: Optional[Provenance] = None

    def local_id(self, source_hash: str) -> str:
        return f"{source_hash}-{self.ordinal:04d}"


class KnowledgeBatch(BaseModel):
    """One ingestion event: what a feed writes into an expert's knowledge subgraph.

    The episodic twin is SessionGraph; this is the knowledge half of G1. The shape is
    deliberately smaller — a Source (the retained article, tier 2), the claims it
    asserts, and the entities those claims are about. No threads, no touches: feeds
    write knowledge, never episodic memory.
    """

    scope: str = Field(description="The expert's scope. Feeds never write `main`.")
    feed: str = Field("manual", description="Feed identity, e.g. `manual`")
    source: Source
    claims: list[LiteratureClaim] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    chunks: list[Chunk] = Field(
        default_factory=list,
        description="Verbatim slices of the Source, co-indexed beside the claims. "
        "Empty is legal and is what every pre-chunking batch has.",
    )
    anchors: dict[int, int] = Field(
        default_factory=dict,
        description="claim index -> chunk ordinal, where the claim's verbatim citation "
        "was located in that chunk. Sparse by design: a citation the model paraphrased "
        "gets no anchor rather than a guessed one.",
    )

    def default_provenance(self) -> Provenance:
        """Tier 2 by construction: curated third-party content, sourced to its origin.

        The tier is not the batch's to choose — a feed writing through this model gets
        CURATED, and anything wilder needs a different write path that does not exist.
        """
        return Provenance(
            tier=Tier.CURATED,
            source=self.source.origin or f"feed:{self.feed}",
            ingested_at=self.source.provenance.ingested_at
            if self.source.provenance
            else datetime.now(timezone.utc),
        )

    def referenced_entity_names(self) -> set[str]:
        referenced: set[str] = set()
        for claim in self.claims:
            referenced.update(claim.about)
        return referenced
