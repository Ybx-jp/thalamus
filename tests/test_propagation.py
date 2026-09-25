"""
Propagation plan tests — the spread's arithmetic and its stopping, minus the graph.

Interfaces: thalamus.harness.propagation (propagate, linked_line, CAPS), run through a
            real thalamus.harness.retrieval.Job
Infrastructure: `expand_one_hop` replaced by a table of (node, relation) -> neighbours;
                no graph
Scope: how activation moves and ranks, which nodes each hop expands, and what a
       tripped cap leaves. The walk each relation stands for is the vocabulary's, tested
       in test_vocabulary.py; what the reflex serves from a spread is test_reflex.py's.
"""

from __future__ import annotations

import pytest

from thalamus.harness import propagation, retrieval
from thalamus.harness.propagation import linked_line, propagate
from thalamus.harness.retrieval import Caps, Job, Tool
from thalamus.substrate.vocabulary import Row


def _row(node_id: str, kind: str = "decision") -> Row:
    return Row(node_id, kind, 1, "2026-09-20", f"about {node_id}")


@pytest.fixture
def graph(monkeypatch):
    """`expand_one_hop` answering from `edges[(node, relation)]`; records each call."""
    edges: dict[tuple[str, str], list[str]] = {}
    walked: list[tuple[str, str]] = []

    def expand(g, node_id, relation, limit=5, scope="main", knowledge_scopes=None):
        walked.append((node_id, relation))
        return [_row(n) for n in edges.get((node_id, relation), [])][:limit]

    tool = retrieval.TOOLS["expand_one_hop"]
    monkeypatch.setitem(retrieval.TOOLS, "expand_one_hop",
                        Tool(tool.params, expand, knowledge=tool.knowledge))
    return edges, walked


def _job(seeds, caps=propagation.CAPS):
    job = Job(object(), scope="main", knowledge_scopes=[], prefix="R2", caps=caps)
    for seed in seeds:
        job.handle_for(seed)
    return job


def test_a_node_one_edge_reaches_outranks_one_of_five(graph):
    """
    Scenario: a problem was resolved by one solution and shares a file with five
    sessions.

    Verifications:
    - the seed's mass splits evenly across the relations that reached anything, then
      across each relation's neighbours: the solution gets DECAY/2, each session a
      fifth of that
    - each reached node records the edge its largest share came over
    - the seed itself is never among what the spread reached
    """
    edges, _ = graph
    edges[("P", "resolved_by")] = ["S"]
    edges[("P", "same_file")] = ["A", "B", "C", "D", "E"]

    spread = propagate(_job(["P"]), ["P"])

    ranked = dict(spread.reached)
    assert spread.reached[0][0] == "S"
    assert ranked["S"] == pytest.approx(propagation.DECAY / 2)
    assert ranked["A"] == pytest.approx(propagation.DECAY / 2 / 5)
    assert spread.via["S"] == ("resolved_by", "P")
    assert "P" not in ranked


def test_a_node_two_seeds_reach_outranks_one_reached_once(graph):
    edges, _ = graph
    edges[("P1", "same_file")] = ["N", "X"]
    edges[("P2", "same_file")] = ["N"]

    spread = propagate(_job(["P1", "P2"]), ["P1", "P2"])

    assert [node for node, _ in spread.reached] == ["N", "X"]
    assert dict(spread.reached)["N"] == pytest.approx(0.25 + 0.5)


def test_every_seed_is_expanded_then_only_the_strongest_frontier(graph):
    """
    Verifications:
    - hop one walks every relation from every seed
    - hop two walks only the FRONTIER strongest nodes hop one reached, never a node
      already expanded, and adds what it reaches at a further DECAY
    - a seed another seed reaches is not listed as reached
    """
    edges, walked = graph
    edges[("P", "same_file")] = ["Q", "A", "B", "C", "D"]
    edges[("P", "resolved_by")] = ["S"]
    edges[("Q", "resolved_by")] = ["P"]
    edges[("S", "threads")] = ["T"]

    spread = propagate(_job(["P", "Q"]), ["P", "Q"])

    from_seeds = {node for node, _ in walked[: 2 * len(propagation.vocabulary.RELATIONS)]}
    assert from_seeds == {"P", "Q"}
    second_hop = [node for node, _ in walked[2 * len(propagation.vocabulary.RELATIONS):]]
    assert len(set(second_hop)) == propagation.FRONTIER
    assert second_hop[0] == "S" and not {"P", "Q"} & set(second_hop)
    assert spread.hops == 2
    ranked = dict(spread.reached)
    assert "Q" not in ranked
    assert ranked["T"] == pytest.approx(ranked["S"] * propagation.DECAY)
    assert spread.via["T"] == ("threads", "S")


def test_a_tripped_cap_stops_the_spread_and_keeps_what_it_reached(graph):
    edges, walked = graph
    edges[("P", "same_file")] = ["A"]
    edges[("A", "same_file")] = ["B"]

    spread = propagate(_job(["P"], caps=Caps(calls=3)), ["P"])

    assert spread.stopped == "cap: 3 calls issued"
    assert len(walked) == 3 and spread.hops == 1
    assert [node for node, _ in spread.reached] == ["A"]


def test_the_caps_admit_every_node_the_spread_can_reach():
    """The compiler's default node cap bounds what a model reads; a spread's rows reach
    no model, and at 40 the cap cut the first hop of every replayed anchor set in walk
    order rather than by strength."""
    relations = len(propagation.vocabulary.RELATIONS)
    expansions = 5 + propagation.FRONTIER * (propagation.DEPTH - 1)
    assert propagation.CAPS.calls == 1 + expansions * relations
    assert propagation.CAPS.nodes >= expansions * relations * propagation.LIMIT


def test_a_linked_line_names_the_edge_it_came_over():
    line = linked_line("R2.6", _row("scope:main:claim:x", kind="chunk"), "same_entity", "R2.1")

    assert line == (
        "R2.6 · source passage · tier 1 · 2026-09-20 · about scope:main:claim:x"
        " · via same_entity from R2.1"
    )
