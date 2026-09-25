"""Pulse view-models — JSON projections of measurements the system already keeps.

Read-only by construction: every number here comes from the trace tap, the
guard/conditioning/pin ledgers, the harness transcripts, or the landed Trace
verdicts in the graph. No new telemetry, no writes, no panel-local metrics —
one priced surface; the dashboard renders it, it never
mints its own.

The states the frontend renders are produced here, not styled there — the page
prints what the payload says and never decides whether something is stuck or stale:
- `health.needs_you` → the act-now items, each with the command that fixes it;
  `health.checks` → one tile per subsystem, its state word composed here;
- `pending` → tap events whose session has not landed a Trace, split at
  `STUCK_AFTER_HOURS` since the session's newest event into in-flight and stuck
  (a trace can only land after its session distills — sync.py);
- `build` → the commit this process loaded at start, and how far the checkout
  has moved since;
- cost buckets the transcript scan cannot see carry a `blind` chip, never a zero;
- query cost is wall time from the span tap, so it carries its own measured tap
  overhead and never a mean without the spread beside it.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from thalamus.contract.manifest import available_scopes
from thalamus.eval.conditioning import conditioning_report
from thalamus.eval.cost import PINS_FILE, cost_report, load_pins
from thalamus.eval.gremlin import gremlin_report
from thalamus.eval.profile import profile_report, to_json as profile_json
from thalamus.eval.pins import TraceRow, VerdictRow
from thalamus.eval.report import scope_report
from thalamus.eval.traces import load_events

logger = logging.getLogger(__name__)

MAIN_SCOPE = "main"
_CHARS_PER_TOKEN = 4

# The fan-out guardrail: recalls returning more nodes than this measured
# 28-40% use vs 66-80% for 3-5 node recalls.
FANOUT_GUARDRAIL = 15

# A session whose newest tap event is older than this, with no Trace landed, is
# stuck rather than in flight. A dial, disclosed on the plate: argued from the
# 2026-09-24 gap, when four pending sessions were hours old and fourteen were
# 2.4-46 days old with nothing between.
STUCK_AFTER_HOURS = 48

# Harness session ids are UUIDs (Claude Code, codex and Cursor alike). Anything
# else in the tap is a fixture that leaked into the operator's ledger
# (`test-123`), and counting it as a stuck session would ask him to fix nothing.
_SESSION_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

# Where the fixes live. Commands are printed for the operator to run; pulse
# never runs them.
SYNC_COMMAND = "thalamus eval sync --write"
RESTART_COMMAND = "systemctl --user restart thalamus-pulse"
GRAPH_COMMAND = "docker compose up -d"
LOG_COMMAND = "journalctl --user -u thalamus-pulse -n 50"

# The paths whose commits change what this page shows: pulse itself and the eval
# reports it projects.
_BUILD_PATHS = ("src/thalamus/pulse", "src/thalamus/eval")

REPO_ROOT = Path(__file__).resolve().parents[3]


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Live snapshot — ledger files only, cheap enough to poll.
# ---------------------------------------------------------------------------


def live_snapshot(
    traces_base: Path | None = None,
    pins_file: Path | None = None,
    limit: int = 40,
) -> dict:
    """The turn-level feed: cost and activity only, never utility.

    A per-turn used% would be fabricated — verdicts exist only after the
    session distills and sync attributes (eval-methodology consultation
    a9bb9f26049a4176). This snapshot therefore carries injection cost,
    fan-out, and event class. The guard and reminder ledgers are read by
    report_snapshot as rates with their n: a feed of guard `pass` rows says
    nothing (consultation c5dcecc212ba4f77).
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
                "tokens": event.injected_chars() // _CHARS_PER_TOKEN,
                "miss": event.is_miss(),
                "rejected": event.is_rejected(),
            }
        )
    feed.reverse()  # newest first

    return {
        "generated_at": _iso(datetime.now(timezone.utc)),
        "feed": _collapse_quiet(feed),
        "fanout_guardrail": FANOUT_GUARDRAIL,
    }


def _collapse_quiet(feed: list[dict]) -> list[dict]:
    """Fold each consecutive run of one tool's zero-injection calls into one row.

    A reflex check that served nothing costs nothing and returns nothing, and a
    run of them pushed every recall that did inject off the eight rows the page
    shows. The folded row keeps the run's newest time, its count and every scope
    in it, and carries `summary` — the words the page prints instead of nodes
    and tokens. A run of one is folded too, so a quiet row reads one way.
    """
    out: list[dict] = []
    for row in feed:
        quiet = row["tokens"] == 0 and row["fanout"] == 0 and not row["rejected"]
        if not quiet:
            out.append(row)
            continue
        last = out[-1] if out else None
        if last is not None and last.get("collapsed") and last["tool"] == row["tool"]:
            last["collapsed"] += 1
            if row["scope"] not in last["scopes"]:
                last["scopes"].append(row["scope"])
        else:
            last = {**row, "collapsed": 1, "scopes": [row["scope"]]}
            out.append(last)
        noun = "check" if row["tool"].startswith("reflex_") else "call"
        last["summary"] = f"{_plural(last['collapsed'], noun)}, nothing served"
    return out


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
    """TraceRow plus the timestamp and tool the trend and session rows need."""

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
    profiles_base: Path | None = None,
    projects_base: Path | None = None,
    since_days: int = 14,
    top: int = 8,
    build: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Session- and lifetime-level view: health, verdicts, cost.

    The pins comparison is not projected: until each side has its own permutation
    null the pair is not comparable (consultation c5dcecc212ba4f77), and the page
    carries it as dated copy rather than as a live number.

    `g` may be None (graph unreachable): the ledger-side reports still render
    and `graph_ok` states it — TAP-ONLY is an explicit condition, not a blank.

    `projects_base` is the transcript root the cost scan walks. It exists as a
    parameter for the same reason the ledger bases do: left unset, `cost_report`
    resolves the operator's own `~/.claude/projects`, so a caller that means to
    report on a fixture reads his archive instead and its numbers are a function
    of what he ran this week.

    `build` is what `record_build` returned when the process started; None reports
    no build. `now` is a parameter for the same reason the bases are: the stuck
    line is an age, and a test reading the wall clock would change verdict as its
    fixture aged.
    """
    now = now or datetime.now(timezone.utc)
    pins = _read_pins(pins_file or PINS_FILE)
    scopes = [MAIN_SCOPE, *available_scopes()]
    events = load_events(base=traces_base)
    out: dict = {
        "generated_at": _iso(now),
        "graph_ok": g is not None,
        "scopes": {},
        "trend": [],
        "sessions": [],
        "pending": None,
        "build": _build_dict(build),
        "disclosures": _disclosures(),
    }

    if g is not None:
        try:
            for scope in scopes:
                out["scopes"][scope] = _scope_dict(scope_report(g, scope=scope, top=top))
            read = _read_graph(g)
            out["trend"] = _daily_trend(read)
            out["sessions"] = _session_utilities(read, pins)
            out["pending"] = _pending(read, events, now)
        except Exception:  # noqa: BLE001 — a graph hiccup degrades to tap-only, honestly
            logger.exception("Graph read failed; serving tap-only report")
            out["graph_ok"] = False

    # Ledger-side reports need no graph.
    out["gremlin"] = _gremlin_dict(gremlin_report(traces_base, guards_base))
    out["query_cost"] = profile_json(profile_report(base=profiles_base, top=top), top=top)
    out["conditioning"] = _conditioning_dict(conditioning_report(conditioning_base, traces_base))
    since = date.today() - timedelta(days=since_days)
    try:
        out["cost"] = _cost_dict(
            cost_report(
                project_dir or REPO_ROOT, since,
                traces_base=traces_base, projects_base=projects_base,
            ),
            since,
        )
    except Exception:  # noqa: BLE001 — transcripts move; cost must not take the page down
        logger.exception("Cost scan failed")
        out["cost"] = None
    out["health"] = _health(out, events, since_days, now)
    return out


def _daily_trend(read: _GraphRead) -> list[dict]:
    """Per-day earned/wasted tokens over attributed verdicts — the waste trend.

    Rates mislead without absolutes (25% of ~731 tok wastes ~183 and 50% of
    ~43.6K wastes ~21,800 — ~119x apart), so each point carries both.
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


def _pending(read: _GraphRead, events: list, now: datetime) -> dict:
    """Tap events not yet landed as Trace nodes, split into in flight and stuck.

    A trace can only land after its session distills; until then it exists in the
    tap alone, and a session hours old is simply in flight. One whose newest tap
    event is more than `STUCK_AFTER_HOURS` old has had every chance to distill and
    sync, so it is stuck. The line is measured from the *newest* event, not the
    oldest: a long session is not stuck for having started two days ago.
    """
    landed_ids = {t.vid.rsplit(":", 1)[-1] for t in read.traces}
    pending: dict[str, dict] = {}
    for event in events:
        if event.is_legacy() or event.trace_id() in landed_ids:
            continue
        if not _SESSION_ID.fullmatch(event.session_id):
            continue
        ts = _iso(event.ts)
        row = pending.setdefault(
            event.session_id,
            {"session": event.session_id[:8], "events": 0, "oldest": ts, "newest": ts},
        )
        row["events"] += 1
        row["oldest"] = min(row["oldest"], ts)
        row["newest"] = max(row["newest"], ts)
    line = now - timedelta(hours=STUCK_AFTER_HOURS)
    stuck = [r for r in pending.values() if _parse_iso(r["newest"]) < line]
    in_flight = [r for r in pending.values() if _parse_iso(r["newest"]) >= line]
    return {
        "stuck_after_hours": STUCK_AFTER_HOURS,
        "stuck": _pending_group(stuck),
        "in_flight": _pending_group(in_flight),
    }


def _pending_group(rows: list[dict]) -> dict:
    return {
        "sessions": sorted(rows, key=lambda r: r["oldest"]),
        "events": sum(r["events"] for r in rows),
    }


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Build — what this process loaded, against what the checkout holds now.
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str | None:
    """Stripped stdout of a successful `git -C root <args>`, else None."""
    try:
        proc = subprocess.run(
            ("git", "-C", str(root), *args), capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _checkout_root() -> Path | None:
    """The checkout this module was imported from, or None.

    The toplevel must hold *this* file: a wheel installed into a virtualenv that
    sits inside some checkout would otherwise report that checkout's HEAD as the
    code pulse is running.
    """
    here = Path(__file__).resolve()
    top = _git(here.parent, "rev-parse", "--show-toplevel")
    if not top:
        return None
    root = Path(top)
    return root if (root / "src/thalamus/pulse/metrics.py").resolve() == here else None


def record_build(root: Path | None = None) -> dict:
    """The commit this process is running and when it started. Call once, at boot.

    The Python is loaded once and frozen; the checkout under it moves. Recording
    HEAD here is what lets a later report say how far behind the process is.
    """
    root = root if root is not None else _checkout_root()
    sha = _git(root, "rev-parse", "HEAD") if root is not None else None
    committed = _git(root, "show", "-s", "--format=%cI", sha) if root and sha else None
    return {
        "root": str(root) if sha else None,
        "sha": sha,
        "started_at": _iso(datetime.now(timezone.utc)),
        "committed_at": committed,
    }


def _build_dict(build: dict | None) -> dict:
    """The recorded build plus how far the checkout has moved since, read now.

    `behind` is None when there is no checkout to be behind (a wheel install, or
    no build recorded) — unknown, never 0. `touching` counts the commits among
    those that change pulse or the eval reports it projects.
    """
    build = build or {}
    sha, root = build.get("sha"), build.get("root")
    out = {
        "sha": sha[:7] if sha else None,
        "started_at": build.get("started_at"),
        "committed_at": build.get("committed_at"),
        "branch": None,
        "behind": None,
        "touching": None,
    }
    if not (sha and root):
        return out
    behind = _git(Path(root), "rev-list", "--count", f"{sha}..HEAD")
    touching = _git(Path(root), "rev-list", "--count", f"{sha}..HEAD", "--", *_BUILD_PATHS)
    out["branch"] = _git(Path(root), "rev-parse", "--abbrev-ref", "HEAD")
    out["behind"] = int(behind) if behind and behind.isdigit() else None
    out["touching"] = int(touching) if touching and touching.isdigit() else None
    return out


# ---------------------------------------------------------------------------
# Health — the Status page's first two sections, composed here.
# ---------------------------------------------------------------------------


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _hhmm(ts: datetime) -> str:
    """Server-local wall time. Pulse and the operator share a machine."""
    return ts.astimezone().strftime("%H:%M")


def _health(out: dict, events: list, since_days: int, now: datetime) -> dict:
    """Act-now items and check tiles, from the report already assembled.

    State words mean one thing each: `failed` is act now and always has a
    needs-you item of its own; `in_flight` is moving and needs nothing; `ok` is
    checked and fine; `count` is a number with no grounded threshold, so it never
    turns red whatever it reads.
    """
    checks = [
        _graph_check(out["graph_ok"], now),
        _tap_check(events, now),
        _sync_check(out.get("pending")),
        _cost_check(out.get("cost"), since_days),
        _memory_query_check(out.get("gremlin")),
        _guard_check(out.get("gremlin")),
    ]
    needs_you = [item for c in checks if (item := c.pop("needs_you", None))]
    stuck = (out.get("pending") or {}).get("stuck") or {}
    if stuck.get("sessions"):
        needs_you.append(_stuck_item(stuck, now))
    build = out.get("build") or {}
    if build.get("behind"):
        needs_you.append(_stale_build_item(build))
    return {"needs_you": needs_you, "checks": checks}


def _check(name: str, state: str, word: str, lines: list[str], short: str, **extra) -> dict:
    """One tile. `short` is the one-line body the phone layout has room for."""
    return {"name": name, "state": state, "word": word, "lines": lines, "short": short, **extra}


def _graph_check(graph_ok: bool, now: datetime) -> dict:
    if graph_ok:
        return _check("Graph", "ok", "OK", ["reachable", f"verdicts as of {_hhmm(now)}"],
                      "reachable")
    return _check(
        "Graph", "failed", "FAILED", ["unreachable", "tap-only: no new verdicts"], "unreachable",
        needs_you={
            "kind": "failed", "word": "FAILED",
            "title": "The graph is unreachable",
            "detail": "Pulse is serving tap-only data: no new verdicts and no sync state.\n"
                      "The tap keeps recording, so nothing is lost while it is down.",
            "command": GRAPH_COMMAND,
        },
    )


def _tap_check(events: list, now: datetime) -> dict:
    if not events:
        return _check("Tap", "count", "COUNT", ["no events recorded", "fills as memory tools run"],
                      "no events yet")
    today = now.astimezone().date()
    n_today = sum(1 for e in events if e.ts.astimezone().date() == today)
    last = _hhmm(max(e.ts for e in events))
    return _check("Tap", "ok", "OK", [f"last event {last}", f"{n_today} recalls today"],
                  f"{last} · {n_today} today")


def _sync_check(pending: dict | None) -> dict:
    """In flight is what the tile reports; stuck has a needs-you item of its own."""
    if pending is None:
        return _check("Sync", "count", "NOT READ", ["needs the graph", "to tell landed from not"],
                      "needs the graph")
    hours = pending["stuck_after_hours"]
    flight, stuck = pending["in_flight"], pending["stuck"]
    n_flight, n_stuck = len(flight["sessions"]), len(stuck["sessions"])
    if n_flight:
        second = f"+ {n_stuck} stuck, above" if n_stuck else f"all younger than {hours} h"
        return _check(
            "Sync", "in_flight", "IN FLIGHT",
            [f"{_plural(n_flight, 'session')} · {_plural(flight['events'], 'event')}", second],
            f"{_plural(n_flight, 'session')} · < {hours} h",
        )
    if n_stuck:
        return _check("Sync", "failed", "STUCK",
                      [f"{_plural(n_stuck, 'session')} stuck", "none in flight"],
                      f"{n_stuck} stuck")
    return _check("Sync", "ok", "OK", ["every tap event landed", "nothing in flight"],
                  "all landed")


def _cost_check(cost: dict | None, since_days: int) -> dict:
    if cost is None:
        return _check(
            "Cost scan", "failed", "FAILED", ["scan failed", "see the server log"], "scan failed",
            needs_you={
                "kind": "failed", "word": "FAILED",
                "title": "The cost scan failed",
                "detail": "The transcript scan raised, so the cost section is empty.\n"
                          "The traceback is in the server log.",
                "command": LOG_COMMAND,
            },
        )
    extract_blind = any(b["name"] == "extract" and b.get("blind") for b in cost["buckets"])
    second = "extract not measured" if extract_blind else "every bucket read"
    return _check("Cost scan", "ok", "OK", [f"{since_days} days read", second], second)


def _memory_query_check(gremlin: dict | None) -> dict:
    mq = (gremlin or {}).get("memory_query") or {}
    total, failed = mq.get("total", 0), mq.get("server_failed", 0)
    return _check(
        "memory_query", "count", "COUNT",
        [f"{_plural(total, 'call')} · {failed} failed",
         f"{mq.get('dialect_rejected', 0)} dialect rejects"],
        f"{failed} failed of {total}",
    )


def _guard_check(gremlin: dict | None) -> dict:
    g = gremlin or {}
    blocks = g.get("blocks", 0)
    seen = blocks + g.get("passes", 0)
    rate = f" ({100 * blocks / seen:.1f}%)" if seen else ""
    return _check(
        "Gremlin guard", "count", "COUNT",
        [f"{blocks} blocks in {seen}{rate}", f"{g.get('rescued', 0)} rescued in-session"],
        f"{blocks} of {seen} blocked",
    )


def _stuck_item(stuck: dict, now: datetime) -> dict:
    sessions = stuck["sessions"]
    oldest = _parse_iso(min(r["oldest"] for r in sessions))
    days = (now - oldest).days
    return {
        "kind": "stuck", "word": "STUCK",
        "title": f"{_plural(len(sessions), 'session')} never synced",
        "detail": f"{stuck['events']} recalls have no verdict. Oldest from "
                  f"{oldest.astimezone().date().isoformat()} — {_plural(days, 'day')}.\n"
                  f"Older than {STUCK_AFTER_HOURS} h with tap events but no Trace = stuck, "
                  "not lagging.",
        "command": SYNC_COMMAND,
    }


def _stale_build_item(build: dict) -> dict:
    committed = build.get("committed_at")
    since = _parse_iso(committed).astimezone().date().isoformat() if committed else build["sha"]
    branch = build.get("branch")
    against = branch if branch and branch != "HEAD" else "this checkout's HEAD"
    count = f"{_plural(build['behind'], 'commit')} behind {against}"
    if build.get("touching") is not None:
        count += f"; {build['touching']} of them change pulse or the eval code it reads"
    return {
        "kind": "stale_build", "word": "STALE BUILD",
        "title": f"Pulse is serving code from {since}",
        "detail": f"{count}.\nThe server loaded its code at start and is not running them.",
        "command": RESTART_COMMAND,
    }


def _disclosures() -> dict:
    """The footer plate: dials and blind spots, rendered verbatim.

    Dials are dials — display them as settings, never as metrics.
    """
    return {
        "dials": [
            f"{_CHARS_PER_TOKEN} chars/token",
            "weighted-token ratios",
            f"{FANOUT_GUARDRAIL}-node guardrail",
            f"{STUCK_AFTER_HOURS} h stuck line",
        ],
        "blind": ["gremlin in script files", "extraction runs"],
        "note": (
            "Retrieval quality (used vs ignored) lives on How it works, with its caveat "
            "attached — it is not an ops signal."
        ),
        "cost_proxy": (
            "weighted-token proxy — API price ratios (input 1 · cache write 1.25 · "
            "cache read 0.1 · output 5). Not dollars."
        ),
        "query_cost": (
            "wall time per traversal shape, one machine, unrepeated — p50/p95/max, "
            "never a bare mean; the tap reports its own measured overhead. Step-level "
            "cost is on demand only (`thalamus eval profile --query`), because "
            "profiling distorts the traversal it measures."
        ),
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


# Buckets the transcript scan reads as zero because it cannot see them, not
# because nothing ran. Neither is probed yet: extraction runs in a temp-dir
# subprocess the scan likely does not walk, and a consult subagent may share its
# caller's transcript (consultation c5dcecc212ba4f77).
_EXTRACT_BLIND = {"chip": "NOT MEASURED", "why": "distillation runs outside the scan"}
_EXPERT_BLIND = {"chip": "0 · UNVERIFIED", "why": "consult subagents may share the caller’s transcript"}


def _blind_spot(name: str, weighted: int) -> dict | None:
    if weighted:
        return None
    if name == "extract":
        return _EXTRACT_BLIND
    if name.startswith("expert:"):
        return _EXPERT_BLIND
    return None


def _cost_dict(report, since: date) -> dict:
    return {
        "since": since.isoformat(),
        "buckets": [
            {
                "name": name,
                "weighted": b.weighted,
                "calls": b.calls,
                "sessions": len(b.sessions),
                "blind": _blind_spot(name, b.weighted),
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
