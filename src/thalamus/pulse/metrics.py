"""Pulse view-models — JSON projections of measurements the system already keeps.

Read-only by construction: every number here comes from the trace tap, the
guard/conditioning/pin ledgers, the harness transcripts, or the landed Trace
verdicts in the graph. No new telemetry, no writes, no panel-local metrics —
one priced surface (docs/04, lab/008); the dashboard renders it, it never
mints its own.

The honesty states the frontend renders are produced here, not styled there:
- `graph_ok: false` → graph-dependent panels stamp TAP-ONLY;
- `pending` → tap events whose session has not distilled (a trace can only
  land after its session distills — sync.py);
- pins carry their floor verdicts verbatim (`insufficient data …` is a state,
  never a zero).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from thalamus.contract.manifest import available_scopes
from thalamus.eval.conditioning import conditioning_report
from thalamus.eval.cost import PINS_FILE, cost_report, load_engaged, load_pins
from thalamus.eval.gremlin import gremlin_report, load_guard_events
from thalamus.eval.pins import (
    TraceRow,
    VerdictRow,
    build_pin_report,
    node_scope,
)
from thalamus.eval.report import scope_report
from thalamus.eval.traces import load_events

logger = logging.getLogger(__name__)

MAIN_SCOPE = "main"
_CHARS_PER_TOKEN = 4

# lab/007's prediction: waste share should land at or below this, with used%
# not falling. Rendered as the target band on the waste trend — a dial on
# display, disclosed as such, never a measured claim.
WASTE_TARGET_PCT = 30.0

# lab/007's fan-out guardrail: recalls returning more nodes than this measured
# 28-40% use vs 66-80% for 3-5 node recalls.
FANOUT_GUARDRAIL = 15

REPO_ROOT = Path(__file__).resolve().parents[3]


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Live snapshot — ledger files only, cheap enough to poll.
# ---------------------------------------------------------------------------


def live_snapshot(
    traces_base: Path | None = None,
    guards_base: Path | None = None,
    conditioning_base: Path | None = None,
    pins_file: Path | None = None,
    limit: int = 40,
) -> dict:
    """The turn-level feed: cost and activity only, never utility.

    A per-turn used% would be fabricated — verdicts exist only after the
    session distills and sync attributes (eval-methodology consultation
    a9bb9f26049a4176). This snapshot therefore carries injection cost,
    fan-out, and event class; the utility numbers live in report_snapshot.
    """
    events = load_events(base=traces_base)
    pins = _read_pins(pins_file or PINS_FILE)

    feed = []
    for event in events[-limit:]:
        fanout = len(event.returned_node_ids())
        feed.append(
            {
                "ts": _iso(event.ts),
                "session": event.session_id[:8],
                "tool": event.tool,
                "scope": event.scope or pins.get(event.session_id, ""),
                "query": event.query_text()[:120],
                "fanout": fanout,
                "over_guardrail": fanout > FANOUT_GUARDRAIL,
                "tokens": len(event.tool_response) // _CHARS_PER_TOKEN,
                "miss": event.is_miss(),
                "rejected": event.is_rejected(),
            }
        )
    feed.reverse()  # newest first

    guards = [
        {
            "ts": _iso(g.ts),
            "session": g.session_id[:8],
            "guard": "terminal-step" + (f" ({g.branch})" if g.branch else ""),
            "verdict": g.verdict,
        }
        for g in load_guard_events(guards_base)[-10:]
    ][::-1]

    conditioning = conditioning_report(conditioning_base, traces_base)
    firings = [
        {"ts": _iso(f.ts), "session": f.session_id[:8], "cls": f.cls, "followed": f.followed}
        for f in conditioning.firings[-10:]
    ][::-1]

    today = datetime.now(timezone.utc).date()
    today_events = [e for e in events if e.ts.astimezone(timezone.utc).date() == today]
    current_session = events[-1].session_id if events else ""

    return {
        "generated_at": _iso(datetime.now(timezone.utc)),
        "feed": feed,
        "guards": guards,
        "conditioning": firings,
        "current_session": current_session[:8],
        "current_scope": pins.get(current_session, ""),
        "today": {
            "retrievals": len(today_events),
            "injected_tokens": sum(len(e.tool_response) for e in today_events)
            // _CHARS_PER_TOKEN,
            "misses": sum(1 for e in today_events if e.is_miss()),
        },
        "fanout_guardrail": FANOUT_GUARDRAIL,
    }


def _read_pins(path: Path) -> dict[str, str]:
    try:
        return load_pins(path)
    except Exception:  # noqa: BLE001 — a corrupt ledger must not take the feed down
        logger.warning("Unreadable pin ledger at %s", path)
        return {}


# ---------------------------------------------------------------------------
# Report snapshot — graph + transcript scan; cached by the web layer.
# ---------------------------------------------------------------------------


@dataclass
class _TimedTrace(TraceRow):
    """TraceRow plus the timestamp the trend needs; feeds build_pin_report as-is."""

    ts: str = ""
    tool: str = ""


@dataclass
class _GraphRead:
    traces: list[_TimedTrace] = field(default_factory=list)
    verdicts: list[VerdictRow] = field(default_factory=list)


def _read_graph(g) -> _GraphRead:
    """The pin_report read (eval/pins.py idiom) widened with ts/tool for the trend."""
    from gremlin_python.process.traversal import T

    read = _GraphRead()
    for row in (
        g.V()
        .has_label("Trace")
        .element_map("scope", "session_id", "returned_count", "injected_chars", "ts", "tool")
        .to_list()
    ):
        read.traces.append(
            _TimedTrace(
                vid=str(row.get(T.id) or row.get("id") or ""),
                scope=_first(row.get("scope")) or MAIN_SCOPE,
                session_id=_first(row.get("session_id")),
                injected_chars=_as_int(row.get("injected_chars")),
                returned_count=_as_int(row.get("returned_count")),
                ts=_first(row.get("ts")),
                tool=_first(row.get("tool")),
            )
        )
    for edge in g.V().has_label("Trace").out_e("RETURNS").element_map().to_list():
        used = edge.get("used")
        read.verdicts.append(
            VerdictRow(
                trace_vid=_edge_endpoint(edge, "OUT"),
                target_vid=_edge_endpoint(edge, "IN"),
                used=None if used is None else _as_bool(used),
            )
        )
    return read


def report_snapshot(
    g,
    project_dir: Path | None = None,
    traces_base: Path | None = None,
    guards_base: Path | None = None,
    conditioning_base: Path | None = None,
    pins_file: Path | None = None,
    since_days: int = 14,
    top: int = 8,
) -> dict:
    """Session- and lifetime-level view: verdicts, trends, routing signal, cost.

    `g` may be None (graph unreachable): the ledger-side reports still render
    and `graph_ok` states it — TAP-ONLY is an explicit condition, not a blank.
    """
    pins = _read_pins(pins_file or PINS_FILE)
    scopes = [MAIN_SCOPE, *available_scopes()]
    out: dict = {
        "generated_at": _iso(datetime.now(timezone.utc)),
        "graph_ok": g is not None,
        "scopes": {},
        "pins": None,
        "trend": [],
        "sessions": [],
        "pending": None,
        "disclosures": _disclosures(),
    }

    if g is not None:
        try:
            for scope in scopes:
                out["scopes"][scope] = _scope_dict(scope_report(g, scope=scope, top=top))
            read = _read_graph(g)
            out["pins"] = _pins_dict(
                build_pin_report(
                    list(read.traces), read.verdicts, pins, available_scopes(),
                    engaged=load_engaged(pins_file or PINS_FILE),
                )
            )
            out["trend"] = _daily_trend(read)
            out["sessions"] = _session_utilities(read, pins)
            out["pending"] = _pending(read, traces_base)
        except Exception:  # noqa: BLE001 — a graph hiccup degrades to tap-only, honestly
            logger.exception("Graph read failed; serving tap-only report")
            out["graph_ok"] = False

    # Ledger-side reports need no graph.
    out["gremlin"] = _gremlin_dict(gremlin_report(traces_base, guards_base))
    out["conditioning"] = _conditioning_dict(conditioning_report(conditioning_base, traces_base))
    since = date.today() - timedelta(days=since_days)
    try:
        out["cost"] = _cost_dict(
            cost_report(project_dir or REPO_ROOT, since, traces_base=traces_base), since
        )
    except Exception:  # noqa: BLE001 — transcripts move; cost must not take the page down
        logger.exception("Cost scan failed")
        out["cost"] = None
    return out


def _daily_trend(read: _GraphRead) -> list[dict]:
    """Per-day earned/wasted tokens over attributed verdicts — the waste trend.

    Rates mislead without absolutes (25% of ~731 tok vs 50% of ~43.6K differ
    ~60x in absolute waste), so each point carries both.
    """
    by_vid = {t.vid: t for t in read.traces}
    days: dict[str, dict[str, int]] = {}
    for verdict in read.verdicts:
        if verdict.used is None:
            continue
        trace = by_vid.get(verdict.trace_vid)
        if trace is None or not trace.ts:
            continue
        day = trace.ts[:10]
        bucket = days.setdefault(day, {"used": 0, "ignored": 0, "used_chars": 0, "ignored_chars": 0})
        if verdict.used:
            bucket["used"] += 1
            bucket["used_chars"] += trace.node_share
        else:
            bucket["ignored"] += 1
            bucket["ignored_chars"] += trace.node_share
    trend = []
    for day in sorted(days):
        b = days[day]
        priced = b["used_chars"] + b["ignored_chars"]
        trend.append(
            {
                "day": day,
                "attributed": b["used"] + b["ignored"],
                "used_pct": 100.0 * b["used"] / (b["used"] + b["ignored"]),
                "waste_pct": (100.0 * b["ignored_chars"] / priced) if priced else None,
                "earned_tokens": b["used_chars"] // _CHARS_PER_TOKEN,
                "wasted_tokens": b["ignored_chars"] // _CHARS_PER_TOKEN,
            }
        )
    return trend


def _session_utilities(read: _GraphRead, pins: dict[str, str]) -> list[dict]:
    """Per-session utility across all scopes, newest first, worst waste surfaced."""
    by_vid = {t.vid: t for t in read.traces}
    sessions: dict[str, dict] = {}
    for trace in read.traces:
        if not trace.session_id:
            continue
        row = sessions.setdefault(
            trace.session_id,
            {
                "session": trace.session_id[:8],
                "scope": pins.get(trace.session_id, trace.scope),
                "first_ts": trace.ts,
                "traces": 0,
                "returns": 0,
                "attributed": 0,
                "used": 0,
                "earned_tokens": 0,
                "wasted_tokens": 0,
                "recalls": [],
            },
        )
        row["traces"] += 1
        row["first_ts"] = min(row["first_ts"], trace.ts) if row["first_ts"] else trace.ts
        row["recalls"].append(
            {
                "vid": trace.vid,
                "tool": trace.tool,
                "ts": trace.ts,
                "fanout": trace.returned_count,
                "tokens": trace.injected_chars // _CHARS_PER_TOKEN,
                "attributed": 0,
                "used": 0,
            }
        )
    recall_index = {
        r["vid"]: r for s in sessions.values() for r in s["recalls"]
    }
    for verdict in read.verdicts:
        trace = by_vid.get(verdict.trace_vid)
        if trace is None or trace.session_id not in sessions:
            continue
        row = sessions[trace.session_id]
        row["returns"] += 1
        recall = recall_index.get(verdict.trace_vid)
        if verdict.used is not None:
            row["attributed"] += 1
            if recall:
                recall["attributed"] += 1
            share_tok = trace.node_share // _CHARS_PER_TOKEN
            if verdict.used:
                row["used"] += 1
                row["earned_tokens"] += share_tok
                if recall:
                    recall["used"] += 1
            else:
                row["wasted_tokens"] += share_tok
    ordered = sorted(sessions.values(), key=lambda r: r["first_ts"], reverse=True)
    for row in ordered:
        row["recalls"].sort(key=lambda r: r["ts"])
    return ordered[:20]


def _pending(read: _GraphRead, traces_base: Path | None) -> dict:
    """Tap events not yet landed as Trace nodes — the honesty badge's data.

    A trace can only land after its session distills; until then it exists in
    the tap alone. Pending can also be *stuck* (session distilled long ago but
    never synced) — the age says which.
    """
    landed_ids = {t.vid.rsplit(":", 1)[-1] for t in read.traces}
    pending: dict[str, dict] = {}
    for event in load_events(base=traces_base):
        if event.is_legacy() or event.trace_id() in landed_ids:
            continue
        row = pending.setdefault(
            event.session_id, {"session": event.session_id[:8], "events": 0, "oldest": _iso(event.ts)}
        )
        row["events"] += 1
        row["oldest"] = min(row["oldest"], _iso(event.ts))
    return {
        "sessions": sorted(pending.values(), key=lambda r: r["oldest"]),
        "total": sum(r["events"] for r in pending.values()),
    }


def _disclosures() -> dict:
    """The calibration plate: dials and blind spots, rendered verbatim.

    Dials are dials (docs/04) — display them as settings, never as metrics.
    """
    return {
        "standing": "layer 1 — instrumented, measuring. No utility claims before layer-2 counterfactuals (docs/04).",
        "dials": [
            "attribution: lexical, ≥2 terms and ≥30% overlap (crude by design; the grader is itself unvalidated — lab/002)",
            "pricing: 4 chars/token; even per-node share of each trace's rendered response",
            "cost proxy: weighted tokens — input 1.0 / cache-create 1.25 / cache-read 0.1 / output 5.0",
            f"waste target band: ≤{WASTE_TARGET_PCT:.0f}% is lab/007's prediction, not a measurement",
            f"fan-out guardrail: {FANOUT_GUARDRAIL} nodes (lab/007)",
            "pin signal floor: ≥10 attributed nodes per side",
        ],
        "surfaces": "priced: recall tools, memory_query (incl. rejections), bash_gremlin via tap. Blind: gremlin in script files (lab/008).",
        "attribution_lag": "verdicts exist only after a session distills and sync runs; the NOW column is cost-only by design.",
    }


# ---------------------------------------------------------------------------
# Dataclass → JSON dict projections.
# ---------------------------------------------------------------------------


def _scope_dict(report) -> dict:
    return {
        "scope": report.scope,
        "traces": report.traces,
        "sessions": report.sessions,
        "misses": report.misses,
        "by_tool": dict(report.by_tool),
        "returns": report.returns,
        "attributed": report.attributed,
        "used": report.used,
        "injected_tokens": report.injected_chars // _CHARS_PER_TOKEN,
        "earned_tokens": report.used_chars // _CHARS_PER_TOKEN,
        "wasted_tokens": report.ignored_chars // _CHARS_PER_TOKEN,
        "most_ignored": [
            {
                "vid": vid,
                "count": count,
                "wasted_tokens": wasted // _CHARS_PER_TOKEN,
                "text": text[:90],
            }
            for vid, count, wasted, text in report.most_ignored
        ],
    }


def _utility_dict(u) -> dict:
    return {
        "returns": u.returns,
        "attributed": u.attributed,
        "used": u.used,
        "used_pct": u.used_pct,
        "earned_tokens": u.used_chars // _CHARS_PER_TOKEN,
        "wasted_tokens": u.ignored_chars // _CHARS_PER_TOKEN,
    }


def _pins_dict(report) -> dict:
    return {
        "experts": [
            {
                "scope": e.scope,
                "pinned": _utility_dict(e.pinned),
                "consulted": _utility_dict(e.consulted),
                "ledger_only": e.ledger_only,
                "idle_spawns": e.idle_spawns,
                "pinned_sessions": len(e.pinned_sessions),
                "signal": e.signal(),
                "floor_met": "insufficient data" not in e.signal(),
            }
            for e in report.experts
        ]
    }


def _gremlin_dict(report) -> dict:
    return {
        "blocks": report.blocks,
        "passes": report.passes,
        "rescued": report.rescued,
        "repeat_blocks": report.repeat_blocks,
        # rescue rate with a zero denominator is undefined, not 0 — the
        # frontend renders the None as "no blocks yet".
        "rescue_rate": (report.rescued / report.blocks) if report.blocks else None,
        "memory_query": {
            "total": report.mq_total,
            "ok": report.mq_ok,
            "empty": report.mq_miss,
            "dialect_rejected": report.mq_dialect,
            "mutation_rejected": report.mq_mutation,
            "server_failed": report.mq_failed,
        },
        "bash": {"total": report.bash_total, "errored": report.bash_errored},
        "reuse": report.reuse,
    }


def _conditioning_dict(report) -> dict:
    by_class: dict[str, dict[str, int]] = {}
    for firing in report.firings:
        row = by_class.setdefault(firing.cls, {"firings": 0, "followed": 0})
        row["firings"] += 1
        row["followed"] += int(firing.followed)
    return {
        "classes": [
            {"cls": cls, **counts, "wallpaper": counts["firings"] - counts["followed"]}
            for cls, counts in sorted(by_class.items())
        ],
        "measured": bool(report.firings),
    }


def _cost_dict(report, since: date) -> dict:
    return {
        "since": since.isoformat(),
        "buckets": [
            {
                "name": name,
                "weighted": b.weighted,
                "calls": b.calls,
                "sessions": len(b.sessions),
            }
            for name, b in sorted(report.buckets.items(), key=lambda kv: -kv[1].weighted)
        ],
        "by_day": [
            {"day": day, "buckets": dict(report.by_day[day])} for day in sorted(report.by_day)
        ],
        "injection": [
            {
                "tool": tool,
                "calls": calls,
                "tokens": chars // _CHARS_PER_TOKEN,
            }
            for tool, (calls, chars) in sorted(
                report.injection.items(), key=lambda kv: -kv[1][1]
            )
        ],
    }


# ---------------------------------------------------------------------------
# Small value coercions (the graph returns lists or scalars per property).
# ---------------------------------------------------------------------------


def _first(value) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value) if value is not None else ""


def _as_int(value) -> int:
    if isinstance(value, list):
        value = value[0] if value else 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_bool(value) -> bool:
    if isinstance(value, list):
        value = value[0] if value else False
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _edge_endpoint(edge: dict, direction: str) -> str:
    from gremlin_python.process.traversal import Direction, T

    key = Direction.OUT if direction == "OUT" else Direction.IN
    node = edge.get(key) or edge.get(direction) or {}
    if isinstance(node, dict):
        return str(node.get(T.id) or node.get("id") or "")
    return str(node)


def to_json(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"))
