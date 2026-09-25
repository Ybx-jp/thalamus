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
    ARM_AGENTIC,
    ARM_LEXICAL,
    POINTER_OPEN,
    Firing,
    load_firings,
    load_shadow,
    reflex_dir,
)
from thalamus.harness.reflex_note import NOTE_ARMS
from thalamus.harness.reflex_queue import JOB_OUTCOMES, load_outcomes

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


def _spread(values: list[int]) -> str:
    ordered = sorted(values)
    p90 = ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))]
    return f"{median(ordered):g}/{p90:g}/{ordered[-1]:g}"


# The per-firing numbers each arm's trace carries, as the report names them. `records`
# is served firings only; a firing that found nothing served none.
_EFFORT_LABELS = (
    ("calls", "calls"), ("nodes", "nodes returned"), ("ms", "ms"),
    ("records", "records served"), ("linked", "of them reached by the spread"),
    ("turns", "model turns"), ("depth", "tool calls before delivery"),
)


@dataclass
class ReflexReport:
    firings: int = 0
    sessions: int = 0
    outcomes: Counter = field(default_factory=Counter)
    # Qualifying failures and served firings by the hook event that ran the reflex;
    # "" is a row written before the hook recorded it.
    by_event: Counter = field(default_factory=Counter)
    served_by_event: Counter = field(default_factory=Counter)
    # Calls the failure test passed over, by event, from the shadow log: all of them,
    # those with any anchor, and those that would have cleared `fire`'s query gate.
    shadowed: Counter = field(default_factory=Counter)
    shadow_anchored: Counter = field(default_factory=Counter)
    shadow_would_query: Counter = field(default_factory=Counter)
    # Rendered chars served, per session that was served anything.
    injected_by_session: dict[str, int] = field(default_factory=dict)
    voiced: int = 0
    # Outcomes of the firings that took a plan, per plan: the denominators every
    # conditional-on-served rate of a plan sits over.
    by_plan: dict[str, Counter] = field(default_factory=dict)
    # Firings that retrieved, by arm, from the tap.
    by_arm: Counter = field(default_factory=Counter)
    # What each arm did per firing, from the tap: calls issued, distinct nodes returned,
    # wall milliseconds, records served and, of those, records the spread reached.
    effort: dict[str, dict[str, list[int]]] = field(default_factory=dict)
    tap_misses: Counter = field(default_factory=Counter)
    # The agentic plan's jobs, from the queue's job ledger: how each ended, and for
    # those that reached the agent, the delivery depth and the queue wait.
    jobs: Counter = field(default_factory=Counter)
    job_depth: list[int] = field(default_factory=list)
    job_queued_ms: list[int] = field(default_factory=list)
    # The agentic plan's note on delivered jobs: how each note fared at the check
    # (valid, absent, too_long, …) and, of the valid ones, which arm it drew.
    note_status: Counter = field(default_factory=Counter)
    note_arm: Counter = field(default_factory=Counter)
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
        if not self.firings and not self.shadowed:
            return "No reflex firings yet — the hook has not seen a qualifying failure."
        lines = [
            "Memory reflex report (read by arm; docs/cli.md, The eval loop)",
            "",
            f"qualifying failures: {self.firings} over {self.sessions} session(s)",
        ]
        for outcome in ("served", "empty", "deduped", "refused", "no_anchors", "queued"):
            lines.append(f"  {outcome}: {self.outcomes.get(outcome, 0)}")
        lines.append("by the event that ran the hook (served / qualifying):")
        for event in sorted(self.by_event):
            label = EVENT_LABELS.get(event, event)
            lines.append(
                f"  {label}: {self.served_by_event.get(event, 0)} / {self.by_event[event]}"
            )
        if self.shadowed:
            lines.append(
                "passed over by the failure test (shadow log; nothing retrieved) — "
                "calls / with anchors / would have queried:"
            )
            for event in sorted(self.shadowed):
                lines.append(
                    f"  {EVENT_LABELS.get(event, event)}: {self.shadowed[event]} / "
                    f"{self.shadow_anchored[event]} / {self.shadow_would_query[event]}"
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
        if self.by_plan:
            lines += ["", "by plan, firings that took one (ledger):"]
            for arm, outcomes in sorted(self.by_plan.items()):
                lines.append(
                    f"  {arm}: " + " / ".join(
                        f"{outcomes.get(outcome, 0)} {outcome}"
                        for outcome in ("served", "empty", "refused", "queued")
                        if outcome != "queued" or outcomes.get(outcome)
                    )
                )
        if self.jobs:
            lines += ["", "agentic jobs, by how they ended (queue ledger):"]
            lines.append("  " + " / ".join(
                f"{self.jobs.get(outcome, 0)} {outcome}" for outcome in JOB_OUTCOMES
            ))
            if self.job_depth:
                lines.append(
                    f"  delivery depth, tool calls after the trigger, p50/p90/max: "
                    f"{_spread(self.job_depth)} (n={len(self.job_depth)})"
                )
            if self.note_status:
                lines.append("  notes on delivered jobs, by check: " + ", ".join(
                    f"{count} {status}" for status, count in sorted(self.note_status.items())
                ))
                lines.append("  valid notes, by arm: " + ", ".join(
                    f"{self.note_arm.get(arm, 0)} {arm}" for arm in NOTE_ARMS
                ))
            if self.job_queued_ms:
                lines.append(
                    f"  queued ms, trigger to claim, p50/p90/max: "
                    f"{_spread(self.job_queued_ms)} (n={len(self.job_queued_ms)})"
                )
        if self.by_arm:
            lines += ["", "retrieved, by arm (trace tap):"]
            for arm, count in sorted(self.by_arm.items()):
                lines.append(f"  {arm}: {count} ({self.tap_misses.get(arm, 0)} misses)")
                effort = self.effort.get(arm, {})
                # Each number has its own n: older traces predate some fields, and
                # only a served firing has records.
                shown = [
                    f"{label} {_spread(effort[key])} (n={len(effort[key])})"
                    for key, label in _EFFORT_LABELS if effort.get(key)
                ]
                if shown:
                    lines.append("    per firing, p50/p90/max: " + "; ".join(shown))
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
        if row.arm and row.outcome in ("served", "empty", "refused", "queued"):
            report.by_plan.setdefault(row.arm, Counter())[row.outcome] += 1
        if row.outcome == "served":
            report.served_by_event[row.event] += 1
            report.injected_by_session[row.session_id] = (
                report.injected_by_session.get(row.session_id, 0) + row.injected_chars
            )
            report.voiced += row.voiced

    for job in load_outcomes(reflex_dir(reflex_base)):
        outcome = str(job.get("outcome") or "")
        report.jobs[outcome] += 1
        if outcome == "delivered" and isinstance(job.get("depth"), int):
            report.job_depth.append(job["depth"])
        if outcome == "delivered" and isinstance(job.get("queued_ms"), int):
            report.job_queued_ms.append(job["queued_ms"])
        if outcome == "delivered" and job.get("note_status"):
            report.note_status[str(job["note_status"])] += 1
            if job.get("note_arm"):
                report.note_arm[str(job["note_arm"])] += 1

    for shadow_row in load_shadow(reflex_base):
        report.shadowed[shadow_row.event] += 1
        if shadow_row.anchors:
            report.shadow_anchored[shadow_row.event] += 1
        if shadow_row.would_query:
            report.shadow_would_query[shadow_row.event] += 1

    # A delivered agentic trace's note arm, by trace id, so the verdicts on the graph
    # can be read with and without the note over the same kind of firing.
    note_arms: dict[str, str] = {}
    for event in load_events(traces_base):
        if event.tool == ARM_AGENTIC and event.tool_input.get("note_arm"):
            note_arms[event.trace_id()] = str(event.tool_input["note_arm"])
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
        effort = report.effort.setdefault(event.tool, {})
        # `hops` marks a plan that spreads; only there is `linked` a measurement.
        spreads = "hops" in event.tool_input
        for key in ("calls", "nodes", "ms", "linked", "turns", "depth"):
            value = event.tool_input.get(key)
            if key == "linked" and not spreads:
                continue
            if isinstance(value, int) and not isinstance(value, bool):
                effort.setdefault(key, []).append(value)
        if event.handles():
            effort.setdefault("records", []).append(len(event.handles()))

    if g is not None:
        report.graph_read = True
        _read_verdicts(g, report, note_arms)
    return report


def _read_verdicts(
    g: GraphTraversalSource, report: ReflexReport, note_arms: dict[str, str] | None = None
) -> None:
    """Landed reflex traces and the verdicts on their RETURNS edges, by arm.

    An agentic trace whose note passed its check is read under its note arm as well —
    `reflex_agentic (note shown)` or `(note withheld)` — from `note_arms`, keyed by the
    trace id that ends the Trace vertex's id.

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
            arm = str(row.get("tool") or ARM_LEXICAL)
            note_arm = (note_arms or {}).get(str(row["id"]).rsplit(":", 1)[-1])
            if arm == ARM_AGENTIC and note_arm:
                arm = f"{arm} (note {note_arm})"
            arms[str(row["id"])] = arm
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
