"""
Gremlin query-cost tests — the span tap and the report over it.

Interfaces: thalamus.substrate.spans (SpanRecorder, shape folding, instrument,
ledger), thalamus.eval.profile (pooling, percentiles, corpus extraction,
step-metric parsing)
Infrastructure: tmp_path ledgers and a fake DriverRemoteConnection; no live
graph, no model. The `profile()` round trip is exercised live, not here.
Scope: the honesty properties the report rests on — that the shape key folds
both dialects to one token sequence, that percentiles come from a named rule
over a bounded sample and say when they were truncated, that the tap measures
its own overhead rather than asserting it, and that recording never breaks or
alters the traversal it wraps.
"""

import json

import pytest

from thalamus.eval.gremlin import step_fingerprint
from thalamus.eval.profile import (
    QueryProfile,
    _flatten,
    lang_corpus,
    percentile,
    profile_report,
    render_query_profile,
    to_json,
)
from thalamus.substrate.spans import (
    SpanRecorder,
    bytecode_shape,
    instrument,
    load_rows,
    step_shape,
)


class _FakeBytecode:
    """gremlin-python's Bytecode as the driver hands it to `submit`."""

    def __init__(self, source, steps):
        self.source_instructions = [[name] for name in source]
        self.step_instructions = [[name, "arg"] for name in steps]


class _FakeConnection:
    def __init__(self, fail=False):
        self.calls = 0
        self._fail = fail

    def submit(self, bytecode):
        self.calls += 1
        if self._fail:
            raise RuntimeError("server said no")
        return f"results for {len(bytecode.step_instructions)} step(s)"


# ---------------------------------------------------------------- the shape key


def test_one_shape_key_spans_both_dialects_and_both_readers():
    """
    Scenario: the same traversal written as gremlin-python text, as gremlin-lang
    text, and as the bytecode the driver actually sends

    Verifications:
    - all three fold to one token sequence, which is what lets a span row and a
      recipe-reuse tag be the same key rather than two spellings of one shape
    - eval.gremlin's fingerprint is that rule, not a second copy of it
    """
    python_text = "g.V().has_label('Trace').out_e('RETURNS').value_map()"
    lang_text = "g.V().hasLabel('Trace').outE('RETURNS').valueMap()"
    bytecode = _FakeBytecode([], ["V", "hasLabel", "outE", "valueMap"])

    expected = ("v", "haslabel", "oute", "valuemap")
    assert step_shape(python_text) == expected
    assert step_shape(lang_text) == expected
    assert bytecode_shape(bytecode) == expected
    assert step_fingerprint(lang_text) == expected


# ---------------------------------------------------------------- the tap


def test_recorder_flushes_one_row_per_shape_and_prices_itself(tmp_path):
    """
    Scenario: two shapes recorded, one of them three times, then flushed

    Verifications:
    - one ledger row per (surface, shape), carrying calls, total and samples —
      aggregation is the reason the ledger does not outgrow what it measures
    - the tap's own cost is written as tap_ns, so the report can state overhead
      as a measured ratio instead of calling it negligible
    - a flush empties the buckets: a second flush does not double-count
    """
    recorder = SpanRecorder(base=tmp_path)
    for ms in (1.0, 3.0, 5.0):
        recorder.record("gremlin-python", ("v", "haslabel"), ms)
    recorder.record("memory_query", ("e", "count"), 12.0)

    path = recorder.flush()
    rows = {(r.surface, r.shape_text): r for r in load_rows(tmp_path)}
    assert path is not None and len(rows) == 2

    hot = rows[("gremlin-python", "v.haslabel")]
    assert hot.calls == 3 and hot.total_ms == pytest.approx(9.0)
    assert hot.samples == [1.0, 3.0, 5.0]
    assert hot.tap_ns > 0

    assert recorder.flush() is None
    assert len(load_rows(tmp_path)) == 2


def test_instrument_times_traversals_without_altering_them(tmp_path):
    """
    Scenario: an instrumented connection submits a traversal, then one that the
    server rejects; the connection is instrumented twice

    Verifications:
    - the caller gets the driver's own return value back untouched
    - a failing traversal is still a cost the caller paid, so it is recorded
    - double instrumentation does not double-count (the wrap is idempotent)
    """
    from thalamus.substrate import spans

    recorder = SpanRecorder(base=tmp_path)
    monkey = spans._RECORDER
    spans._RECORDER = recorder
    try:
        connection = _FakeConnection()
        instrument(connection)
        instrument(connection)  # no-op
        result = connection.submit(_FakeBytecode([], ["V", "count"]))
        assert result == "results for 2 step(s)"

        failing = _FakeConnection(fail=True)
        instrument(failing)
        with pytest.raises(RuntimeError):
            failing.submit(_FakeBytecode([], ["V", "drop"]))

        recorder.flush()
    finally:
        spans._RECORDER = monkey

    rows = {r.shape_text: r for r in load_rows(tmp_path)}
    assert rows["v.count"].calls == 1  # not 2 — instrument is idempotent
    assert rows["v.drop"].calls == 1  # the failure was still paid for


def test_recording_is_off_when_disabled(tmp_path, monkeypatch):
    """
    Scenario: THALAMUS_PROFILE=0

    Verifications:
    - `instrument` leaves the connection's own submit in place, so an operator
      who turns the tap off is running the unwrapped driver, not a cheaper wrap
    """
    from thalamus.substrate import spans

    monkeypatch.setenv("THALAMUS_PROFILE", "0")
    recorder = SpanRecorder(base=tmp_path)
    monkeypatch.setattr(spans, "_RECORDER", recorder)

    connection = _FakeConnection()
    instrument(connection)
    connection.submit(_FakeBytecode([], ["V", "count"]))

    assert not getattr(connection, "_thalamus_timed", False)
    assert recorder.flush() is None


# ---------------------------------------------------------------- the report


def _ledger(tmp_path, rows):
    directory = tmp_path / "profiles"
    directory.mkdir()
    (directory / "2026-08.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return directory


def test_percentile_rule_is_nearest_rank():
    """A reader has to know which percentile definition produced the number."""
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 95) == 4.0
    assert percentile([7.0], 95) == 7.0
    assert percentile([], 50) is None


def test_report_pools_by_shape_and_keeps_origins_apart(tmp_path):
    """
    Scenario: one shape recorded by two different origins, plus a rarer but
    individually slower shape

    Verifications:
    - a shape's calls and samples pool across the rows that recorded it
    - ranking is by total time, so the frequent cheap shape outranks the rare
      expensive one — which is the cost, not the worst single reading
    - origins are reported separately, because a warm long-lived process and a
      fresh CLI invocation are not one population
    - overhead is a measured ratio against the traversal time beside it
    """
    base = _ledger(
        tmp_path,
        [
            {
                "ts": "2026-08-20T10:00:00Z", "origin": "mcp", "scope": "main",
                "surface": "gremlin-python", "shape": "v.haslabel.valuemap",
                "calls": 3, "total_ms": 30.0, "ms": [8.0, 10.0, 12.0], "tap_ns": 3000,
            },
            {
                "ts": "2026-08-21T10:00:00Z", "origin": "cli:contract", "scope": "",
                "surface": "gremlin-python", "shape": "v.haslabel.valuemap",
                "calls": 2, "total_ms": 40.0, "ms": [18.0, 22.0], "tap_ns": 2000,
            },
            {
                "ts": "2026-08-22T10:00:00Z", "origin": "cli:contract", "scope": "",
                "surface": "memory_query", "shape": "e.elementmap",
                "calls": 1, "total_ms": 50.0, "ms": [50.0], "tap_ns": 1000,
            },
        ],
    )
    report = profile_report(base=base)

    assert report.calls == 6 and report.total_ms == pytest.approx(120.0)
    assert [s.shape_text for s in report.shapes] == ["v.haslabel.valuemap", "e.elementmap"]
    pooled = report.shapes[0]
    assert pooled.calls == 5 and pooled.origins == {"mcp", "cli:contract"}
    assert pooled.p(50) == 12.0 and pooled.p(100) == 22.0
    assert [o.origin for o in report.origins] == ["cli:contract", "mcp"]
    # 6000 ns of tap against 120 ms of traversal.
    assert report.tap_overhead_pct == pytest.approx(0.005)

    rendered = report.render()
    assert "cli:contract" in rendered and "mcp" in rendered
    assert "one machine" in rendered  # the reading's scope travels with it


def test_truncated_samples_are_declared_not_hidden(tmp_path):
    """
    Scenario: a shape called 500 times whose row retained only 200 durations

    Verifications:
    - the projection reports `sampled` beside `calls`, and the rendered report
      marks the percentile as covering a sample — a bounded reservoir that
      reads as the whole population is the failure this guards
    """
    base = _ledger(
        tmp_path,
        [
            {
                "ts": "2026-08-20T10:00:00Z", "origin": "mcp", "scope": "main",
                "surface": "gremlin-python", "shape": "v.haslabel",
                "calls": 500, "total_ms": 1000.0, "ms": [2.0] * 200, "tap_ns": 500,
            }
        ],
    )
    report = profile_report(base=base)
    assert report.shapes[0].sampled == 200 and report.shapes[0].calls == 500
    assert "bounded sample" in report.render()
    assert to_json(report)["shapes"][0]["sampled"] == 200


def test_empty_ledger_says_so_rather_than_reporting_zeroes(tmp_path):
    """An unmeasured state is a state, never a zero (the pulse honesty rule)."""
    report = profile_report(base=tmp_path / "nothing")
    assert report.calls == 0
    assert "No spans recorded yet" in report.render()
    assert to_json(report)["calls"] == 0


# ---------------------------------------------------------------- step profiles


def test_step_metrics_flatten_with_depth_and_counts():
    """
    Scenario: TinkerPop's TraversalMetrics map, with one nested child step

    Verifications:
    - nanosecond durations become milliseconds, counts survive intact, and the
      nesting is kept as depth so a child step is not read as a sibling
    - `elements` counts top-level steps only, so a nested step's elements are
      not added to their own parent's
    """
    steps = _flatten(
        [
            {
                "name": "TinkerGraphStep(vertex,[])",
                "dur": 2_500_000,
                "counts": {"elementCount": 11, "traverserCount": 11},
                "annotations": {"percentDur": 80.0},
                "metrics": [
                    {
                        "name": "HasStep([used.eq(false)])",
                        "dur": 500_000,
                        "counts": {"elementCount": 4, "traverserCount": 4},
                        "annotations": {},
                        "metrics": [],
                    }
                ],
            }
        ]
    )
    assert [s.depth for s in steps] == [0, 1]
    assert steps[0].ms == pytest.approx(2.5) and steps[0].elements == 11
    assert steps[1].ms == pytest.approx(0.5) and steps[1].pct == 0.0

    profile = QueryProfile(name="q", query="g.V()", wall_ms=[3.0, 4.0], steps=steps)
    assert profile.elements == 11  # not 15


def test_render_reports_raw_observations_and_flags_an_empty_traversal():
    """
    Scenario: a corpus template whose placeholder ids match nothing

    Verifications:
    - the runs are printed as raw observations with their n, never as a mean
    - touching nothing is called out, so a fast empty traversal is not read as
      a finding about the graph
    """
    rendered = render_query_profile(
        QueryProfile(name="template", query="g.V('scope:<s>:claim:<id>')", wall_ms=[6.2, 4.4])
    )
    assert "6.2/4.4" in rendered and "n=2" in rendered
    assert "touched nothing" in rendered


def test_a_gremlin_python_recipe_is_refused_by_the_read_only_floor(tmp_path):
    """
    Scenario: `profile_query` is handed a snippet in the wrong dialect

    Verifications:
    - it is rejected before any client is opened, by the same guard the
      memory_query surface enforces — so nothing profileable here is
      unrunnable there
    """
    from thalamus.eval.profile import profile_query

    profile = profile_query("ws://unused/gremlin", "g.V().count().next()")
    assert not profile.ok and "gremlin-python dialect" in profile.error


def test_corpus_numbers_recipes_that_share_a_heading(tmp_path):
    """
    Scenario: a store where several gremlin-lang recipes sit under one heading,
    beside a python recipe and a duplicate query

    Verifications:
    - only gremlin-lang blocks are taken; python recipes are the span tap's job
    - duplicates collapse, and same-named recipes are numbered, so a slow one
      is nameable rather than one of several identical rows
    """
    store = tmp_path / "SKILL.md"
    store.write_text(
        "## Tested recipes\n\n"
        "    g.V().hasLabel('Trace').count()\n\n"
        "some prose\n\n"
        "    g.V().hasLabel('Claim').count()\n\n"
        "more prose\n\n"
        "    g.V().hasLabel('Trace').count()\n\n"
        "## Python recipe\n\n"
        "```python\nfrom thalamus.substrate.writer import connect\n```\n"
    )
    corpus = lang_corpus([store])
    assert [name for name, _ in corpus] == ["Tested recipes", "Tested recipes #2"]
    assert all(query.startswith("g.") for _, query in corpus)
