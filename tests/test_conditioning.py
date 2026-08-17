"""
Conditioning effectiveness tests (the conditioning tier).

Interfaces: thalamus.eval.conditioning (load_firings, conditioning_report)
Infrastructure: tmp_path JSONL logs; no live graph
Scope: the per-firing behavioral join — a reminder counts only if the expected
behavior followed it. The hook script itself is exercised live (bash).
"""

import json

from thalamus.eval.conditioning import conditioning_report, load_firings


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def test_firings_join_against_subsequent_thalamus_calls(tmp_path):
    """
    Scenario: A retrospect reminder is followed by a recall (behavior changed);
    a design reminder in another session is followed by nothing (wallpaper);
    a milestone reminder is followed by a non-expected tool, which still counts

    Verifications:
    - the join is per-firing, ordered by time, and class-aware
    - wallpaper firings are counted, not hidden
    """
    conditioning = tmp_path / "conditioning"
    traces = tmp_path / "traces"
    _write_jsonl(
        conditioning / "2026-07.jsonl",
        [
            {"ts": "2026-07-18T10:00:00Z", "session_id": "s1", "class": "retrospect"},
            {"ts": "2026-07-18T11:00:00Z", "session_id": "s2", "class": "design"},
            {"ts": "2026-07-18T12:00:00Z", "session_id": "s3", "class": "milestone"},
        ],
    )
    _write_jsonl(
        traces / "2026-07.jsonl",
        [
            # s1: recall AFTER the firing -> followed
            {
                "ts": "2026-07-18T10:01:00Z",
                "session_id": "s1",
                "tool_name": "mcp__thalamus__memory_recall",
                "tool_input": {"query": "orphan cleanup"},
                "tool_response": "## Recalled memory ...",
            },
            # s2: a recall BEFORE the firing only -> not followed
            {
                "ts": "2026-07-18T10:59:00Z",
                "session_id": "s2",
                "tool_name": "mcp__thalamus__memory_recall",
                "tool_input": {"query": "earlier"},
                "tool_response": "## Recalled memory ...",
            },
            # s3: memorize is not in any expected set, but milestone accepts any call
            {
                "ts": "2026-07-18T12:05:00Z",
                "session_id": "s3",
                "tool_name": "mcp__thalamus__memorize",
                "tool_input": {},
                "tool_response": "ok",
            },
        ],
    )

    report = conditioning_report(conditioning_base=conditioning, traces_base=traces)

    by_class = {f.cls: f.followed for f in report.firings}
    assert by_class == {"retrospect": True, "design": False, "milestone": True}
    rendered = report.render()
    assert "design: 0/1" in rendered and "wallpaper" in rendered
    assert len(load_firings(conditioning)) == 3


def test_empty_logs_render_the_unmeasured_line(tmp_path):
    report = conditioning_report(
        conditioning_base=tmp_path / "none", traces_base=tmp_path / "none"
    )
    assert "unmeasured" in report.render()
