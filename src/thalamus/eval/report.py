"""Read the eval loop's layer-1 verdicts back out of the graph.

Aggregates Trace nodes and RETURNS verdicts into the per-scope numbers docs/04 asks
for: how often retrieval fires, how often it comes back empty, and how much of what it
returns the agent actually uses. The "most ignored" list is the seed of layer 3 —
nodes repeatedly retrieved-but-ignored are the decay candidates — surfaced here as a
report long before anything acts on it.

Discipline (docs/04): these numbers say "instrumented, measuring". They do not say the
memory helps. That claim needs layer 2's counterfactual arms, which do not exist yet.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from gremlin_python.process.graph_traversal import GraphTraversalSource
from gremlin_python.process.traversal import Direction, T

from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.eval.rankers import UNKNOWN as RANKER_UNKNOWN

# Rendered chars per token — the same rough dial as eval/cost.py.
_CHARS_PER_TOKEN = 4


def parse_window_bound(
    value: str | datetime | None, *, end_of_day: bool = False
) -> datetime | None:
    """Accept an ISO date or datetime as a UTC-aware window bound.

    A bare date used as the upper bound covers that whole day. `--until 2026-07-20`
    meaning "up to 00:00 on the 20th" would silently drop a day of traces, and a
    window that quietly loses its last day is the kind of thing that survives as a
    number nobody can reproduce.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        stamp = value
    else:
        text = str(value)
        stamp = datetime.fromisoformat(text)
        if end_of_day and len(text.strip()) == 10:
            stamp = stamp.replace(hour=23, minute=59, second=59, microsecond=999999)
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp


def _trace_ts(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        stamp = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp


@dataclass
class ScopeReport:
    scope: str
    since: datetime | None = None
    until: datetime | None = None
    # Ranker fingerprints observed in the window, by trace count. A window spanning
    # more than one is not a measurement of either ranker — the report says so rather
    # than averaging across a dial change (lab/029).
    by_ranker: Counter = field(default_factory=Counter)
    # Traces in scope that fell outside the window, and those with no usable ts.
    out_of_window: int = 0
    undated: int = 0
    traces: int = 0
    sessions: int = 0
    misses: int = 0
    by_tool: Counter = field(default_factory=Counter)
    returns: int = 0
    attributed: int = 0
    used: int = 0
    # Injection pricing (docs/04 layer 1b). A returned node's share of its trace's
    # rendered response is injected_chars / returned_count — even, crude, honest.
    injected_chars: int = 0
    used_chars: int = 0
    ignored_chars: int = 0
    # (vid, times_ignored, wasted_chars, text) — ranked by wasted chars.
    most_ignored: list[tuple[str, int, int, str]] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"Eval report — scope `{self.scope}` (layer 1: instrumented, measuring)",
        ]
        if self.since or self.until:
            window = (
                f"{self.since.date() if self.since else 'start'} → "
                f"{self.until.date() if self.until else 'now'}"
            )
            skipped = f"{self.out_of_window} outside" if self.out_of_window else ""
            if self.undated:
                skipped = f"{skipped}, " if skipped else ""
                skipped += f"{self.undated} undated (excluded)"
            lines.append(f"  window: {window}" + (f"; {skipped}" if skipped else ""))
        lines.append(
            f"  retrievals: {self.traces} across {self.sessions} session(s); "
            f"{self.misses} returned nothing"
        )

        if self.by_ranker:
            rankers = " · ".join(
                f"{fingerprint} {count}" for fingerprint, count in self.by_ranker.most_common()
            )
            lines.append(f"  ranker: {rankers}")
            served = [f for f in self.by_ranker if f != RANKER_UNKNOWN]
            if len(served) > 1:
                lines.append(
                    "    ⚠ this window straddles a ranker change — the numbers below "
                    "average across it and measure neither setting. Narrow the window."
                )
            elif not served:
                lines.append(
                    "    ⚠ no trace here records which ranker served it (all predate the "
                    "ranker ledger), so these numbers cannot be attributed to a setting."
                )
        if self.by_tool:
            tools = " · ".join(f"{tool} {count}" for tool, count in self.by_tool.most_common())
            lines.append(f"  by tool: {tools}")

        if self.returns:
            unattributed = self.returns - self.attributed
            if self.attributed:
                ignored = self.attributed - self.used
                pct = 100.0 * self.used / self.attributed
                lines.append(
                    f"  returned nodes: {self.returns}; attributed {self.attributed}: "
                    f"{self.used} used ({pct:.0f}%), {ignored} ignored"
                )
            else:
                lines.append(f"  returned nodes: {self.returns}; none attributed yet")
            if unattributed:
                lines.append(
                    f"  {unattributed} unattributed (no retained transcript at sync "
                    "time, or no agent output after the retrieval — never counted "
                    "as ignored)"
                )
        else:
            lines.append("  returned nodes: 0")

        if self.injected_chars:
            line = (
                f"  injection cost: ~{self.injected_chars // _CHARS_PER_TOKEN:,} tokens "
                "rendered into context"
            )
            priced = self.used_chars + self.ignored_chars
            if priced:
                wasted_pct = 100.0 * self.ignored_chars / priced
                line += (
                    f"; of the attributed share, ~{self.used_chars // _CHARS_PER_TOKEN:,} "
                    f"earned (used) vs ~{self.ignored_chars // _CHARS_PER_TOKEN:,} wasted "
                    f"({wasted_pct:.0f}%)"
                )
            lines.append(line)
            # The bare percentage above is a point estimate with no interval and no
            # chance correction, and both matter more than it does: sessions are the
            # sampling unit (design effect ~2.5, so the honest interval is ~3.5x the
            # verdict-level one), and the judge calls ~59% of *unrelated* tokens used.
            # Printing it without this line is how "50% wasted" travelled into docs
            # and a skill as if it were a measurement.
            lines.append(
                "    ^ point estimate only — no interval, no chance correction. "
                "See experiments/002 for the session-clustered interval "
                "(+/-7pp at this corpus size) and what the figure becomes once "
                "corrected against the permuted null."
            )

        if self.most_ignored:
            lines.append(
                "  retrieved-but-ignored, by wasted tokens (layer-3 decay candidates):"
            )
            for node_id, count, wasted, text in self.most_ignored:
                label = f" — {text[:70]}" if text else ""
                lines.append(
                    f"    {count}x ~{wasted // _CHARS_PER_TOKEN:>5,} tok  `{node_id}`{label}"
                )

        if not self.traces:
            lines.append("  (no traces landed — run `thalamus eval sync --write` first)")
        return "\n".join(lines)


def scope_report(
    g: GraphTraversalSource,
    scope: str = MAIN_SCOPE,
    top: int = 5,
    since: str | datetime | None = None,
    until: str | datetime | None = None,
) -> ScopeReport:
    """Layer-1 numbers for one scope, optionally windowed by trace timestamp.

    The window exists so a dial change can be measured against its own before and
    after. Without it every number is a lifetime aggregate, which is why lab/007's
    fan-out prediction could not be checked after the fact even though every trace
    it needed was already in the graph (lab/029). `until` is inclusive of the whole
    day when given as a bare date.

    Windowing excludes traces with no parseable `ts` rather than assuming they fall
    inside — an undated trace is unattributable to a period, and the count is
    reported so the exclusion is visible.
    """
    since_ts = parse_window_bound(since)
    until_ts = parse_window_bound(until, end_of_day=True)
    report = ScopeReport(scope=scope, since=since_ts, until=until_ts)
    windowed = since_ts is not None or until_ts is not None

    traces = (
        g.V()
        .has_label("Trace")
        .has("scope", scope)
        .element_map("tool", "session_id", "returned_count", "injected_chars", "ts", "ranker_config")
        .to_list()
    )
    session_ids = set()
    # Trace vid -> each returned node's share of the rendered response. Traces synced
    # before layer 1b carry no injected_chars; they price as zero, never as a guess.
    node_share: dict[str, int] = {}
    in_window: set[str] = set()
    for row in traces:
        trace_vid = str(row.get(T.id) or row.get("id") or "")
        if windowed:
            stamp = _trace_ts(_first(row.get("ts")))
            if stamp is None:
                report.undated += 1
                continue
            if (since_ts and stamp < since_ts) or (until_ts and stamp > until_ts):
                report.out_of_window += 1
                continue
        if trace_vid:
            in_window.add(trace_vid)
        report.traces += 1
        report.by_ranker[_first(row.get("ranker_config")) or RANKER_UNKNOWN] += 1
        tool = _first(row.get("tool"))
        if tool:
            report.by_tool[tool] += 1
        session_ids.add(_first(row.get("session_id")))
        returned_count = _as_int(row.get("returned_count"))
        if returned_count == 0:
            report.misses += 1
        injected = _as_int(row.get("injected_chars"))
        report.injected_chars += injected
        if trace_vid and returned_count:
            node_share[trace_vid] = injected // returned_count
    report.sessions = len(session_ids - {""})

    edges = (
        g.V()
        .has_label("Trace")
        .has("scope", scope)
        .out_e("RETURNS")
        .element_map()
        .to_list()
    )
    ignored_counter: Counter = Counter()
    wasted_chars: Counter = Counter()
    for edge in edges:
        if windowed and _edge_source(edge) not in in_window:
            continue
        report.returns += 1
        used = edge.get("used")
        if used is None:
            continue
        report.attributed += 1
        share = node_share.get(_edge_source(edge), 0)
        if _as_bool(used):
            report.used += 1
            report.used_chars += share
        else:
            target = _edge_target(edge)
            ignored_counter[target] += 1
            wasted_chars[target] += share
            report.ignored_chars += share

    ranked = sorted(
        wasted_chars.items(), key=lambda kv: (-kv[1], -ignored_counter[kv[0]], kv[0])
    )
    report.most_ignored = [
        (node_id, ignored_counter[node_id], wasted, _node_text(g, node_id))
        for node_id, wasted in ranked[:top]
        if node_id
    ]
    return report


def _edge_source(edge: dict) -> str:
    source = edge.get(Direction.OUT) or edge.get("OUT") or {}
    if isinstance(source, dict):
        return str(source.get(T.id) or source.get("id") or "")
    return str(source)


def _edge_target(edge: dict) -> str:
    target = edge.get(Direction.IN) or edge.get("IN") or {}
    if isinstance(target, dict):
        return str(target.get(T.id) or target.get("id") or "")
    return str(target)


def _node_text(g: GraphTraversalSource, node_id: str) -> str:
    try:
        rows = g.V(node_id).value_map("summary", "description", "title").limit(1).to_list()
    except Exception:
        return ""
    if not rows:
        return "(no longer in graph)"
    for key in ("title", "summary", "description"):
        value = rows[0].get(key)
        if isinstance(value, list) and value:
            return str(value[0])
    return ""


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


def _first(value) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value) if value is not None else ""
