"""
Graph writer traversal construction and diagnostics tests.

Interfaces: Gremlin merge_v option modulators, thalamus.substrate.writer._iterate
Infrastructure: none; fake traversals only
Scope: merge token encoding and contextual write failure reporting
"""

from datetime import UTC, datetime

import pytest
from gremlin_python.driver.protocol import GremlinServerError
from gremlin_python.process.traversal import Merge

from gremlin_python.process.traversal import T

from thalamus.substrate.schema import (
    Artifact,
    ArtifactType,
    Decision,
    SessionGraph,
    Source,
    Thread,
    Tier,
    Tool,
)
from thalamus.substrate.writer import (
    GraphWriteError,
    _iterate,
    _upsert_session_vertex,
    write_session,
)


class FakeTraversal:
    def __init__(self, error=None):
        self.bytecode = "fake-bytecode"
        self.error = error
        self.options = []

    def option(self, key, value):
        self.options.append((key, value))
        return self

    def iterate(self):
        if self.error:
            raise self.error
        return self


class FakeGraphTraversalSource:
    def __init__(self, graph_traversal):
        self.graph_traversal = graph_traversal

    def merge_v(self, _values):
        return self.graph_traversal


def test_session_upsert_uses_merge_enum_tokens():
    """
    Scenario: Encode merge option modulators for a session upsert

    Requires:
    - infrastructure: none

    Verifications:
    - on-create and on-match options use Gremlin Merge tokens, not strings
    """
    graph_traversal = FakeTraversal()
    g = FakeGraphTraversalSource(graph_traversal)
    session = SessionGraph(
        session_id="test-session",
        timestamp=datetime(2026, 7, 9, tzinfo=UTC),
        tool=Tool.CURSOR,
        project="example-project",
        summary="Regression test",
    )

    _upsert_session_vertex(g, session)

    # Verifies: on-create and on-match options use Gremlin Merge tokens, not strings
    assert [key for key, _ in graph_traversal.options] == [
        Merge.on_create,
        Merge.on_match,
    ]


def test_iterate_reports_operation_target_and_server_details():
    """
    Scenario: Report a Gremlin server write failure

    Requires:
    - infrastructure: none

    Verifications:
    - write errors identify the failed operation, target, status, and server exception
    """
    server_error = GremlinServerError(
        {
            "code": 599,
            "message": "bad traversal",
            "attributes": {
                "exceptions": ["java.lang.IllegalStateException"],
                "stackTrace": "server stack",
            },
        }
    )

    with pytest.raises(GraphWriteError) as error:
        _iterate(FakeTraversal(server_error), "upsert Session", "session:test")

    message = str(error.value)
    # Verifies: write errors identify the failed operation, target, status, and server exception
    assert "upsert Session `session:test` failed" in message
    assert "Gremlin server 599: bad traversal" in message
    assert "java.lang.IllegalStateException" in message


class RecordingGraph:
    """Captures every vertex and edge a write would produce, without a graph server."""

    def __init__(self):
        self.vertices: list[dict] = []
        self.edges: list[dict] = []
        self._pending: dict | None = None

    # -- traversal surface used by the writer --
    def merge_v(self, values):
        self._pending = {"match": values, "properties": {}}
        self.vertices.append(self._pending)
        return self

    def merge_e(self, values):
        self.edges.append(values)
        return self

    def option(self, key, value):
        if key is Merge.on_create and self._pending is not None:
            self._pending["properties"] = value
        return self

    def V(self, *_args):
        return self

    def has_label(self, *_args):
        return self

    def property(self, *_args):
        return self

    def iterate(self):
        return self

    @property
    def bytecode(self):
        return "recording"


def test_every_written_node_carries_a_provenance_envelope():
    """
    Scenario: Write a session containing a claim, an artifact, and a thread

    Requires:
    - infrastructure: none; a recording fake stands in for the graph

    Verifications:
    - every vertex written carries tier, source, and ingested_at

    docs/05 makes provenance an obligation on every node in the graph, enforced at write
    time. The extraction YAML never mentions it — the writer stamps it — so this test is
    what keeps "no provenance, no write" true rather than aspirational.
    """
    session = SessionGraph(
        session_id="s1",
        timestamp=datetime(2026, 7, 14, tzinfo=UTC),
        tool=Tool.CLAUDE_CODE,
        project="thalamus",
        summary="Wrote the substrate.",
        artifacts=[Artifact(identifier="src/a.py", type=ArtifactType.FILE)],
        decisions=[Decision(description="d", rationale="r", artifacts=["src/a.py"])],
        threads=[Thread(id="t1", title="T", description="D")],
    )

    graph = RecordingGraph()
    write_session(graph, session)

    # Verifies: session + artifact + claim + thread — nothing written without provenance
    assert len(graph.vertices) == 4
    for vertex in graph.vertices:
        properties = vertex["properties"]
        assert properties["tier"] == int(Tier.FIRST_PARTY)
        assert properties["source"] == "session:s1"
        assert properties["ingested_at"]


def test_artifacts_are_written_unscoped_and_everything_else_scoped():
    """
    Scenario: Write a session pinned to an expert scope

    Verifications:
    - the Artifact vertex ID carries no scope segment (it is the global join key)
    - session, claim, and thread vertex IDs are scoped to the pin
    """
    session = SessionGraph(
        session_id="s1",
        timestamp=datetime(2026, 7, 14, tzinfo=UTC),
        tool=Tool.CLAUDE_CODE,
        scope="literature",
        summary="Read a paper.",
        artifacts=[Artifact(identifier="src/a.py", type=ArtifactType.FILE)],
        decisions=[Decision(description="d", rationale="r", artifacts=["src/a.py"])],
    )

    graph = RecordingGraph()
    write_session(graph, session)

    ids = {vertex["properties"][T.id] for vertex in graph.vertices}

    # Verifies: the global artifact is reachable identically from every scope
    assert "artifact:src/a.py" in ids
    # Verifies: scoped nodes are namespaced by the pin, so scopes cannot collide
    assert "scope:literature:session:s1" in ids
    assert any(node_id.startswith("scope:literature:claim:") for node_id in ids)


class _VertexChain:
    def __init__(self, fake, vid):
        self.fake = fake
        self.vid = vid
        self.bytecode = "fake-bytecode"

    def has_label(self, _label):
        return self

    def has_next(self):
        return self.vid in self.fake.existing

    def property(self, key, value):
        self.fake.status_updates.append((self.vid, key, value))
        return self

    def iterate(self):
        return self


class _ThreadRefFake:
    """Just enough traversal source for _write_thread_refs: V() lookups and merge_e."""

    def __init__(self, existing):
        self.existing = set(existing)
        self.edges = []
        self.status_updates = []

    def V(self, vid):
        return _VertexChain(self, vid)

    def merge_e(self, spec):
        self.edges.append(spec)
        return FakeTraversal()


def test_thread_refs_to_nonexistent_threads_are_dropped_not_fatal():
    """
    Scenario: A session's thread_refs name one real thread and one the model invented

    Verifications:
    - the real ref gets its status update and RESOLVES/CONTINUES edge
    - the invented ref is dropped without any write, and nothing raises
      (previously it crashed the whole write: mergeE cannot create an edge
      to a missing vertex)
    """
    from thalamus.substrate.schema import ThreadRef, ThreadStatus
    from thalamus.substrate.writer import _write_thread_refs
    from thalamus.contract.ontology import vid as make_vid

    session = SessionGraph(
        session_id="s1",
        tool=Tool.CLAUDE_CODE,
        summary="x",
        thread_refs=[
            ThreadRef(id="real-thread", status=ThreadStatus.RESOLVED),
            ThreadRef(id="hallucinated-thread", status=ThreadStatus.RESOLVED),
        ],
    )
    fake = _ThreadRefFake(existing={make_vid("Thread", "real-thread", session.scope)})

    _write_thread_refs(fake, session, make_vid("Session", "s1", session.scope))

    assert [u[0] for u in fake.status_updates] == [
        make_vid("Thread", "real-thread", session.scope)
    ]
    assert len(fake.edges) == 1


class _SnapshotFake:
    """Just enough traversal source for _write_sources: the heads query and the writes."""

    def __init__(self, heads):
        self.heads = list(heads)
        self.edges = []

    def V(self, *_args):
        return self

    def merge_v(self, *_args):
        return FakeTraversal()

    def merge_e(self, spec):
        self.edges.append(spec)
        return FakeTraversal()

    # -- the _snapshot_heads chain --
    def out(self, *_args):
        return self

    def has_label(self, *_args):
        return self

    def has(self, *_args):
        return self

    def not_(self, *_args):
        return self

    def id_(self):
        return self

    def to_list(self):
        return list(self.heads)


def _snapshot_session(content_hash: str) -> SessionGraph:
    from thalamus.substrate.schema import Source

    return SessionGraph(
        session_id="s1",
        timestamp=datetime(2026, 7, 15, tzinfo=UTC),
        tool=Tool.CLAUDE_CODE,
        summary="x",
        sources=[
            Source(content_hash=content_hash, title="Session s1", uri=f"archive://{content_hash}")
        ],
    )


def test_new_transcript_snapshot_supersedes_the_previous_heads():
    """
    Scenario: A session distilled earlier is distilled again from a grown transcript

    Verifications:
    - the new snapshot writes a SUPERSEDES edge to every current head
      (plural heads heal graphs written before the lineage existed)
    - the DERIVED_FROM floor edge is still written

    A session distilled while open accumulates snapshots (docs/10, lab/002); the
    lineage is what makes "the transcript of session X" a defined head instead of a
    byte-size guess that silently under-counts attribution.
    """
    from gremlin_python.process.traversal import Direction

    from thalamus.substrate.writer import _write_sources
    from thalamus.contract.ontology import vid as make_vid

    session = _snapshot_session("newhash")
    session_vid = make_vid("Session", "s1", session.scope)
    old_a = make_vid("Source", "oldhash-a", session.scope)
    old_b = make_vid("Source", "oldhash-b", session.scope)
    fake = _SnapshotFake(heads=[old_a, old_b])

    _write_sources(fake, session, session_vid)

    new_vid = make_vid("Source", "newhash", session.scope)
    supersedes = [e for e in fake.edges if e[T.label] == "SUPERSEDES"]
    assert {(e[Direction.from_], e[Direction.to]) for e in supersedes} == {
        (new_vid, old_a),
        (new_vid, old_b),
    }
    assert any(e[T.label] == "DERIVED_FROM" for e in fake.edges)


def test_rewriting_the_same_snapshot_does_not_supersede_itself():
    """
    Scenario: A --force re-extraction of an unchanged transcript (same content hash)

    The head it finds is itself; a self-SUPERSEDES edge would orphan the lineage.
    """
    from thalamus.substrate.writer import _write_sources
    from thalamus.contract.ontology import vid as make_vid

    session = _snapshot_session("samehash")
    session_vid = make_vid("Session", "s1", session.scope)
    fake = _SnapshotFake(heads=[make_vid("Source", "samehash", session.scope)])

    _write_sources(fake, session, session_vid)

    assert not [e for e in fake.edges if e[T.label] == "SUPERSEDES"]


class _PropertyFake:
    """Just enough traversal source for _source_on_match: one vertex's stored properties."""

    def __init__(self, stored=None):
        self.stored = stored  # None => the vertex does not exist yet

    def V(self, *_args):
        return self

    def value_map(self, *_keys):
        return self

    def limit(self, *_args):
        return self

    def to_list(self):
        # TinkerGraph hands back list-valued properties; mirror that so the unwrapping
        # is exercised rather than assumed.
        return [] if self.stored is None else [{k: [v] for k, v in self.stored.items()}]


_A_SOURCE = "scope:literature:source:abc123"


def _properties(tier: int, origin: str) -> dict:
    return {"content_hash": "abc123", "title": "A paper", "tier": tier, "origin": origin}


def test_reingest_under_friendlier_provenance_cannot_raise_a_sources_trust():
    """
    Scenario: bytes already held at tier 2 are re-written claiming tier 1

    Effective trust is the floor of the derivation chain (docs/05), and every Claim
    hangs its floor off the Source it was derived from. If a re-ingest could relabel
    that Source, the cheapest attack on the trust model is to re-submit the same bytes
    under a friendlier provenance — so the two readings combine to the least trusted.
    """
    from thalamus.substrate.writer import _source_on_match

    fake = _PropertyFake({"tier": 2, "origin": "https://arxiv.org/html/2601.00821"})
    on_match = _source_on_match(
        fake, _A_SOURCE, _properties(1, "https://arxiv.org/html/2601.00821")
    )

    assert on_match["tier"] == 2


def test_reingest_under_wilder_provenance_does_lower_trust():
    """
    Scenario: bytes already held at tier 2 are re-written at tier 3

    The rule is a floor, not a freeze: trust may fall on new evidence about where the
    bytes came from. Only lifting it silently is forbidden.
    """
    from thalamus.substrate.writer import _source_on_match

    fake = _PropertyFake({"tier": 2, "origin": "https://example.org/x"})
    on_match = _source_on_match(fake, _A_SOURCE, _properties(3, "https://example.org/x"))

    assert on_match["tier"] == 3


def test_reingest_from_a_second_address_keeps_the_first_origin():
    """
    Scenario: identical bytes are reached at a second URL

    `origin` is the key `_article_heads` searches by, so rewriting it moves an
    article's supersession lineage under readers that already walked it — and an
    article Source carries no body digest to detect the move with.
    """
    from thalamus.substrate.writer import _source_on_match

    fake = _PropertyFake({"tier": 2, "origin": "https://arxiv.org/abs/2601.00821"})
    on_match = _source_on_match(
        fake, _A_SOURCE, _properties(2, "https://arxiv.org/html/2601.00821")
    )

    # The match writes no origin at all, which is what leaves the stored one standing.
    assert "origin" not in on_match
    # Refreshable properties still go through — this holds one field, not the write.
    assert on_match["title"] == "A paper"


def test_a_first_write_passes_trust_and_origin_through():
    """
    Scenario: the Source does not exist yet

    Nothing is held, so nothing is protected — and the node must still come out
    carrying provenance, which the contract rejects it for lacking.
    """
    from thalamus.substrate.writer import _source_on_match

    on_match = _source_on_match(_PropertyFake(None), _A_SOURCE, _properties(2, "u"))

    assert on_match["tier"] == 2
    assert on_match["origin"] == "u"


def test_a_source_predating_the_tier_property_still_gets_one():
    """
    Scenario: a vertex exists but carries no `tier`

    Holding "what the graph already has" would hold *nothing* here and leave the node
    with no tier at all, which fails the contract's provenance obligation.
    """
    from thalamus.substrate.writer import _source_on_match

    on_match = _source_on_match(
        _PropertyFake({"origin": "u"}), _A_SOURCE, _properties(2, "u")
    )

    assert on_match["tier"] == 2


# --------------------------------------------------------------------------------------
# written_at — the transaction-time axis ingested_at could not carry.
# --------------------------------------------------------------------------------------


class _StampFake:
    """A graph that can answer the stored-text lookup, unlike the write-only recorders."""

    def __init__(self, stored: dict | None = None):
        self._stored = stored
        self.asked = []

    def V(self, vertex_id):
        self.asked.append(vertex_id)
        return self

    def value_map(self, *_keys):
        return self

    def limit(self, _n):
        return self

    def to_list(self):
        return [self._stored] if self._stored is not None else []


def test_unchanged_text_keeps_its_original_written_at():
    """
    Scenario: A session is re-distilled and its summary comes back identical

    Verifications:
    - the stored stamp is preserved, not refreshed

    If every write refreshed it, `written_at` would mean "last written" — which is
    what `ingested_at` already fails to be useful as, since it carries the writing
    session's timestamp and can move backwards. The whole value of this field is
    that it moves only when the text does.
    """
    from thalamus.substrate.writer import _text_stamp

    digest = _text_stamp(_StampFake(), "v", "the same summary")["text_digest"]
    graph = _StampFake({"written_at": ["2026-01-01T00:00:00+00:00"],
                        "text_digest": [digest]})

    stamp = _text_stamp(graph, "v", "the same summary")

    assert stamp["written_at"] == "2026-01-01T00:00:00+00:00"


def test_changed_text_moves_written_at():
    """
    Scenario: A session's summary is rewritten by a later distillation

    This is the mutable-text exposure the graph could not previously answer: a node's
    text could change with nothing recording that it had, which is why the exposure
    had to be inferred from evidence strings rather than queried.
    """
    from thalamus.substrate.writer import _text_stamp

    graph = _StampFake({"written_at": ["2026-01-01T00:00:00+00:00"],
                        "text_digest": ["0000000000000000"]})

    stamp = _text_stamp(graph, "v", "a rewritten summary")

    assert stamp["written_at"] != "2026-01-01T00:00:00+00:00"
    assert stamp["text_digest"] != "0000000000000000"


def test_a_first_write_stamps_now_rather_than_failing():
    """
    Scenario: The vertex does not exist yet, or the traversal source cannot answer

    A vertex with no prior text has nothing to differ from, so the stamp is the write
    itself. Same posture as _snapshot_heads: an unanswerable lookup on a first write
    is not an error.
    """
    from thalamus.substrate.writer import _text_stamp

    class _Mute:
        def V(self, _vid):
            raise RuntimeError("no such traversal surface")

    assert _text_stamp(_Mute(), "v", "text")["written_at"]
    assert _text_stamp(_StampFake(), "v", "text")["written_at"]


def test_written_at_lands_on_every_node_whose_text_can_change():
    """
    Scenario: Write a full session subgraph

    Verifications:
    - Session, Thread and Source carry written_at
    - Artifact does not — its text is its identifier, which is its identity and
      therefore cannot change under it
    - Claim does not — a rewritten description hashes to a different content_id and
      mints a new vertex, so its text is immutable in place

    The field exists for exactly the nodes where a stable identity can carry moving
    text. Putting it on the others would imply a mutability they do not have.
    """
    session = SessionGraph(
        session_id="s1",
        timestamp=datetime(2026, 7, 14, tzinfo=UTC),
        tool=Tool.CLAUDE_CODE,
        project="thalamus",
        summary="Wrote the substrate.",
        artifacts=[Artifact(identifier="src/a.py", type=ArtifactType.FILE)],
        decisions=[Decision(description="d", rationale="r", artifacts=["src/a.py"])],
        threads=[Thread(id="t1", title="T", description="D")],
        sources=[Source(content_hash="abc123", title="transcript", uri="file:///x")],
    )

    graph = RecordingGraph()
    write_session(graph, session)

    by_label = {}
    for entry in graph.vertices:
        label = entry["match"].get(T.label)
        by_label.setdefault(label, []).append(entry["properties"])

    for label in ("Session", "Thread", "Source"):
        assert by_label.get(label), f"no {label} written"
        assert all("written_at" in props for props in by_label[label]), label

    for label in ("Artifact", "Claim"):
        if by_label.get(label):
            assert all("written_at" not in props for props in by_label[label]), label
