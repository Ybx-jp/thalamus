"""Gremlin query cost — the metric over the span tap, and the on-demand step profile.

Two channels, deliberately not one, because the cheap measurement and the detailed
one distort by different amounts and their milliseconds are not comparable.

**Span records** (always on, `substrate/spans.py`). Wall time for every traversal the
house issues, aggregated by traversal shape. This is a tracing record, not a
profiler: the question it answers is "which shape is this system spending its time
in", which is Dapper's question (Sigelman et al., Google TR 2010) rather than DCPI's.
Fleet-scale continuous profiling (Anderson et al., SOSP 1997; Ren et al., IEEE Micro
2010) is a different instrument whose load-bearing assumption is aggregation across
many machines — one operator on one box does not have it, so nothing here samples.

**Step profiles** (on demand, this module's `profile_query`). TinkerPop's own
`profile()` step asks the server for its per-step metrics: element and traverser
counts, time, and percent of duration. Its reference manual states the cost plainly —
"Profiling a Traversal will impede the Traversal's performance… durations are best
considered in relation to each other" — and this repo has measured the same class of
artifact on itself: `contract check` ran 10.29 / 10.35 / 10.36 s plain against
37.69 / 38.02 s under cProfile, a 3.67x slowdown that was briefly written up as
irreproducibility. Profilers are themselves biased measurements (Mytkowicz, Diwan,
Hauswirth & Sweeney, "Evaluating the Accuracy of Java Profilers", PLDI 2010). So a
step profile's milliseconds are read against each other and never against a span
row's.

What the report will and will not say:

- Every figure carries its **n**, and a distribution is reported as p50/p95/max
  rather than as a mean — the reporting contract of Hoefler & Belli, "Scientific
  Benchmarking of Parallel Computing Systems" (SC 2015) and Georges, Buytaert &
  Eeckhout, "Statistically Rigorous Java Performance Evaluation" (OOPSLA 2007). No
  confidence interval is computed: at these run counts on one machine it would lend
  unearned authority.
- **Element counts sit beside the milliseconds.** Counts are machine-independent and
  the durations are not. HELM draws the same line for inference cost, separating an
  *idealized* runtime that can be compared across systems from the per-request
  runtime a user actually experiences, "which cannot be used to compare models and
  model providers due to disparities in how these models are served" (Liang et al.,
  arXiv 2211.09110, TMLR 2023). Here the element count is the comparable half.
- **No threshold and no gate.** With one machine and small n, an automatic
  regression alarm is a false-alarm generator. This instrument reports; it never
  fails a build.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from thalamus.substrate.query import validate_query
from thalamus.substrate.spans import SpanRow, load_rows

# Repeats for a step profile. Deterministic input against a warm in-memory graph, so
# repetition is cheap; three is enough to show a spread and too few for an interval.
DEFAULT_REPEAT = 3

# TinkerPop reports step durations in nanoseconds over the wire.
_NS_PER_MS = 1_000_000


def percentile(samples: list[float], pct: float) -> float | None:
    """Nearest-rank percentile. Named because a reader has to know which one it is."""
    if not samples:
        return None
    ordered = sorted(samples)
    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


# ---------------------------------------------------------------------------
# Channel 1 — the span ledger.
# ---------------------------------------------------------------------------


@dataclass
class ShapeStat:
    """One traversal shape's cost, pooled across the rows that recorded it."""

    shape: tuple[str, ...]
    surface: str
    calls: int = 0
    total_ms: float = 0.0
    samples: list[float] = field(default_factory=list)
    origins: set[str] = field(default_factory=set)

    @property
    def shape_text(self) -> str:
        return ".".join(self.shape) or "(no steps)"

    @property
    def mean_ms(self) -> float:
        return self.total_ms / self.calls if self.calls else 0.0

    def p(self, pct: float) -> float | None:
        return percentile(self.samples, pct)

    @property
    def sampled(self) -> int:
        return len(self.samples)


@dataclass
class OriginStat:
    origin: str
    calls: int = 0
    total_ms: float = 0.0
    shapes: set[str] = field(default_factory=set)


@dataclass
class ProfileReport:
    rows: int = 0
    calls: int = 0
    total_ms: float = 0.0
    tap_ns: int = 0
    first: datetime | None = None
    last: datetime | None = None
    shapes: list[ShapeStat] = field(default_factory=list)
    origins: list[OriginStat] = field(default_factory=list)
    surfaces: dict[str, int] = field(default_factory=dict)

    @property
    def tap_overhead_pct(self) -> float | None:
        """The tap's own cost as a share of the traversal time it sits beside.

        Reported rather than asserted: an instrument that calls its overhead
        negligible without a ratio is making a claim it has not measured.
        """
        if not self.total_ms:
            return None
        return 100.0 * (self.tap_ns / _NS_PER_MS) / self.total_ms

    def render(self, top: int = 10) -> str:
        lines = ["Gremlin query cost — span records", ""]
        if not self.calls:
            return "\n".join(
                lines
                + [
                    "No spans recorded yet. Every traversal through `connect()` and every "
                    "memory_query is timed; the ledger fills as the system is used, and a "
                    "process flushes on exit. THALAMUS_PROFILE=0 disables recording.",
                ]
            )

        window = ""
        if self.first and self.last:
            window = f", {self.first:%Y-%m-%d} .. {self.last:%Y-%m-%d}"
        lines.append(
            f"{self.calls:,} traversal(s) over {self.total_ms / 1000:.1f}s, "
            f"from {self.rows:,} flushed bucket(s){window}"
        )
        surfaces = ", ".join(f"{name} {count:,}" for name, count in sorted(self.surfaces.items()))
        lines.append(f"Surfaces: {surfaces}")
        lines.append("")

        lines.append("By origin — measurements are only comparable within one:")
        for origin in self.origins:
            share = 100.0 * origin.total_ms / self.total_ms if self.total_ms else 0.0
            lines.append(
                f"  {origin.origin:<22} {origin.calls:>8,} call(s)  "
                f"{origin.total_ms / 1000:>7.1f}s  {share:>5.1f}%  "
                f"{len(origin.shapes)} shape(s)"
            )
        lines.append("")

        lines.append(f"Costliest traversal shapes (top {top} by total time):")
        lines.append(
            f"  {'calls':>8}  {'p50':>8}  {'p95':>8}  {'max':>8}  {'total':>8}  shape"
        )
        for stat in self.shapes[:top]:
            truncated = "*" if stat.sampled < stat.calls else " "
            lines.append(
                f"  {stat.calls:>8,}  {_ms(stat.p(50))}{truncated} {_ms(stat.p(95))}  "
                f"{_ms(stat.p(100))}  {stat.total_ms / 1000:>7.1f}s  {stat.shape_text}"
            )
        if any(s.sampled < s.calls for s in self.shapes[:top]):
            lines.append(
                "  * percentiles over a bounded sample of that shape's calls, not all of them"
            )
        lines.append("")

        overhead = self.tap_overhead_pct
        if overhead is not None:
            lines.append(
                f"Tap overhead: {self.tap_ns / _NS_PER_MS:.1f}ms measured across "
                f"{self.calls:,} recordings — {overhead:.3f}% of the traversal time it "
                f"sits beside."
            )
        lines.append(
            "Wall time on one machine, unrepeated: read a shape's spread, not a "
            "single figure, and never as a comparison against another machine."
        )
        return "\n".join(lines)


def _ms(value: float | None) -> str:
    """A duration in a fixed 8-column field, unit attached so no header has to carry it."""
    if value is None:
        return f"{'—':>8}"
    if value >= 1000:
        return f"{value / 1000:>6.2f}s "
    return f"{value:>6.1f}ms"


def profile_report(
    base: Path | None = None, rows: list[SpanRow] | None = None, top: int = 10
) -> ProfileReport:
    """Pool the span ledger into per-shape and per-origin cost."""
    rows = load_rows(base) if rows is None else rows
    report = ProfileReport(rows=len(rows))
    shapes: dict[tuple[str, str], ShapeStat] = {}
    origins: dict[str, OriginStat] = {}
    for row in rows:
        report.calls += row.calls
        report.total_ms += row.total_ms
        report.tap_ns += row.tap_ns
        report.first = row.ts if report.first is None else min(report.first, row.ts)
        report.last = row.ts if report.last is None else max(report.last, row.ts)
        report.surfaces[row.surface] = report.surfaces.get(row.surface, 0) + row.calls

        key = (row.surface, row.shape_text)
        stat = shapes.get(key)
        if stat is None:
            stat = shapes[key] = ShapeStat(shape=row.shape, surface=row.surface)
        stat.calls += row.calls
        stat.total_ms += row.total_ms
        stat.samples.extend(row.samples)
        if row.origin:
            stat.origins.add(row.origin)

        origin = origins.get(row.origin)
        if origin is None:
            origin = origins[row.origin] = OriginStat(origin=row.origin or "(unlabelled)")
        origin.calls += row.calls
        origin.total_ms += row.total_ms
        origin.shapes.add(row.shape_text)

    report.shapes = sorted(shapes.values(), key=lambda s: -s.total_ms)
    report.origins = sorted(origins.values(), key=lambda o: -o.total_ms)
    return report


# ---------------------------------------------------------------------------
# Channel 2 — the on-demand step profile.
# ---------------------------------------------------------------------------


@dataclass
class StepMetric:
    name: str
    elements: int
    traversers: int
    ms: float
    pct: float
    depth: int = 0


@dataclass
class QueryProfile:
    name: str
    query: str
    wall_ms: list[float] = field(default_factory=list)
    server_ms: float = 0.0
    steps: list[StepMetric] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def elements(self) -> int:
        """Total elements the top-level steps touched — the machine-independent half."""
        return sum(step.elements for step in self.steps if step.depth == 0)


def profile_query(
    url: str, query: str, repeat: int = DEFAULT_REPEAT, name: str = "", warmup: int = 1
) -> QueryProfile:
    """Run one read-only traversal under TinkerPop's `profile()` and report its steps.

    The read-only floor is `substrate.query.validate_query` — the same guard the
    `memory_query` surface enforces, so nothing profileable here is unrunnable there.
    Deliberately submits its own client rather than going through `run_query`: that
    renderer clips values at 400 characters, which would truncate the metrics map.

    Runs are not recorded to the span ledger. A profiled traversal is a distorted one
    (see the module docstring), and mixing it into the always-on record would poison
    the numbers the tap exists to produce.
    """
    from gremlin_python.driver.client import Client

    profile = QueryProfile(name=name or _short(query), query=query)
    text = query.strip().rstrip(";")
    rejection = validate_query(text)
    if rejection:
        profile.error = rejection
        return profile
    if not text.endswith(".profile()"):
        text = f"{text}.profile()"

    client = Client(url, "g")
    try:
        rows = None
        for run in range(warmup + max(1, repeat)):
            started = time.perf_counter()
            rows = client.submit(text).all().result()
            elapsed = (time.perf_counter() - started) * 1000.0
            if run >= warmup:
                profile.wall_ms.append(elapsed)
        metrics = rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001 — a bad query is a reported result
        profile.error = str(exc).splitlines()[0][:300]
        return profile
    finally:
        client.close()

    if isinstance(metrics, dict):
        profile.server_ms = float(metrics.get("dur", 0)) / _NS_PER_MS
        profile.steps = _flatten(metrics.get("metrics") or [])
    return profile


def _flatten(metrics: list, depth: int = 0) -> list[StepMetric]:
    steps: list[StepMetric] = []
    for entry in metrics:
        if not isinstance(entry, dict):
            continue
        counts = entry.get("counts") or {}
        annotations = entry.get("annotations") or {}
        steps.append(
            StepMetric(
                name=str(entry.get("name", "?")),
                elements=int(counts.get("elementCount", 0) or 0),
                traversers=int(counts.get("traverserCount", 0) or 0),
                ms=float(entry.get("dur", 0) or 0) / _NS_PER_MS,
                pct=float(annotations.get("percentDur", 0) or 0),
                depth=depth,
            )
        )
        steps.extend(_flatten(entry.get("metrics") or [], depth + 1))
    return steps


def render_query_profile(profile: QueryProfile) -> str:
    lines = [profile.name]
    query = _short(profile.query, 160)
    if query != profile.name:
        lines.append(f"  {query}")
    if not profile.ok:
        lines.append(f"  FAILED — {profile.error}")
        return "\n".join(lines)

    n = len(profile.wall_ms)
    spread = "/".join(f"{ms:.1f}" for ms in profile.wall_ms)
    lines.append(
        f"  round trip: {spread} ms (n={n}, raw observations, one machine) · "
        f"server-side total {profile.server_ms:.2f} ms · "
        f"{profile.elements:,} element(s) touched"
    )
    if not profile.elements:
        # Usually a template with placeholder ids. Its milliseconds are a reading of
        # an empty traversal, which is a fact about the corpus and not about the graph.
        lines.append("  touched nothing — the timing here measures an empty traversal")
    lines.append(f"  {'elements':>9} {'travs':>7} {'ms':>9} {'%dur':>6}  step")
    for step in profile.steps:
        indent = "  " * step.depth
        lines.append(
            f"  {step.elements:>9,} {step.traversers:>7,} {step.ms:>9.3f} "
            f"{step.pct:>5.1f}%  {indent}{step.name}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The corpus — the gremlin-lang recipes the skills already store.
# ---------------------------------------------------------------------------


def lang_corpus(paths: list[Path] | None = None) -> list[tuple[str, str]]:
    """(name, query) for every gremlin-lang recipe in the two stores.

    Reuses `gremlin._dated_blocks`, which already reads both the fenced blocks of
    RECIPES.md and the indented ones of the recall-strategy skill — the corpus is
    the store, so a recipe promoted for reuse is a query this instrument prices
    from then on, with no second list to keep in step.
    """
    from thalamus.eval.gremlin import RECALL_STRATEGY_PATH, RECIPES_PATH, _dated_blocks

    corpus: list[tuple[str, str]] = []
    seen: set[str] = set()
    for path in paths or [RECIPES_PATH, RECALL_STRATEGY_PATH]:
        if not path.is_file():
            continue
        used: dict[str, int] = {}
        for name, code, _validated in _dated_blocks(path.read_text()):
            query = " ".join(code.split())
            if not query.startswith("g.") or query in seen:
                continue
            seen.add(query)
            # Several recipes share one section heading — recall-strategy keeps all
            # of its query recipes under a single `##`. Number them so a slow one is
            # nameable rather than one of nine rows reading the same.
            label = name or _short(query)
            used[label] = used.get(label, 0) + 1
            if used[label] > 1:
                label = f"{label} #{used[label]}"
            corpus.append((label, query))
    return corpus


def profile_corpus(
    url: str, repeat: int = DEFAULT_REPEAT, paths: list[Path] | None = None
) -> list[QueryProfile]:
    return [
        profile_query(url, query, repeat=repeat, name=name) for name, query in lang_corpus(paths)
    ]


def render_corpus(profiles: list[QueryProfile]) -> str:
    if not profiles:
        return (
            "No gremlin-lang recipes to profile. The corpus is the stored recipes that "
            "are written as gremlin-lang; python recipes run through the span tap "
            "instead (`thalamus eval recipes`, then `thalamus eval profile`)."
        )
    ran = [p for p in profiles if p.ok]
    # A stored block that reads like a query but is written in gremlin-python is not a
    # member of this corpus; it is not a failure either. Counted and named, never
    # silently dropped — a corpus that quietly shrinks reads as full coverage.
    wrong_dialect = [p for p in profiles if not p.ok and "gremlin-python dialect" in p.error]
    failed = [p for p in profiles if not p.ok and p not in wrong_dialect]
    ordered = sorted(ran, key=lambda p: -(p.server_ms))

    headline = (
        f"Gremlin corpus step profile — {len(ran)} ran, "
        f"n={len(ran[0].wall_ms) if ran else 0} timed run(s) each after one warm-up"
    )
    if wrong_dialect:
        headline += (
            f"; {len(wrong_dialect)} stored block(s) skipped as gremlin-python, "
            "which this surface does not speak"
        )
    if failed:
        headline += f"; {len(failed)} failed"
    lines = [
        headline,
        "",
        "Profiling impedes the traversal it measures (TinkerPop reference manual); "
        "read these against each other, never against a span-ledger figure.",
        "",
    ]
    for profile in ordered + failed:
        lines.append(render_query_profile(profile))
        lines.append("")
    for profile in wrong_dialect:
        lines.append(f"skipped (gremlin-python): {profile.name}")
    return "\n".join(lines).rstrip()


def _short(text: str, limit: int = 70) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def to_json(report: ProfileReport, top: int = 8) -> dict:
    """The pulse projection — the same numbers, no rendering opinions."""
    return {
        "calls": report.calls,
        "total_ms": round(report.total_ms, 1),
        "rows": report.rows,
        "first": report.first.isoformat().replace("+00:00", "Z") if report.first else None,
        "last": report.last.isoformat().replace("+00:00", "Z") if report.last else None,
        "tap_overhead_pct": report.tap_overhead_pct,
        "surfaces": report.surfaces,
        "origins": [
            {
                "origin": o.origin,
                "calls": o.calls,
                "total_ms": round(o.total_ms, 1),
                "shapes": len(o.shapes),
            }
            for o in report.origins[:top]
        ],
        "shapes": [
            {
                "shape": s.shape_text,
                "surface": s.surface,
                "calls": s.calls,
                "sampled": s.sampled,
                "p50": s.p(50),
                "p95": s.p(95),
                "max": s.p(100),
                "total_ms": round(s.total_ms, 1),
            }
            for s in report.shapes[:top]
        ],
    }
