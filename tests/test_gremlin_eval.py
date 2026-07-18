"""
Gremlin fluency metrics tests (eval-methodology consultation 918ddb8ddf094a29).

Interfaces: thalamus.eval.gremlin (guard events, fingerprints, report, smoke),
thalamus.eval.traces (memory_query/bash_gremlin classification)
Infrastructure: tmp_path JSONL taps and recipe files; no live graph
Scope: the metrics that grade the fluency layer — rescue rate from guard
events, rejection classes, reuse tagging by traversal shape, and the smoke
run's read-only refusal. Live execution is exercised live.
"""

import json

from thalamus.eval.gremlin import (
    SmokeResult,
    gremlin_report,
    is_recipe_derived,
    load_guard_events,
    recipe_fingerprints,
    render_smoke,
    smoke_recipes,
    step_fingerprint,
)
from thalamus.eval.traces import load_events


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def test_rescue_joins_on_intent_not_any_pass(tmp_path):
    """
    Scenario: A session's doomed traversal is blocked twice (same command),
    then corrected (terminal pass, same shape); meanwhile an unrelated
    text-edit pass fires, and another session's block is abandoned amid
    wrapper passes

    Verifications:
    - the corrected retry counts as a rescue; wrapper/text-edit passes never do
      (the saturation bias — verification finding 1)
    - friction counts only the re-submitted identical command
    """
    guards = tmp_path / "guards"
    _write_jsonl(
        guards / "2026-07.jsonl",
        [
            {"ts": "2026-07-17T10:00:00Z", "session_id": "s1", "verdict": "block",
             "branch": "none", "command_hash": "aaaa", "fingerprint": "v,haslabel,has"},
            {"ts": "2026-07-17T10:00:30Z", "session_id": "s1", "verdict": "pass",
             "branch": "textedit", "command_hash": "eeee", "fingerprint": "sub"},
            {"ts": "2026-07-17T10:01:00Z", "session_id": "s1", "verdict": "block",
             "branch": "none", "command_hash": "aaaa", "fingerprint": "v,haslabel,has"},
            {"ts": "2026-07-17T10:02:00Z", "session_id": "s1", "verdict": "pass",
             "branch": "terminal", "command_hash": "bbbb",
             "fingerprint": "v,haslabel,has,tolist"},
            {"ts": "2026-07-17T11:00:00Z", "session_id": "s2", "verdict": "block",
             "branch": "none", "command_hash": "cccc", "fingerprint": "v,groupcount,by"},
            {"ts": "2026-07-17T11:01:00Z", "session_id": "s2", "verdict": "pass",
             "branch": "wrapper", "command_hash": "dddd", "fingerprint": "v,groupcount,by"},
        ],
    )

    report = gremlin_report(traces_base=tmp_path / "none", guards_base=guards)

    assert report.blocks == 3
    assert report.passes == 3
    assert report.rescued == 2  # both s1 blocks — s2's wrapper pass is not a rescue
    assert report.repeat_blocks == 1  # only the identical re-submission
    assert len(load_guard_events(guards)) == 6


def test_reuse_tagging_matches_recipe_shape_across_dialects():
    """
    Scenario: A session adapts the stored census recipe (new arguments, same
    traversal shape) in gremlin-python, and a recall-strategy recipe in
    gremlin-lang; a third query shares no stored shape

    Verifications:
    - shape reuse is detected across snake_case/camelCase and argument changes
    - an unrelated traversal is from-scratch
    """
    prints = recipe_fingerprints()
    assert prints, "stores should yield fingerprints"

    adapted_census = "connect().V().group_count().by(T.label).next()"
    assert is_recipe_derived(adapted_census, prints) is not None

    # Temporal bound: a query predating the recipe's admission was the recipe's
    # source, not its reuse (verification finding 3 — selection on success).
    from datetime import datetime, timezone

    before_store = datetime(2026, 7, 1, tzinfo=timezone.utc)
    after_store = datetime(2026, 7, 18, tzinfo=timezone.utc)
    assert is_recipe_derived(adapted_census, prints, ts=before_store) is None
    assert is_recipe_derived(adapted_census, prints, ts=after_store) is not None

    adapted_lang = (
        "g.V().hasLabel('Artifact').has('identifier', containing('writer.py'))"
        ".project('file','sessions').by(values('identifier'))"
        ".by(__.in('TOUCHES').values('session_id').fold())"
    )
    assert is_recipe_derived(adapted_lang, prints) is not None

    assert is_recipe_derived("g.E().sample(3).label()", prints) is None


def test_step_fingerprint_folds_dialect():
    assert step_fingerprint("g.V().has_label('x').out_e('Y')") == step_fingerprint(
        "g.V().hasLabel('a').outE('B')"
    )


def test_memory_query_and_bash_gremlin_trace_classification(tmp_path):
    """
    Scenario: The tap holds a dialect rejection, an empty memory_query result,
    and a bash_gremlin execution whose stdout carries a bare vertex ID

    Verifications:
    - rejection is rejected, not legacy, not a miss; empty result is a miss
    - bash_gremlin output gets vertex IDs backticked at parse; never legacy
    - a marker-mentioning text-edit command is filtered out of the retrieval
      surface entirely (over-inclusion — verification finding 2)
    """
    traces = tmp_path / "traces"
    _write_jsonl(
        traces / "2026-07.jsonl",
        [
            {
                "ts": "2026-07-17T10:00:00Z",
                "session_id": "s1",
                "tool_name": "mcp__thalamus__memory_query",
                "tool_input": {"query": "g.V().to_list()"},
                "tool_response": "Rejected: `to_list` is gremlin-python dialect. ...",
            },
            {
                "ts": "2026-07-17T10:01:00Z",
                "session_id": "s1",
                "tool_name": "mcp__thalamus__memory_query",
                "tool_input": {"query": "g.V().hasLabel('Nope')"},
                "tool_response": "Query returned no results.",
            },
            {
                "ts": "2026-07-17T10:02:00Z",
                "session_id": "s1",
                "tool_name": "bash_gremlin",
                "tool_input": {
                    "command": "python -c 'from thalamus.substrate.writer import connect; print(connect().V().to_list())'"
                },
                "tool_response": "{'id': 'scope:main:claim:abc123', 'n': 3}",
            },
            {
                "ts": "2026-07-17T10:03:00Z",
                "session_id": "s1",
                "tool_name": "bash_gremlin",
                "tool_input": {
                    "command": "sed -i 's/from thalamus.substrate.writer import connect/x/' a.py"
                },
                "tool_response": "edited",
            },
        ],
    )

    events = load_events(traces)
    assert len(events) == 3
    rejected, miss, bash = events

    assert rejected.is_rejected() and not rejected.is_legacy() and not rejected.is_miss()
    assert miss.is_miss()
    assert bash.returned_node_ids() == ["scope:main:claim:abc123"]
    assert not bash.is_legacy()

    report = gremlin_report(traces_base=traces, guards_base=tmp_path / "none")
    assert report.mq_total == 2
    assert report.mq_dialect == 1
    assert report.mq_miss == 1
    assert report.bash_total == 1
    assert report.bash_errored == 0


def test_smoke_refuses_mutating_recipe_without_executing(tmp_path):
    """
    Scenario: A stored recipe drifted onto the write path (drop())

    Verifications:
    - the smoke run fails it lexically, before any execution
    - rendering marks it FAIL
    """
    recipes = tmp_path / "RECIPES.md"
    recipes.write_text(
        "# Store\n\n## Bad actor\n\n```python\n"
        "from thalamus.substrate.writer import connect\n"
        "connect().V().drop().iterate()\n```\n"
    )

    results = smoke_recipes("ws://nowhere:1/gremlin", path=recipes)

    assert len(results) == 1
    assert not results[0].ok
    assert "mutating" in results[0].detail
    assert "FAIL" in render_smoke(results)


def test_smoke_render_counts():
    rendered = render_smoke([SmokeResult("a", True), SmokeResult("b", False, "boom")])
    assert rendered.startswith("Recipe smoke run — 1/2 OK")
