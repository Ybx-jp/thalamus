"""Span records over gremlin traversals — what each traversal shape costs in wall time.

The tap, not the metric. This module times traversals at the two seams the house owns
(`writer.connect`'s remote connection and `query.run_query`'s client) and appends what
it measured to ~/.thalamus/profiles/<YYYY-MM>.jsonl. Reading those rows into a report
is `eval/profile.py`'s job, the same split the trace tap already has: the hook records,
`eval/traces.py` interprets.

Sits in `substrate/` because that is all it knows — a traversal, a duration, and the
step names in between. It imports nothing from the layers above, which is what lets
`writer.py` call it.

**Aggregated in-process, one flush per process.** A row per traversal would be the
raw record and is also the reason not to write one: a single `contract check` issues
thousands, and a ledger that grows faster than the thing it measures is its own
problem. Rows are keyed by (surface, traversal shape) — the unit a reader can act on,
since a slow shape is a query to rewrite and a slow individual call is usually the
machine. Each row carries its call count, its total, and up to `_MAX_SAMPLES` of the
individual durations, so the reader computes a distribution rather than trusting a
mean.

**The tap measures its own cost.** Every `record` call is itself timed and the total
is written to the row as `tap_ns`, so the overhead is reported as a ratio against the
traversal time it sits beside rather than asserted to be negligible.

What it does not see: a traversal built on a `DriverRemoteConnection` or `Client` the
caller constructed itself instead of reaching for `connect()` / `run_query` — ad-hoc
Bash gremlin that skips the house idiom is the realistic case. `eval/profile.py`'s
step profiler is the one deliberate exclusion: a profiled traversal is a distorted
one, and mixing it into this record would poison it.

Set `THALAMUS_PROFILE=0` to disable recording entirely.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

PROFILES_DIR = Path.home() / ".thalamus" / "profiles"

# Per (surface, shape), how many individual durations are kept for the percentile
# read. The whole distribution would make the ledger unbounded again; a bounded
# prefix keeps p50/p95 honest for every shape a session actually leans on and
# reports its own truncation (`calls` exceeds `len(ms)` when it happened).
_MAX_SAMPLES = 200

# How long a long-lived process (the MCP server) may hold measurements before they
# reach disk. Checked on `close_connection`, never on the traversal itself.
_FLUSH_INTERVAL_S = 60.0

_STEP_RE = re.compile(r"\.\s*([A-Za-z_]+)\s*\(")


def step_shape(text: str) -> tuple[str, ...]:
    """The ordered gremlin step sequence of a written query, dialect-folded.

    `has_label` and `hasLabel` fold to the same token, so a shape matches across the
    gremlin-python / gremlin-lang split. Quoting, arguments and whitespace are
    invisible: this is the shape of the traversal, not the question it asked.
    """
    return tuple(m.lower().replace("_", "") for m in _STEP_RE.findall(text))


def bytecode_shape(bytecode) -> tuple[str, ...]:
    """The same shape, read off gremlin-python bytecode instead of off text.

    Bytecode carries the step names directly, so this needs no parsing and cannot
    disagree with what the driver actually sent. Folded identically to `step_shape`,
    which is what makes one aggregation key cover both surfaces.
    """
    steps = []
    for group in ("source_instructions", "step_instructions"):
        for instruction in getattr(bytecode, group, None) or ():
            if instruction:
                steps.append(str(instruction[0]).lower().replace("_", ""))
    return tuple(steps)


def origin() -> str:
    """A coarse label for what issued a traversal — the covariate, not the identity.

    Measurements are only comparable within an origin: the MCP server's traversals
    run against a warm process and a warm page cache, a fresh CLI invocation's do
    not, and averaging the two describes neither.
    """
    explicit = os.environ.get("THALAMUS_PROFILE_ORIGIN", "")
    if explicit:
        return explicit
    argv0 = Path(sys.argv[0]).name if sys.argv else ""
    if "pytest" in argv0:
        return "test"
    if "mcp" in argv0:
        return "mcp"
    if argv0.startswith("thalamus") or argv0 == "cli.py":
        subcommand = next((a for a in sys.argv[1:] if not a.startswith("-")), "")
        return f"cli:{subcommand}" if subcommand else "cli"
    if argv0 in ("-c", "-"):  # python -c / stdin: a scratch script, not a named surface
        return "python -c"
    return argv0 or "python"


def enabled() -> bool:
    return os.environ.get("THALAMUS_PROFILE", "1").strip().lower() not in (
        "0",
        "false",
        "off",
        "no",
    )


@dataclass
class SpanRow:
    """One (surface, shape) bucket as a process flushed it."""

    ts: datetime
    origin: str
    scope: str
    surface: str
    shape: tuple[str, ...]
    calls: int
    total_ms: float
    samples: list[float] = field(default_factory=list)
    tap_ns: int = 0

    @property
    def shape_text(self) -> str:
        return ".".join(self.shape)


@dataclass
class _Bucket:
    calls: int = 0
    total_ms: float = 0.0
    samples: list[float] = field(default_factory=list)
    tap_ns: int = 0


class SpanRecorder:
    """Aggregates durations by (surface, shape) and flushes them as JSONL rows."""

    def __init__(self, base: Path | None = None):
        self._base = base
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._last_flush = time.monotonic()

    def record(self, surface: str, shape: tuple[str, ...], ms: float) -> None:
        started = time.perf_counter_ns()
        key = (surface, ".".join(shape))
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = self._buckets[key] = _Bucket()
            bucket.calls += 1
            bucket.total_ms += ms
            if len(bucket.samples) < _MAX_SAMPLES:
                bucket.samples.append(ms)
            bucket.tap_ns += time.perf_counter_ns() - started

    def maybe_flush(self) -> None:
        """Flush if the interval has lapsed. Called off the traversal path."""
        if time.monotonic() - self._last_flush >= _FLUSH_INTERVAL_S:
            self.flush()

    def flush(self) -> Path | None:
        with self._lock:
            buckets = self._buckets
            self._buckets = {}
            self._last_flush = time.monotonic()
        if not buckets:
            return None
        now = datetime.now(timezone.utc)
        stamp = now.isoformat().replace("+00:00", "Z")
        who = origin()
        scope = os.environ.get("THALAMUS_SCOPE", "")
        lines = [
            json.dumps(
                {
                    "ts": stamp,
                    "origin": who,
                    "scope": scope,
                    "surface": surface,
                    "shape": shape,
                    "calls": bucket.calls,
                    "total_ms": round(bucket.total_ms, 4),
                    "ms": [round(sample, 4) for sample in bucket.samples],
                    "tap_ns": bucket.tap_ns,
                },
                separators=(",", ":"),
            )
            for (surface, shape), bucket in sorted(buckets.items())
        ]
        directory = self._base or PROFILES_DIR
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{now:%Y-%m}.jsonl"
            with path.open("a") as handle:
                handle.write("\n".join(lines) + "\n")
        except OSError:  # an unwritable ledger must never take a traversal down
            logger.warning("Could not write span ledger under %s", directory)
            return None
        return path


_RECORDER = SpanRecorder()
atexit.register(_RECORDER.flush)


def record(surface: str, shape: tuple[str, ...], ms: float) -> None:
    if enabled():
        _RECORDER.record(surface, shape, ms)


def flush() -> Path | None:
    return _RECORDER.flush()


def maybe_flush() -> None:
    if enabled():
        _RECORDER.maybe_flush()


def instrument(connection, surface: str = "gremlin-python") -> None:
    """Time every traversal a `DriverRemoteConnection` submits.

    Wraps the instance, not the driver class: every house caller reaches the graph
    through `writer.connect`, and a class-level patch would also catch a driver some
    other code constructed for its own reasons.

    `submit` is the single funnel — it blocks until the server's results are in hand,
    so one `perf_counter` pair around it is the traversal's whole round trip. Wrapped
    once per connection; a second call is a no-op.
    """
    if not enabled() or connection is None or getattr(connection, "_thalamus_timed", False):
        return
    inner = connection.submit

    def timed(bytecode):
        started = time.perf_counter()
        try:
            return inner(bytecode)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            try:
                _RECORDER.record(surface, bytecode_shape(bytecode), elapsed_ms)
            except Exception:  # noqa: BLE001 — the tap never breaks the traversal
                logger.debug("Span record failed", exc_info=True)

    connection.submit = timed
    connection._thalamus_timed = True


def load_rows(base: Path | None = None) -> list[SpanRow]:
    """Parse every monthly span file into rows, oldest first."""
    directory = base or PROFILES_DIR
    if not directory.is_dir():
        return []
    rows: list[SpanRow] = []
    for path in sorted(directory.glob("*.jsonl")):
        with path.open(errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = _parse(line)
                if row is not None:
                    rows.append(row)
    rows.sort(key=lambda r: r.ts)
    return rows


def _parse(line: str) -> SpanRow | None:
    try:
        record_ = json.loads(line)
        ts = datetime.fromisoformat(str(record_.get("ts", "")).replace("Z", "+00:00"))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(record_, dict) or not record_.get("calls"):
        return None
    samples = record_.get("ms")
    return SpanRow(
        ts=ts,
        origin=str(record_.get("origin", "")),
        scope=str(record_.get("scope", "")),
        surface=str(record_.get("surface", "")),
        shape=tuple(s for s in str(record_.get("shape", "")).split(".") if s),
        calls=int(record_["calls"]),
        total_ms=float(record_.get("total_ms", 0.0)),
        samples=[float(s) for s in samples] if isinstance(samples, list) else [],
        tap_ns=int(record_.get("tap_ns", 0)),
    )
