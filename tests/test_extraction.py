"""
Stage-2 extraction tests — everything that runs without a model.

Interfaces: thalamus.harness.extraction.render_digest, build_prompt,
            parse_extraction, merge_extraction
Infrastructure: none; synthetic JSONL bytes and extraction dicts
Scope: digest rendering and elision, YAML parsing, and the merge that keeps the
       deterministic layer authoritative over model judgement
"""

import json
from datetime import datetime

import pytest

from thalamus.contract.conformance import check_session, prune_orphan_artifacts
from thalamus.harness import extraction
from thalamus.substrate.schema import (
    Artifact,
    ArtifactType,
    SessionGraph,
    Source,
    Tool,
    Touch,
)


def _payload(records) -> bytes:
    return ("\n".join(json.dumps(r) for r in records) + "\n").encode()


def _records():
    return [
        {
            "type": "user",
            "message": {"content": "the governor is clamping too early"},
        },
        {
            "type": "user",
            "message": {"content": "<system-reminder>injected noise</system-reminder>"},
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Looking at the clamp threshold now."},
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "src/governor.py"}},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}},
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "content": "3 passed, 1 failed: test_clamp " + "x" * 900}
                ]
            },
        },
        {
            # Sidechains are their own episodes, not this one.
            "type": "assistant",
            "isSidechain": True,
            "message": {"content": [{"type": "text", "text": "SIDECHAIN TEXT"}]},
        },
    ]


def test_digest_keeps_the_conversation_and_drops_the_plumbing():
    """
    Scenario: Render a transcript with user prompts, tool calls, results, injected
    system noise, and a sidechain

    Verifications:
    - user prompts and assistant prose survive
    - tool calls render as name + salient input; bash shows the command
    - tool results are included but truncated
    - system-injected user content ("<...") and sidechains are dropped
    """
    digest = extraction.render_digest(_payload(_records()))

    assert "USER: the governor is clamping too early" in digest
    assert "ASSISTANT: Looking at the clamp threshold now." in digest
    assert "tool: Edit src/governor.py" in digest
    assert "tool: Bash $ pytest -q" in digest
    assert "3 passed, 1 failed" in digest
    assert "…[truncated]" in digest
    assert "system-reminder" not in digest
    assert "SIDECHAIN TEXT" not in digest


def test_digest_over_budget_elides_the_middle_not_the_ends():
    """
    Scenario: A transcript far larger than the budget

    Verifications:
    - the opening (intent) and the ending (outcome) both survive
    - the middle is replaced by an elision marker, and the budget is respected
    """
    records = [
        {"type": "user", "message": {"content": f"turn {i}: " + "words " * 200}}
        for i in range(200)
    ]
    digest = extraction.render_digest(_payload(records), budget=20_000)

    assert "turn 0:" in digest
    assert "turn 199:" in digest
    assert "messages elided for length" in digest
    assert len(digest) < 25_000


def test_parse_extraction_reads_the_yaml_fence_and_rejects_non_mappings():
    fenced = "Here you go:\n```yaml\nsummary: did the thing\n```\ntrailing prose"
    assert extraction.parse_extraction(fenced) == {"summary": "did the thing"}

    # No fence: the whole text is tried as YAML.
    assert extraction.parse_extraction("summary: bare yaml") == {"summary": "bare yaml"}

    with pytest.raises(extraction.ExtractionError):
        extraction.parse_extraction("- just\n- a\n- list")


def _stage1_graph() -> SessionGraph:
    return SessionGraph(
        session_id="abc-123",
        timestamp=datetime(2026, 7, 1, 10, 0),
        tool=Tool.CLAUDE_CODE,
        scope="main",
        project="chartgen",
        summary="Fix the governor — opened with: the governor is clamping",
        sources=[
            Source(content_hash="f" * 64, title="Fix the governor", uri="archive://" + "f" * 64)
        ],
        artifacts=[Artifact(identifier="src/governor.py", type=ArtifactType.FILE)],
        touched=[Touch(identifier="src/governor.py", anchors=["a1"])],
    )


def _model_output() -> dict:
    return {
        # The model was told not to emit these; a disobedient one must still lose.
        "session_id": "WRONG-ID",
        "scope": "not-my-scope",
        "sources": [{"content_hash": "0" * 64, "title": "forged", "uri": "archive://forged"}],
        "touched": [{"identifier": "forged.py"}],
        "summary": "Raised the clamp threshold after tests showed early clamping.",
        "artifacts": [
            {"identifier": "src/governor.py", "type": "file"},
            {"identifier": "pytest", "type": "dependency"},
        ],
        "decisions": [
            {
                "description": "Raise the clamp threshold",
                "rationale": "Tests showed clamping fired before fatigue accumulated",
                "artifacts": ["src/governor.py"],
            }
        ],
        "problems": [
            {
                "description": "Governor clamped too early",
                "category": "bug",
                "artifacts": ["src/governor.py"],
            }
        ],
        "solutions": [
            {
                "description": "Threshold raised",
                "approach": "Doubled the window",
                "worked": True,
                "problem_ref": 0,
                "artifacts": ["src/governor.py", "pytest"],
            }
        ],
        "threads": [
            {
                "id": "tune-governor-window",
                "title": "Tune the governor window",
                "description": "The doubled window is a guess; sweep it properly.",
                "status": "open",
                "artifacts": ["src/governor.py"],
            }
        ],
    }


def test_merge_keeps_the_deterministic_layer_authoritative():
    """
    Scenario: Merge model output that (illegally) tries to set identity, scope,
    sources, and touches

    Verifications:
    - session identity, scope, sources, and anchored touches come from stage 1
    - summary, claims, and threads come from the model
    - artifacts are the union, deduped by identifier
    """
    merged = extraction.merge_extraction(_stage1_graph(), _model_output())

    assert merged.session_id == "abc-123"
    assert merged.scope == "main"
    assert [s.content_hash for s in merged.sources] == ["f" * 64]
    assert [t.identifier for t in merged.touched] == ["src/governor.py"]
    assert merged.touched[0].anchors == ["a1"]

    assert merged.summary.startswith("Raised the clamp threshold")
    assert len(merged.decisions) == 1
    assert len(merged.problems) == 1
    assert merged.solutions[0].problem_ref == 0
    assert merged.threads[0].id == "tune-governor-window"

    identifiers = sorted(a.identifier for a in merged.artifacts)
    assert identifiers == ["pytest", "src/governor.py"]

    assert check_session(merged) == []


def test_merge_falls_back_to_the_stage1_summary_when_the_model_omits_one():
    data = _model_output()
    del data["summary"]
    merged = extraction.merge_extraction(_stage1_graph(), data)
    assert merged.summary.startswith("Fix the governor")


def test_model_orphan_artifacts_are_prunable_without_losing_stage1_nodes():
    """
    Scenario: The model lists an artifact it never references from any claim or thread

    Verifications:
    - prune_orphan_artifacts removes the orphan, so the write is not rejected
    - stage-1 artifacts (referenced via touched) survive the prune
    """
    data = _model_output()
    data["artifacts"].append({"identifier": "never/referenced.py", "type": "file"})

    merged = extraction.merge_extraction(_stage1_graph(), data)
    assert check_session(merged) != []  # orphan detected

    pruned = prune_orphan_artifacts(merged)
    identifiers = sorted(a.identifier for a in pruned.artifacts)
    assert identifiers == ["pytest", "src/governor.py"]
    assert check_session(pruned) == []
