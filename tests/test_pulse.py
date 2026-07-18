"""
Pulse dashboard tests: the JSON view-models and the web app's honesty states.

Interfaces: thalamus.pulse.metrics, thalamus.pulse.web
Infrastructure: tmp_path ledgers + a stubbed graph read — no live graph, no model
Scope: the projections the frontend trusts blind. The dashboard's whole contract
is that honesty states (tap-only, pending, undefined-rate, floors) are produced
by the data layer, so that is what gets pinned here.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from thalamus.pulse import metrics
from thalamus.pulse.metrics import (
    _TimedTrace,
    _GraphRead,
    live_snapshot,
    report_snapshot,
)
from thalamus.eval.pins import VerdictRow
from thalamus.pulse.web import create_pulse_app


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


def _ledgers(tmp_path: Path) -> dict:
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "2026-07.jsonl").write_text(
        "\n".join(
            [
                _tap_line(),
                _tap_line(
                    ts="2026-07-15T11:00:00Z",
                    session_id="sess-2",
                    tool_response="No matching memories found.",
                ),
                _tap_line(
                    ts="2026-07-15T12:00:00Z",
                    tool_response="**Node:** `scope:main:claim:x` "
                    + " ".join(f"`scope:main:claim:n{i}`" for i in range(20)),
                ),
            ]
        )
    )
    guards = tmp_path / "guards"
    guards.mkdir()
    (guards / "2026-07.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-07-15T10:30:00Z",
                "session_id": "sess-1",
                "scope": "main",
                "guard": "terminal-step",
                "verdict": "pass",
                "command_hash": "aa",
            }
        )
    )
    conditioning = tmp_path / "conditioning"
    conditioning.mkdir()
    pins = tmp_path / "pins.jsonl"
    pins.write_text(
        json.dumps({"session_id": "sess-1", "scope": "homelab", "ts": "2026-07-15T09:59:00Z"})
    )
    return {
        "traces_base": traces,
        "guards_base": guards,
        "conditioning_base": conditioning,
        "pins_file": pins,
    }


def test_live_snapshot_is_cost_only_and_flags_the_guardrail(tmp_path):
    """
    Scenario: three tap events — a normal recall, a miss, and a 21-node fan-out

    Verifications:
    - the feed is newest-first and carries cost/fan-out, never a used%
    - the over-guardrail event is flagged (lab/007's dial travels with the data)
    - the miss is an event class, not an error state
    - the pinned scope from the ledger reaches the feed rows
    """
    live = live_snapshot(**_ledgers(tmp_path))

    assert [e["ts"] for e in live["feed"]] == sorted(
        (e["ts"] for e in live["feed"]), reverse=True
    )
    assert all("used" not in e and "used_pct" not in e for e in live["feed"])
    big = live["feed"][0]
    assert big["fanout"] == 21 and big["over_guardrail"] is True
    assert live["feed"][1]["miss"] is True and live["feed"][1]["fanout"] == 0
    assert live["feed"][2]["scope"] == "homelab"
    assert live["guards"][0]["verdict"] == "pass"


def test_report_without_graph_is_tap_only_not_empty(tmp_path):
    """
    Scenario: the graph is unreachable (g=None)

    Verifications:
    - graph_ok is False and graph-side sections are absent/empty, not fabricated
    - ledger-side reports (gremlin, conditioning) still render
    - the calibration-plate disclosures are always present
    """
    ledgers = _ledgers(tmp_path)
    report = report_snapshot(
        None,
        project_dir=tmp_path / "nowhere",
        **ledgers,
    )

    assert report["graph_ok"] is False
    assert report["scopes"] == {} and report["pins"] is None and report["trend"] == []
    assert report["gremlin"]["passes"] == 1
    assert report["gremlin"]["rescue_rate"] is None  # zero blocks: undefined, never 0
    assert report["conditioning"]["measured"] is False
    assert any("dial" in d or "≥2 terms" in d for d in report["disclosures"]["dials"])
    assert "layer 1" in report["disclosures"]["standing"]


def test_trend_and_sessions_price_verdicts_with_absolutes(tmp_path):
    """
    Scenario: two traces on different days; one verdict used, two ignored,
    one unattributed

    Verifications:
    - per-day trend carries both the rate and the absolute earned/wasted tokens
    - unattributed verdicts never count as ignored (lab/002's rule survives
      the projection)
    - session rows aggregate the same verdicts
    """
    t1 = _TimedTrace(
        vid="scope:main:trace:aaa", scope="main", session_id="s1",
        injected_chars=8000, returned_count=2, ts="2026-07-14T10:00:00Z",
    )
    t2 = _TimedTrace(
        vid="scope:main:trace:bbb", scope="main", session_id="s1",
        injected_chars=4000, returned_count=2, ts="2026-07-15T10:00:00Z",
    )
    read = _GraphRead(
        traces=[t1, t2],
        verdicts=[
            VerdictRow("scope:main:trace:aaa", "scope:main:claim:1", used=True),
            VerdictRow("scope:main:trace:aaa", "scope:main:claim:2", used=False),
            VerdictRow("scope:main:trace:bbb", "scope:main:claim:3", used=False),
            VerdictRow("scope:main:trace:bbb", "scope:main:claim:4", used=None),
        ],
    )

    trend = metrics._daily_trend(read)
    assert [d["day"] for d in trend] == ["2026-07-14", "2026-07-15"]
    day1 = trend[0]
    assert day1["used_pct"] == 50.0 and day1["waste_pct"] == 50.0
    assert day1["earned_tokens"] == 1000 and day1["wasted_tokens"] == 1000
    day2 = trend[1]
    assert day2["attributed"] == 1  # the None verdict is absent, not "ignored"
    assert day2["waste_pct"] == 100.0 and day2["wasted_tokens"] == 500

    sessions = metrics._session_utilities(read, pins={"s1": "main"})
    assert len(sessions) == 1
    row = sessions[0]
    assert row["attributed"] == 3 and row["used"] == 1
    assert row["earned_tokens"] == 1000 and row["wasted_tokens"] == 1500
    assert len(row["recalls"]) == 2


def test_pending_names_undistilled_sessions(tmp_path):
    """
    Scenario: the tap holds three events; only one has landed as a Trace node

    Verifications:
    - pending counts tap events whose trace_id has no landed Trace
    - pending is grouped per session with the oldest timestamp (stuck detection)
    """
    ledgers = _ledgers(tmp_path)
    from thalamus.eval.traces import load_events

    events = load_events(ledgers["traces_base"])
    landed = _TimedTrace(
        vid=f"scope:main:trace:{events[0].trace_id()}",
        scope="main", session_id="sess-1", ts="2026-07-15T10:00:00Z",
    )
    pending = metrics._pending(
        _GraphRead(traces=[landed]), traces_base=ledgers["traces_base"]
    )

    assert pending["total"] == 2
    assert {row["session"] for row in pending["sessions"]} == {"sess-1", "sess-2"}


def test_web_app_serves_dashboard_and_degrades_without_graph(tmp_path, monkeypatch):
    """
    Scenario: the pulse app runs with ledgers but no reachable graph

    Verifications:
    - / serves the dashboard page
    - /api/live returns the feed
    - /api/report returns a tap-only report instead of failing
    """
    ledgers = _ledgers(tmp_path)
    monkeypatch.setattr("thalamus.pulse.web._try_connect", lambda url: None)
    app = create_pulse_app(project_dir=tmp_path / "nowhere", **ledgers)
    client = TestClient(app)

    page = client.get("/")
    assert page.status_code == 200 and "Thalamus Pulse" in page.text

    live = client.get("/api/live").json()
    assert len(live["feed"]) == 3

    report = client.get("/api/report").json()
    assert report["graph_ok"] is False
    assert report["disclosures"]["standing"].startswith("layer 1")
