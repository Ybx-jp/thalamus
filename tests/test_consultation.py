"""
Consultation-ticket protocol tests (docs/02 — "the mint is the write").

Interfaces: thalamus.harness.consultation, thalamus.substrate.writer.write_exchange/
close_exchange, thalamus.eval.traces.TraceEvent.ticket
Infrastructure: none; fakes and monkeypatched reader functions only
Scope: the exchange record's lifecycle — mint, scoped retrieval grant, citation
validation, single-use burn. Brief *content* comes from reader functions tested in
test_reader.py; what is pinned here is the protocol around them.

Grounding: citation validation is a write-path defense — consultation is a memory
write channel, and "existing prompt injection defenses fail to cover memory poisoning"
(arXiv 2606.04329), so the gate lives where the exchange is written, not where the
answer is read. The exchange record itself is execution provenance for a multi-agent
collaboration step (arXiv 2606.04990).
"""

from datetime import datetime, timezone

from gremlin_python.process.traversal import Merge, T

from thalamus.contract.manifest import ExpertManifest
from thalamus.eval.traces import TraceEvent
from thalamus.harness import consultation
from thalamus.eval.sync import answering_context
from thalamus.harness.consultation import (
    consult_answer,
    consult_request,
    exchange_vid,
    extract_citations,
    ticket_scope,
)
# --------------------------------------------------------------------------------------
# Fake graph: just enough traversal surface for load_exchange, _vertex_exists,
# write_exchange, and close_exchange.
# --------------------------------------------------------------------------------------


class FakeGraph:
    def __init__(self, vertices: dict[str, dict] | None = None):
        # vid -> {"label": ..., <flat properties>}
        self.vertices = dict(vertices or {})
        self.merged_vertices: list[dict] = []
        self.property_writes: list[tuple[str, str, object]] = []
        self.edges: list[dict] = []

    def V(self, vid=None):
        return _VertexChain(self, vid)

    def merge_v(self, spec):
        record = {"spec": spec, "on_create": {}}
        self.merged_vertices.append(record)
        return _MergeChain(record)

    def merge_e(self, spec):
        record = {"spec": dict(spec), "properties": {}}
        self.edges.append(record)
        return _MergeChain(record, properties_key="properties")


class _MergeChain:
    def __init__(self, record, properties_key="on_create"):
        self.record = record
        self.properties_key = properties_key
        self.bytecode = "fake"

    def option(self, key, value):
        if key is Merge.on_create:
            self.record[self.properties_key] = value
        return self

    def iterate(self):
        return self


class _VertexChain:
    def __init__(self, graph, vid):
        self.graph = graph
        self.vid = vid
        self.keys: tuple[str, ...] = ()
        self.bytecode = "fake"

    def has_label(self, label):
        vertex = self.graph.vertices.get(self.vid)
        if vertex is not None and vertex.get("label") != label:
            self.vid = None  # label mismatch: traversal yields nothing
        return self

    def has(self, key, value):
        if self.vid is None:  # no-arg V(): scan for the first property match
            self.vid = next(
                (v for v, props in self.graph.vertices.items() if props.get(key) == value),
                None,
            )
        elif self.graph.vertices.get(self.vid, {}).get(key) != value:
            self.vid = None
        return self

    def value_map(self, *keys):
        self.keys = keys
        return self

    def limit(self, _n):
        return self

    def to_list(self):
        vertex = self.graph.vertices.get(self.vid)
        if vertex is None:
            return []
        return [{k: [vertex[k]] for k in self.keys if k in vertex}]

    def has_next(self):
        return self.vid in self.graph.vertices

    def property(self, key, value):
        self.graph.property_writes.append((self.vid, key, value))
        vertex = self.graph.vertices.get(self.vid)
        if vertex is not None:
            vertex[key] = value
        return self

    def iterate(self):
        return self


def _open_exchange_graph(ticket="t1", expert="literature", status="open"):
    cited_vid = f"scope:{expert}:claim:abc123"
    graph = FakeGraph(
        {
            exchange_vid(ticket): {
                "label": "Exchange",
                "question": "How is provenance floored?",
                "expert": expert,
                "from_scope": "main",
                "status": status,
            },
            cited_vid: {"label": "Claim", "description": "a knowledge claim"},
        }
    )
    return graph, cited_vid


# --------------------------------------------------------------------------------------
# Citations
# --------------------------------------------------------------------------------------


def test_citations_are_backticked_scoped_vertex_ids_only():
    """
    Scenario: An answer cites a scoped claim, names a global artifact, and mentions
    an ID-shaped string in prose

    Verifications:
    - backticked scoped IDs are extracted, deduplicated, in order
    - global artifact IDs and unbackticked prose are not citations

    The IDs double as citation handles (decision log 2026-07-15); a global artifact
    is shared vocabulary, not evidence inside the consulted scope — citing one is
    exactly the "orphan artifact" advice the protocol rejects.
    """
    answer = (
        "Per `scope:literature:claim:9f3a` and again `scope:literature:claim:9f3a`, "
        "the floor is DERIVED_FROM. See `artifact:src/a.py` and "
        "scope:literature:claim:bare-prose, plus `scope:literature:entity:tiers`."
    )

    assert extract_citations(answer) == [
        "scope:literature:claim:9f3a",
        "scope:literature:entity:tiers",
    ]


# --------------------------------------------------------------------------------------
# Minting — the mint IS the write
# --------------------------------------------------------------------------------------


def _stub_brief(monkeypatch, sections=("## Open threads\n\nx",), refs=("scope:literature:thread:t1",)):
    monkeypatch.setattr(
        consultation, "_assemble_brief", lambda g, scope, question: (list(sections), list(refs))
    )


def _stub_manifests(monkeypatch, scopes=("literature",)):
    manifest = ExpertManifest(
        scope="literature", name="Technical literature", domain="agent memory"
    )
    monkeypatch.setattr(consultation, "available_scopes", lambda: list(scopes))
    monkeypatch.setattr(consultation, "load_manifest", lambda scope: manifest)


def test_minting_a_ticket_writes_the_exchange_record(monkeypatch):
    """
    Scenario: A main-pinned session consults the literature expert

    Verifications:
    - the Exchange vertex is written at mint time, open, with a provenance envelope
    - the brief's served nodes become role=brief REFERENCES edges
    - the returned text carries the ticket and the exchange vertex ID

    "The mint is the write": an unrecorded consultation is impossible by construction
    because the ticket only exists as the exchange record's ID (docs/02) — the
    exchange is an execution-provenance record of the collaboration step (2606.04990).
    """
    _stub_manifests(monkeypatch)
    _stub_brief(monkeypatch)
    graph = FakeGraph()

    result = consult_request(graph, "literature", "How is provenance floored?", "main")

    assert len(graph.merged_vertices) == 1
    written = graph.merged_vertices[0]["on_create"]
    vertex_id = written[T.id]
    # Verifies: the record opens before any answer exists
    assert written["status"] == "open"
    assert written["expert"] == "literature"
    assert written["from_scope"] == "main"
    # Verifies: provenance is stamped, not asked for (docs/05)
    assert written["tier"] == 1
    assert written["source"] == "consultation:main"
    assert written["ingested_at"]
    # Verifies: consultation routes through main, never expert-to-expert
    assert vertex_id.startswith("scope:main:exchange:")
    # Verifies: what the brief served is recorded, by ID, never copied
    assert graph.edges[0]["spec"][T.label] == "REFERENCES"
    assert graph.edges[0]["properties"] == {"role": "brief"}
    # Verifies: the caller gets the handles the protocol needs
    assert f"`{vertex_id}`" in result
    assert "consult_answer" in result


def test_consultation_is_refused_when_there_is_nothing_to_consult(monkeypatch):
    """
    Scenario: The consulted scope's memory is empty

    An expert with nothing to cite cannot produce a citable answer — consult_answer
    would reject everything it says — so the refusal happens at mint time and no
    orphan exchange record is written.
    """
    _stub_manifests(monkeypatch)
    _stub_brief(monkeypatch, sections=(), refs=())
    graph = FakeGraph()

    result = consult_request(graph, "literature", "Anything?", "main")

    assert "refused" in result.lower()
    assert "holds no memory" in result
    assert graph.merged_vertices == []


def test_refusal_distinguishes_no_match_from_empty_scope(monkeypatch):
    """
    Scenario: The consulted scope holds memory, but nothing matched the question

    A knowledge-only scope (claims, no sessions or threads) yields an empty brief
    whenever the question misses its vocabulary. Telling the caller the scope "holds
    no memory" sends them chasing a phantom ingestion problem (measured 2026-07-19:
    eval-methodology held 11 claims and was reported empty); the honest remedy is
    rephrasing. Still refused, still no orphan exchange record.
    """
    _stub_manifests(monkeypatch)
    _stub_brief(monkeypatch, sections=(), refs=())
    graph = FakeGraph(
        {"scope:literature:claim:abc": {"label": "Claim", "scope": "literature"}}
    )

    result = consult_request(graph, "literature", "Anything?", "main")

    assert "refused" in result.lower()
    assert "nothing in scope `literature` matched" in result
    assert "holds no memory" not in result
    assert graph.merged_vertices == []


def test_self_consultation_unknown_experts_and_empty_questions_are_refused(monkeypatch):
    """
    Scenario: The model asks for its own scope, a scope with no manifest, and
    nothing at all

    The manifest set is the roster (docs/01): no manifest, no expert. Consulting
    yourself is just recall wearing a costume.
    """
    _stub_manifests(monkeypatch)
    graph = FakeGraph()

    assert "refused" in consult_request(graph, "main", "q", "main").lower()
    assert "refused" in consult_request(graph, "phantom", "q", "main").lower()
    assert "refused" in consult_request(graph, "literature", "  ", "main").lower()
    assert graph.merged_vertices == []


# --------------------------------------------------------------------------------------
# Answering — citation validation and the single-use burn
# --------------------------------------------------------------------------------------


def test_an_uncited_answer_is_rejected_and_the_ticket_stays_open():
    """
    Scenario: The expert answers in confident prose with no citations

    Verifications:
    - the answer is rejected, the exchange stays open, nothing is written

    This is the docs/05 poisoning defense made mechanical: advice that cannot be
    traced to the consulted scope's own memory never becomes part of the record.
    The gate is on the write path — where 2606.04329 says memory defenses have to
    live — not on the reader.
    """
    graph, _ = _open_exchange_graph()

    result = consult_answer(graph, "t1", "Trust me, use a Bayesian score.")

    assert "Rejected" in result
    assert graph.vertices[exchange_vid("t1")]["status"] == "open"
    assert graph.edges == []


def test_citations_outside_the_consulted_scope_are_rejected():
    """
    Scenario: The answer cites a node from a different expert's scope

    An expert answers from its own memory; a cross-scope citation would let the
    subagent smuggle in authority the ticket never granted.
    """
    graph, _ = _open_exchange_graph(expert="literature")

    result = consult_answer(
        graph, "t1", "Because `scope:main:claim:deadbeef` says so."
    )

    assert "Rejected" in result
    assert "outside the consulted scope" in result
    assert graph.vertices[exchange_vid("t1")]["status"] == "open"


def test_citations_that_resolve_to_nothing_are_rejected():
    """
    Scenario: The answer cites a well-formed ID that was never written

    Hallucinated references are a measured failure mode of this very corpus
    (bootstrap findings: hallucinated thread_refs are real); a citation must point
    at real memory.
    """
    graph, _ = _open_exchange_graph(expert="literature")

    result = consult_answer(
        graph, "t1", "See `scope:literature:claim:0000000000000000`."
    )

    assert "Rejected" in result
    assert "does not exist" in result
    assert graph.vertices[exchange_vid("t1")]["status"] == "open"


def test_a_validly_cited_answer_burns_the_ticket_and_records_its_evidence():
    """
    Scenario: The expert answers citing a claim that exists in its scope

    Verifications:
    - the exchange closes: answer recorded, status answered
    - each citation becomes a role=citation REFERENCES edge (evidence tracing —
      the answer's evidence-support relations, 2606.04990)
    - the burned ticket refuses a second answer (single-use)
    """
    graph, cited_vid = _open_exchange_graph()

    result = consult_answer(graph, "t1", f"The floor is DERIVED_FROM; see `{cited_vid}`.")

    assert "closed" in result
    assert graph.vertices[exchange_vid("t1")]["status"] == "answered"
    assert graph.vertices[exchange_vid("t1")]["answer"].startswith("The floor")
    citation_edges = [e for e in graph.edges if e["properties"] == {"role": "citation"}]
    assert [e["spec"][T.label] for e in citation_edges] == ["REFERENCES"]

    # Verifies: single-use — the mint opened it, one answer closes it, forever
    second = consult_answer(graph, "t1", f"Actually, also `{cited_vid}`.")
    assert "burned" in second


def test_unminted_tickets_are_rejected():
    """
    Scenario: The model invents a plausible-looking ticket

    Authority crosses scopes only through a server-minted ticket; an uninvented
    ticket loads no exchange record and grants nothing.
    """
    graph = FakeGraph()

    assert "no exchange was ever minted" in consult_answer(
        graph, "cafebabe", "answer `scope:x:claim:y`"
    )


# --------------------------------------------------------------------------------------
# The retrieval grant
# --------------------------------------------------------------------------------------


def test_only_an_open_ticket_grants_its_expert_scope():
    """
    Scenario: Resolve retrieval scope from an open ticket, a burned one, and a
    never-minted one

    The grant is per-exchange and dies with the ticket — the server resolves it from
    the exchange record, never from model input (docs/07).
    """
    open_graph, _ = _open_exchange_graph(ticket="t1", status="open")
    burned_graph, _ = _open_exchange_graph(ticket="t2", status="answered")

    assert ticket_scope(open_graph, "t1") == "literature"
    assert ticket_scope(burned_graph, "t2") is None
    assert ticket_scope(FakeGraph(), "t3") is None


# --------------------------------------------------------------------------------------
# The trace join key
# --------------------------------------------------------------------------------------


def test_a_trace_records_the_ticket_it_ran_under():
    """
    Scenario: A recall ran inside a consultation; its tap line carries the ticket

    The MCP server cannot see its caller's session (lab/001), so the ticket recorded
    verbatim in the trace input is the only join between the consulting Session and
    the Exchange — it is how eval sync lands the CONSULTS edge and stamps
    exchange_id on the Trace node.
    """
    event = TraceEvent(
        ts=datetime(2026, 7, 15, tzinfo=timezone.utc),
        session_id="sess-1",
        cwd="/home/op/code/thalamus",
        tool="memory_recall",
        tool_input={"query": "trust floors", "ticket": "t1"},
        tool_response="**Node:** `scope:literature:claim:9f3a`",
    )

    assert event.ticket() == "t1"
    assert TraceEvent(
        ts=event.ts, session_id="s", cwd="", tool="memory_recall", tool_input={}
    ).ticket() == ""


def test_exchange_ids_rendered_in_responses_are_trace_extractable():
    """
    Scenario: A tool response mentions an exchange vertex ID

    The trace matcher derives its prefix alternation from the ontology, so the new
    Exchange type is node-level traceable the day it exists — the decision-log
    invariant ("the tap can never lag the reader") extended to consultations.
    """
    event = TraceEvent(
        ts=datetime(2026, 7, 15, tzinfo=timezone.utc),
        session_id="sess-1",
        cwd="",
        tool="memory_recall",
        tool_input={},
        tool_response="Opened `scope:main:exchange:abcd1234` for the question.",
    )

    assert event.returned_node_ids() == ["scope:main:exchange:abcd1234"]


def test_answering_context_separates_a_voiced_expert_from_a_self_answer():
    """
    Scenario: The same exchange is closed from four different calling contexts

    The citation gate proves an answer rests on the expert's own memory; it cannot
    prove *who assembled it*. A session that answers its own ticket inline writes a
    byte-identical Exchange record to one a subagent voiced, so the independence the
    protocol asks for was unauditable. Measured 2026-07-28: a subagent shares its
    parent's session_id, so the tap's agent_type is the only separating signal.

    `unknown` is pinned separately from `self` on purpose — a trace written before
    the tap kept the field records no fact about who answered, and collapsing that
    into "the main loop did it" would manufacture provenance, the failure the
    retroactive-stamp rule (decision log 2026-07-27) exists to prevent.
    """
    assert answering_context("thalamus-literature", "literature") == "voiced"
    assert answering_context("", "literature") == "self"
    assert answering_context("general-purpose", "literature") == "agent:general-purpose"
    assert answering_context(None, "literature") == "unknown"

    # The expert's own agent definition is scope-specific: a subagent voicing a
    # *different* expert is independent of the main loop but is not this expert.
    assert answering_context("thalamus-eval-methodology", "literature") == (
        "agent:thalamus-eval-methodology"
    )


def test_trace_event_preserves_absent_agent_fields_as_none():
    """
    Scenario: Tap lines written before and after the agent fields existed

    An absent field and an empty field are different facts — empty means the main
    loop called, absent means the tap did not record it. `or ""` on the read path
    would fuse them and silently backdate every legacy consultation to `self`.
    """
    import json

    from thalamus.eval.traces import _parse_line

    legacy = _parse_line(json.dumps(
        {
            "ts": "2026-07-15T00:00:00Z",
            "session_id": "s",
            "tool_name": "mcp__thalamus__consult_answer",
            "tool_input": {"ticket": "t1"},
            "tool_response": "closed",
        }
    ))
    assert legacy is not None and legacy.agent_type is None

    main_loop = _parse_line(json.dumps(
        {
            "ts": "2026-07-28T00:00:00Z",
            "session_id": "s",
            "tool_name": "mcp__thalamus__consult_answer",
            "tool_input": {"ticket": "t1"},
            "tool_response": "closed",
            "agent_id": "",
            "agent_type": "",
        }
    ))
    assert main_loop is not None and main_loop.agent_type == ""


# --------------------------------------------------------------------------------------
# A closed design ticket is the mechanical signal that a design was settled.
# --------------------------------------------------------------------------------------


def test_a_design_question_is_classified_at_mint_not_recognized_later():
    """
    Scenario: Tickets are minted for design work and for ordinary questions

    Verifications:
    - design intent is recorded as a stored `kind`
    - questions that merely mention past work are not design

    Recorded at mint because closing a design ticket is the point where a design was
    settled, and a property decided later is decided only when someone remembers to
    look — which is the failure the readiness check already had. The classifier is the
    same lexical rule `conditioning.sh` fires on at UserPromptSubmit: two regexes would
    be two different answers to one question.
    """
    assert consultation.question_kind("Should we adopt bi-temporal claim identity?") == "design"
    assert consultation.question_kind("Design a new eval metric for waste") == "design"
    assert consultation.question_kind("Two coupled schema questions about time") == "design"

    assert consultation.question_kind("What happened in the last session?") == "general"
    assert consultation.question_kind("Review a draft case study") == "general"
    assert consultation.question_kind("") == "general"


def test_closing_a_design_ticket_names_the_readiness_check():
    """
    Scenario: A validly cited answer closes a ticket that was minted as design work

    Verifications:
    - the close message names the readiness skill and its trigger condition
    - it says the check is advisory, so it cannot read as a gate on the work
    - a general ticket closes silently

    The readiness check used to fire on the consulting agent's judgement about whether
    a design had been settled. consult_answer closing a design ticket is that same fact,
    mechanically — the whole reason to ask an expert was to act on the answer.
    """
    ticket = "abc123"
    graph = FakeGraph({
        exchange_vid(ticket): {
            "label": "Exchange", "expert": "literature", "status": "open",
            "kind": "design",
        },
        "scope:literature:claim:aaa": {"label": "Claim"},
    })

    message = consult_answer(graph, ticket, "Adopt it — see `scope:literature:claim:aaa`.")

    assert "closed" in message
    assert "thalamus-design-readiness" in message
    assert "advisory, never blocking" in message


def test_closing_a_general_ticket_says_nothing_about_readiness():
    """A reminder that fires on every close is the wallpaper the design-intent
    classifier exists to avoid."""
    ticket = "def456"
    graph = FakeGraph({
        exchange_vid(ticket): {
            "label": "Exchange", "expert": "literature", "status": "open",
            "kind": "general",
        },
        "scope:literature:claim:aaa": {"label": "Claim"},
    })

    message = consult_answer(graph, ticket, "See `scope:literature:claim:aaa`.")

    assert "closed" in message
    assert "thalamus-design-readiness" not in message


def test_the_brief_ranks_open_threads_against_the_question(monkeypatch):
    """
    Scenario: a brief is assembled for a scope whose open threads outnumber the
    section's limit

    Verifications:
    - the question is passed through to the thread recall as its ranking topic

    Every other section of the brief is question-matched. Unranked, threads come back
    ordered by status — a sample, not a list — and in a small scope that sample is the
    whole scope, served to every consultation whatever was asked. Measured 2026-08-11:
    the section was 40% of a literature brief, and a thread minted from a probe's
    return value ("Thalamus memory store currently has zero open threads", while 402
    were open) rode 43 briefs into the scope whose job is grounding.
    """
    seen = {}

    def fake_open_threads(g, project, limit, scope, topic=""):
        seen["project"], seen["limit"], seen["scope"], seen["topic"] = (
            project, limit, scope, topic,
        )
        return []

    monkeypatch.setattr(consultation, "recall_open_threads", fake_open_threads)
    monkeypatch.setattr(consultation, "recall_exchanges", lambda *a, **k: [])
    monkeypatch.setattr(consultation, "recall_recent", lambda *a, **k: [])
    monkeypatch.setattr(consultation, "recall", lambda *a, **k: [])

    consultation._assemble_brief(FakeGraph(), "literature", "how should a thread close?")

    # Verifies: the question reaches the ranker, not just the other sections
    assert seen["topic"] == "how should a thread close?"
    assert seen["scope"] == "literature"


def test_the_ticket_carries_the_research_protocol_the_subagent_works_from(monkeypatch):
    """
    Scenario: a minted ticket, read as the answering subagent receives it

    The answering side had three sentences of mechanics and no method, while the
    asking side had a documented one. Verifications:
    - the procedure ships in the ticket, which is what the subagent is handed
    - the stopping rule is present and precedes the self-check. MAST splits failure
      fatality: not knowing when to stop appears almost exclusively in failed runs,
      where missing verification occurs in successful ones too, so the order is the
      finding rather than a preference (arXiv 2503.13657).
    - no sufficiency gate. "Decide whether you have enough before answering" was
      measured at ~19pp of answerable accuracy for ~59% refusal, so its absence is
      deliberate and a later edit must not quietly add it back.
    """
    _stub_manifests(monkeypatch)
    _stub_brief(monkeypatch)
    graph = FakeGraph()

    result = consult_request(graph, "literature", "How is provenance floored?", "main")

    assert "## How to research this" in result
    stop = result.index("Stop on a dry round")
    check = result.index("Check the answer in parts")
    assert stop < check, "the stopping rule must precede the self-check"
    assert "reformulate on a miss" in result
    assert "refute the asker" in result
    assert "Do not gate the answer on feeling sufficiently informed" in result
