"""The propagation plan — a deterministic spread from the word-match hits over the graph's edges.

The memory reflex's second plan, and the no-model multi-hop baseline the agentic plan
has to beat. It starts where word match stops: the nodes `recall()` returned for the
anchors are the seeds, and activation spreads from them through the retrieval compiler
(`harness/retrieval.py`), one `expand_one_hop` call per seed and relation. No model is
in the loop and nothing here writes Gremlin.

The shape is HippoRAG's — Personalized PageRank from the query's matches — truncated to
`DEPTH` hops of power iteration from the seeds, client-side, because the Gremlin server
binds one plain graph with no GraphComputer and every vocabulary primitive confines
scope per call. Mass moves as a typed random walk: a node passes `DECAY` of its
activation on, split evenly across the relations that reached anything from it and
then across that relation's neighbours, so one solution a problem was resolved by
receives more than each of five sessions that touched the same file. The conditions
HippoRAG's results were measured under — one node type, uniformly extracted edges, a
specificity weight per seed — do not hold for this graph, and seeds are weighted
uniformly for want of a specificity statistic; whether the shape transfers is what the
plan comparison reads.

Two properties are inherited from `expand_one_hop` rather than chosen: a relation
reads at most `_HOP_WINDOW` neighbours and keeps the newest `LIMIT` of those readable,
so recency decides which neighbours of a hub the spread can reach at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from thalamus.harness.retrieval import Caps, Job, Refused
from thalamus.substrate import vocabulary
from thalamus.substrate.vocabulary import Row

# Hops of spread from the seeds; the second reaches a seed's neighbours' neighbours.
DEPTH = 2
# The share of a node's activation it passes on per hop.
DECAY = 0.5
# Neighbours read per seed and relation: `expand_one_hop`'s default, the size the
# vocabulary was measured at.
LIMIT = 5
# Nodes expanded on every hop after the first, strongest first. Hop one expands every
# seed.
FRONTIER = 3

# The job's ceilings. One word-match call, then every relation from each seed
# (`recall()` returns at most five nodes for the reflex's three candidates: #251) and
# from each frontier node. The node cap admits everything those calls can return: the
# compiler's default of 40 bounds what a model reads, but rows here never enter a
# model's context, and at 40 the cap bound on the first hop of every replayed anchor
# set, keeping whichever seed and relation were walked first rather than the strongest.
# The time cap stops the spread, and what the completed calls returned is still served.
_EXPANSIONS = (5 + FRONTIER * (DEPTH - 1)) * len(vocabulary.RELATIONS)
CAPS = Caps(calls=1 + _EXPANSIONS, nodes=_EXPANSIONS * LIMIT, seconds=8.0)


@dataclass
class Spread:
    """What the spread reached beyond its seeds, strongest first."""

    # (vertex id, activation) for every node reached that is not a seed.
    reached: list[tuple[str, float]] = field(default_factory=list)
    rows: dict[str, Row] = field(default_factory=dict)
    # node -> (relation, source node) of the largest single contribution it received.
    via: dict[str, tuple[str, str]] = field(default_factory=dict)
    hops: int = 0
    # The compiler's refusal that stopped the spread early, or "".
    stopped: str = ""


def propagate(job: Job, seeds: list[str]) -> Spread:
    """Spread activation from `seeds` (vertex ids this job returned) for `DEPTH` hops."""
    spread = Spread()
    activation = dict.fromkeys(seeds, 1.0)
    best: dict[str, float] = {}
    expanded: set[str] = set()
    frontier = list(seeds)

    for _ in range(DEPTH):
        incoming: dict[str, float] = {}
        for source in frontier:
            expanded.add(source)
            reached: dict[str, list[Row]] = {}
            for relation in vocabulary.RELATIONS:
                try:
                    rows = job.rows("expand_one_hop", {
                        "handle": job.handle_for(source), "relation": relation,
                        "limit": LIMIT,
                    })
                except Refused as refusal:
                    spread.stopped = str(refusal)
                    break
                if rows:
                    reached[relation] = rows
            if reached:
                share = activation[source] * DECAY / len(reached)
                for relation, rows in reached.items():
                    gain = share / len(rows)
                    for row in rows:
                        spread.rows.setdefault(row.vid, row)
                        incoming[row.vid] = incoming.get(row.vid, 0.0) + gain
                        if gain > best.get(row.vid, 0.0):
                            best[row.vid] = gain
                            spread.via[row.vid] = (relation, source)
            if spread.stopped:
                break
        for node, gain in incoming.items():
            activation[node] = activation.get(node, 0.0) + gain
        spread.hops += 1
        if spread.stopped:
            break
        frontier = [
            node for node, _ in sorted(incoming.items(), key=lambda kv: -kv[1])
            if node not in expanded
        ][:FRONTIER]
        if not frontier:
            break

    spread.reached = sorted(
        ((node, score) for node, score in activation.items() if node not in seeds),
        key=lambda item: -item[1],
    )
    return spread


# A row's kind in the words `reflex._kind_of` heads a word-match line with.
_KIND_WORDS = {"external": "external claim", "chunk": "source passage"}


def linked_line(handle: str, row: Row, relation: str, source_handle: str) -> str:
    """One digest line for a node the spread reached: the word-match line's fields,
    with the edge it came over in place of the anchors it matched."""
    fields = [handle, _KIND_WORDS.get(row.kind, row.kind), f"tier {row.tier}"]
    if row.date:
        fields.append(row.date)
    fields += [row.summary, f"via {relation} from {source_handle}"]
    return " · ".join(fields)
