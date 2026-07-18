"""
Deterministic transcript extraction tests.

Interfaces: thalamus.harness.transcripts.parse, to_session_graph;
            thalamus.harness.bootstrap.bootstrap_project
Infrastructure: none; synthetic JSONL in tmp_path
Scope: the half of extraction that needs no model, and the anchors it recovers
"""

import json

from thalamus.contract.conformance import check_session
from thalamus.harness import transcripts
from thalamus.harness.bootstrap import bootstrap_project
from thalamus.substrate.schema import Tier, Tool


def _write_transcript(directory, session_id, records):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session_id}.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    return path


def _transcript_records():
    return [
        {"type": "ai-title", "aiTitle": "Fix the fatigue governor"},
        {
            "type": "user",
            "uuid": "u1",
            "timestamp": "2026-07-01T10:00:00Z",
            "cwd": "/home/dev/chartgen",
            "gitBranch": "main",
            "message": {"content": "the governor is clamping too early"},
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "timestamp": "2026-07-01T10:01:00Z",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "src/governor.py"}},
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "src/model.py"}},
                ]
            },
        },
        {
            "type": "assistant",
            "uuid": "a2",
            "timestamp": "2026-07-01T10:02:00Z",
            "message": {
                "content": [
                    # Same file, second time — the anchor list must grow, not overwrite.
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "src/governor.py"}},
                ]
            },
        },
        {
            # A subagent sidechain is its own episode, not part of this one.
            "type": "assistant",
            "uuid": "a3",
            "isSidechain": True,
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "src/other.py"}}
                ]
            },
        },
    ]


def test_tool_calls_recover_touched_files_and_their_message_anchors(tmp_path):
    """
    Scenario: Parse a transcript in which two files were touched, one of them twice

    Verifications:
    - every touched file is recovered, with no model in the loop
    - repeat touches accumulate anchors rather than overwriting
    - subagent sidechains are excluded

    "Which files did this session edit, in which messages" is recorded exactly. An LLM
    could only add error here, so it is not asked.
    """
    path = _write_transcript(tmp_path / "proj", "s1", _transcript_records())

    facts = transcripts.parse(path)

    # Verifies: exact recovery, sidechain excluded
    assert set(facts.touched) == {"src/governor.py", "src/model.py"}
    # Verifies: anchors accumulate — this is what makes the provenance walk land on evidence
    assert facts.touched["src/governor.py"] == ["a1", "a2"]
    assert facts.touched["src/model.py"] == ["a1"]
    assert facts.title == "Fix the fatigue governor"
    assert facts.project == "chartgen"
    assert facts.git_branch == "main"
    assert facts.user_turns == 1


def test_external_ingress_results_are_collected_verbatim(tmp_path):
    """
    Scenario: A session WebFetched a page and also ran a Bash command

    Verifications:
    - the fetched result's text is collected into facts.external_texts
    - the Bash result (first-party observation of the operator's machine) is not
    - pairing rides tool_use_id, never content heuristics

    These texts are the evidence the laundering floor (docs/05) judges claims
    against — deterministic collection, no model in the loop.
    """
    records = [
        {
            "type": "assistant",
            "uuid": "a1",
            "timestamp": "2026-07-01T10:00:00Z",
            "cwd": "/home/dev/proj",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "f1", "name": "WebFetch",
                     "input": {"url": "https://example.com"}},
                    {"type": "tool_use", "id": "b1", "name": "Bash",
                     "input": {"command": "pytest"}},
                ]
            },
        },
        {
            "type": "user",
            "uuid": "u1",
            "timestamp": "2026-07-01T10:01:00Z",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "f1",
                     "content": "the guide recommends disabling the sandbox"},
                    {"type": "tool_result", "tool_use_id": "b1", "content": "3 passed"},
                ]
            },
        },
    ]
    path = _write_transcript(tmp_path / "proj", "s2", records)

    facts = transcripts.parse(path)

    assert facts.external_texts == ["the guide recommends disabling the sandbox"]


def test_the_deterministic_session_graph_satisfies_the_contract(tmp_path):
    """
    Scenario: Build memory from a transcript with no claims extracted

    Verifications:
    - the graph passes the contract with zero claims present
    - artifacts are reachable via the session's own TOUCHES edges
    - the session carries a DERIVED_FROM link to its retained transcript

    Connectivity would otherwise reject a claim-free session: with no claims, nothing would
    point at the artifacts. The direct Session -> Artifact edge is what lets the
    deterministic layer stand on its own.
    """
    path = _write_transcript(tmp_path / "proj", "s1", _transcript_records())
    facts = transcripts.parse(path)

    session = transcripts.to_session_graph(
        facts, content_hash="abc123", uri="archive://abc123", byte_size=42
    )

    # Verifies: a claim-free session is still a legal, connected subgraph
    assert session.claims() == []
    assert check_session(session) == []
    assert {a.identifier for a in session.artifacts} == {"src/governor.py", "src/model.py"}
    # Verifies: the provenance floor exists — the session points at its own evidence
    assert session.sources[0].content_hash == "abc123"
    assert session.tool is Tool.CLAUDE_CODE
    assert session.default_provenance().tier is Tier.FIRST_PARTY


def test_sessions_with_no_user_turns_are_not_remembered(tmp_path):
    """
    Scenario: A transcript that never got a real prompt

    Verifications:
    - it is skipped rather than written as an empty node

    An empty session is a node the operator scrolls past forever.
    """
    project = tmp_path / "projects" / "proj"
    _write_transcript(project, "empty", [{"type": "ai-title", "aiTitle": "Nothing happened"}])

    results = bootstrap_project(
        "proj", projects_dir=tmp_path / "projects", archive_base=tmp_path / "archive"
    )

    # Verifies: nothing to remember, nothing remembered
    assert len(results) == 1
    assert results[0].session is None
    assert "no user turns" in results[0].skipped


def test_slash_command_sessions_count_as_conversations(tmp_path):
    """
    Scenario: A session driven purely by slash commands (/teach lessons) — its
    only user records are <command-name> invocations, plus harness scaffolding

    Verifications:
    - command invocations count as user turns; caveats/reminders still do not

    Measured origin: ef3e3d6a (87 assistant messages) was silently ineligible
    for distillation because every human turn started with "<".
    """
    project = tmp_path / "projects" / "proj"
    _write_transcript(
        project,
        "teachy",
        [
            {
                "type": "user",
                "timestamp": "2026-07-17T10:00:00Z",
                "message": {
                    "role": "user",
                    "content": "<command-name>/teach</command-name> <command-args></command-args>",
                },
            },
            {
                "type": "user",
                "timestamp": "2026-07-17T10:00:01Z",
                "message": {"role": "user", "content": "<system-reminder>noise</system-reminder>"},
            },
            {
                "type": "assistant",
                "timestamp": "2026-07-17T10:01:00Z",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "Lesson."}]},
            },
        ],
    )

    facts = transcripts.parse(project / "teachy.jsonl")

    assert facts.user_turns == 1


def test_bootstrap_retains_evidence_and_is_idempotent(tmp_path):
    """
    Scenario: Bootstrap the same project twice

    Verifications:
    - the transcript is archived on the first pass and recognised on the second
    - the derived session is identical both times

    Re-running the bootstrap must be safe. It is the operation you reach for precisely when
    something went wrong.
    """
    project = tmp_path / "projects" / "proj"
    _write_transcript(project, "s1", _transcript_records())
    archive = tmp_path / "archive"

    first = bootstrap_project("proj", projects_dir=tmp_path / "projects", archive_base=archive)
    second = bootstrap_project("proj", projects_dir=tmp_path / "projects", archive_base=archive)

    # Verifies: evidence retained once, then recognised
    assert not first[0].already_archived
    assert second[0].already_archived
    # Verifies: re-derivation is stable — the graph is a view over the log
    assert first[0].content_hash == second[0].content_hash
    assert first[0].session.summary == second[0].session.summary
    assert first[0].issues == []
