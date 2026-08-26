"""
Live-graph audit tests — `thalamus contract check`.

Interfaces: thalamus.contract.conformance.audit_vertices/audit_edges/audit_orphans/audit_evidence
Infrastructure: tmp_path for the archive check; no graph
Scope: the contract re-verified against what is actually in the graph, not what came
through the front door. Pure functions over plain rows, so drift is testable.
"""

import hashlib

from thalamus.contract.conformance import (
    ADVISORY,
    VIOLATION,
    AuditEdge,
    AuditVertex,
    audit_declarations,
    audit_edges,
    audit_evidence,
    audit_exchanges,
    audit_orphans,
    audit_vertices,
    severity_of,
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

    The trust model makes provenance an obligation on every node; a label outside the
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
    where they disagree means something wrote around the floor.
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

    The first is the scope-boundary violation the ontology forbids; the second is shared
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
    expert scope — an ordinary recall serving tier-2 knowledge, or a
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
    assert "SUPERSEDES between wrong endpoints" in issues[0]
    assert "source is a Claim, not Source" in issues[0]
    assert severity_of(issues[0]) == VIOLATION


def test_consults_is_a_sessions_edge_to_its_exchange_record():
    """
    Scenario: A CONSULTS edge written between the wrong node types

    The ontology makes the consultation a Session -> Exchange fact; anything else is a
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

    consult_answer is the only close path and it validates citations (the write-path
    stance of arXiv 2606.04329) — so an answered-but-uncited exchange in
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
    `role: brief` edges. The quick tier drops the brief on purpose, so an
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


def _close_edge(basis, thread_vid="scope:homelab:thread:t1"):
    return AuditEdge(
        label="RESOLVES",
        from_vid="agent:operator", from_label="Agent",
        to_vid=thread_vid, to_label="Thread",
        properties={"basis": basis} if basis is not None else {},
    )


def test_an_agent_may_close_a_thread_in_any_scope():
    """
    Scenario: the operator approves the close of a homelab thread

    Verifications:
    - `Agent -> Thread` is legal across scopes, with no exception on RESOLVES

    An Agent is global, so this is not a crossing at all — which is what lets the
    operator close a thread anywhere without relaxing `RESOLVES.may_cross_scope`. The
    partition guards a channel for content, and a close carries none.
    """
    legal = _close_edge("scope:homelab:session:s9")

    # Verifies: no complaint about the topology
    assert audit_edges([legal]) == []


def test_an_agent_close_must_cite_a_basis():
    """
    Scenario: an agent-written close arrives with no evidence property

    Verifications:
    - it is rejected

    Distillation's `Session -> Thread` needs no basis: the session IS the evidence and
    its transcript is archived. An Agent has no transcript, so without a basis the edge
    is a status flip with a name on it — and the whole reason not to do a bare flip was
    that an adjudication has nothing to walk.
    """
    issues = audit_edges([_close_edge(None)])

    # Verifies: named as uncited, not silently accepted
    assert len(issues) == 1
    assert "Uncited close" in issues[0]


def test_a_close_may_not_cite_evidence_its_readers_cannot_resolve():
    """
    Scenario: a close on a homelab thread cites a literature-scope vertex

    Verifications:
    - a foreign-scope basis is rejected
    - a basis in the thread's own scope passes
    - a global basis passes

    This is where the safety property moved when the closer became global. The edge is
    legal because an Agent carries no content; a basis pointing into a third scope
    would put content back on it, leaving the thread's own readers holding a citation
    they are confined away from.
    """
    foreign = _close_edge("scope:literature:claim:c1")
    own_scope = _close_edge("scope:homelab:session:s9")
    global_basis = _close_edge("artifact:src/app.js")

    issues = audit_edges([foreign, own_scope, global_basis])

    # Verifies: exactly the foreign one, and it says why
    assert len(issues) == 1
    assert "Unreadable basis" in issues[0]
    assert "literature" in issues[0]


def _claim(vid="scope:main:claim:c1", kind="decision", scope="main"):
    return AuditVertex(vid=vid, label="Claim",
                       properties={**_PROV, "scope": scope, "kind": kind})


def test_a_declaration_nothing_writes_is_reported_and_does_not_fail_the_run():
    """
    Scenario: A graph holding one Session, one Claim and one CONTAINS edge, audited
    against the full declared ontology

    Every other check here reads the ontology as ground truth. This one runs the
    comparison the other way — the ontology against what writers produce — which is
    the only direction that catches a declaration with nothing behind it. Three were
    live at once before it existed, the largest across 31,042 edges.

    Verifications:
    - node types, node kinds and edge types nobody wrote are each reported
    - every finding is ADVISORY, so an audit that meets them still exits 0
    """
    vertices = [_session(), _claim()]
    edges = [AuditEdge(label="CONTAINS",
                       from_vid="scope:main:session:s1", from_label="Session",
                       to_vid="scope:main:claim:c1", to_label="Claim")]

    issues = audit_declarations(vertices, edges)

    # Verifies: absence is reported for each declared kind of thing
    assert any("Unwritten node type: `Thread`" in issue for issue in issues)
    assert any("Unwritten edge type: `SOLVED_BY`" in issue for issue in issues)
    assert any("Unwritten Claim kind(s)" in issue for issue in issues)

    # Verifies: reporting only. A rule that can fail forever on unfixable history is
    # a rule nobody can land, which is the whole reason severity exists.
    assert all(severity_of(issue) == ADVISORY for issue in issues)


def test_a_property_a_writer_produces_and_the_ontology_omits_is_reported():
    """
    Scenario: A TOUCHES edge carrying its declared `anchors` plus an undeclared key

    Drift runs both ways. A declared-and-unwritten property is a promise to consumers
    that nothing keeps; a written-and-undeclared one is a consumer surface the
    ontology cannot be read to discover. `RETURNS.judged_terms` was the second kind.
    """
    edges = [AuditEdge(label="TOUCHES",
                       from_vid="scope:main:session:s1", from_label="Session",
                       to_vid="artifact:src/app.js", to_label="Artifact",
                       properties={"anchors": "u1", "invented_key": "x"})]

    issues = audit_declarations([_session()], edges)

    # Verifies: the undeclared key is named, the declared one is not complained about
    assert any(
        "Undeclared TOUCHES propert(ies): invented_key" in issue for issue in issues
    )
    assert not any("Unwritten TOUCHES propert" in issue for issue in issues)


def test_a_claim_kind_landing_on_an_entity_is_reported_as_undeclared():
    """
    Scenario: An Entity carrying `literature/finding`, a *claim* kind

    `Claim.kind` is open by design — an expert manifest adds namespaced values without
    touching the ontology — so a namespaced claim kind is not drift. Entity has no such
    extension surface, which makes the same string on an Entity a writer escaping its
    vocabulary. Two Entities carry exactly this in the live graph, from an extraction
    prompt that presented both vocabularies in adjacent bullets sharing a word.
    """
    entity = AuditVertex(vid="scope:literature:entity:e1", label="Entity",
                         properties={**_PROV, "kind": "literature/finding",
                                     "scope": "literature"})
    claim = _claim(vid="scope:literature:claim:c1", kind="literature/finding",
                   scope="literature")

    issues = audit_declarations([entity, claim], [])

    # Verifies: flagged on the Entity, and the extensible Claim is left alone
    assert any(
        "Undeclared Entity kind(s): literature/finding" in issue for issue in issues
    )
    assert not any("Undeclared Claim kind" in issue for issue in issues)
