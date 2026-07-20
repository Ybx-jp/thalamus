"""
Retrieval-rendering tests.

Interfaces: thalamus.substrate.reader.MemoryResult.format, _extract_keywords
Infrastructure: none
Scope: recalled memory enters context as data with provenance, never as instructions
"""

from thalamus.substrate.reader import (
    MemoryResult,
    ThreadResult,
    _extract_keywords,
    _keyword_predicate,
)
from thalamus.substrate.schema import Tier


def test_recalled_memory_carries_its_trust_tier_into_context():
    """
    Scenario: Render a retrieved session for the agent's context

    Verifications:
    - the rendered block is labelled as recalled memory
    - the trust tier travels with the content

    docs/05 requires retrieved memory to enter context as "quoted material with its trust
    tier attached". Everything in the graph is tier-1 today, so the exposure is small —
    but this formatter is the injection surface the moment a feed writes tier-2 content,
    which is why the tier is rendered rather than dropped.
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
    - the framing names it data, never instructions (docs/05)
    - the vertex ID renders, so the trace tap sees the node (docs/09 G5)
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
      retrieval waste — lab/006)
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
    assert "4 more claim(s)" in selected[-1]["description"]


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
