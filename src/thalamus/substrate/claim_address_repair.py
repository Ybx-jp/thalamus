"""Move mis-addressed Claims back to the address their own content produces.

A Claim's vertex id carries a hash of its `(kind, normalized description)`, so the id
is a claim *about* the content. `audit_content_addresses` re-asks it and reports the
vertices that no longer satisfy it. This is the repair, and the audit's split is the
reason there are two of them rather than one.

**A stale vertex is rewired, then dropped.** An identity re-key left it behind: its
twin at the recomputed id holds the `CONTAINS` and the subtype edges, and the stale
member holds only what it acquired *after* the re-key — `RETURNS` from traces, and in
one case a `REFERENCES` from a consultation. Dropping it outright would discard the
record that retrieval ever surfaced that content, including the citation, which is
the evidence the eval loop's witnessed-vs-used question is asked against. So the
edges move first.

**Some of those moves collapse, and that is a correction.** Where a trace already
`RETURNS` the twin, it returned the same claim twice under two ids and its fan-out
was counted as two. Merging the pair does not rewrite that measurement, it repairs
it — but it does change a number that has been reported, so a collapse is planned,
counted and printed rather than absorbed silently.

**A wrong-address vertex is re-minted, not renamed.** It has no twin: it is the live
record, session-contained and edge-complete, sitting at an id an in-place property
rewrite invalidated. Rewriting the id back is what produced this class in the first
place, so the repair a content-addressed store allows is to mint at the correct
address, move every edge, and drop the old vertex — the operation the re-key
performed correctly, applied to the ones it could not have known about.

The old ids survive in retained transcripts and in the trace ledger, and nothing here
can reach those. `eval sync` already answers for them: it builds a `RETURNS` edge only
to a node still present in the graph and counts the rest as dangling, so a re-sync of
the historical ledger reports the old address as gone rather than re-creating it.

**Identity is never restated here.** The expected address is recomputed by calling
`Claim.content_id` and `vid`, the same two functions the write path mints through, so
a change to the identity function moves this migration with it instead of past it.

`classify` and `moved_edges` are pure over rows already read, which is deliberately
where the judgement that decides a deletion lives — the same split
`scan_retirement.decide` makes, and for the same reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from gremlin_python.process.graph_traversal import GraphTraversalSource, __
from gremlin_python.process.traversal import Direction as GremlinDirection
from gremlin_python.process.traversal import Merge, T

from thalamus.contract.ontology import MAIN_SCOPE, scope_of, vid
from thalamus.substrate.schema import Claim

_CLAIM = "Claim"

# `(label, other endpoint, incoming)` — what makes two edges the same edge for the
# purpose of deciding whether a move merges rather than adds.
EdgeKey = tuple[str, str, bool]


@dataclass(frozen=True)
class MovedEdge:
    """One incident edge, and what re-creating it at the destination would do.

    `collapses` is true when the destination already holds an edge with this label
    to (or from) the same neighbour. The move is then a merge: the edge is not
    re-created, and one edge stops existing. That is the case worth printing.
    """

    label: str
    other: str
    incoming: bool
    properties: dict[str, object] = field(default_factory=dict)
    collapses: bool = False

    @property
    def key(self) -> EdgeKey:
        return (self.label, self.other, self.incoming)

    def describe(self) -> str:
        arrow = (
            f"<-{self.label}- {self.other}" if self.incoming
            else f"-{self.label}-> {self.other}"
        )
        return f"{arrow}{'   [collapses]' if self.collapses else ''}"


@dataclass(frozen=True)
class Misaddressed:
    """A Claim whose id its own content does not produce, and where it belongs."""

    vertex_id: str
    target: str
    kind: str
    description: str
    twinned: bool


@dataclass(frozen=True)
class Rewire:
    """A stale duplicate: move its edges onto the twin, then drop it."""

    stale: str
    twin: str
    kind: str
    description: str
    edges: tuple[MovedEdge, ...]

    @property
    def collapsing(self) -> tuple[MovedEdge, ...]:
        return tuple(e for e in self.edges if e.collapses)


@dataclass(frozen=True)
class Remint:
    """A live record at a wrong address: mint at the right one, move everything, drop."""

    old: str
    new: str
    kind: str
    description: str
    properties: dict[str, object]
    edges: tuple[MovedEdge, ...]


@dataclass
class AddressRepair:
    rewires: list[Rewire] = field(default_factory=list)
    remints: list[Remint] = field(default_factory=list)
    examined: int = 0

    def total(self) -> int:
        return len(self.rewires) + len(self.remints)

    def collapses(self) -> int:
        return sum(len(r.collapsing) for r in self.rewires)


def expected_vid(vertex_id: str, kind: str, description: str) -> str:
    """The address this content produces, in this vertex's own scope."""
    content_id = Claim(kind=kind, description=description).content_id()
    return vid(_CLAIM, content_id, scope=scope_of(vertex_id) or MAIN_SCOPE)


def classify(rows: Sequence[tuple[str, str, str]]) -> list[Misaddressed]:
    """Which Claims are at an address their content does not produce.

    Pure over `(vertex id, kind, description)`. `twinned` decides the repair and is
    the one judgement here that can be wrong in a costly direction: a vertex read as
    twinned is dropped, so the twin lookup is built from this same row set — a vertex
    that is not in the graph cannot excuse one that is — and is scope-qualified,
    because `vid` puts the scope in the address and two scopes may legitimately hold
    the same content at the same hash.
    """
    known = {vertex_id for vertex_id, _, _ in rows}
    found = []
    for vertex_id, kind, description in rows:
        target = expected_vid(vertex_id, kind, description)
        if vertex_id == target:
            continue
        found.append(Misaddressed(vertex_id, target, kind, description, target in known))
    found.sort(key=lambda m: m.vertex_id)
    return found


def moved_edges(
    incident: Sequence[MovedEdge], destination_keys: frozenset[EdgeKey] | set[EdgeKey]
) -> tuple[MovedEdge, ...]:
    """Stamp each incident edge with whether re-creating it merges into an existing one."""
    return tuple(
        MovedEdge(e.label, e.other, e.incoming, e.properties, e.key in destination_keys)
        for e in incident
    )


def flatten(properties: Mapping[str, object]) -> dict[str, object]:
    """`value_map()` returns every property as a list; the write path wants the value.

    An empty list is dropped rather than written as `None`: a property the source
    vertex does not carry must not appear on the destination carrying nothing, which
    reads to every audit as a present-but-empty value.
    """
    flat: dict[str, object] = {}
    for key, value in properties.items():
        if isinstance(value, list):
            if value:
                flat[str(key)] = value[0]
        else:
            flat[str(key)] = value
    return flat


def claim_rows(g: GraphTraversalSource) -> list[tuple[str, str, str]]:
    """Every Claim as `(vertex id, kind, description)`.

    `contract.conformance` asks the same three columns for the audit, and this does not
    import it: conformance sits above substrate, and a migration reaching up for a read
    it can issue itself would invert the layers. The identity *logic* is shared — both
    call `Claim.content_id` — and only the traversal is written twice.
    """
    rows = (
        g.V().has_label(_CLAIM)
        .project("vid", "kind", "description")
        .by(T.id).by("kind").by("description")
        .to_list()
    )
    return [(str(r["vid"]), str(r["kind"]), str(r["description"])) for r in rows]


def incident_edges(g: GraphTraversalSource, vertex_id: str) -> tuple[MovedEdge, ...]:
    """Every edge on a vertex, unstamped — `collapses` is decided by `moved_edges`."""
    incoming = (
        g.V(vertex_id).in_e()
        .project("label", "other", "props")
        .by(__.label()).by(__.out_v().id_()).by(__.value_map())
        .to_list()
    )
    outgoing = (
        g.V(vertex_id).out_e()
        .project("label", "other", "props")
        .by(__.label()).by(__.in_v().id_()).by(__.value_map())
        .to_list()
    )
    return tuple(
        MovedEdge(str(r["label"]), str(r["other"]), incoming_side, dict(r["props"]))
        for rows, incoming_side in ((incoming, True), (outgoing, False))
        for r in rows
    )


def plan(g: GraphTraversalSource) -> AddressRepair:
    """What is at the wrong address, and what moving it would do.

    Reads only. Every Claim is examined, because a wrong address is only visible by
    recomputing the right one — there is no selector for it. Edges and properties are
    then read for the handful `classify` picked out, not for the whole label.
    """
    rows = claim_rows(g)
    repair = AddressRepair(examined=len(rows))

    for finding in classify(rows):
        incident = incident_edges(g, finding.vertex_id)
        if finding.twinned:
            held = {e.key for e in incident_edges(g, finding.target)}
            repair.rewires.append(
                Rewire(
                    finding.vertex_id, finding.target, finding.kind, finding.description,
                    moved_edges(incident, held),
                )
            )
        else:
            properties = dict(g.V(finding.vertex_id).value_map().next())
            repair.remints.append(
                Remint(
                    finding.vertex_id, finding.target, finding.kind, finding.description,
                    properties, moved_edges(incident, set()),
                )
            )
    return repair


def _move_edge(g: GraphTraversalSource, edge: MovedEdge, destination: str) -> None:
    from_vid, to_vid = (
        (edge.other, destination) if edge.incoming else (destination, edge.other)
    )
    traversal = g.merge_e(
        {T.label: edge.label, GremlinDirection.from_: from_vid, GremlinDirection.to: to_vid}
    )
    properties = flatten(edge.properties)
    if properties:
        traversal = traversal.option(Merge.on_create, properties).option(
            Merge.on_match, properties
        )
    traversal.iterate()


def write_repairs(g: GraphTraversalSource, repair: AddressRepair) -> tuple[int, int, int]:
    """Apply the plan. Returns `(rewired, re-minted, edges moved)`.

    Edges are re-created before the old vertex is dropped, so an interruption between
    the two leaves a duplicate edge — recoverable — rather than a lost one. Dropping a
    vertex takes its remaining edges with it, which is what retires the collapsing ones
    without a second traversal.

    Idempotent: a second run plans nothing, because every vertex it moved now sits at
    the address its own content produces and `classify` skips it.
    """
    moved = 0

    for rewire in repair.rewires:
        for edge in rewire.edges:
            if edge.collapses:
                continue
            _move_edge(g, edge, rewire.twin)
            moved += 1
        g.V(rewire.stale).drop().iterate()

    for remint in repair.remints:
        properties = flatten(remint.properties)
        (
            g.merge_v({T.id: remint.new, T.label: _CLAIM})
            .option(Merge.on_create, {T.id: remint.new, **properties})
            .option(Merge.on_match, properties)
            .iterate()
        )
        for edge in remint.edges:
            _move_edge(g, edge, remint.new)
            moved += 1
        g.V(remint.old).drop().iterate()

    return len(repair.rewires), len(repair.remints), moved
