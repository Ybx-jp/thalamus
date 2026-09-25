"""Remove named Sources from the graph, with what was derived from them and nothing else.

For a Source that should never have been written: an ingest that ran with its archive
somewhere else, so the evidence floor it claims is not there (issue #164). Named by
vertex id, never selected by a pattern, because the decision that a Source is bad is
the operator's and a selector would be a second, unreviewed one.

What goes with a Source is decided by derivation, the same rule `scan_retirement` uses
for Artifacts: **a vertex goes only when everything it rests on is going.**

- A Chunk or Claim goes when every `DERIVED_FROM` target it has is a retired Source. A
  Claim is content-addressed, so the same statement ingested from a second document
  carries a second `DERIVED_FROM` edge and survives on it.
- An Entity is scope-wide and shared across documents. It goes only when every vertex
  adjacent to it is going, since one with no edge left is an orphan that
  `contract check` would report forever.

**What the removal costs is printed before it happens.** Edges from surviving vertices
onto a retiring Claim or Chunk (a Trace's `RETURNS`, an Exchange's citation) are dropped
with it, and they are recall and consultation history. The dry run counts them by
label, so the history lost is part of the decision rather than discovered after it.

Retained bytes are not touched; there are usually none, which is why these are retired.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from gremlin_python.process.graph_traversal import GraphTraversalSource, __
from gremlin_python.process.traversal import T

from thalamus.substrate.scan_retirement import Doomed


@dataclass
class SourceRetirement:
    sources: list[Doomed] = field(default_factory=list)
    chunks: list[Doomed] = field(default_factory=list)
    claims: list[Doomed] = field(default_factory=list)
    entities: list[Doomed] = field(default_factory=list)
    # Claims that also derive from a Source not being retired: (vid, surviving targets).
    kept_claims: list[tuple[str, int]] = field(default_factory=list)
    # Entities still referenced from outside the retirement: (name, surviving edges).
    kept_entities: list[tuple[str, int]] = field(default_factory=list)
    # Edges from surviving vertices that go with a retiring vertex, by edge label.
    lost_edges: Counter = field(default_factory=Counter)

    def doomed_vids(self) -> list[str]:
        return [d.vid for d in (*self.claims, *self.chunks, *self.entities, *self.sources)]

    def total(self) -> int:
        return len(self.doomed_vids())


def decide(
    *,
    sources: list[dict],
    derived: list[dict],
    entities: list[dict],
) -> SourceRetirement:
    """Work out what goes, given rows already read. Pure, and the part worth testing.

    `derived` rows are the Claims and Chunks with a `DERIVED_FROM` edge onto a named
    Source: `vid`, `label`, `detail`, `derived_from` (every target id) and `edges`
    (every incident edge as `(label, other_vid)`). `entities` rows carry `vid`, `name`
    and `neighbours` (every adjacent vertex id).
    """
    plan = SourceRetirement()
    retiring = {str(row["vid"]) for row in sources}
    for row in sources:
        plan.sources.append(
            Doomed(vid=str(row["vid"]), label="Source", detail=str(row.get("title", "")))
        )

    doomed: set[str] = set(retiring)
    for row in derived:
        targets = [str(t) for t in row.get("derived_from", ())]
        survivors = [t for t in targets if t not in retiring]
        entry = Doomed(vid=str(row["vid"]), label=str(row["label"]),
                       detail=str(row.get("detail", ""))[:100])
        if survivors:
            if entry.label == "Claim":
                plan.kept_claims.append((entry.vid, len(survivors)))
            continue
        doomed.add(entry.vid)
        (plan.claims if entry.label == "Claim" else plan.chunks).append(entry)

    for row in entities:
        survivors = [str(n) for n in row.get("neighbours", ()) if str(n) not in doomed]
        name = str(row.get("name", row["vid"]))
        if survivors:
            plan.kept_entities.append((name, len(survivors)))
        else:
            plan.entities.append(Doomed(vid=str(row["vid"]), label="Entity", detail=name))
            doomed.add(str(row["vid"]))

    for row in derived:
        if str(row["vid"]) not in doomed:
            continue
        for label, other in row.get("edges", ()):
            if str(other) not in doomed:
                plan.lost_edges[str(label)] += 1

    plan.kept_claims.sort()
    plan.kept_entities.sort()
    return plan


def plan(g: GraphTraversalSource, source_vids: list[str]) -> SourceRetirement:
    """Read the named Sources and everything derived from them, and decide what goes.

    Refuses an id that is not a Source vertex: retiring by id is only safe when every
    id names what the operator thinks it names.
    """
    source_rows = []
    for source_vid in source_vids:
        found = g.V(source_vid).element_map().to_list()
        if not found or found[0].get(T.label) != "Source":
            raise ValueError(f"`{source_vid}` is not a Source vertex in this graph")
        source_rows.append({"vid": source_vid, "title": found[0].get("title", "")})

    derived_rows: list[dict] = []
    for row in (
        g.V(*source_vids).in_("DERIVED_FROM").has_label("Claim", "Chunk").dedup()
        .project("vid", "label", "description", "ordinal")
        .by(T.id).by(T.label)
        .by(__.coalesce(__.values("description"), __.constant("")))
        .by(__.coalesce(__.values("ordinal"), __.constant("")))
        .to_list()
    ):
        vertex = str(row["vid"])
        derived_rows.append({
            "vid": vertex,
            "label": row["label"],
            "detail": row["description"] or f"chunk {row['ordinal']}",
            "derived_from": g.V(vertex).out("DERIVED_FROM").id_().to_list(),
            "edges": [
                (edge["label"], edge["other"])
                for edge in g.V(vertex).both_e()
                .project("label", "other").by(T.label).by(__.other_v().id_())
                .to_list()
            ],
        })

    entity_rows: list[dict] = []
    if derived_rows:
        for row in (
            g.V(*[r["vid"] for r in derived_rows]).out("ABOUT").has_label("Entity").dedup()
            .project("vid", "name").by(T.id)
            .by(__.coalesce(__.values("name"), __.constant("")))
            .to_list()
        ):
            entity_rows.append({
                "vid": row["vid"],
                "name": row["name"],
                "neighbours": g.V(row["vid"]).both().id_().to_list(),
            })

    return decide(sources=source_rows, derived=derived_rows, entities=entity_rows)


def retire(g: GraphTraversalSource, retirement: SourceRetirement) -> int:
    """Drop the planned vertices; incident edges go with them. Returns the count.

    Idempotent: a second run refuses, because the named Sources are no longer there.
    """
    doomed = retirement.doomed_vids()
    if not doomed:
        return 0
    g.V(*doomed).drop().iterate()
    return len(doomed)
