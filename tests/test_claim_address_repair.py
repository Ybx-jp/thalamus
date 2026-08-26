"""
Moving a mis-addressed Claim back to the address its own content produces.

Interfaces: thalamus.substrate.claim_address_repair.classify/moved_edges/flatten/
            expected_vid
Infrastructure: none — the judgement is pure over rows already read, which is
                deliberately where the decision that drops a vertex lives
Scope: which vertex is dropped and which is re-minted. The asymmetry is the point:
       a stale duplicate read as live costs a duplicate that another pass can still
       find, and a live record read as stale is deleted, so every case here pins the
       direction that keeps the vertex.
"""

from __future__ import annotations

from thalamus.substrate.claim_address_repair import (
    MovedEdge,
    classify,
    expected_vid,
    flatten,
    moved_edges,
)
from thalamus.substrate.schema import Claim


def _row(kind: str, description: str, scope: str = "main") -> tuple[str, str, str]:
    """A Claim row sitting at the address its own content produces."""
    return (expected_vid(f"scope:{scope}:claim:x", kind, description), kind, description)


def test_a_claim_at_its_own_address_is_not_a_finding():
    rows = [_row("decision", "Adopt TinkerGraph as the substrate.")]
    assert classify(rows) == []


def test_normalization_is_not_drift():
    """`_normalized` collapses whitespace and a trailing period, so a description
    differing only by those hashes to the same address and must not be reported."""
    kind, canonical = "decision", "Adopt TinkerGraph as the substrate"
    vertex_id = expected_vid("scope:main:claim:x", kind, canonical)
    for variant in (f"{canonical}.", f"{canonical}  ", f"  {canonical}\n"):
        assert classify([(vertex_id, kind, variant)]) == [], variant


def test_a_stale_vertex_with_a_live_twin_is_twinned():
    kind, description = "solution", "Stub the two live seams in the install sandbox."
    twin = _row(kind, description)
    stale = ("scope:main:claim:0000000000000000", kind, description)

    found = classify([stale, twin])

    assert len(found) == 1
    assert found[0].vertex_id == stale[0]
    assert found[0].target == twin[0]
    assert found[0].twinned is True


def test_a_wrong_address_with_no_twin_is_not_twinned():
    """The distinction that decides the repair: no vertex holds the recomputed id, so
    this is the live record and dropping it would delete the claim."""
    kind, description = "decision", "Scrub the committed key before landing the port."
    wrong = ("scope:main:claim:0000000000000000", kind, description)

    found = classify([wrong])

    assert found[0].twinned is False
    assert found[0].target == expected_vid(wrong[0], kind, description)


def test_the_twin_lookup_is_scoped():
    """`vid` puts the scope in the address, so a correctly addressed vertex in
    `literature` must not excuse a stale one in `main` — dropping it would delete a
    claim no other vertex in its scope holds."""
    kind, description = "literature/technique", "The survey reviews memory evaluation."
    elsewhere = _row(kind, description, scope="literature")
    stale = ("scope:main:claim:0000000000000000", kind, description)

    found = classify([stale, elsewhere])

    assert found[0].twinned is False, "a twin in another scope is not this scope's twin"
    assert found[0].target.startswith("scope:main:claim:")


def test_a_twin_that_is_only_expected_does_not_count():
    """`known` is built from the rows, not from the recomputed addresses: a vertex
    that would be the twin but is not in the graph cannot license a deletion."""
    kind, description = "problem", "The scan walks the operator's archive."
    stale_a = ("scope:main:claim:aaaaaaaaaaaaaaaa", kind, description)
    stale_b = ("scope:main:claim:bbbbbbbbbbbbbbbb", kind, description)

    found = classify([stale_a, stale_b])

    assert [f.twinned for f in found] == [False, False]
    assert {f.target for f in found} == {expected_vid(stale_a[0], kind, description)}


def test_findings_are_ordered_by_vertex_id():
    kind = "problem"
    rows = [
        ("scope:main:claim:cccccccccccccccc", kind, "third"),
        ("scope:main:claim:aaaaaaaaaaaaaaaa", kind, "first"),
        ("scope:main:claim:bbbbbbbbbbbbbbbb", kind, "second"),
    ]
    assert [f.vertex_id for f in classify(rows)] == [
        "scope:main:claim:aaaaaaaaaaaaaaaa",
        "scope:main:claim:bbbbbbbbbbbbbbbb",
        "scope:main:claim:cccccccccccccccc",
    ]


def test_expected_vid_agrees_with_the_write_path():
    """Recomputed by calling the two functions the write path mints through, so this
    test fails rather than the migration drifting if either one changes."""
    kind, description = "decision", "Federate on one graph store with scoped vids."
    content_id = Claim(kind=kind, description=description).content_id()
    assert expected_vid("scope:main:claim:x", kind, description) == (
        f"scope:main:claim:{content_id}"
    )


def test_an_edge_the_destination_already_holds_collapses():
    trace = "scope:main:trace:f205a96f4eaf745f"
    incident = (MovedEdge("RETURNS", trace, incoming=True),)

    stamped = moved_edges(incident, {("RETURNS", trace, True)})

    assert stamped[0].collapses is True
    assert "[collapses]" in stamped[0].describe()


def test_direction_and_label_both_qualify_a_collapse():
    """A TOUCHES out to an artifact is not the RETURNS in from a trace, and an edge
    pointing the other way is a different edge — neither may be read as already held."""
    other = "artifact:src/thalamus/cli.py"
    incident = (MovedEdge("TOUCHES", other, incoming=False),)

    assert moved_edges(incident, {("TOUCHES", other, True)})[0].collapses is False
    assert moved_edges(incident, {("RETURNS", other, False)})[0].collapses is False
    assert moved_edges(incident, {("TOUCHES", other, False)})[0].collapses is True


def test_an_unstamped_edge_is_additive():
    edge = MovedEdge("REFERENCES", "scope:main:exchange:3f47831f43f2447b", incoming=True)
    stamped = moved_edges((edge,), set())
    assert stamped[0].collapses is False
    assert stamped[0].describe() == (
        "<-REFERENCES- scope:main:exchange:3f47831f43f2447b"
    )


def test_edge_properties_survive_the_move():
    """A RETURNS edge carries the layer-1 verdict. Moving it without its properties
    would silently un-judge the retrieval it records."""
    edge = MovedEdge(
        "RETURNS", "scope:main:trace:aaa", incoming=True,
        properties={"used": [True], "evidence": ["cited in the answer"]},
    )
    assert moved_edges((edge,), set())[0].properties == {
        "used": [True], "evidence": ["cited in the answer"],
    }


def test_flatten_unwraps_value_map_lists():
    assert flatten({"kind": ["decision"], "tier": [1]}) == {"kind": "decision", "tier": 1}


def test_flatten_drops_an_empty_property_rather_than_writing_none():
    """A present-but-empty value is what every audit reads as a provenance hole, so a
    property the source does not carry must not appear on the destination at all."""
    assert flatten({"kind": ["decision"], "outcome": []}) == {"kind": "decision"}


def test_flatten_passes_through_a_scalar():
    assert flatten({"kind": "decision", "used": True}) == {"kind": "decision", "used": True}
