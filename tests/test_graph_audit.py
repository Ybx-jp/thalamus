"""
Live-graph audit tests — `thalamus contract check`.

Interfaces: thalamus.contract.conformance.audit_vertices/audit_edges/audit_orphans/audit_evidence
Infrastructure: tmp_path for the archive check; no graph
Scope: the contract re-verified against what is actually in the graph, not what came
through the front door. Pure functions over plain rows, so drift is testable.
"""

import hashlib

from thalamus.contract.conformance import (
    AuditEdge,
    AuditVertex,
    audit_edges,
    audit_evidence,
    audit_exchanges,
    audit_orphans,
    audit_vertices,
)

_PROV = {"tier": 1, "source": "session:s1", "ingested_at": "2026-07-15T00:00:00"}


def _session(vid="scope:main:session:s1", scope="main"):
    return AuditVertex(vid=vid, label="Session", properties={**_PROV, "scope": scope})


def test_a_clean_scoped_vertex_raises_nothing():
    assert audit_vertices([_session()]) == []


def test_provenance_holes_and_unknown_labels_are_reported():
    """
    Scenario: A vertex written without its envelope, and one with a label the
    ontology never declared

    docs/05 makes provenance an obligation on every node; a label outside the
    ontology is a write that bypassed the contract entirely.
    """
    naked = AuditVertex(vid="scope:main:session:s2", label="Session",
                        properties={"scope": "main"})
    alien = AuditVertex(vid="scope:main:widget:w1", label="Widget", properties=_PROV)

    issues = audit_vertices([naked, alien])

    assert any("Provenance hole" in i and "s2" in i for i in issues)
    assert any("Unknown vertex label" in i and "Widget" in i for i in issues)


def test_a_vertex_lying_about_its_scope_is_caught():
    """
    Scenario: A node whose `scope` property disagrees with its vertex-ID segment

    Server-side scoping filters on the property; the ID namespaces the vertex. If they
    disagree, a node is reachable from a scope it does not belong to — the exact
    failure the pin exists to prevent.
    """
    liar = AuditVertex(vid="scope:literature:claim:abc", label="Claim",
                       properties={**_PROV, "scope": "main", "description": "x"})

    issues = audit_vertices([liar])

    assert len(issues) == 1
    assert "Scope integrity" in issues[0]


def test_globals_must_not_carry_a_scope():
    claimed = AuditVertex(vid="artifact:src/a.py", label="Artifact",
                          properties={**_PROV, "scope": "main"})

    issues = audit_vertices([claimed])

    assert len(issues) == 1
    assert "global" in issues[0]


def test_an_external_claim_carrying_first_party_trust_is_laundering():
    """
    Scenario: A claim marked external (transcript ingress) but stamped tier 1;
    a correctly-floored twin at tier 2

    The mark and the tier are both written by apply_ingress_floor — a live vertex
    where they disagree means something wrote around the floor (docs/05).
    """
    laundered = AuditVertex(
        vid="scope:main:claim:bad1", label="Claim",
        properties={**_PROV, "scope": "main", "description": "x",
                    "external": True, "tier": 1},
    )
    floored = AuditVertex(
        vid="scope:main:claim:ok1", label="Claim",
        properties={**_PROV, "scope": "main", "description": "y",
                    "external": True, "tier": 2},
    )

    issues = audit_vertices([laundered, floored])

    assert len(issues) == 1
    assert "Laundered ingress" in issues[0]
    assert "bad1" in issues[0]


def test_cross_scope_edges_are_legal_only_where_the_ontology_says_so():
    """
    Scenario: A direct expert-to-expert CONTAINS edge, and a TOUCHES edge into the
    global Artifact vertex

    The first is the boundary violation docs/02 forbids; the second is shared
    vocabulary, not a channel, and must not be flagged.
    """
    illegal = AuditEdge(label="CONTAINS",
                        from_vid="scope:literature:session:s1", from_label="Session",
                        to_vid="scope:dl:claim:c1", to_label="Claim")
    legal = AuditEdge(label="TOUCHES",
                      from_vid="scope:literature:session:s1", from_label="Session",
                      to_vid="artifact:src/a.py", to_label="Artifact")

    issues = audit_edges([illegal, legal])

    assert len(issues) == 1
    assert "Illegal cross-scope edge" in issues[0]


def test_returns_may_cross_scope_because_the_tap_records_what_the_reader_served():
    """
    Scenario: a main-scope retrieval trace RETURNS a knowledge claim from an
    expert scope — an ordinary recall serving tier-2 knowledge (docs/05), or a
    ticket-scoped consultation recall.

    The tap is observability, not authority: what the reader may return is the
    reader's server-side policy, and the trace must be able to record it.
    """
    served = AuditEdge(label="RETURNS",
                       from_vid="scope:main:trace:t1", from_label="Trace",
                       to_vid="scope:literature:claim:c1", to_label="Claim")

    assert audit_edges([served]) == []


def test_supersedes_is_for_evidence_snapshots_only():
    wrong = AuditEdge(label="SUPERSEDES",
                      from_vid="scope:main:claim:a", from_label="Claim",
                      to_vid="scope:main:claim:b", to_label="Claim")

    issues = audit_edges([wrong])

    assert len(issues) == 1
    assert "SUPERSEDES between non-Sources" in issues[0]


def test_consults_is_a_sessions_edge_to_its_exchange_record():
    """
    Scenario: A CONSULTS edge written between the wrong node types

    docs/02 makes the consultation a Session -> Exchange fact; anything else is a
    write that bypassed the ticket protocol.
    """
    wrong = AuditEdge(label="CONSULTS",
                      from_vid="scope:main:session:s1", from_label="Session",
                      to_vid="scope:literature:claim:c1", to_label="Claim")
    right = AuditEdge(label="CONSULTS",
                      from_vid="scope:main:session:s1", from_label="Session",
                      to_vid="scope:main:exchange:t1", to_label="Exchange")

    issues = audit_edges([wrong, right])

    assert len(issues) == 1
    assert "CONSULTS between wrong endpoints" in issues[0]


def test_an_answered_exchange_must_cite_and_statuses_are_closed_vocabulary():
    """
    Scenario: Three Exchange vertices — answered with a citation edge, answered
    with none, and one carrying a status the protocol never mints

    consult_answer is the only close path and it validates citations (docs/02, the
    write-path stance of arXiv 2606.04329) — so an answered-but-uncited exchange in
    the live graph means something wrote around the protocol.
    """
    def _exchange(vid, status):
        return AuditVertex(vid=vid, label="Exchange",
                           properties={**_PROV, "scope": "main", "status": status})

    cited = _exchange("scope:main:exchange:t1", "answered")
    uncited = _exchange("scope:main:exchange:t2", "answered")
    alien = _exchange("scope:main:exchange:t3", "haunted")
    citation = AuditEdge(label="REFERENCES",
                         from_vid=cited.vid, from_label="Exchange",
                         to_vid="scope:literature:claim:c1", to_label="Claim",
                         properties={"role": "citation"})
    brief_only = AuditEdge(label="REFERENCES",
                           from_vid=uncited.vid, from_label="Exchange",
                           to_vid="scope:literature:thread:th1", to_label="Thread",
                           properties={"role": "brief"})

    issues = audit_exchanges([cited, uncited, alien], [citation, brief_only])

    assert len(issues) == 2
    assert any("t2" in i and "cites nothing" in i for i in issues)
    assert any("t3" in i and "haunted" in i for i in issues)


def test_unknown_edge_labels_are_reported():
    alien = AuditEdge(label="LIKES",
                      from_vid="scope:main:session:s1", from_label="Session",
                      to_vid="scope:main:claim:c1", to_label="Claim")

    assert any("Unknown edge label" in i for i in audit_edges([alien]))


def test_orphans_are_vertices_no_edge_reaches():
    connected = _session()
    orphan = AuditVertex(vid="artifact:src/lonely.py", label="Artifact", properties=_PROV)
    edge = AuditEdge(label="CONTAINS",
                     from_vid=connected.vid, from_label="Session",
                     to_vid="scope:main:claim:c1", to_label="Claim")

    issues = audit_orphans([connected, orphan], [edge])

    assert issues == ["Orphan vertex: `artifact:src/lonely.py` (Artifact) has no edges"]


def test_an_open_quick_exchange_is_edgeless_by_construction():
    """
    Scenario: A quick consultation was minted and its fork never answered; and a
    second quick exchange closed as answered without citations landing

    Verifications:
    - the open one is not reported as an orphan
    - the answered one still is

    The full ticket's Exchange is born connected, because the server's brief becomes
    `role: brief` edges. The quick tier drops the brief on purpose (docs/02), so an
    open quick exchange has nothing to point at until its citations land — honest
    data, with `brief_served: false` and `fork_error` saying what happened. Answering
    removes the exemption: an answered exchange must cite, like any other.
    """
    open_quick = AuditVertex(
        vid="scope:main:exchange:q1", label="Exchange",
        properties={**_PROV, "protocol": "quick", "status": "open"},
    )
    answered_quick = AuditVertex(
        vid="scope:main:exchange:q2", label="Exchange",
        properties={**_PROV, "protocol": "quick", "status": "answered"},
    )

    issues = audit_orphans([open_quick, answered_quick], [])

    assert issues == ["Orphan vertex: `scope:main:exchange:q2` (Exchange) has no edges"]


def test_evidence_floor_requires_the_blob_to_exist(tmp_path):
    """
    Scenario: Two Source nodes — one whose blob is retained, one dangling

    A Source whose bytes are gone is a provenance chain ending in a pointer to
    nothing; the audit is what keeps "immutable archive" an invariant instead of
    an intention.
    """
    payload = b"retained evidence"
    content_hash = hashlib.sha256(payload).hexdigest()
    (tmp_path / content_hash[:2]).mkdir()
    (tmp_path / content_hash[:2] / f"{content_hash}.jsonl").write_bytes(payload)

    retained = AuditVertex(vid=f"scope:main:source:{content_hash}", label="Source",
                           properties={**_PROV, "content_hash": content_hash})
    dangling = AuditVertex(vid="scope:main:source:deadbeef", label="Source",
                           properties={**_PROV, "content_hash": "deadbeef" * 8})

    issues = audit_evidence([retained, dangling], archive_base=tmp_path)

    assert len(issues) == 1
    assert "no such blob is retained" in issues[0]
