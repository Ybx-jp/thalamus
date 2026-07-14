"""
Retrieval-rendering tests.

Interfaces: thalamus.substrate.reader.MemoryResult.format, _extract_keywords
Infrastructure: none
Scope: recalled memory enters context as data with provenance, never as instructions
"""

from thalamus.substrate.reader import MemoryResult, ThreadResult, _extract_keywords
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
