"""The core ontology — declared once, derived everywhere.

Before this module the node/edge vocabulary was hardcoded in seven places (schema,
writer, reader, mermaid, view_model, view_query, and the frontend legend), which meant
adding a node type touched all seven. That is exactly the "bespoke glue"
docs/01-federation-contract.md forbids, and M1's literature expert would have hit it
immediately. Everything downstream now derives from the tuples below.

Two contract rules are encoded here rather than described in prose:

1. **`Artifact` and `Agent` are global.** They are the unscoped node types — a single
   vertex per identifier, shared across every scope. Artifacts are the join key between
   scopes and much of why the main plane is connective at all. They are safe to share
   because they are tier-1 observations of the operator's own repo, not a poisoning
   vector. An Agent is safe for the same reason and one more: it carries no content at
   all, only an identity that acted, so sharing it moves no claim across a boundary.
   That is what lets an operator close a thread in any scope without the close becoming
   a scope crossing — the partition guards a channel for content, and a close has none.

2. **Which edges may cross a scope.** Direct expert→expert edges between *scoped*
   nodes are illegal: consultation routes through a session in the main scope, which is
   what makes an exchange a first-class memory event rather than a lost subagent
   transcript (docs/02). Edges into global nodes are not scope crossings at all — see
   the density note in docs/09 G3.

Consumers depend on **core types only**. An expert may add `kind` values (namespaced,
e.g. `literature/finding`) without any consumer changing: the plane and the eval loop
query the `Claim` label, not its subtypes. That is the whole reason Claim is one label
discriminated by `kind` rather than one label per subtype.
"""

from __future__ import annotations

from dataclasses import dataclass

MAIN_SCOPE = "main"


@dataclass(frozen=True)
class NodeType:
    label: str
    """Graph label, and the unit consumers are allowed to depend on."""

    id_prefix: str
    """Vertex-ID segment: `scope:<scope>:<id_prefix>:<local>`, or `<id_prefix>:<local>`
    when the type is global."""

    label_property: str
    """Which property renders as the human-readable label in the viewer."""

    scoped: bool = True
    """False only for globals: `Artifact` and `Agent`."""

    kinds: tuple[str, ...] = ()
    """Discriminator values, if this label has subtypes. Extensions may add more."""

    expandable: bool = True


@dataclass(frozen=True)
class EdgeType:
    label: str
    may_cross_scope: bool = False
    note: str = ""


CORE_NODES: tuple[NodeType, ...] = (
    NodeType("Session", "session", "summary"),
    NodeType("Thread", "thread", "title"),
    NodeType(
        "Claim",
        "claim",
        "description",
        kinds=("decision", "problem", "solution"),
    ),
    # Primary evidence, retained verbatim and content-addressed. A session transcript is a
    # tier-1 Source; a paper will be a tier-2 Source. Same node type — they differ only by
    # tier and locator, which is why bootstrapping transcripts is a zero-risk rehearsal of
    # the M1 ingestion path (docs/06).
    #
    # Source is what gives the provenance chain a FLOOR. Without it, a tier-1 claim's
    # `source` points at a Session whose content is a summary — a distillation of itself.
    # docs/03's inspector ("walk from a belief to where it came from") needs to terminate
    # in evidence, not in another summary.
    NodeType("Source", "source", "title", kinds=("transcript", "article")),
    # The knowledge half of G1: a domain concept in an expert's knowledge subgraph.
    # Scoped — each expert names its own world. Convergence across experts happens
    # through claims and global artifacts, never through shared entities: a shared
    # entity vocabulary would be a channel, and channels route through consultation.
    NodeType("Entity", "entity", "name", kinds=("concept", "technique", "system")),
    # A verbatim slice of a retained Source, co-indexed into retrieval beside claims
    # (lab/052). Tier 2 by construction — it is third-party source text, not a belief —
    # so it informs and never instructs (docs/05), and its DERIVED_FROM edge is what
    # makes reaching it provenance-mediated rather than provenance-free.
    # Literature scope only: the 2026-07-14 decision against chunk nodes stands for the
    # 98% of the archive that is session transcripts, where the node count is the
    # ~100x it predicted.
    NodeType("Chunk", "chunk", "text", expandable=False),
    # Global. Not scoped, deliberately. See module docstring.
    NodeType("Artifact", "artifact", "identifier", scoped=False),
    # Who acted, when the actor is not a session. Global for the same reason Artifact
    # is, plus one stronger: an Agent carries no content, only an identity, so it can
    # be an endpoint in any scope without moving anything across the boundary.
    #
    # It exists because a thread closed by the operator has no session behind it, and
    # the two alternatives are both worse: a bare status flip leaves nothing for an
    # adjudication to walk, and minting a Session for a conversation that never
    # happened corrupts the entrypoint surface. PROV-O's *attribution without activity*
    # pattern is the precedent — ascribe to the agent when the generating activity is
    # irrelevant (`scope:architect:source:6b96671ab84faf12ce3f041aca12c3f93a6df2ed242348810743179a68e69555`).
    NodeType("Agent", "agent", "name", scoped=False, expandable=False),
    # A retrieval event: one memory-tool call, recorded verbatim by the PostToolUse tap
    # and landed here by `thalamus eval sync`. The eval loop reads the same substrate it
    # grades — "the trace store IS a property graph" (docs/04) — so utility verdicts sit
    # next to the nodes they grade instead of in a side database. Scoped to the pin the
    # querying session ran under: a trace is episodic memory of that expert's use.
    NodeType("Trace", "trace", "query", expandable=False),
    # One inter-expert consultation (docs/02). The vertex IS the ticket: minting it
    # opens the exchange record, so an unrecorded consultation is impossible by
    # construction, and `consult_answer` is the only close path. Lives in `main` —
    # consultation routes through the main scope, never expert-to-expert — and holds
    # both sides of the exchange: what was asked (question, from_scope) and what was
    # served (answer, plus REFERENCES edges into the consulted scope's nodes).
    NodeType("Exchange", "exchange", "question", expandable=False),
)

CORE_EDGES: tuple[EdgeType, ...] = (
    EdgeType("CONTAINS", note="Session -> Claim"),
    EdgeType("SPAWNS", note="Session -> Thread"),
    EdgeType("CONTINUES", note="Session -> Thread"),
    # Two closers, one label, at two levels of detail. Distillation writes the bare
    # `Session -> Thread` when a transcript settles a thread; an operator-approved
    # close writes `Agent -> Thread` carrying its evidence in edge properties (basis,
    # role, on_behalf_of, surface, approval_ref, approver_evidence, closed_at,
    # disposition). PROV-O's qualification pattern licenses exactly this — the
    # qualified form implies the unqualified — and it is already the house idiom
    # (`RETURNS.used`, `DERIVED_FROM.anchors`). Consumers that only ask "is this thread
    # closed and by what" keep working against the label alone.
    #
    # `may_cross_scope` stays False and needs no exception: an Agent is global, and
    # `edge_crosses_scope` does not count a global endpoint as a crossing.
    EdgeType("RESOLVES", note="Session|Agent -> Thread"),
    EdgeType("BLOCKS", note="Thread -> Thread"),
    EdgeType("SOLVED_BY", note="Claim(problem) -> Claim(solution)"),
    EdgeType(
        "TOUCHES",
        may_cross_scope=True,
        note="* -> Artifact. Artifact is global, so this is not a scope crossing "
        "in the sense the density metric counts (docs/09 G3).",
    ),
    # Declared now, unused until M1/M3. They exist here so the contract can already
    # answer 'is this edge legal?' rather than growing the question later.
    EdgeType(
        "DERIVED_FROM",
        may_cross_scope=True,
        note="Session/Claim -> Source. Effective tier = max(tier) over this closure — "
        "'distillation does not launder' (docs/05). Carries an `anchors` property: the "
        "message UUIDs inside the Source that this node was distilled from, so the "
        "provenance walk lands on the exact evidence rather than a whole transcript.",
    ),
    EdgeType(
        "REFERENCES",
        may_cross_scope=True,
        note="main -> expert node, by ID. Never copies. From an Exchange it carries a "
        "`role` property: 'brief' (served into the consultation's expert brief) or "
        "'citation' (cited by the validated answer) — the evidence-support record of "
        "the exchange.",
    ),
    EdgeType(
        "CONSULTS",
        may_cross_scope=True,
        note="Session -> Exchange (docs/02). The consulting session's side of a "
        "consultation. The MCP server cannot see its caller's session id (a measured "
        "harness limit, lab/001), so this edge is landed by `eval sync`/distillation "
        "from the ticket carried in retrieval traces, not at mint time.",
    ),
    # The eval loop's layer 1 (docs/04). QUERIES parallels CONTAINS/SPAWNS: the session
    # is the hub, the trace is its child event. RETURNS records what the retrieval put
    # into context; after attribution it carries `used` (bool) and `evidence` — the
    # used-vs-ignored verdict lives on the edge because it is a fact about *this
    # retrieval* of the node, not about the node itself.
    EdgeType("QUERIES", note="Session -> Trace"),
    # Snapshot lineage. A session distilled while still open archives its transcript
    # as it stands, and a grown transcript hashes to a new blob — so one session can
    # legitimately hold several Source snapshots (docs/10, lab/002). Rather than
    # prevent that (immutable evidence is the point), the newer snapshot SUPERSEDES
    # the older, giving "the transcript of session X" a well-defined head: the Source
    # with no incoming SUPERSEDES edge. Superseded snapshots stay archived and
    # walkable — they are evidence of what earlier distillations saw.
    EdgeType(
        "SUPERSEDES",
        note="Source -> Source, within one evidence lineage: a session's transcript "
        "snapshots, or re-ingestions of one article origin (docs/06).",
    ),
    # Claim -> Entity: what an assertion is about. The knowledge subgraph's connective
    # tissue — entities are reached through the claims that mention them, so an entity
    # nobody asserts anything about is an orphan the contract rejects.
    EdgeType("ABOUT", note="Claim/Chunk -> Entity"),
    EdgeType(
        "ANCHORS",
        note="Claim -> Chunk. The claim's verbatim `citation` was found inside that "
        "chunk, so a note reaches the passage it came from. Carries `start`/`end`: "
        "the citation's character offsets within the Source text, which is the "
        "locator the 2026-07-14 decision promised and never built.",
    ),
    EdgeType(
        "ADJACENT_IN_TEXT",
        note="Chunk -> Chunk, document order, next-only. Lets a retrieved chunk expand "
        "to its neighbours — a secondary affordance, not the mechanism: expansion over "
        "verbatim chunks measured a no-op (lab/052).",
    ),
    EdgeType(
        "RETURNS",
        may_cross_scope=True,
        note="Trace -> Session/Claim/Thread/Artifact. Carries `used`/`evidence` after "
        "attribution. May cross scope: the reader serves expert knowledge claims into "
        "any session (tier-2, informs-never-instructs) and ticket-scoped consultation "
        "recall returns consulted-scope nodes — the trace records what the reader "
        "actually returned, and its legality is the reader's server-side policy, not "
        "the tap's. A trace that cannot point at what was served is a tap that lies.",
    ),
)

NODES_BY_LABEL: dict[str, NodeType] = {n.label: n for n in CORE_NODES}
EDGES_BY_LABEL: dict[str, EdgeType] = {e.label: e for e in CORE_EDGES}

GLOBAL_LABELS: frozenset[str] = frozenset(n.label for n in CORE_NODES if not n.scoped)
EXPANDABLE_LABELS: frozenset[str] = frozenset(n.label for n in CORE_NODES if n.expandable)
LABEL_PROPERTIES: dict[str, str] = {n.label: n.label_property for n in CORE_NODES}


def is_global(label: str) -> bool:
    """True if this node type is shared across all scopes."""
    return label in GLOBAL_LABELS


def vid(label: str, local_id: str, scope: str = MAIN_SCOPE) -> str:
    """Build a vertex ID.

    Global types ignore scope entirely — that is what makes them the join key:

        vid("Artifact", "src/foo.py")            -> 'artifact:src/foo.py'
        vid("Session", "abc", scope="main")      -> 'scope:main:session:abc'
        vid("Claim", "9f3a…", scope="literature")-> 'scope:literature:claim:9f3a…'
    """
    node = NODES_BY_LABEL[label]
    if not node.scoped:
        return f"{node.id_prefix}:{local_id}"
    return f"scope:{scope}:{node.id_prefix}:{local_id}"


def scope_of(vertex_id: str) -> str | None:
    """Scope encoded in a vertex ID, or None for globals."""
    if vertex_id.startswith("scope:"):
        return vertex_id.split(":", 2)[1]
    return None


def edge_crosses_scope(source_id: str, target_id: str) -> bool:
    """Does this edge cross a scope boundary *in the sense that matters*?

    Edges touching a global node are NOT crossings. This is load-bearing: if paths
    through the shared Artifact vertex counted, then any two experts that ever touched
    the same file would look densely interconnected, and the cross-scope density metric
    that grades roster granularity (docs/08 split/merge) would be measuring "same repo"
    instead of "same domain". See docs/09 G3.
    """
    source_scope = scope_of(source_id)
    target_scope = scope_of(target_id)
    if source_scope is None or target_scope is None:
        return False  # a global endpoint: shared vocabulary, not a channel
    return source_scope != target_scope
