"""
Eval-loop layer-1 tests: the tap, node identity, and used-vs-ignored.

Interfaces: thalamus.eval.traces, thalamus.eval.attribution
Infrastructure: tmp_path only — no graph, no model
Scope: the model-free half of the eval loop. Landing traces in the graph is exercised
live (it is one write path shared with everything else); the parsing and judging logic
is what can silently rot, so it is what gets pinned here.
"""

import json
from datetime import datetime, timezone

from thalamus.eval.attribution import Verdict, attribute, outputs_after
from thalamus.eval.traces import TraceEvent, load_events
from thalamus.substrate.reader import MemoryResult, ThreadResult


def _tap_line(**overrides) -> str:
    record = {
        "ts": "2026-07-15T10:00:00Z",
        "session_id": "sess-1",
        "cwd": "/home/op/code/thalamus",
        "tool_name": "mcp__thalamus__memory_recall",
        "tool_input": {"query": "gremlin write failures"},
        "tool_response": "**Node:** `scope:main:session:abc` — a summary.",
    }
    record.update(overrides)
    return json.dumps(record)


def test_tap_lines_become_typed_retrieval_events(tmp_path):
    """
    Scenario: A monthly tap file holds a retrieval, a memorize call, and junk

    Verifications:
    - retrieval calls come back typed, with the mcp prefix stripped
    - non-retrieval thalamus tools (memorize, visualize) are excluded
    - malformed lines are skipped, not fatal

    The tap is a dumb append-only file written by a shell hook; every robustness
    obligation lives on the reading side.
    """
    (tmp_path / "2026-07.jsonl").write_text(
        "\n".join(
            [
                _tap_line(),
                _tap_line(tool_name="mcp__thalamus__memorize"),
                "not json at all {",
                "",
            ]
        )
    )

    events = load_events(tmp_path)

    assert len(events) == 1
    assert events[0].tool == "memory_recall"
    assert events[0].session_id == "sess-1"
    assert events[0].ts == datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)


def test_events_sort_chronologically_across_monthly_files(tmp_path):
    """
    Scenario: Traces span two monthly files, written out of order
    """
    (tmp_path / "2026-07.jsonl").write_text(_tap_line(ts="2026-07-02T00:00:00Z"))
    (tmp_path / "2026-06.jsonl").write_text(_tap_line(ts="2026-06-30T00:00:00Z"))

    events = load_events(tmp_path)

    assert [e.ts.month for e in events] == [6, 7]


def test_returned_nodes_are_recovered_from_the_rendered_response():
    """
    Scenario: A recall response rendered by the reader, carrying vertex IDs

    Verifications:
    - every backticked scoped vertex ID is recovered, in order, deduplicated
    - prose that merely resembles an ID (no backticks) is not matched

    This is the G5 contract: the tap records the response verbatim, so the reader's
    inline vertex IDs ARE the node-level trace. No side schema.
    """
    event = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s",
        cwd="",
        tool="memory_recall",
        tool_response=(
            "**Node:** `scope:main:session:abc-123`\n"
            "- **decision** `scope:main:claim:9f3a00aa11bb22cc`: use the graph\n"
            "- **decision** `scope:main:claim:9f3a00aa11bb22cc`: (repeated)\n"
            "mentioned in prose: scope:main:session:not-a-hit\n"
        ),
    )

    assert event.returned_node_ids() == [
        "scope:main:session:abc-123",
        "scope:main:claim:9f3a00aa11bb22cc",
    ]
    assert event.scope_hint() == "main"


def test_reader_rendering_and_tap_extraction_agree():
    """
    Scenario: Round-trip — format a retrieval result, then read it back as a trace

    The reader and the trace parser are two halves of one contract. If the rendering
    changes shape and extraction stops seeing nodes, the eval loop silently goes blind;
    this is the test that refuses to let that be silent.
    """
    rendered = MemoryResult(
        session_id="abc",
        summary="Ported the substrate.",
        timestamp="2026-07-14T00:00:00",
        tool="claude_code",
        project="thalamus",
        node_id="scope:main:session:abc",
        details=[
            {"kind": "decision", "description": "graph-first", "node_id": "scope:main:claim:aa"}
        ],
    ).format()
    rendered_thread = ThreadResult(
        thread_id="build-linking-workflow",
        title="Build linking workflow",
        description="Group subgraphs.",
        status="open",
        project="thalamus",
        node_id="scope:main:thread:build-linking-workflow",
    ).format()

    event = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s",
        cwd="",
        tool="memory_recall",
        tool_response=rendered + "\n\n---\n\n" + rendered_thread,
    )

    assert event.returned_node_ids() == [
        "scope:main:session:abc",
        "scope:main:claim:aa",
        "scope:main:thread:build-linking-workflow",
    ]


def test_misses_and_legacy_traces_are_told_apart():
    """
    Scenario: One trace found nothing; another predates node-level rendering

    A miss ("the graph had nothing") grades recall and must be recorded. A legacy trace
    (prose response, no vertex IDs) predates G5 and must be excluded, or it would be
    indistinguishable from a miss and poison the miss rate.
    """
    miss = TraceEvent(
        ts=datetime.now(timezone.utc), session_id="s", cwd="", tool="memory_recall",
        tool_response="No matching memories found.",
    )
    legacy = TraceEvent(
        ts=datetime.now(timezone.utc), session_id="s", cwd="", tool="memory_recall",
        tool_response="## Recalled memory\n**Summary:** old format, no ids",
    )

    assert miss.is_miss() and not miss.is_legacy()
    assert legacy.is_legacy() and not legacy.is_miss()


def test_trace_identity_is_content_addressed():
    """
    Scenario: The same tap line synced twice; a different call synced once

    Re-syncing must converge on the same Trace vertex (idempotent landings), and two
    different retrievals must never collide.
    """
    kwargs = dict(
        ts=datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc),
        session_id="s",
        cwd="",
        tool="memory_recall",
        tool_input={"query": "x"},
    )
    same_a = TraceEvent(**kwargs)
    same_b = TraceEvent(**kwargs)
    other = TraceEvent(**{**kwargs, "tool_input": {"query": "y"}})

    assert same_a.trace_id() == same_b.trace_id()
    assert same_a.trace_id() != other.trace_id()


def _transcript(*records) -> bytes:
    return "\n".join(json.dumps(r) for r in records).encode()


def _assistant(ts: str, text: str = "", tool_input: dict | None = None, **extra) -> dict:
    content = []
    if text:
        content.append({"type": "text", "text": text})
    if tool_input is not None:
        content.append({"type": "tool_use", "name": "Edit", "input": tool_input})
    return {"type": "assistant", "timestamp": ts, "message": {"content": content}, **extra}


def test_outputs_are_the_agents_own_and_only_after_the_retrieval():
    """
    Scenario: A transcript with output before the retrieval, after it, from the user,
    and from a sidechain

    Verifications:
    - only assistant output AFTER the trace timestamp counts
    - user turns and sidechains never count

    Used-vs-ignored asks whether retrieval changed the AGENT's subsequent behavior.
    Earlier output cannot have been changed by it; the operator's words are not the
    agent's behavior.
    """
    after = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
    transcript = _transcript(
        _assistant("2026-07-15T09:00:00Z", text="before-retrieval-token"),
        {"type": "user", "timestamp": "2026-07-15T11:00:00Z",
         "message": {"content": "user-token"}},
        _assistant("2026-07-15T11:00:00Z", text="sidechain-token", isSidechain=True),
        _assistant("2026-07-15T12:00:00Z", text="after-retrieval-token",
                   tool_input={"file_path": "src/thing.py"}),
    )

    outputs = outputs_after(transcript, after)

    assert "after-retrieval-token" in outputs
    assert "src/thing.py" in outputs  # tool calls are behavior too
    assert "before-retrieval-token" not in outputs
    assert "user-token" not in outputs
    assert "sidechain-token" not in outputs


def test_citing_a_vertex_id_is_the_strongest_used_signal():
    """
    Scenario: The agent quoted a recalled node's vertex ID in its answer
    """
    verdicts = attribute(
        {"scope:main:claim:9f3a": "anything at all"},
        "As decided before (scope:main:claim:9f3a), we keep the graph first.",
    )

    assert verdicts == [Verdict("scope:main:claim:9f3a", True, "cited by vertex ID")]


def test_lexical_echo_marks_a_node_used_and_silence_marks_it_ignored():
    """
    Scenario: Two nodes retrieved; the session's later output echoes one of them

    The attribution is crude lexical overlap by design (docs/04): a measured crude
    number over an asserted smart one.
    """
    outputs = "Refactored the gremlin writer to batch idempotent merges for tinkergraph."

    verdicts = {
        v.node_id: v
        for v in attribute(
            {
                "scope:main:claim:used1": "Batch gremlin merges so tinkergraph writes stay idempotent",
                "scope:main:claim:ignored": "Frontend legend colors come from the ontology tuples",
            },
            outputs,
        )
    }

    assert verdicts["scope:main:claim:used1"].used
    assert "terms" in verdicts["scope:main:claim:used1"].evidence
    assert not verdicts["scope:main:claim:ignored"].used


def test_content_with_no_distinctive_terms_cannot_be_marked_used():
    """
    Scenario: A node whose text is all stopwords

    It must come back ignored-with-reason rather than crashing on a zero division or
    accidentally matching everything.
    """
    [verdict] = attribute({"scope:main:claim:x": "it was to be of the"}, "any output")

    assert not verdict.used
    assert verdict.evidence == "no distinctive terms to match on"


def test_thread_slugs_count_as_citations():
    """
    Scenario: The agent named a recalled thread by its slug while working
    """
    [verdict] = attribute(
        {"scope:main:thread:build-linking-workflow": "unrelated words entirely"},
        "picking build-linking-workflow back up now",
    )

    assert verdict.used
    assert "slug" in verdict.evidence
