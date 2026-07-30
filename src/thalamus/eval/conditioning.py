"""Conditioning effectiveness — the per-firing behavioral join.

The conditioning hook (harness/hooks/claude-code/conditioning.sh) injects
throttled reminders to recall / consult / check recipes. A reminder's fire
count is activity, not effectiveness (lab/008): the honest metric is whether
the behavior followed, per firing — did the session make a thalamus call after
the injection? This joins the conditioning event log against the trace tap,
the same two-JSONL join the guard metrics use.

The classes carry different expected behaviors:
- design      -> a consult_request or a literature recall should follow
- retrospect  -> a recall should follow (instead of transcript archaeology)
- milestone   -> any memory call counts (threads/recall/consult)
- falsify     -> another traversal should follow: the class asks for the check
                 that would overturn the conclusion, and that check is itself a
                 query. A firing with no second traversal is the class failing
                 in exactly the way it exists to prevent (lab/029).

An injection with no thalamus call after it is a "wallpaper" firing — the
reminder rode along in context and changed nothing. Rising wallpaper share is
the signal to retune or retire a class (Self-RAG's lesson, arXiv 2310.11511:
indiscriminate injection is the baseline to beat, not the goal).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from thalamus.eval.traces import load_events

CONDITIONING_DIR = Path.home() / ".thalamus" / "conditioning"

# Which trace-tap tools satisfy each class's expected follow-through.
_EXPECTED: dict[str, frozenset | None] = {
    "design": frozenset({"consult_request", "memory_recall", "memory_query"}),
    "retrospect": frozenset(
        {
            "memory_recall",
            "memory_recall_by_artifact",
            "memory_recall_by_project",
            "memory_recall_recent",
            "memory_thread",
            "memory_query",
        }
    ),
    "milestone": None,  # any thalamus call counts
    "falsify": frozenset({"memory_query", "bash_gremlin"}),
}


@dataclass
class Firing:
    ts: datetime
    session_id: str
    cls: str
    harness: str = "claude-code"
    followed: bool = False


@dataclass
class ConditioningReport:
    firings: list[Firing] = field(default_factory=list)

    def render(self) -> str:
        if not self.firings:
            return "No conditioning firings yet — instrumentation pending, unmeasured."
        lines = ["Conditioning report (per-firing behavioral join)", ""]
        by_class: dict[str, list[Firing]] = {}
        for firing in self.firings:
            by_class.setdefault(firing.cls, []).append(firing)
        for cls, events in sorted(by_class.items()):
            followed = sum(e.followed for e in events)
            lines.append(
                f"{cls}: {followed}/{len(events)} firings followed by the expected "
                f"thalamus call ({len(events) - followed} wallpaper)"
            )

        # Split by harness whenever both are present. Cursor delivers a firing
        # one tool call late (the spool — docs/07), so its rescue rate is not
        # comparable to Claude Code's immediate injection and must not be
        # averaged in with it.
        by_harness: dict[str, list[Firing]] = {}
        for firing in self.firings:
            by_harness.setdefault(firing.harness, []).append(firing)
        if len(by_harness) > 1:
            lines += ["", "By harness (Cursor injection is delivered one tool call late):"]
            for harness, events in sorted(by_harness.items()):
                followed = sum(e.followed for e in events)
                lines.append(f"  {harness}: {followed}/{len(events)} followed")
        return "\n".join(lines)


def load_firings(base: Path | None = None) -> list[Firing]:
    directory = base or CONDITIONING_DIR
    if not directory.is_dir():
        return []
    firings: list[Firing] = []
    for path in sorted(directory.glob("*.jsonl")):
        with path.open(errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    ts = datetime.fromisoformat(
                        str(record.get("ts", "")).replace("Z", "+00:00")
                    )
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(record, dict):
                    continue
                session = record.get("session_id")
                cls = record.get("class")
                if not session or not cls:
                    continue
                firings.append(Firing(
                    ts=ts, session_id=str(session), cls=str(cls),
                    harness=str(record.get("harness") or "claude-code"),
                ))
    firings.sort(key=lambda f: f.ts)
    return firings


def conditioning_report(
    conditioning_base: Path | None = None, traces_base: Path | None = None
) -> ConditioningReport:
    firings = load_firings(conditioning_base)
    if not firings:
        return ConditioningReport()

    calls = load_events(traces_base, tools=None)  # every thalamus tool call
    by_session: dict[str, list] = {}
    for event in calls:
        by_session.setdefault(event.session_id, []).append(event)

    for firing in firings:
        expected = _EXPECTED.get(firing.cls)
        for event in by_session.get(firing.session_id, ()):
            if event.ts <= firing.ts:
                continue
            if expected is None or event.tool in expected:
                firing.followed = True
                break

    return ConditioningReport(firings=firings)
