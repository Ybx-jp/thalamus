"""Calibrating the used-vs-ignored judge against its own null (docs/04 layer 1).

A used-rate on its own is not a result. lab/032 showed why: judging a retrieval's
nodes against a *different* session's output window scores ~59% used against 62.9%
for the real one, so the shipped rate is roughly 59 points of shared project
vocabulary plus 4 points of retrieval utility, with nothing separating them. Any
number quoted without that floor beside it reads as five times more signal than it
has — and the "used% above ~50" target the project once shipped sat *below* chance.

So this module makes the floor a standing instrument rather than a one-off script:

    used% (null p̄₀ [CI], κ)

where κ = (p − p̄₀) / (1 − p̄₀) is the chance-corrected agreement — the share of the
*available* headroom the judge actually captures.

Two things lab/032's draft did not do, and this does:

- **The null carries its own interval.** Its cross-project 5.0% came from one
  rotation against one pool. One draw is not an estimate, and a null without an
  interval cannot say whether a 4-point gap is real.
- **Rotations are stratified on window length.** The judge's used% moves 51.7% →
  69.7% between short and long windows on identical inputs, because term membership
  is tested anywhere in an unbounded window. An unstratified rotation therefore
  confounds the null with session length: it would measure the length mismatch it
  introduced, not the vocabulary floor it is meant to isolate.

Everything here is computed from retained data — the tap, the archive, and a named
graph snapshot — so a published figure regenerates from `(snapshot, seed)` and
nothing else. Judges are compared, never silently swapped: `JUDGES` in
`attribution.py` holds the variants, `shipped` is what the graph's stored verdicts
mean, and adopting another is a measured decision.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from gremlin_python.process.graph_traversal import GraphTraversalSource, __

from thalamus.eval.attribution import (
    JUDGES,
    Judge,
    OutputWindow,
    attribute_prepared,
    node_terms,
    output_window,
    prepare,
)
from thalamus.eval.sync import _retained_transcript
from thalamus.contract.ontology import vid

# Length strata for the rotation. Quartiles of the window's character length: a
# rotation must swap in a window of comparable size, or the null measures the size
# change. Four buckets is the coarsest split that separates lab/032's measured
# 20-100k / 100k+ break without leaving strata too thin to sample from.
STRATA = 4


@dataclass
class Case:
    """One retrieval, with everything needed to re-judge it from scratch."""

    trace_id: str
    session_id: str
    scope: str
    tool: str
    ts: datetime
    nodes: dict[str, str]
    window: OutputWindow
    # What `eval sync` stored for these nodes, for the reconstruction-fidelity gate.
    stored: dict[str, bool] = field(default_factory=dict)
    stratum: int = 0

    @property
    def window_chars(self) -> int:
        return len(self.window.text())


@dataclass
class JudgeResult:
    """What one judge scored, and what the same judge scores on rotated windows."""

    judge: str
    verdicts: dict[str, dict[str, bool]] = field(default_factory=dict)  # trace -> node -> used
    used: int = 0
    total: int = 0
    null_rates: list[float] = field(default_factory=list)
    discordance: float = 0.0  # share of node-verdicts that flip under rotation
    # Cases with no cross-session partner inside their length stratum. Surfaced
    # rather than absorbed: a thin stratum silently shrinks the null's corpus,
    # and a null computed over a different set than the rate is not that rate's null.
    unpartnered: int = 0

    @property
    def rate(self) -> float:
        return self.used / self.total if self.total else 0.0

    @property
    def null_mean(self) -> float:
        return sum(self.null_rates) / len(self.null_rates) if self.null_rates else 0.0

    @property
    def kappa(self) -> float:
        return kappa(self.rate, self.null_mean)

    @property
    def null_ci(self) -> tuple[float, float]:
        return percentile_ci(self.null_rates)


def kappa(rate: float, null_rate: float) -> float:
    """Share of the headroom above chance that the judge actually captures.

    Returns 0.0 when the null is at ceiling: with no headroom there is nothing to
    capture, and the alternative (dividing by zero, or reporting the raw gap) would
    turn a degenerate case into a large-looking number.
    """
    headroom = 1.0 - null_rate
    return (rate - null_rate) / headroom if headroom > 1e-9 else 0.0


def percentile_ci(values: list[float], alpha: float = 0.05) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    ordered = sorted(values)
    lo = ordered[max(0, int(len(ordered) * alpha / 2) - 1)]
    hi = ordered[min(len(ordered) - 1, int(len(ordered) * (1 - alpha / 2)))]
    return (lo, hi)


def load_cases(
    g: GraphTraversalSource, *, scope: str = "main"
) -> tuple[list[Case], dict[str, int]]:
    """Rebuild the judgeable corpus from a graph (live or served snapshot) + the archive.

    Read from the **graph**, not the tap, for two reasons. The graph is what a
    snapshot pins, so a calibration run is addressable to a named state and
    reproducible from it; and its Trace vertices are the same population
    `eval report` counts, so a rate computed here and a rate printed there share a
    denominator instead of differing by an unexplained filter.

    Cross-scope returns are kept. A main-scope retrieval that returns a homelab
    Session is not a foreign trace — it is the consultation path working, and it is
    also where the topic detector is most exposed (63% within-project vs 5% across),
    so dropping it would remove exactly the cases the calibration exists to price.

    Returns the cases and a census of what could not be rebuilt and why. A case can
    fail on a missing transcript or an empty window, and those are different claims
    about coverage — counted separately, never folded into "ignored".
    """
    census: dict[str, int] = defaultdict(int)

    rows = (
        g.V()
        .has_label("Trace")
        .has("scope", scope)
        .out_e("RETURNS")
        .project("trace", "session_id", "ts", "tool", "node", "used", "text")
        .by(__.out_v().id_())
        .by(__.out_v().coalesce(__.values("session_id"), __.constant("")))
        .by(__.out_v().coalesce(__.values("ts"), __.constant("")))
        .by(__.out_v().coalesce(__.values("tool"), __.constant("")))
        .by(__.in_v().id_())
        .by(__.coalesce(__.values("used"), __.constant("unjudged")))
        .by(
            __.in_v().coalesce(
                __.values("summary"), __.values("description"), __.values("title"),
                __.constant(""),
            )
        )
        .to_list()
    )

    grouped: dict[str, dict] = {}
    for row in rows:
        census["returns"] += 1
        if row["used"] == "unjudged":
            census["unjudged"] += 1
            continue
        if not row["text"]:
            census["node_without_text"] += 1
            continue
        entry = grouped.setdefault(
            row["trace"],
            {
                "session_id": row["session_id"],
                "ts": row["ts"],
                "tool": row["tool"],
                "nodes": {},
                "stored": {},
            },
        )
        entry["nodes"][row["node"]] = row["text"]
        entry["stored"][row["node"]] = bool(row["used"])

    transcripts: dict[str, bytes | None] = {}
    cases: list[Case] = []
    for trace_id, entry in grouped.items():
        census["traces"] += 1
        session_id = entry["session_id"]
        if not session_id or not entry["ts"]:
            census["trace_without_session"] += 1
            continue
        if session_id not in transcripts:
            transcripts[session_id] = _retained_transcript(g, vid("Session", session_id, scope))
        transcript = transcripts[session_id]
        if transcript is None:
            census["no_transcript"] += 1
            continue

        ts = datetime.fromisoformat(str(entry["ts"]).replace("Z", "+00:00"))
        window = output_window(transcript, ts)
        if not window.text().strip():
            census["empty_window"] += 1
            continue

        cases.append(
            Case(
                trace_id=trace_id,
                session_id=session_id,
                scope=scope,
                tool=entry["tool"],
                ts=ts,
                nodes=entry["nodes"],
                window=window,
                stored=entry["stored"],
            )
        )
        census["cases"] += 1
        census["verdicts"] += len(entry["nodes"])

    _assign_strata(cases)
    return cases, dict(census)


def fidelity(cases: list[Case], result: JudgeResult) -> tuple[int, int]:
    """Does re-judging reproduce the verdicts `eval sync` stored? (matched, total)

    The gate lab/032 set for itself, kept as a standing check: a calibration whose
    replay disagrees with the production path is measuring its own reconstruction,
    not the instrument. Only meaningful for the `shipped` judge — a variant is
    *supposed* to disagree.
    """
    matched = total = 0
    for case in cases:
        for node_id, stored in case.stored.items():
            replayed = result.verdicts.get(case.trace_id, {}).get(node_id)
            if replayed is None:
                continue
            total += 1
            matched += int(replayed == stored)
    return matched, total


def _assign_strata(cases: list[Case]) -> None:
    """Bucket cases into equal-count window-length strata."""
    if not cases:
        return
    ordered = sorted(cases, key=lambda c: c.window_chars)
    size = max(1, len(ordered) // STRATA)
    for index, case in enumerate(ordered):
        case.stratum = min(STRATA - 1, index // size)


class _Prepared:
    """Lowercased text and token set per (window, judge), computed once.

    Calibration judges each window `rotations` times — 200 × 384 cases here —
    and both the window tokenisation and the node term extraction are pure
    functions of their inputs. Without this the run is dominated by re-deriving
    the same sets, and a calibration nobody waits for is a calibration nobody
    runs.
    """

    def __init__(self, judge: Judge):
        self.judge = judge
        self._windows: dict[int, tuple[str, set[str]]] = {}
        self._terms: dict[str, list[str]] = {}

    def window(self, window: OutputWindow) -> tuple[str, set[str]]:
        key = id(window)
        if key not in self._windows:
            self._windows[key] = prepare(
                window.text(
                    turns=self.judge.turns, prose=self.judge.prose, tools=self.judge.tools
                )
            )
        return self._windows[key]

    def terms(self, nodes: dict[str, str]) -> dict[str, list[str]]:
        for node_id, content in nodes.items():
            if node_id not in self._terms:
                self._terms[node_id] = node_terms(content)
        return self._terms

    def judge_against(self, nodes: dict[str, str], window: OutputWindow):
        lower, tokens = self.window(window)
        return attribute_prepared(nodes, lower, tokens, self.terms(nodes))


def score(cases: list[Case], judge: Judge, prepared: "_Prepared | None" = None) -> JudgeResult:
    """Judge every case against its own output window — the real rate."""
    prepared = prepared or _Prepared(judge)
    result = JudgeResult(judge=judge.name)
    for case in cases:
        verdicts = {
            v.node_id: v.used for v in prepared.judge_against(case.nodes, case.window)
        }
        result.verdicts[case.trace_id] = verdicts
        result.used += sum(1 for used in verdicts.values() if used)
        result.total += len(verdicts)
    return result


def rotate(
    cases: list[Case],
    judge: Judge,
    result: JudgeResult,
    *,
    rotations: int,
    seed: int,
    prepared: "_Prepared | None" = None,
) -> JudgeResult:
    """Re-judge every case against another session's window, `rotations` times.

    The swap is constrained twice: a different **session** (or the vocabulary is
    shared by construction and the null is not a null) and the same **length
    stratum** (or the null measures the length change). A case with no eligible
    partner is skipped rather than paired loosely, and the skip is visible in the
    per-rotation denominator.
    """
    prepared = prepared or _Prepared(judge)
    rng = random.Random(seed)
    by_stratum: dict[int, list[Case]] = defaultdict(list)
    for case in cases:
        by_stratum[case.stratum].append(case)

    unpartnered = {
        case.trace_id
        for case in cases
        if not any(c.session_id != case.session_id for c in by_stratum[case.stratum])
    }
    result.unpartnered = len(unpartnered)
    flips = 0
    comparable = 0
    for turn in range(rotations):
        used = total = 0
        for case in cases:
            pool = [c for c in by_stratum[case.stratum] if c.session_id != case.session_id]
            if not pool:
                continue
            other = pool[rng.randrange(len(pool))]
            for verdict in prepared.judge_against(case.nodes, other.window):
                used += int(verdict.used)
                total += 1
                if turn == 0:
                    real = result.verdicts.get(case.trace_id, {}).get(verdict.node_id)
                    if real is not None:
                        comparable += 1
                        flips += int(real != verdict.used)
        if total:
            result.null_rates.append(used / total)
    result.discordance = flips / comparable if comparable else 0.0
    return result


def calibrate(
    cases: list[Case], *, judges: list[str] | None = None, rotations: int = 200, seed: int = 20260730
) -> dict[str, JudgeResult]:
    """Score every judge variant and its null on one corpus, one seed."""
    names = judges or list(JUDGES)
    results = {}
    for name in names:
        judge = JUDGES[name]
        prepared = _Prepared(judge)
        result = score(cases, judge, prepared)
        results[name] = rotate(
            cases, judge, result, rotations=rotations, seed=seed, prepared=prepared
        )
    return results


def cluster_bootstrap(
    cases: list[Case], result: JudgeResult, *, draws: int = 2000, seed: int = 20260730
) -> tuple[float, float]:
    """Resample **sessions**, not verdicts, for the real rate's interval.

    Verdicts inside one session are not independent draws: they share an output
    window, a topic and an operator. The measured ICC on this corpus is 0.264 with
    a design effect near 4, so a verdict-level interval is roughly half as wide as
    the truth (lab/034). Sessions are the primary sampling unit.
    """
    rng = random.Random(seed)
    by_session: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for case in cases:
        verdicts = result.verdicts.get(case.trace_id, {})
        by_session[case.session_id].append(
            (sum(1 for u in verdicts.values() if u), len(verdicts))
        )
    sessions = list(by_session)
    if len(sessions) < 2:
        return (0.0, 1.0)

    rates = []
    for _ in range(draws):
        used = total = 0
        for _ in sessions:
            for u, t in by_session[sessions[rng.randrange(len(sessions))]]:
                used += u
                total += t
        if total:
            rates.append(used / total)
    return percentile_ci(rates)


def by_dimension(
    cases: list[Case], result: JudgeResult, key
) -> dict[str, tuple[int, int]]:
    """Used/total split by any per-case dimension (tool, stratum, node kind)."""
    buckets: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for case in cases:
        verdicts = result.verdicts.get(case.trace_id, {})
        for node_id, used in verdicts.items():
            bucket = buckets[str(key(case, node_id))]
            bucket[0] += int(used)
            bucket[1] += 1
    return {name: (u, t) for name, (u, t) in buckets.items()}


def node_kind(node_id: str) -> str:
    parts = node_id.split(":")
    return parts[-2] if len(parts) >= 2 else "unknown"


__all__ = [
    "Case",
    "JudgeResult",
    "by_dimension",
    "calibrate",
    "cluster_bootstrap",
    "fidelity",
    "kappa",
    "load_cases",
    "node_kind",
    "percentile_ci",
    "rotate",
    "score",
]
