"""Pin-quality report — the routing signal (docs/02, docs/04).

Pinning replaces a learned router with a tier-0 operator decision, and the eval loop
grades that decision instead of trusting it: sustained low-utility retrieval under a
pin means either the pin or the expert needs work, and this report is how the data
says which (docs/02). For each expert scope it renders two utilities side by side:

- **pinned** — verdicts on traces from sessions pinned to the expert (its own
  episodic service), broken out per session so one mis-pinned session stands out
  from a scope-wide problem;
- **consulted** — verdicts on the expert's nodes served into *other* scopes' traces
  (consultation answers and cross-scope knowledge recall).

Reading the pair: pinned low while consulted high → the pin was wrong (the expert's
knowledge earns its keep when other sessions ask for it); both low → the expert
needs work. Both numbers are attribution, not utility claims — the counterfactual
bar (docs/00 principle 4) still applies, and the signal line is floor-gated rather
than asserted from thin samples.

Prior work: cost-utility frontiers for agent memory are BudgetMem's frame (arXiv
2602.06025) — but there the frontier is a *control input* to a trained budget-tier
router, where this report deliberately stops at attribution, keeping routing an
operator decision (the legibility trade docs/02 accepts). Per-session granularity
is the AgentOps session-level metric layer (arXiv 2411.05285). Instantiation, not
novelty (docs/11 §2b).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gremlin_python.process.graph_traversal import GraphTraversalSource
from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.eval.report import (
    _as_bool,
    _as_int,
    _edge_source,
    _edge_target,
    _first,
)
from gremlin_python.process.traversal import T

# Rendered chars per token — the same rough dial as eval/cost.py and eval/report.py.
_CHARS_PER_TOKEN = 4

# Signal dials — arbitrary, here to be pressure-tested (same discipline as the
# attribution thresholds in docs/04). Below the floor the report says "insufficient
# data" instead of pretending a verdict.
SIGNAL_FLOOR = 10  # attributed nodes required on each side before a signal renders
LOW_USED_PCT = 50.0


@dataclass
class TraceRow:
    """One Trace node, as the pin report needs it."""

    vid: str
    scope: str
    session_id: str
    injected_chars: int = 0
    returned_count: int = 0

    @property
    def node_share(self) -> int:
        return self.injected_chars // self.returned_count if self.returned_count else 0


@dataclass
class VerdictRow:
    """One RETURNS edge: which trace served which node, and the layer-1 verdict."""

    trace_vid: str
    target_vid: str
    used: bool | None = None  # None = not yet attributed


@dataclass
class Utility:
    returns: int = 0
    attributed: int = 0
    used: int = 0
    used_chars: int = 0
    ignored_chars: int = 0

    @property
    def used_pct(self) -> float:
        return 100.0 * self.used / self.attributed if self.attributed else 0.0

    def add(self, used: bool, share: int) -> None:
        self.attributed += 1
        if used:
            self.used += 1
            self.used_chars += share
        else:
            self.ignored_chars += share

    def line(self) -> str:
        if not self.attributed:
            return f"{self.returns} returned, none attributed"
        return (
            f"{self.attributed} attributed, {self.used} used ({self.used_pct:.0f}%), "
            f"~{self.used_chars // _CHARS_PER_TOKEN:,} tok earned / "
            f"~{self.ignored_chars // _CHARS_PER_TOKEN:,} wasted"
        )


@dataclass
class SessionUtility(Utility):
    session_id: str = ""
    traces: int = 0


@dataclass
class ExpertPins:
    scope: str
    pinned_sessions: list[SessionUtility] = field(default_factory=list)
    pinned: Utility = field(default_factory=Utility)
    consulted: Utility = field(default_factory=Utility)
    # Denominator split (semantics vetted: scope:main:exchange:63b647977a624b85).
    # Spawn records alone conflate roster bring-up with routing decisions, so
    # ledger_only is gated on engagement — a session with no user prompt had no
    # measurement opportunity and carries no routing signal. Both counts stay
    # attribution, never utility claims (docs/04).
    ledger_only: int = 0  # engaged in the ledger, no traces landed
    idle_spawns: int = 0  # spawned, never engaged — roster churn, disclosed not judged

    def signal(self) -> str:
        if self.pinned.attributed < SIGNAL_FLOOR or self.consulted.attributed < SIGNAL_FLOOR:
            return (
                f"insufficient data (needs ≥{SIGNAL_FLOOR} attributed on each side; "
                f"pinned {self.pinned.attributed}, consulted {self.consulted.attributed})"
            )
        pinned_low = self.pinned.used_pct < LOW_USED_PCT
        consulted_low = self.consulted.used_pct < LOW_USED_PCT
        if pinned_low and not consulted_low:
            return (
                "pin quality — the knowledge earns its keep when consulted, "
                "but pinned sessions ignore what they retrieve (docs/02: the pin was wrong)"
            )
        if pinned_low and consulted_low:
            return "expert needs work — low used% both pinned and consulted (docs/02)"
        return "healthy — pinned retrievals are being used"


@dataclass
class PinReport:
    experts: list[ExpertPins] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            "Pin-quality report — routing signal (attribution, not utility claims; docs/04)",
            f"  dials: signal floor {SIGNAL_FLOOR} attributed/side · low = used% < {LOW_USED_PCT:.0f}",
        ]
        if not self.experts:
            lines.append("  no expert scopes found (manifests, ledger, and traces are all empty)")
            return "\n".join(lines)
        for expert in self.experts:
            lines.append("")
            lines.append(f"expert `{expert.scope}`")
            if expert.pinned_sessions:
                note = f" (+{expert.ledger_only} engaged with none landed)" if expert.ledger_only else ""
                lines.append(f"  pinned sessions with traces: {len(expert.pinned_sessions)}{note}")
                for row in expert.pinned_sessions:
                    lines.append(
                        f"    {row.session_id[:8]:<8s}  {row.traces} retrieval(s) · {row.line()}"
                    )
                lines.append(f"  pinned:    {expert.pinned.line()}")
            elif expert.ledger_only:
                lines.append(
                    f"  pinned sessions with traces: 0 (+{expert.ledger_only} engaged "
                    "with none landed — engaged but never retrieved, itself a signal)"
                )
            else:
                lines.append("  pinned sessions with traces: 0")
            if expert.idle_spawns:
                lines.append(
                    f"  excluded: {expert.idle_spawns} idle spawn(s) — ledger entries with "
                    "no user prompt (roster bring-up, not a routing decision)"
                )
            lines.append(f"  consulted: {expert.consulted.line()} (served into other scopes)")
            lines.append(f"  signal: {expert.signal()}")
        return "\n".join(lines)


def node_scope(vid: str) -> str:
    """The scope segment of a vertex id, '' for global nodes (Artifact)."""
    parts = vid.split(":", 2)
    return parts[1] if len(parts) == 3 and parts[0] == "scope" else ""


def build_pin_report(
    traces: list[TraceRow],
    verdicts: list[VerdictRow],
    pins: dict[str, str],
    experts: list[str] | None = None,
    engaged: set[str] | None = None,
) -> PinReport:
    """Pure aggregation — the graph/ledger readers feed this; tests exercise it directly."""
    by_vid = {t.vid: t for t in traces}
    scopes: set[str] = {e for e in (experts or []) if e and e != MAIN_SCOPE}
    scopes |= {t.scope for t in traces if t.scope and t.scope != MAIN_SCOPE}
    scopes |= {s for s in pins.values() if s and s != MAIN_SCOPE}
    scopes |= {
        node_scope(v.target_vid)
        for v in verdicts
        if node_scope(v.target_vid) not in ("", MAIN_SCOPE)
    }

    report = PinReport()
    for scope in sorted(scopes):
        expert = ExpertPins(scope=scope)
        sessions: dict[str, SessionUtility] = {}
        for trace in traces:
            if trace.scope == scope and trace.session_id:
                row = sessions.setdefault(trace.session_id, SessionUtility(session_id=trace.session_id))
                row.traces += 1
        for verdict in verdicts:
            trace = by_vid.get(verdict.trace_vid)
            if trace is None:
                continue
            if trace.scope == scope:
                expert.pinned.returns += 1
                if trace.session_id in sessions:
                    sessions[trace.session_id].returns += 1
                if verdict.used is not None:
                    expert.pinned.add(verdict.used, trace.node_share)
                    if trace.session_id in sessions:
                        sessions[trace.session_id].add(verdict.used, trace.node_share)
            elif node_scope(verdict.target_vid) == scope:
                expert.consulted.returns += 1
                if verdict.used is not None:
                    expert.consulted.add(verdict.used, trace.node_share)
        expert.pinned_sessions = sorted(
            sessions.values(), key=lambda r: (-r.ignored_chars, r.session_id)
        )
        traced_sessions = set(sessions)
        # engaged=None means the ledger has no engagement records (pre-2026-07-19
        # rows, or a caller without the ledger) — every spawn counts, old behavior.
        for sid, s in pins.items():
            if s != scope or sid in traced_sessions:
                continue
            if engaged is None or sid in engaged:
                expert.ledger_only += 1
            else:
                expert.idle_spawns += 1
        report.experts.append(expert)
    return report


def pin_report(
    g: GraphTraversalSource,
    pins: dict[str, str],
    experts: list[str] | None = None,
    engaged: set[str] | None = None,
) -> PinReport:
    """Read every scope's traces and verdicts and build the routing signal."""
    trace_rows = []
    for row in g.V().has_label("Trace").element_map(
        "scope", "session_id", "returned_count", "injected_chars"
    ).to_list():
        trace_rows.append(
            TraceRow(
                vid=str(row.get(T.id) or row.get("id") or ""),
                scope=_first(row.get("scope")) or MAIN_SCOPE,
                session_id=_first(row.get("session_id")),
                injected_chars=_as_int(row.get("injected_chars")),
                returned_count=_as_int(row.get("returned_count")),
            )
        )
    verdict_rows = []
    for edge in g.V().has_label("Trace").out_e("RETURNS").element_map().to_list():
        used = edge.get("used")
        verdict_rows.append(
            VerdictRow(
                trace_vid=_edge_source(edge),
                target_vid=_edge_target(edge),
                used=None if used is None else _as_bool(used),
            )
        )
    return build_pin_report(trace_rows, verdict_rows, pins, experts, engaged)
