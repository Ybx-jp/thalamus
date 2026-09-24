"""The memory reflex, read by arm — `thalamus eval reflex`.

The reflex (harness/reflex.py) is measured on its own instrument, separate from
`eval conditioning`: a reminder conditions the agent to *call* memory, an injected
block is dynamic RAG, and the two axes are not pooled. What this reads:

- the reflex ledger (`~/.thalamus/reflex/sessions/`) — every qualifying failure the
  hook handed over and what became of it, which is the only place the denominator
  lives, since the trace tap sees only the firings that retrieved;
- the trace tap — the firings that retrieved, by arm (`tool_name` `reflex_*`), the
  way `eval report` counts every other retrieval surface, and the pointer files the
  agent opened (`reflex_pointer_open`), a secondary signal read beside the arms;
- the graph, when it answers — the `RETURNS {used}` verdicts `eval sync` landed on
  reflex traces, split into the lexical verdict and the citation verdict.

The two verdicts are reported side by side and mean different things. The lexical
used-verdict carries ~4 points of discrimination over a ~59-point chance floor
(`eval/attribution.py`), so a reflex used-rate on it is read as *delivery*, not use.
A citation — a vertex id, or the digest handle standing for it, in the agent's
subsequent output — is the unfakeable form and the primary use signal.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

from gremlin_python.process.graph_traversal import GraphTraversalSource, __
from gremlin_python.process.traversal import Direction, T, TextP

from thalamus.eval.rates import Rate
from thalamus.eval.traces import load_events
from thalamus.harness.reflex import (
    ARM_LEXICAL,
    POINTER_OPEN,
    Firing,
    load_firings,
    reflex_dir,
)

# The evidence `attribution._judge` writes when the agent quoted the node's id or the
# handle it was shown for it: "cited by vertex ID", "cited by handle R3.1".
CITED_EVIDENCE = "cited by "

# Every reflex arm's `tool` value starts with this; the report filters on the prefix
# and enumerates nothing, so a later arm appears as a row with no change here. The one
# `reflex_` value that is not an arm is the pointer-open tap's.
ARM_PREFIX = "reflex_"

# Claude Code writes a hook string longer than this to a file and hands the agent its
# first 2,000 characters (#258).
SPILL_CHARS = 10_000


# How the report names each hook event: the event is the exit status, which is what a
# reader splitting the population wants to see. A row with no event predates the hook
# recording it, and every such row came from `PostToolUse` alone — the only event the
# reflex was wired on then — so it counts only failures whose exit status a pipe or
# wrapper swallowed (A0166, cites-as-live).
EVENT_LABELS = {
    "PostToolUse": "PostToolUse (exit 0)",
    "PostToolUseFailure": "PostToolUseFailure (non-zero exit)",
    "": "unrecorded (exit 0 only; written before the event was recorded)",
}


def _is_arm(tool: str) -> bool:
    return tool.startswith(ARM_PREFIX) and tool != POINTER_OPEN


@dataclass
class ReflexReport:
    firings: int = 0
    sessions: int = 0
    outcomes: Counter = field(default_factory=Counter)
    # Qualifying failures and served firings by the hook event that ran the reflex;
    # "" is a row written before the hook recorded it.
    by_event: Counter = field(default_factory=Counter)
    served_by_event: Counter = field(default_factory=Counter)
    # Rendered chars served, per session that was served anything.
    injected_by_session: dict[str, int] = field(default_factory=dict)
    voiced: int = 0
    # Firings that retrieved, by arm, from the tap.
    by_arm: Counter = field(default_factory=Counter)
    tap_misses: Counter = field(default_factory=Counter)
    # Digests that went over Claude Code's 10,000-char spill line, from the tap.
    spilled: int = 0
    # Served firings whose pointer file the agent later named in a tool call, keyed
    # by the pointer's path; and every open event, a firing opened twice counting two.
    opened: set[str] = field(default_factory=set)
    opens: int = 0
    pointers_served: set[str] = field(default_factory=set)
    # From the graph: landed traces and their verdicts, by arm.
    graph_read: bool = False
    landed: Counter = field(default_factory=Counter)
    returns: Counter = field(default_factory=Counter)
    attributed: Counter = field(default_factory=Counter)
    used: Counter = field(default_factory=Counter)
    cited: Counter = field(default_factory=Counter)

    def render(self) -> str:
        if not self.firings:
            return "No reflex firings yet — the hook has not seen a qualifying failure."
        lines = [
            "Memory reflex report (read by arm; docs/cli.md, The eval loop)",
            "",
            f"qualifying failures: {self.firings} over {self.sessions} session(s)",
        ]
        for outcome in ("served", "empty", "deduped", "refused", "no_anchors"):
            lines.append(f"  {outcome}: {self.outcomes.get(outcome, 0)}")
        lines.append("by the event that ran the hook (served / qualifying):")
        for event in sorted(self.by_event):
            label = EVENT_LABELS.get(event, event)
            lines.append(
                f"  {label}: {self.served_by_event.get(event, 0)} / {self.by_event[event]}"
            )
        lines.append(
            Rate(
                label="served per qualifying failure",
                hits=self.outcomes.get("served", 0),
                total=self.firings,
                null_reason="a delivery count, not a judgement — nothing here says "
                "the served block was worth serving",
                interval_reason="counts only at this rung",
            ).render()
        )
        if self.injected_by_session:
            values = sorted(self.injected_by_session.values())
            lines.append(
                f"injected chars per served session: median {median(values):,.0f}, "
                f"max {values[-1]:,}, total {sum(values):,} over {len(values)} session(s)"
            )
        if self.voiced:
            lines.append(
                f"served blocks phrased as instructions: {self.voiced} "
                "(quoted verbatim and named as records in the envelope)"
            )
        if self.by_arm:
            lines += ["", "retrieved, by arm (trace tap):"]
            for arm, count in sorted(self.by_arm.items()):
                lines.append(f"  {arm}: {count} ({self.tap_misses.get(arm, 0)} misses)")
            lines.append(
                f"  over the 10,000-char spill line: {self.spilled} "
                "(reached the agent as a 2,000-char preview)"
            )
        if self.pointers_served:
            lines.append(Rate(
                label="pointer files opened per served digest",
                hits=len(self.opened & self.pointers_served),
                total=len(self.pointers_served),
                null_reason="an open is a secondary signal — the agent looked, not "
                "that the record changed what it did — and carries position bias",
                interval_reason="counts only at this rung",
            ).render() + f"; {self.opens} open event(s)")
        lines.append("")
        if not self.graph_read:
            lines.append(
                "verdicts: graph not read — run `thalamus eval sync --write` and "
                "`thalamus eval reflex` against a running graph for used-vs-ignored"
            )
            return "\n".join(lines)
        if not self.landed:
            lines.append(
                "verdicts: no reflex traces landed yet — traces land after their "
                "session is distilled (`thalamus eval sync --write`)"
            )
            return "\n".join(lines)
        lines.append("verdicts on landed reflex traces:")
        for arm in sorted(self.landed):
            lines.append(
                f"  {arm}: {self.landed[arm]} traces, {self.returns[arm]} returned nodes, "
                f"{self.attributed[arm]} attributed"
            )
            lines.append("  " + Rate(
                label="  lexical used-rate",
                hits=self.used[arm],
                total=self.attributed[arm],
                null_reason="~59-point vocabulary floor with ~4 points of discrimination "
                "(eval/attribution.py) — read as delivery, not use",
                interval_reason="no session resampling at this rung",
            ).render())
            lines.append("  " + Rate(
                label="  citation used-rate",
                hits=self.cited[arm],
                total=self.attributed[arm],
                null_reason="a vertex id or its digest handle in later output is not produced by "
                "chance; the rate is bounded below by the lexical verdict's recall",
                interval_reason="no session resampling at this rung",
            ).render())
        return "\n".join(lines)


def load_all_firings(base: Path | None = None) -> list[Firing]:
    directory = reflex_dir(base) / "sessions"
    if not directory.is_dir():
        return []
    firings: list[Firing] = []
    for path in sorted(directory.glob("*.jsonl")):
        firings.extend(load_firings(path.stem, base))
    firings.sort(key=lambda row: row.ts)
    return firings


def reflex_report(
    reflex_base: Path | None = None,
    traces_base: Path | None = None,
    g: GraphTraversalSource | None = None,
) -> ReflexReport:
    report = ReflexReport()
    firings = load_all_firings(reflex_base)
    report.firings = len(firings)
    report.sessions = len({row.session_id for row in firings})
    for row in firings:
        report.outcomes[row.outcome] += 1
        report.by_event[row.event] += 1
        if row.outcome == "served":
            report.served_by_event[row.event] += 1
            report.injected_by_session[row.session_id] = (
                report.injected_by_session.get(row.session_id, 0) + row.injected_chars
            )
            report.voiced += row.voiced

    for event in load_events(traces_base):
        pointer = str(event.tool_input.get("pointer") or "")
        if event.tool == POINTER_OPEN:
            report.opens += 1
            if pointer:
                report.opened.add(pointer)
            continue
        if not _is_arm(event.tool):
            continue
        report.by_arm[event.tool] += 1
        if not event.returned_node_ids():
            report.tap_misses[event.tool] += 1
        if event.injected_chars() > SPILL_CHARS:
            report.spilled += 1
        if pointer:
            report.pointers_served.add(pointer)

    if g is not None:
        report.graph_read = True
        _read_verdicts(g, report)
    return report


def _read_verdicts(g: GraphTraversalSource, report: ReflexReport) -> None:
    """Landed reflex traces and the verdicts on their RETURNS edges, by arm.

    Reads every scope: a reflex fires in whichever scope the session was pinned to,
    and the arm — not the scope — is the axis the ladder compares on.
    """
    rows = (
        g.V()
        .has_label("Trace")
        .has("tool", TextP.starting_with(ARM_PREFIX))
        .not_(__.has("tool", POINTER_OPEN))
        .project("id", "tool")
        .by(T.id)
        .by(__.values("tool"))
        .to_list()
    )
    arms: dict[str, str] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("id") is not None:
            arms[str(row["id"])] = str(row.get("tool") or ARM_LEXICAL)
    for arm in arms.values():
        report.landed[arm] += 1
    if not arms:
        return

    edges = (
        g.V()
        .has_label("Trace")
        .has("tool", TextP.starting_with(ARM_PREFIX))
        .not_(__.has("tool", POINTER_OPEN))
        .out_e("RETURNS")
        .element_map()
        .to_list()
    )
    for edge in edges:
        source = edge.get(Direction.OUT) or edge.get("OUT") or {}
        source_id = (
            str(source.get(T.id) or source.get("id") or "")
            if isinstance(source, dict) else str(source)
        )
        arm = arms.get(source_id, ARM_LEXICAL)
        report.returns[arm] += 1
        used = edge.get("used")
        if used is None:
            continue
        report.attributed[arm] += 1
        if used is True or str(used).lower() == "true":
            report.used[arm] += 1
        if str(edge.get("evidence") or "").startswith(CITED_EVIDENCE):
            report.cited[arm] += 1
