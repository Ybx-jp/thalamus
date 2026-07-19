"""Cost accounting — the denominator of the eval loop (docs/04).

Layer 1 grades what retrieval returned and whether it was used; this module grades
what the memory system *spends*. The field grades memory on accuracy–cost frontiers,
not accuracy alone (BudgetMem, arXiv 2602.06025, measures cost by aggregating token
usage per query), and token cost is a session-level observability metric in the
AgentOps taxonomy (arXiv 2411.05285). This is the local, in-deployment instantiation
of both: no new telemetry is emitted — every number is read from records the system
already keeps.

Three sources, all local files, no graph connection:

- **harness transcripts** (`~/.claude/projects/*/*.jsonl`) — per-API-call usage
  fields. Bucketed into the operation ontology below.
- **the trace tap** (`~/.thalamus/traces/*.jsonl`) — verbatim tool responses, so
  the injection cost of each retrieval is its rendered size. Injected tokens also
  ride along in every subsequent call of the session; that multiplier is reported
  as a count of calls, not estimated away.
- **the pin ledger** (`~/.thalamus/pins/pins.jsonl`) — session → scope, which is
  how an expert session's burn is told apart from the operator's own.

Operation ontology (the cost analog of an operation registry with risk weights —
same pattern, different dimension): `interactive` (the operator's own sessions in
the project), `extract` (headless `claude -p` distillation/ingest runs),
`expert:<scope>` (pinned expert sessions), `other` (everything else on the machine,
reported so thalamus's share has a denominator).

The weighted-token proxy is a dial, not a truth: subscription limit weights are not
public, so this uses API-price ratios (cache reads ~0.1x input, cache writes ~1.25x,
output ~5x). Arbitrary dials, here to be pressure-tested — same discipline as the
attribution thresholds in docs/04.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from thalamus.eval.traces import TRACES_DIR, load_events

PROJECTS_DIR = Path.home() / ".claude" / "projects"
PINS_FILE = Path.home() / ".thalamus" / "pins" / "pins.jsonl"

_EXTRACT_SLUG_PREFIX = "-tmp-thalamus-extract"

# Weighted-token proxy dials (API-price ratios; see module docstring).
_W_INPUT = 1.0
_W_CACHE_CREATE = 1.25
_W_CACHE_READ = 0.1
_W_OUTPUT = 5.0

# Rendered response chars per token, the usual rough English/markdown ratio.
_CHARS_PER_TOKEN = 4


def weighted_tokens(usage: dict) -> int:
    """Collapse one API call's usage record into the single proxy number."""
    return int(
        _W_INPUT * usage.get("input_tokens", 0)
        + _W_CACHE_CREATE * usage.get("cache_creation_input_tokens", 0)
        + _W_CACHE_READ * usage.get("cache_read_input_tokens", 0)
        + _W_OUTPUT * usage.get("output_tokens", 0)
    )


@dataclass
class BucketCost:
    weighted: int = 0
    calls: int = 0
    sessions: set = field(default_factory=set)


@dataclass
class CostReport:
    since: date
    project: str
    buckets: dict[str, BucketCost] = field(default_factory=dict)
    by_day: dict[str, dict[str, int]] = field(default_factory=dict)
    # Tap side: tool -> (calls, injected chars).
    injection: dict[str, tuple[int, int]] = field(default_factory=dict)

    def render(self) -> str:
        lines = [
            f"Cost report — project `{self.project}`, since {self.since.isoformat()} "
            "(weighted-token proxy; dials in eval/cost.py)",
        ]
        thalamus_buckets = [b for b in self.buckets if b != "other"]
        if thalamus_buckets:
            lines.append("  harness burn by operation:")
            for name in sorted(thalamus_buckets, key=lambda b: -self.buckets[b].weighted):
                b = self.buckets[name]
                lines.append(
                    f"    {name:<18s} {b.weighted:>14,} weighted "
                    f"({len(b.sessions)} session(s), {b.calls} calls)"
                )
        else:
            lines.append("  no project sessions found in the harness transcripts")

        other = self.buckets.get("other")
        if other:
            lines.append(
                f"    {'other projects':<18s} {other.weighted:>14,} weighted "
                f"({len(other.sessions)} session(s)) — the denominator"
            )

        if self.injection:
            total_calls = sum(c for c, _ in self.injection.values())
            total_chars = sum(ch for _, ch in self.injection.values())
            lines.append(
                f"  context injection (trace tap): {total_calls} tool calls, "
                f"~{total_chars // _CHARS_PER_TOKEN:,} tokens rendered into context "
                "(each rides along in every later call of its session)"
            )
            for tool, (calls, chars) in sorted(
                self.injection.items(), key=lambda kv: -kv[1][1]
            ):
                per_call = chars // _CHARS_PER_TOKEN // max(calls, 1)
                lines.append(
                    f"    {tool:<24s} n={calls:<3d} ~{chars // _CHARS_PER_TOKEN:>7,} tokens "
                    f"({per_call:,}/call)"
                )
        else:
            lines.append("  context injection (trace tap): no tap lines in range")

        if self.by_day:
            lines.append("  per-day weighted (project buckets only):")
            for day in sorted(self.by_day):
                total = sum(self.by_day[day].values())
                parts = " · ".join(
                    f"{name} {value:,}"
                    for name, value in sorted(self.by_day[day].items(), key=lambda kv: -kv[1])
                )
                lines.append(f"    {day}  {total:>14,}  ({parts})")
        return "\n".join(lines)


def _ledger_records(path: Path | None = None):
    pins_path = path or PINS_FILE
    if not pins_path.is_file():
        return
    for line in pins_path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("session_id"):
            yield record


def load_pins(path: Path | None = None) -> dict[str, str]:
    """session_id -> scope, last pin wins (a session re-pins by overwriting).

    Spawn lines only — event lines (pin-engaged.sh's {"event": "engaged"}) are a
    different record type in the same ledger and are read by load_engaged.
    """
    return {
        str(r["session_id"]): str(r.get("scope") or "")
        for r in _ledger_records(path)
        if not r.get("event")
    }


def load_engaged(path: Path | None = None) -> set[str]:
    """Sessions that received at least one user prompt (pin-engaged.sh).

    The engagement boundary for the pin report's denominator: spawn records alone
    conflate roster bring-up with operator routing (the 2026-07-19 confound;
    semantics vetted in scope:main:exchange:63b647977a624b85).
    """
    return {
        str(r["session_id"])
        for r in _ledger_records(path)
        if r.get("event") == "engaged"
    }


def _bucket(slug: str, session_id: str, project_slug: str, pins: dict[str, str]) -> str:
    if slug.startswith(_EXTRACT_SLUG_PREFIX):
        return "extract"
    scope = pins.get(session_id, "")
    if scope and scope != "main":
        return f"expert:{scope}"
    if slug == project_slug:
        return "interactive"
    return "other"


def project_slug(project_dir: Path) -> str:
    """The harness's transcript-directory name for a working directory."""
    return str(project_dir).replace("/", "-").replace(".", "-")


def cost_report(
    project_dir: Path,
    since: date,
    *,
    projects_base: Path | None = None,
    traces_base: Path | None = None,
    pins_path: Path | None = None,
) -> CostReport:
    base = projects_base or PROJECTS_DIR
    pins = load_pins(pins_path)
    slug = project_slug(project_dir)
    report = CostReport(since=since, project=project_dir.name)

    if base.is_dir():
        for pdir in base.iterdir():
            if not pdir.is_dir():
                continue
            for transcript in pdir.glob("*.jsonl"):
                _tally_transcript(report, transcript, pdir.name, slug, pins, since)

    for event in load_events(traces_base or TRACES_DIR, tools=None):
        if event.ts.date() < since:
            continue
        calls, chars = report.injection.get(event.tool, (0, 0))
        report.injection[event.tool] = (calls + 1, chars + len(event.tool_response))

    return report


def _tally_transcript(
    report: CostReport,
    transcript: Path,
    slug: str,
    project_slug: str,
    pins: dict[str, str],
    since: date,
) -> None:
    session_id = transcript.stem
    bucket_name = _bucket(slug, session_id, project_slug, pins)
    bucket = report.buckets.setdefault(bucket_name, BucketCost())
    with transcript.open(errors="ignore") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            message = record.get("message")
            usage = message.get("usage") if isinstance(message, dict) else None
            if not isinstance(usage, dict):
                continue
            timestamp = str(record.get("timestamp") or "")
            if len(timestamp) < 10 or timestamp[:10] < since.isoformat():
                continue
            weight = weighted_tokens(usage)
            bucket.weighted += weight
            bucket.calls += 1
            bucket.sessions.add(session_id)
            if bucket_name != "other":
                day = report.by_day.setdefault(timestamp[:10], defaultdict(int))
                day[bucket_name] += weight
