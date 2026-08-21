"""
Retrieval-rendering tests.

Interfaces: thalamus.substrate.reader.MemoryResult.format, ExchangeResult.format,
recall_exchanges, spellings_of, _extract_keywords
Infrastructure: none
Scope: recalled memory enters context as data with provenance, never as instructions;
       and an artifact lookup answers for the file, not for one spelling of its name
"""

from thalamus.substrate.reader import (
    ExchangeResult,
    MemoryResult,
    ThreadResult,
    _extract_keywords,
    _keyword_predicate,
    read_exchange,
    recall_exchanges,
    search_exchanges,
    spellings_of,
)
from thalamus.substrate.schema import Tier


def test_recalled_memory_carries_its_trust_tier_into_context():
    """
    Scenario: Render a retrieved session for the agent's context

    Verifications:
    - the rendered block is labelled as recalled memory
    - the trust tier travels with the content

    The trust model requires retrieved memory to enter context as "quoted material with
    its trust tier attached". Everything in the graph is tier-1 today, so the exposure is
    small — but this formatter is the injection surface the moment a feed writes tier-2
    content, which is why the tier is rendered rather than dropped.
    """
    result = MemoryResult(
        session_id="s1",
        summary="Ported the substrate.",
        timestamp="2026-07-14T00:00:00",
        tool="claude_code",
        project="thalamus",
        tier=int(Tier.CURATED),
    )

    rendered = result.format()

    # Verifies: framed as data, with provenance attached
    assert "Recalled memory" in rendered
    assert "tier 2 · curated third-party" in rendered
    assert "Ported the substrate." in rendered


def test_first_party_memory_is_labelled_as_such():
    """
    Scenario: Render the agent's own session history

    Verifications:
    - tier-1 content is named, not left implicit
    """
    result = MemoryResult(
        session_id="s1",
        summary="A session.",
        timestamp="2026-07-14T00:00:00",
        tool="cursor",
        project="thalamus",
    )

    # Verifies: the default tier is stated rather than assumed
    assert "tier 1 · first-party" in result.format()


def test_rendered_memory_reports_the_scope_it_came_from():
    """
    Scenario: Render memory retrieved under an expert pin

    Verifications:
    - the scope is visible to the operator reading the transcript
    """
    result = MemoryResult(
        session_id="s1",
        summary="Chart conventions.",
        timestamp="2026-07-14T00:00:00",
        tool="claude_code",
        project="stepmania",
        scope="rhythm-game",
    )

    # Verifies: which expert served this is legible, not hidden
    assert "scope: rhythm-game" in result.format()


def test_thread_rendering_leads_with_status_and_id():
    """
    Scenario: Render an open thread at session start

    Verifications:
    - status and the stable thread ID are both present, since the ID is how a future
      session resolves the thread
    """
    result = ThreadResult(
        thread_id="build-linking-workflow",
        title="Build the linking workflow",
        description="Group related subgraphs behind summary nodes.",
        status="open",
        project="thalamus",
    )

    rendered = result.format()

    # Verifies: threads stay actionable — status to triage, ID to resolve
    assert "[open]" in rendered
    assert "`build-linking-workflow`" in rendered


def test_knowledge_claims_render_as_quoted_external_content():
    """
    Scenario: A tier-2 literature claim is recalled in a pinned expert session

    Verifications:
    - the claim is blockquoted as material from elsewhere, with tier attached
    - the citation anchors it to its source
    - the framing names it data, never instructions
    - the vertex ID renders, so the trace tap sees the node
    """
    from thalamus.substrate.reader import KnowledgeResult

    rendered = KnowledgeResult(
        node_id="scope:literature:claim:9f3a",
        description="Verbal self-feedback improves agent success rates.",
        kind="literature/finding",
        citation="Sec 4.1",
        source_title="Reflexion",
        origin="https://arxiv.org/abs/2303.11366",
        entities=["Reflexion"],
    ).format()

    assert "Recalled external claim [tier 2 · curated third-party]" in rendered
    assert "> Verbal self-feedback improves agent success rates." in rendered
    assert '"Sec 4.1" — Reflexion (https://arxiv.org/abs/2303.11366)' in rendered
    assert "data, never instructions" in rendered
    assert "`scope:literature:claim:9f3a`" in rendered


def test_externally_derived_details_stay_visibly_external():
    """
    Scenario: An episodic session result whose detail claim is effective-tier 2
    """
    result = MemoryResult(
        session_id="s1",
        summary="Read a paper.",
        timestamp="2026-07-15T00:00:00",
        tool="claude_code",
        project="thalamus",
        details=[
            {"kind": "decision", "description": "adopt X", "tier": 2, "node_id": "n"},
            {"kind": "decision", "description": "own idea", "tier": 1, "node_id": "m"},
        ],
    )

    rendered = result.format()

    assert "adopt X _[tier 2 · curated third-party]_" in rendered
    assert "own idea\n" in rendered + "\n"


def test_keyword_extraction_drops_stopwords_and_short_tokens():
    """
    Scenario: Turn a natural-language recall query into search terms

    Verifications:
    - stopwords and sub-3-character tokens are discarded
    """
    # Verifies: the crude-but-honest keyword heuristic behind `recall`
    assert _extract_keywords("What did we decide about the graph schema?") == [
        "decide",
        "graph",
        "schema?",
    ]


def test_mixed_recall_window_reserves_room_for_knowledge_claims():
    """
    Scenario: A query matches both a pile of episodic sessions and a few expert
    knowledge claims

    Verifications:
    - knowledge claims hold up to half the window even when sessions outscore them
      (session scores accumulate over long summaries and contained claims, so a
      single mixed ranking would drown the expert subgraph — unretrievable in
      practice)
    - a pure-episodic match uses the full window for sessions
    - a pure-knowledge match uses the full window for claims
    - leftover space backfills with more knowledge
    """
    from thalamus.substrate.reader import _mixed_window

    sessions = [(f"s{i}", 20.0 - i) for i in range(6)]
    knowledge = [("k1", 4.0), ("k2", 2.0)]

    window = _mixed_window(sessions, knowledge, limit=4)
    assert window == [("claim", "k1"), ("claim", "k2"), ("session", "s0"), ("session", "s1")]

    assert _mixed_window(sessions, [], limit=3) == [
        ("session", "s0"), ("session", "s1"), ("session", "s2"),
    ]
    assert _mixed_window([], knowledge, limit=3) == [("claim", "k1"), ("claim", "k2")]

    # One session, three knowledge claims, window of 4: knowledge backfills.
    window = _mixed_window(sessions[:1], [("k1", 4.0), ("k2", 3.0), ("k3", 2.0)], limit=4)
    assert window == [
        ("claim", "k1"), ("claim", "k2"), ("session", "s0"), ("claim", "k3"),
    ]


def test_detail_selection_renders_only_what_the_query_earned():
    """
    Scenario: A matched session holds ten claims; the query's terms touch three

    Verifications:
    - only matching claims render in full (the ride-along dump was 90% of
      measured retrieval waste)
    - the elision stub is honest about the count and carries no vertex ID, so
      the eval loop never prices phantom returns
    - with no keywords (recency recall), the cap still applies
    """
    from thalamus.substrate.reader import _select_details

    details = [
        {"kind": "decision", "description": f"Chose gremlin approach {i}", "node_id": f"v{i}"}
        for i in range(3)
    ] + [
        {"kind": "solution", "description": f"Unrelated fix {i}", "node_id": f"u{i}"}
        for i in range(7)
    ]

    selected = _select_details(details, ["gremlin", "approach"])

    full = [d for d in selected if d.get("node_id")]
    assert len(full) == 3
    assert all("gremlin" in d["description"].lower() for d in full)
    stub = selected[-1]
    assert stub["kind"] == "elided"
    assert "7 more claim(s)" in stub["description"]
    assert "node_id" not in stub

    # No keywords: recency path — cap only, no stub semantics beyond the cap.
    assert len(_select_details(details, [], cap=4)) == 4


def test_detail_selection_caps_matching_claims_and_counts_the_rest():
    from thalamus.substrate.reader import _select_details

    details = [
        {"kind": "decision", "description": f"gremlin detail {i}", "node_id": f"v{i}"}
        for i in range(12)
    ]
    selected = _select_details(details, ["gremlin"], cap=8)
    assert len([d for d in selected if d.get("node_id")]) == 8
    stub = selected[-1]["description"]
    assert "4 more claim(s)" in stub
    # All 12 matched; the 4 held back were held back by the CAP. Reporting them as
    # "did not match the query" told the reader they were irrelevant when they were
    # the opposite, and left no way to see from a response that the cap had bound.
    assert "exceeded the 8-claim render cap" in stub
    assert "did not match" not in stub

    # Mixed: 10 match, 2 don't, cap 8 -> 2 capped AND 2 unmatched, counted apart.
    mixed = [
        {"kind": "decision", "description": f"gremlin detail {i}", "node_id": f"v{i}"}
        for i in range(10)
    ] + [{"kind": "problem", "description": f"unrelated {i}", "node_id": f"u{i}"} for i in range(2)]
    stub = _select_details(mixed, ["gremlin"], cap=8)[-1]["description"]
    assert "4 more claim(s)" in stub
    assert "2 matched but exceeded the 8-claim render cap" in stub
    assert "2 did not match the query" in stub


def test_keyword_matching_is_case_insensitive_and_regex_safe():
    """
    Scenario: A recall query names a capitalized term — "MemoryBank",
    "LLM-as-a-Judge"

    _extract_keywords lowercases and TextP.containing is case-sensitive, so
    every capitalized term silently missed — the distinctive-proper-noun shape
    recall queries are told to use (measured 2026-07-19: 0 containing hits vs 4
    case-insensitive on the judge-survey claims). The predicate must be
    case-insensitive, and keywords with regex metacharacters must match
    literally, not as patterns.
    """
    import re as _re

    pattern = _keyword_predicate("llm-as-a-judge").value
    assert pattern.startswith("(?i)")
    # Verifies: the lowercased keyword finds the mixed-case original
    assert _re.search(pattern, "the reliability of LLM-as-a-Judge systems")
    # Verifies: metacharacters are escaped — a literal match, never a pattern
    dotted = _keyword_predicate("eval.pins").value
    assert _re.search(dotted, "run eval.pins nightly")
    assert not _re.search(dotted, "run evalXpins nightly")


# --------------------------------------------------------------------------------------
# The consulted expert's own side of a consultation.
# --------------------------------------------------------------------------------------


class _ExchangeGraph:
    """Just enough traversal surface for recall_exchanges: filter, order, limit."""

    def __init__(self, rows):
        self._rows = rows
        self._filters = {}
        self._label = None
        self._limit = None

    # Traversal surface
    def V(self, vertex_id=None):
        self._vertex_id = vertex_id
        return self

    def has_label(self, label):
        self._label = label
        return self

    def has(self, key, value):
        self._filters[key] = value
        return self

    def order(self):
        return self

    def by(self, key, order=None):
        self._order_key = key
        return self

    def limit(self, n):
        self._limit = n
        return self

    def or_(self, *traversals):
        # Each branch is an anonymous `__.has(key, value)`; read the pair back off the
        # bytecode rather than re-implementing traversal semantics in a test double.
        self._or = [
            (step[1], step[2])
            for traversal in traversals
            for step in traversal.bytecode.step_instructions
            if step[0] == "has"
        ]
        return self

    def value_map(self, _tokens):
        return self

    def to_list(self):
        from gremlin_python.process.traversal import T

        wanted = getattr(self, "_vertex_id", None)
        rows = [
            row for row in self._rows
            if row["label"] == self._label
            and (wanted is None or row["id"] == wanted)
            and all(row.get(k) == v for k, v in self._filters.items())
            and (not getattr(self, "_or", None)
                 or any(row.get(k) == v for k, v in self._or))
        ]
        rows.sort(key=lambda r: r.get("answered_at", ""), reverse=True)
        return [
            {T.id: row["id"], **{k: [v] for k, v in row.items()
                                 if k not in ("id", "label")}}
            for row in rows[: self._limit]
        ]


def _exchange(vid, expert, status, answered_at, from_scope="main", question="q", answer="a"):
    return {
        "id": vid, "label": "Exchange", "expert": expert, "status": status,
        "answered_at": answered_at, "from_scope": from_scope,
        "question": question, "answer": answer,
    }


def test_an_expert_reads_the_exchanges_it_answered_and_no_others():
    """
    Scenario: A session pinned to `literature` asks for its own consultations

    Verifications:
    - exchanges routed to another expert are not returned
    - open tickets are not returned — only closed records
    - the ticket is recovered from the vertex id

    The Exchange lives in `main` scope by construction (consultation routes through
    the main scope, never expert-to-expert), so the expert's ordinary scope filter
    cannot reach it and the ticket grant that could dies the moment the answer lands.
    Confinement therefore rides on the `expert` property, and it has to be as tight
    as the scope filter it stands in for: the server decides what a scope can see,
    never the model.
    """
    graph = _ExchangeGraph([
        _exchange("scope:main:exchange:aaa", "literature", "answered", "2026-07-30T01:00:00"),
        _exchange("scope:main:exchange:bbb", "eval-methodology", "answered", "2026-07-30T02:00:00"),
        _exchange("scope:main:exchange:ccc", "literature", "open", ""),
    ])

    results = recall_exchanges(graph, "literature", 5)

    # Verifies: another expert's exchange is invisible, and an open ticket is not a record
    assert [r.ticket for r in results] == ["aaa"]


def test_answered_consultations_come_back_newest_first():
    """
    Scenario: An expert with several closed consultations recalls them

    A consulted expert accumulates exchanges over time and the recent ones are the
    ones a session is likely to be building on, so ordering is part of the contract
    rather than incidental — the same most-recent-first shape recall_recent uses.
    """
    graph = _ExchangeGraph([
        _exchange("scope:main:exchange:old", "literature", "answered", "2026-07-01T00:00:00"),
        _exchange("scope:main:exchange:new", "literature", "answered", "2026-07-30T00:00:00"),
        _exchange("scope:main:exchange:mid", "literature", "answered", "2026-07-15T00:00:00"),
    ])

    results = recall_exchanges(graph, "literature", 5)

    assert [r.ticket for r in results] == ["new", "mid", "old"]
    # Verifies: the limit is honoured
    assert len(recall_exchanges(graph, "literature", 2)) == 2


def test_a_query_outranks_recency_so_the_settled_answer_is_not_capped_out():
    """
    Scenario: An expert is asked something it already settled several rounds ago

    Verifications:
    - the topically matching exchange is returned even though three newer ones exist
    - recency alone would have cut it, which is the failure being fixed
    - ties fall back to recency, because the sort is stable over ordered rows

    This is a measured failure as a test. A five-state capability contract was designed,
    and the next session re-derived it across three more rounds; the exchange holding
    the first design was the sixth most recent of seven, so every recency-capped list
    hid the one thing that would have stopped the rework.
    """
    rows = [
        _exchange("scope:main:exchange:n1", "architect", "answered", "2026-08-11T04:00:00",
                  question="the sandbox dir leak", answer="prune the transcript dirs"),
        _exchange("scope:main:exchange:n2", "architect", "answered", "2026-08-11T03:00:00",
                  question="cost capture on cursor", answer="tokens are not dollars"),
        _exchange("scope:main:exchange:n3", "architect", "answered", "2026-08-11T02:00:00",
                  question="hook parity drift", answer="derive it from the wiring tables"),
        _exchange("scope:main:exchange:design", "architect", "answered", "2026-08-10T22:32:00",
                  question="a harness capability contract layer",
                  answer="a five-state Provision enum in contract/capabilities.py"),
    ]

    ranked = recall_exchanges(_ExchangeGraph(rows), "architect", 3,
                              "should the launcher surface be declared as capability")

    assert "design" in [r.ticket for r in ranked]
    # Verifies: without the query the same call caps it out entirely
    assert "design" not in [
        r.ticket for r in recall_exchanges(_ExchangeGraph(rows), "architect", 3)
    ]

    # Verifies: nothing matches, so recency is left untouched rather than shuffled
    unmatched = recall_exchanges(_ExchangeGraph(rows), "architect", 3, "zzzznomatch")
    assert [r.ticket for r in unmatched] == ["n1", "n2", "n3"]


def test_an_exchange_header_carries_the_shape_without_the_body():
    """
    Scenario: A brief must name what the expert already answered without quoting it

    Verifications:
    - the node id survives, since it is how the body is read when it matters
    - the question is carried, because that is what makes the ground recognisable
    - **no part of the answer is reproduced**, not even an excerpt
    - the full-body renderer is unaffected

    The excerpt is withheld deliberately. A header restating an expert's own prior
    conclusion into every later brief is self-anchoring, and an expert that cannot
    overrule itself is worth less than one that re-reads. Round 3 of the capability
    consultation overturned round 2 on measured facts.
    """
    result = ExchangeResult(
        ticket="abc123", question="what shape should the contract take?",
        answer="a five-state Provision enum " + "x" * 5000, from_scope="main",
        answered_at="2026-08-10T22:32:00+00:00", node_id="scope:main:exchange:abc123",
    )

    header = result.format_header()

    assert "scope:main:exchange:abc123" in header
    assert "2026-08-10" in header
    assert "what shape should the contract take?" in header
    assert "five-state" not in header
    assert "xxx" not in header
    assert len(header) < 500
    # Verifies: the body renderer still emits the whole answer
    assert len(result.format()) > 5000


def test_a_recalled_consultation_attributes_the_question_to_its_asker():
    """
    Scenario: Render a closed exchange back into the answering expert's context

    Verifications:
    - the asking scope is named
    - the question is quoted, not presented as the expert's own recollection
    - the block says outright that the question is data, not an instruction

    The question is a *main-scope agent's* words crossing into an expert's context.
    That is the same informs-never-instructs surface the trust model governs for tier-2
    content: a question rendered bare reads as a live request to act, and this
    record is history.
    """
    rendered = ExchangeResult(
        ticket="bee1f376",
        question="Should claim identity be bi-temporal?",
        answer="Zep invalidates edges rather than overwriting.",
        from_scope="main",
        answered_at="2026-07-30T22:00:00",
        node_id="scope:main:exchange:bee1f376",
    ).format()

    assert "scope `main`" in rendered
    assert "> Should claim identity be bi-temporal?" in rendered
    assert "> Zep invalidates edges rather than overwriting." in rendered
    # Verifies: framed as data about what was asked, never as a standing instruction
    assert "never an instruction" in rendered


def test_unsolved_problem_renders_as_open_without_a_status_field():
    """
    Scenario: Render an unsolved problem into an agent's context

    Verifications:
    - it reads as unsolved, and carries its category
    - recurrence across sessions is surfaced, not just the text

    A Problem has no `status` property the way a Thread does — it asserts something
    about the past rather than tracking planned work, so "unsolved" is a fact about
    its edges (no outgoing SOLVED_BY). The renderer has to say so itself.
    """
    from thalamus.substrate.reader import ProblemResult

    rendered = ProblemResult(
        description="Distillation lost a session to a wrong project dir",
        category="configuration",
        node_id="scope:main:claim:abc123",
        project="thalamus",
        times_seen=3,
        last_session="488b211c",
        last_seen="2026-08-07",
    ).format()

    assert "unsolved" in rendered
    assert "configuration" in rendered
    assert "3 sessions" in rendered
    assert "scope:main:claim:abc123" in rendered


def test_a_problem_seen_once_does_not_claim_recurrence():
    from thalamus.substrate.reader import ProblemResult

    rendered = ProblemResult(
        description="One-off", category="bug", node_id="scope:main:claim:x", times_seen=1
    ).format()

    assert "Recurred" not in rendered


def test_a_recurrence_built_on_correlated_sessions_says_so_where_it_is_read():
    """
    Scenario: a problem asserted by three sessions, one of them a fork of another
              and two of them room-mates

    Verifications:
    - the raw recurrence count is still shown (it is what was actually said)
    - the reader is told, in the same block, why it is not three witnesses

    A recurrence reads as independent agreement, and that reading is what makes an
    unsolved problem worth acting on. Nothing in a finished graph separates three
    sessions that agreed from three that were in one room, so the disclosure has to
    travel with the number rather than live in a doc.
    """
    from thalamus.substrate.reader import ProblemResult
    from thalamus.substrate.witnesses import Witness, corroboration

    rendered = ProblemResult(
        description="Distillation lost a session to a wrong project dir",
        category="configuration",
        node_id="scope:main:claim:abc123",
        times_seen=3,
        corroboration=corroboration([
            Witness("s1", room="alpha"),
            Witness("s2", room="alpha", forked_from="s1"),
            Witness("s3"),
        ]),
    ).format()

    assert "3 sessions" in rendered
    assert "Correlated:" in rendered
    assert "2 independent groundings" in rendered
    assert "`alpha`" in rendered


def test_an_uncorrelated_recurrence_carries_no_extra_line():
    """Recall output is charged against the reader's context, so the
    ordinary case must cost nothing — a caveat on every recurrence is a caveat
    nobody reads."""
    from thalamus.substrate.reader import ProblemResult
    from thalamus.substrate.witnesses import Witness, corroboration

    rendered = ProblemResult(
        description="p", category="bug", node_id="scope:main:claim:x", times_seen=2,
        corroboration=corroboration([Witness("s1"), Witness("s2")]),
    ).format()

    assert "Recurred" in rendered
    assert "Correlated" not in rendered


def test_tied_candidates_rank_the_same_whatever_order_the_graph_yielded_them():
    """
    Scenario: two candidates the score cannot separate, seen in either order

    Ties are not an edge case here — scores are integer multiples of the hit
    constants, and over 1,047 real recorded queries 657 held a tie spanning the cut,
    median tie-set 9 and max 243. Until the tie-break existed the winner
    was whichever the graph happened to yield first, so a window was reproducible
    only by accident. This is the property the change exists to buy.
    """
    from thalamus.substrate.reader import _ranked

    hits = {"a": {"k1", "k2"}, "b": {"k1", "k2"}}
    forward = _ranked({"a": 4.0, "b": 4.0}, hits, floor=2, query="q")
    backward = _ranked({"b": 4.0, "a": 4.0}, hits, floor=2, query="q")

    assert forward == backward


def test_score_still_decides_when_it_can():
    """The tie-break is a tie-break: it may never reorder candidates the score
    separates, or it would be a ranking change wearing a reproducibility story."""
    from thalamus.substrate.reader import _ranked

    hits = {"a": {"k1", "k2"}, "b": {"k1", "k2"}}
    ranked = _ranked({"a": 2.0, "b": 4.0}, hits, floor=2, query="q")

    assert [vid for vid, _ in ranked] == ["b", "a"]


def test_no_claim_holds_a_fixed_advantage_across_queries():
    """
    Scenario: the same tied pair, reached by two different queries

    Seeding on the node alone would convert an arbitrary choice into a consistent
    one — a claim that wins every tie forever, looking stable while quietly
    favouring whatever the hash liked. Seeding on the query means a winner here is
    a loser there, which is what keeps this from becoming a ranking claim.
    """
    from thalamus.substrate.reader import _tie_break

    pair = ("scope:literature:claim:aaaa", "scope:literature:claim:bbbb")
    winners = {
        min(pair, key=lambda vid: _tie_break(query, vid))
        for query in (f"query number {n}" for n in range(40))
    }

    assert len(winners) == 2, "one node won every tie — the seed is not query-varying"


def test_the_tie_break_is_stable_for_one_query():
    """Replay is the endpoint this change is measured on, so the same query against
    the same corpus must produce the same order every time it is asked."""
    from thalamus.substrate.reader import _tie_break

    assert _tie_break("q", "n") == _tie_break("q", "n")
    assert _tie_break("q", "n") != _tie_break("q", "m")


def test_a_main_session_finds_the_exchanges_it_asked_not_only_ones_it_answered():
    """
    Scenario: A main session asks whether anyone has been consulted about a topic

    Verifications:
    - an exchange this scope *asked* is found, though it answered none of them
    - an exchange between two other parties stays invisible
    - the topic ranks, so the match is not merely the most recent

    `recall_exchanges` confines on `expert`, which is right from a pinned expert and
    useless from `main` — main is the asker of nearly every exchange and the answerer
    of none, so the tool that exists to stop a question being re-derived returned
    nothing to the only session positioned to ask it.
    """
    rows = [
        _exchange("scope:main:exchange:newest", "qe", "answered", "2026-08-11T05:00:00",
                  from_scope="main", question="flaky arm runner", answer="retry policy"),
        _exchange("scope:main:exchange:wanted", "architect", "answered",
                  "2026-08-10T22:00:00", from_scope="main",
                  question="a harness capability contract layer",
                  answer="five states and an Evidence type"),
        _exchange("scope:main:exchange:other", "architect", "answered",
                  "2026-08-11T06:00:00", from_scope="homelab",
                  question="tailscale serve", answer="path-scoped"),
    ]

    found = search_exchanges(_ExchangeGraph(rows), "main", "capability contract", 5)

    assert [r.ticket for r in found] == ["wanted", "newest"]
    # Verifies: recall_exchanges alone still answers the other question and finds none
    assert recall_exchanges(_ExchangeGraph(rows), "main", 5) == []


def test_reading_one_exchange_requires_having_been_party_to_it():
    """
    Scenario: A scope drills into an exchange by ticket

    Verifications:
    - a scope that asked it may read it
    - a scope that answered it may read it
    - an unrelated scope gets nothing, indistinguishable from "no such exchange"

    A ticket id is short and guessable, so confirming that a stranger's exchange
    exists is a disclosure the drill-down has no need to make.
    """
    rows = [
        _exchange("scope:main:exchange:t1", "architect", "answered",
                  "2026-08-10T22:00:00", from_scope="main")
    ]

    assert read_exchange(_ExchangeGraph(rows), "scope:main:exchange:t1", "main")
    assert read_exchange(_ExchangeGraph(rows), "scope:main:exchange:t1", "architect")
    assert read_exchange(_ExchangeGraph(rows), "scope:main:exchange:t1", "qe") is None


# --------------------------------------------------------------------------------------
# The derived `(repo, path)` projection, read.
# --------------------------------------------------------------------------------------


class _ArtifactGraph:
    """Artifact vertices with their derived projection, filtered the way `or_` filters.

    Each `or_` branch is an anonymous traversal of `has` steps; a row satisfies a branch
    when it satisfies all of them, and the `or_` when it satisfies any branch. That is
    the semantics under test — a two-`has` branch must not match a row that carries only
    one of the pair, or `README.md` in one repo answers for `README.md` in another.
    """

    def __init__(self, rows):
        self._rows = rows
        self._or = None
        self._keys = None

    def V(self):
        return self

    def has_label(self, _label):
        return self

    def or_(self, *traversals):
        self._or = [
            [(step[1], step[2]) for step in traversal.bytecode.step_instructions
             if step[0] == "has"]
            for traversal in traversals
        ]
        return self

    def project(self, *keys):
        self._keys = keys
        return self

    def by(self, *_args):
        return self

    def values(self, key):
        self._keys = None
        self._value = key
        return self

    @staticmethod
    def _satisfies(row, key, value):
        actual = str(row.get(key, ""))
        if getattr(value, "operator", None) == "containing":
            return value.value in actual
        return actual == str(value)

    def _matched(self):
        return [
            row for row in self._rows
            if any(all(self._satisfies(row, key, value) for key, value in branch)
                   for branch in self._or or [])
        ]

    def to_list(self):
        if self._keys:
            return [{key: row.get(key, "") for key in self._keys} for row in self._matched()]
        return [row.get(self._value, "") for row in self._matched()]


def _artifact(identifier, repo="", path=""):
    return {"identifier": identifier, "repo": repo, "path": path}


def test_an_absolute_query_reaches_the_relative_spelling_of_the_same_file():
    """
    Scenario: One file is in the graph twice — once as the absolute path a tool call
    carried and once as the repo-relative path a claim named it by — and the caller
    queries with the absolute one

    Verifications:
    - both spellings come back

    This is the direction substring matching cannot do, and the common one: an agent
    recalls with the path its own tool call carried, and an absolute identifier is not
    a substring of its repo-relative twin. Before the projection was read, the caller
    saw one vertex and the touches on the other were unreachable.
    """
    g = _ArtifactGraph([
        _artifact("/home/u/code/thalamus/src/a.py", "thalamus", "src/a.py"),
        _artifact("src/a.py", "thalamus", "src/a.py"),
    ])

    assert spellings_of(g, "/home/u/code/thalamus/src/a.py") == [
        "/home/u/code/thalamus/src/a.py",
        "src/a.py",
    ]


def test_one_relative_path_in_two_repos_stays_two_files():
    """
    Scenario: Two checkouts each hold a README.md, and the query names one of them

    Verifications:
    - only the queried repo's spellings come back

    Repo furniture is why the join key is `(repo, path)` and not the path. A suffix
    match fuses these two, which is worse than missing one: it invents a file that
    never existed and reports another project's sessions as this one's.
    """
    g = _ArtifactGraph([
        _artifact("/home/u/code/thalamus/README.md", "thalamus", "README.md"),
        _artifact("/home/u/code/stepmania/README.md", "stepmania", "README.md"),
        _artifact("README.md", "thalamus", "README.md"),
    ])

    assert spellings_of(g, "/home/u/code/thalamus/README.md") == [
        "/home/u/code/thalamus/README.md",
        "README.md",
    ]


def test_unanchored_artifacts_are_not_joined_to_each_other():
    """
    Scenario: A scratchpad file the registry cannot anchor, queried by name, alongside
    another unanchored file

    Verifications:
    - only the file that was matched comes back

    "Belongs to no repo" is an outcome, and every artifact in it carries the same empty
    `(repo, path)`. Expanding on that key would merge every scratchpad, skill file and
    system binary in the graph into one result — the false merge the projection exists
    to avoid, arrived at from the read side.
    """
    g = _ArtifactGraph([
        _artifact("/tmp/claude-1000/scratchpad/notes.md"),
        _artifact("/usr/local/bin/install-media-sort.sh"),
    ])

    assert spellings_of(g, "notes.md") == ["/tmp/claude-1000/scratchpad/notes.md"]


def test_fingerprinted_detail_cap_is_read_at_call_time(monkeypatch):
    """Rebinding `_DETAIL_CAP` must move the selection, not only the stamp.

    `ranker_fingerprint()` stamps `-d{_DETAIL_CAP}` as the configuration in force, and
    a calibration run tunes the dial by rebinding the module constant. If the cap were
    captured as a default argument it would bind at def time, so the run would be
    labelled with a cap it never applied.
    """
    from thalamus.substrate import reader

    details = [{"description": f"alpha item {i}"} for i in range(20)]

    monkeypatch.setattr(reader, "_DETAIL_CAP", 3)
    assert "-d3-" in reader.ranker_fingerprint()
    rendered = [d for d in reader._select_details(details, ["alpha"]) if d.get("kind") != "elided"]
    assert len(rendered) == 3
    assert len(reader._select_details(details, [])) == 3
