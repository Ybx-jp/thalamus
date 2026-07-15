"""
Knowledge-subgraph tests — the other half of G1.

Interfaces: schema.LiteratureClaim/Entity/KnowledgeBatch, conformance.check_knowledge,
writer.write_knowledge
Infrastructure: none; recording fakes only
Scope: what a feed may write, at what tier, and in what shape. The episodic half has
its own tests; these pin the ingestion side of the contract.
"""

from gremlin_python.process.traversal import Direction, T

from thalamus.contract.conformance import check_knowledge
from thalamus.substrate.schema import (
    ClaimKind,
    Decision,
    Entity,
    KnowledgeBatch,
    LiteratureClaim,
    Source,
    SourceKind,
    Tier,
)
from thalamus.substrate.writer import write_knowledge


def _batch(**overrides) -> KnowledgeBatch:
    values = dict(
        scope="literature",
        feed="manual",
        source=Source(
            content_hash="abc123",
            kind=SourceKind.ARTICLE,
            title="A paper",
            uri="archive://abc123",
            origin="https://arxiv.org/abs/2401.00001",
        ),
        claims=[
            LiteratureClaim(
                description="Reflexion improves agent success via verbal self-feedback",
                citation="§4.1",
                about=["Reflexion"],
            )
        ],
        entities=[Entity(name="Reflexion", kind="technique")],
    )
    values.update(overrides)
    return KnowledgeBatch(**values)


def test_claim_kinds_are_plain_strings_even_when_given_the_enum():
    """
    Scenario: Core code passes ClaimKind members; an expert passes a namespaced string

    Content hashes and graph properties must never depend on Python enum identity —
    the same assertion must hash identically whichever way its kind was spelled.
    """
    decision = Decision(description="d", rationale="r")
    literature = LiteratureClaim(description="d")

    assert type(decision.kind) is str and decision.kind == "decision"
    assert literature.kind == "literature/finding"
    assert Decision(description="d", rationale="r", kind=ClaimKind.DECISION).content_id() == (
        decision.content_id()
    )


def test_entity_slugs_are_stable_and_id_safe():
    assert Entity(name="Retrieval-Augmented Generation (RAG)").slug() == (
        "retrieval-augmented-generation-rag"
    )


def test_a_well_formed_batch_passes_the_contract():
    assert check_knowledge(_batch()) == []


def test_feeds_may_not_write_the_main_scope():
    """
    docs/06: feeds write only into their designated expert's knowledge subgraph —
    never episodic memory, never toward the master plane.
    """
    issues = check_knowledge(_batch(scope="main"))

    assert any("never `main`" in issue for issue in issues)


def test_provenance_is_explicit_or_rejected():
    naked_source = Source(content_hash="", kind=SourceKind.ARTICLE, title="t", uri="u")

    issues = check_knowledge(_batch(source=naked_source))

    assert any("no origin" in issue for issue in issues)
    assert any("no content_hash" in issue for issue in issues)


def test_entities_exist_only_through_claims():
    """
    Scenario: One entity no claim mentions, one mention of an undeclared entity

    Entities are reached through claims or not at all — an unreferenced entity is the
    knowledge-graph twin of the orphan artifact.
    """
    issues = check_knowledge(
        _batch(
            entities=[Entity(name="Reflexion"), Entity(name="Unmentioned")],
            claims=[LiteratureClaim(description="x", about=["Reflexion", "Ghost"])],
        )
    )

    assert any("Orphan entity: 'Unmentioned'" in issue for issue in issues)
    assert any("undeclared entity: 'Ghost'" in issue for issue in issues)


def test_knowledge_claims_use_namespaced_kinds_and_cannot_mint_trust():
    """
    Scenario: A batch smuggles an episodic kind, and a claim self-declares tier 1

    Core kinds belong to episodic claims; and a feed asserting first-party trust is
    exactly the laundering docs/05 forbids.
    """
    from thalamus.substrate.schema import Provenance

    issues = check_knowledge(
        _batch(
            claims=[
                LiteratureClaim(description="a", kind="decision"),
                LiteratureClaim(
                    description="b",
                    provenance=Provenance(tier=Tier.FIRST_PARTY, source="feed:manual"),
                ),
            ]
        )
    )

    assert any("must be namespaced" in issue for issue in issues)
    assert any("cannot mint trust above" in issue for issue in issues)


def test_a_batch_that_asserts_nothing_is_rejected():
    issues = check_knowledge(_batch(claims=[], entities=[]))

    assert any("asserts nothing" in issue for issue in issues)


class _KnowledgeRecorder:
    """Records merge_v/merge_e; the article-heads lookup chain is absent on purpose —
    write_knowledge must survive a graph that cannot answer it (first ingest)."""

    def __init__(self):
        self.vertices = []
        self.edges = []
        self._pending = None

    def merge_v(self, values):
        self._pending = {"match": values, "properties": {}}
        self.vertices.append(self._pending)
        return self

    def merge_e(self, values):
        self.edges.append(values)
        return self

    def option(self, key, value):
        from gremlin_python.process.traversal import Merge

        if key is Merge.on_create and self._pending is not None:
            self._pending["properties"] = value
        return self

    def V(self, *_args):
        return self

    def has_label(self, *_args):
        return self

    def iterate(self):
        return self

    @property
    def bytecode(self):
        return "recording"


def test_written_knowledge_is_scoped_tier_2_and_derived_from_its_source():
    """
    Scenario: Write one ingestion event through the recording fake

    Verifications:
    - Source, Claim, and Entity vertices are scoped to the expert and carry tier 2
    - every claim is DERIVED_FROM the retained Source (the provenance floor)
    - ABOUT edges connect claims to their entities
    """
    graph = _KnowledgeRecorder()
    batch = _batch()

    write_knowledge(graph, batch)

    by_id = {v["properties"][T.id]: v["properties"] for v in graph.vertices}
    assert "scope:literature:source:abc123" in by_id
    assert any(node_id.startswith("scope:literature:claim:") for node_id in by_id)
    assert "scope:literature:entity:reflexion" in by_id
    for properties in by_id.values():
        assert properties["tier"] == int(Tier.CURATED)
        assert properties["scope"] == "literature"

    edge_pairs = {(e[T.label], e[Direction.to]) for e in graph.edges}
    assert ("DERIVED_FROM", "scope:literature:source:abc123") in edge_pairs
    assert ("ABOUT", "scope:literature:entity:reflexion") in edge_pairs


def test_feed_identity_lands_on_the_source_and_only_the_source():
    """
    Scenario: A per-project feed (docs/06 procurement) writes a batch

    docs/06's contract obligations require feed identity on every write. It lives on
    the Source vertex — the ingestion event — and nowhere else: claims and entities
    converge across feeds, so stamping them would let the latest feed overwrite the
    history of who brought what in.
    """
    graph = _KnowledgeRecorder()
    batch = _batch(feed="stepmania-chart-generator")

    write_knowledge(graph, batch)

    by_id = {v["properties"][T.id]: v["properties"] for v in graph.vertices}
    assert by_id["scope:literature:source:abc123"]["feed"] == "stepmania-chart-generator"
    for node_id, properties in by_id.items():
        if not node_id.startswith("scope:literature:source:"):
            assert "feed" not in properties
