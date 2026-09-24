"""
Pulse dashboard tests: the JSON view-models and the web app's honesty states.

Interfaces: thalamus.pulse.metrics, thalamus.pulse.web
Infrastructure: tmp_path ledgers + a stubbed graph read — no live graph, no model
Scope: the projections the frontend trusts blind. The dashboard's whole contract
is that honesty states (tap-only, pending, undefined-rate, floors) are produced
by the data layer, so that is what gets pinned here.
"""

import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from thalamus.pulse import metrics
from thalamus.pulse.metrics import (
    _TimedTrace,
    _GraphRead,
    live_snapshot,
    report_snapshot,
)
from thalamus.eval.pins import VerdictRow
from thalamus.eval.traces import TraceEvent
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
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "2026-07.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-07-15T10:05:00Z",
                "origin": "mcp",
                "scope": "main",
                "surface": "gremlin-python",
                "shape": "v.haslabel.valuemap",
                "calls": 4,
                "total_ms": 40.0,
                "ms": [8.0, 9.0, 11.0, 12.0],
                "tap_ns": 4000,
            }
        )
    )
    pins = tmp_path / "pins.jsonl"
    pins.write_text(
        json.dumps({"session_id": "sess-1", "scope": "homelab", "ts": "2026-07-15T09:59:00Z"})
    )
    # An empty transcript root, not an absent one. Left unset, the cost scan walks
    # `~/.claude/projects` and every room the pin ledger names, so the report under
    # test would be assembled from the operator's own sessions.
    projects = tmp_path / "projects"
    projects.mkdir()
    return {
        "traces_base": traces,
        "guards_base": guards,
        "conditioning_base": conditioning,
        "profiles_base": profiles,
        "pins_file": pins,
        "projects_base": projects,
    }


def test_live_snapshot_is_cost_only_and_flags_the_guardrail(tmp_path):
    """
    Scenario: three tap events — a normal recall, a miss, and a 21-node fan-out

    Verifications:
    - the feed is newest-first and carries cost/fan-out, never a used%
    - the over-guardrail event is flagged (the dial travels with the data)
    - the miss is an event class, not an error state
    - the pinned scope from the ledger reaches the feed rows
    """
    ledgers = _ledgers(tmp_path)
    live = live_snapshot(traces_base=ledgers["traces_base"], pins_file=ledgers["pins_file"])

    assert [e["ts"] for e in live["feed"]] == sorted(
        (e["ts"] for e in live["feed"]), reverse=True
    )
    assert all("used" not in e and "used_pct" not in e for e in live["feed"])
    big = live["feed"][0]
    assert big["fanout"] == 21 and big["over_guardrail"] is True
    assert live["feed"][1]["miss"] is True and live["feed"][1]["fanout"] == 0
    assert live["feed"][2]["scope"] == "homelab"
    # The guard ledger is a rate on the report, never a feed of `pass` rows here.
    assert set(live) == {"generated_at", "feed", "fanout_guardrail"}


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
    assert report["scopes"] == {} and report["trend"] == [] and "pins" not in report
    assert report["gremlin"]["passes"] == 1
    assert report["gremlin"]["rescue_rate"] is None  # zero blocks: undefined, never 0
    assert report["conditioning"]["measured"] is False
    assert "48 h stuck line" in report["disclosures"]["dials"]
    assert "15-node guardrail" in report["disclosures"]["dials"]

    # The graph being down is a failed check with an act-now item of its own; the
    # sync tile cannot tell landed from not without it, and says so in a neutral
    # word rather than a red one — the one red is the graph's.
    checks = {c["name"]: c for c in report["health"]["checks"]}
    assert checks["Graph"]["state"] == "failed"
    assert checks["Sync"]["state"] == "count" and checks["Sync"]["word"] == "NOT READ"
    assert [i["title"] for i in report["health"]["needs_you"]] == ["The graph is unreachable"]
    assert report["pending"] is None
    # No build recorded is unknown, never "0 behind".
    assert report["build"]["behind"] is None

    # Query cost is span-ledger side: it survives the graph being down, and it
    # arrives with the spread and its own measured overhead rather than a mean.
    cost = report["query_cost"]
    assert cost["calls"] == 4 and cost["shapes"][0]["shape"] == "v.haslabel.valuemap"
    assert cost["shapes"][0]["p50"] == 9.0 and cost["shapes"][0]["max"] == 12.0
    assert "mean" not in cost["shapes"][0]
    assert cost["tap_overhead_pct"] == pytest.approx(0.01)
    assert "one machine" in report["disclosures"]["query_cost"]

    # The transcript scan ran against the fixture's empty root and found nothing.
    # Non-empty here means `projects_base` stopped reaching `cost_report` and the
    # scan walked the operator's own archive, which is not this test's subject and
    # would make its verdict a function of what he ran this week.
    assert report["cost"]["buckets"] == [] and report["cost"]["by_day"] == []


def test_trend_and_sessions_price_verdicts_with_absolutes(tmp_path):
    """
    Scenario: two traces on different days; one verdict used, two ignored,
    one unattributed

    Verifications:
    - per-day trend carries both the rate and the absolute earned/wasted tokens
    - unattributed verdicts never count as ignored (the rule survives the projection)
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


_NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
_S_FRESH = "11111111-1111-4111-8111-111111111111"
_S_LONG = "22222222-2222-4222-8222-222222222222"
_S_OLD = "33333333-3333-4333-8333-333333333333"


def _event(session_id: str, hours_ago: float, tool: str = "memory_recall") -> TraceEvent:
    return TraceEvent(
        ts=_NOW - timedelta(hours=hours_ago),
        session_id=session_id,
        cwd="/home/op/code/thalamus",
        tool=tool,
        tool_input={"query": f"{session_id} {hours_ago}"},
        tool_response="",  # an empty response is a miss, never legacy
    )


def _pending_events() -> list[TraceEvent]:
    return [
        _event(_S_FRESH, 2),
        # Started 70 h ago, last active 10 h ago: in flight. The line is measured
        # from the newest event, so a long session is not stuck for its start.
        _event(_S_LONG, 70),
        _event(_S_LONG, 10),
        # Newest event 49 h old, nothing landed: stuck.
        _event(_S_OLD, 60),
        _event(_S_OLD, 49),
        # A fixture id that leaked into the operator's tap.
        _event("test-123", 900),
    ]


def test_pending_splits_stuck_from_in_flight_at_48h_since_newest_event():
    """
    Scenario: three UUID sessions with no landed Trace, one fixture id, one event landed

    Verifications:
    - a session is stuck only when its NEWEST event is past the 48 h line
    - a landed event drops out of pending and out of the counts
    - a non-UUID session id is not pending at all (fixture leak, not a stuck session)
    """
    events = _pending_events()
    landed = _TimedTrace(
        vid=f"scope:main:trace:{events[0].trace_id()}", scope="main", session_id=_S_FRESH,
    )
    pending = metrics._pending(_GraphRead(traces=[landed]), events, _NOW)

    assert pending["stuck_after_hours"] == 48
    assert [r["session"] for r in pending["in_flight"]["sessions"]] == [_S_LONG[:8]]
    assert pending["in_flight"]["events"] == 2
    assert [r["session"] for r in pending["stuck"]["sessions"]] == [_S_OLD[:8]]
    assert pending["stuck"]["events"] == 2
    every = pending["in_flight"]["sessions"] + pending["stuck"]["sessions"]
    assert "test-123" not in {r["session"] for r in every}


def test_health_names_the_stuck_sessions_and_keeps_sync_in_flight():
    """
    Scenario: a report with the pending split above and a reachable graph

    Verifications:
    - stuck sessions are a needs-you item carrying the command that lands them —
      with --write, since a bare `eval sync` is a dry run
    - the Sync tile reports the in-flight sessions and points at the stuck ones
    - count tiles never go red, whatever they read
    """
    pending = metrics._pending(_GraphRead(), _pending_events(), _NOW)
    out = {
        "graph_ok": True,
        "pending": pending,
        "cost": {"buckets": [{"name": "extract", "weighted": 0,
                              "blind": metrics._blind_spot("extract", 0)}]},
        "gremlin": {"blocks": 46, "passes": 884, "rescued": 6,
                    "memory_query": {"total": 303, "server_failed": 2, "dialect_rejected": 12}},
        "build": metrics._build_dict(None),
    }
    health = metrics._health(out, _pending_events(), 14, _NOW)

    [item] = health["needs_you"]
    assert item["kind"] == "stuck" and item["word"] == "STUCK"
    assert item["title"] == "1 session never synced"
    assert item["command"] == "thalamus eval sync --write"
    assert "2 recalls have no verdict" in item["detail"]

    checks = {c["name"]: c for c in health["checks"]}
    assert set(checks) == {"Graph", "Tap", "Sync", "Cost scan", "memory_query", "Gremlin guard"}
    assert checks["Sync"]["state"] == "in_flight"
    assert checks["Sync"]["lines"] == ["2 sessions · 3 events", "+ 1 stuck, above"]
    assert checks["Cost scan"]["lines"][1] == "extract not measured"
    assert checks["Gremlin guard"]["state"] == "count"
    assert checks["Gremlin guard"]["lines"][0] == "46 blocks in 930 (4.9%)"
    assert checks["memory_query"]["state"] == "count"
    assert all("needs_you" not in c for c in health["checks"])


def test_zero_cost_buckets_the_scan_cannot_see_carry_a_chip_not_a_zero():
    """
    Verifications:
    - extract at 0 is NOT MEASURED; a pinned expert at 0 is 0 · UNVERIFIED
    - a bucket that read something, or `interactive` at 0, carries no chip
    """
    assert metrics._blind_spot("extract", 0)["chip"] == "NOT MEASURED"
    assert metrics._blind_spot("expert:literature", 0)["chip"] == "0 · UNVERIFIED"
    assert metrics._blind_spot("expert:designer", 5) is None
    assert metrics._blind_spot("extract", 5) is None
    assert metrics._blind_spot("interactive", 0) is None


def _vcs(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_build_reports_how_far_the_checkout_moved_since_boot(tmp_path):
    """
    Scenario: pulse records its build, then two commits land — one touching pulse

    Verifications:
    - behind counts commits since the recorded sha; touching counts those that
      change pulse or the eval code it reads
    - behind > 0 is a STALE BUILD needs-you item naming the branch and the restart
    - a directory that is no checkout reports behind None (unknown), never 0
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _vcs(repo, "init", "-q", "-b", "master")
    (repo / "README").write_text("a")
    _vcs(repo, "add", "README")
    _vcs(repo, "commit", "-qm", "one")
    build = metrics.record_build(repo)
    assert build["sha"] == _vcs(repo, "rev-parse", "HEAD")
    assert metrics._build_dict(build)["behind"] == 0

    (repo / "README").write_text("b")
    _vcs(repo, "commit", "-qam", "two")
    (repo / "src/thalamus/pulse").mkdir(parents=True)
    (repo / "src/thalamus/pulse/web.py").write_text("")
    _vcs(repo, "add", "src")
    _vcs(repo, "commit", "-qm", "three")

    now = metrics._build_dict(build)
    assert now["behind"] == 2 and now["touching"] == 1 and now["branch"] == "master"
    health = metrics._health(
        {"graph_ok": True, "pending": None, "cost": {"buckets": []}, "gremlin": None,
         "build": now},
        [], 14, _NOW,
    )
    stale = [i for i in health["needs_you"] if i["kind"] == "stale_build"]
    assert len(stale) == 1
    assert stale[0]["command"] == "systemctl --user restart thalamus-pulse"
    assert stale[0]["detail"].startswith("2 commits behind master; 1 of them change pulse")

    nowhere = tmp_path / "not-a-checkout"
    nowhere.mkdir()
    assert metrics._build_dict(metrics.record_build(nowhere))["behind"] is None


_CONSOLE = Path(metrics.__file__).parents[1] / "console" / "static"
_PULSE = Path(metrics.__file__).parent / "static"


def _root_tokens(css: str) -> dict[str, str]:
    match = re.search(r":root\s*\{(.*?)\n\}", css, re.S)
    assert match, "no :root block"
    root = re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.S)
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", root))


def test_pulse_uses_the_console_tokens_and_identity_hues_verbatim():
    """
    Pulse joins the console's system rather than keeping a palette of its own, so a
    drift between the two is a defect. Every token both declare must hold one value,
    the spec's list must be present, and the identity hash must be the same code
    over the same palette — otherwise a scope is one hue on the console and another
    on the dashboard.
    """
    page = (_PULSE / "index.html").read_text()
    pulse_tokens = _root_tokens(page)
    console_tokens = _root_tokens((_CONSOLE / "style.css").read_text())
    required = {"--bg", "--panel", "--panel-hi", "--hair", "--ink", "--muted", "--faint",
                "--danger", "--danger-text", "--warn", "--ok", "--pending", "--accent",
                "--mono", "--ui"}
    assert required <= set(pulse_tokens)
    for name in set(pulse_tokens) & set(console_tokens):
        assert pulse_tokens[name].strip() == console_tokens[name].strip(), name

    console_js = (_CONSOLE / "app.js").read_text()
    for pattern in (r'const MAIN_HUE = "[^"]+"', r"const PALETTE = \[[^\]]+\]",
                    r"function hashHue\(name\) \{.*?\n\}"):
        match = re.search(pattern, console_js, re.S)
        assert match and match.group(0) in page, pattern

    # The faces are pulse's own copies, byte-identical to the console's subsets.
    for face in ("plex-mono-400", "plex-mono-600", "plex-sans-400", "plex-sans-600"):
        name = f"{face}.woff2"
        assert (_PULSE / name).read_bytes() == (_CONSOLE / name).read_bytes(), name


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
    assert [c["name"] for c in report["health"]["checks"]][0] == "Graph"
    # The page is one file, revalidated on every load: see web.py for why.
    assert page.headers["cache-control"] == "no-cache"


def test_web_app_serves_the_pwa_install_surface(tmp_path, monkeypatch):
    """
    Scenario: a browser evaluates installability behind the /pulse mount

    Verifications:
    - the page links the manifest
    - manifest + icons are served with correct media types, relative URLs
    - the manifest scopes the app to /pulse/ (path-scope discipline: Android
      WebAPKs ignore ports, so /pulse/ must stay disjoint from /console/ etc.)
    - unknown asset names 404 instead of leaking arbitrary paths
    """
    monkeypatch.setattr("thalamus.pulse.web._try_connect", lambda url: None)
    client = TestClient(create_pulse_app(**_ledgers(tmp_path)))

    assert '<link rel="manifest" href="manifest.webmanifest">' in client.get("/").text

    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    body = manifest.json()
    assert body["scope"] == "/pulse/" and body["start_url"] == "/pulse/"
    assert {i["src"] for i in body["icons"]} == {"icon-192.png", "icon-512.png"}

    for icon in ("icon-192.png", "icon-512.png"):
        r = client.get(f"/{icon}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    for face in ("plex-mono-400", "plex-mono-600", "plex-sans-400", "plex-sans-600"):
        r = client.get(f"/{face}.woff2")
        assert r.status_code == 200 and r.headers["content-type"] == "font/woff2"
        assert f'url("{face}.woff2")' in client.get("/").text
    assert client.get("/PLEX-OFL.txt").status_code == 200

    assert client.get("/no-such-file").status_code == 404
    assert client.get("/../pyproject.toml").status_code == 404
