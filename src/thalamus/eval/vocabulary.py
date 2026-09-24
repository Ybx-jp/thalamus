"""What each retrieval-vocabulary tool returns over real anchors — `thalamus eval vocabulary`.

The compiler's per-job caps (`harness/retrieval.Caps`) bound calls, distinct nodes,
characters of rows and wall time, and a cap set by guess is a cap that either never
binds or binds on the first call. This replays the anchor sets the memory reflex has
actually extracted — from served and unserved firings in the reflex ledger, and from
the calls the failure test passed over in the shadow log — through every tool the way
a planner could reach it, and reports the distribution of what came back.

The sweep is deliberately exhaustive per anchor set: every kind searched, and from the
top node of each kind, every relation walked and the drill-downs that apply. That is
more than any one planner would issue, which is the point — its per-job totals are the
ceiling a cap has to sit under, and its per-call sizes are what one call costs.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

from gremlin_python.process.graph_traversal import GraphTraversalSource

from thalamus.eval.reflex import load_all_firings
from thalamus.harness.reflex import load_shadow
from thalamus.harness.retrieval import Caps, Job
from thalamus.substrate import vocabulary

# A measurement job runs the whole sweep; nothing about it may be capped.
_UNCAPPED = Caps(calls=10**9, nodes=10**9, row_chars=10**12, seconds=float("inf"))

_PREFIX = "M"
_PATH_HINTS = ("/", ".py", ".sh", ".md", ".js", ".toml", ".yaml")


@dataclass
class Sample:
    chars: int
    rows: int
    seconds: float


@dataclass
class VocabularyReport:
    anchor_sets: int = 0
    # tool (with its kind or relation) -> one sample per call.
    calls: dict[str, list[Sample]] = field(default_factory=lambda: defaultdict(list))
    # One entry per anchor set: what the whole sweep issued and returned.
    jobs: list[Sample] = field(default_factory=list)
    job_calls: list[int] = field(default_factory=list)
    job_nodes: list[int] = field(default_factory=list)

    def render(self) -> str:
        if not self.anchor_sets:
            return "No anchor sets to replay — the reflex ledger and shadow log are empty."
        lines = [
            f"Retrieval vocabulary over {self.anchor_sets} real anchor set(s) "
            "(docs/cli.md, eval vocabulary)",
            "",
            "per call: n · rows p50/p90/max · chars p50/p90/max · ms p50/p90/max",
        ]
        for tool in sorted(self.calls):
            samples = self.calls[tool]
            lines.append(
                f"  {tool}: {len(samples)} · "
                f"{_spread([s.rows for s in samples])} · "
                f"{_spread([s.chars for s in samples])} · "
                f"{_spread([round(s.seconds * 1000) for s in samples])}"
            )
        lines += [
            "",
            "per anchor set, the whole sweep (the ceiling a per-job cap sits under):",
            f"  calls {_spread(self.job_calls)}",
            f"  distinct nodes {_spread(self.job_nodes)}",
            f"  row chars {_spread([s.chars for s in self.jobs])}",
            f"  wall ms {_spread([round(s.seconds * 1000) for s in self.jobs])}",
        ]
        return "\n".join(lines)


def _spread(values: list[int]) -> str:
    if not values:
        return "-"
    ordered = sorted(values)
    p90 = ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))]
    return f"{median(ordered):g}/{p90:g}/{ordered[-1]:g}"


def anchor_sets(reflex_base: Path | None = None, limit: int = 40) -> list[list[str]]:
    """Distinct anchor sets the reflex extracted, newest first, at most `limit`."""
    candidates = [row.anchors for row in load_all_firings(reflex_base)]
    candidates += [row.anchors for row in load_shadow(reflex_base)]
    seen: set[tuple[str, ...]] = set()
    chosen: list[list[str]] = []
    for anchors in reversed(candidates):
        key = tuple(sorted(anchors))
        if len(anchors) < 2 or key in seen:
            continue
        seen.add(key)
        chosen.append(list(anchors))
        if len(chosen) >= limit:
            break
    return chosen


def _handles(output: str) -> list[str]:
    return [
        line.split(" · ", 1)[0] for line in output.splitlines()
        if line.startswith(f"{_PREFIX}.")
    ]


def _kind_of(output_line: str) -> str:
    parts = output_line.split(" · ")
    return parts[1] if len(parts) > 1 else ""


def measure(
    g: GraphTraversalSource,
    sets: list[list[str]],
    scope: str,
    knowledge_scopes: list[str],
    clock=time.monotonic,
) -> VocabularyReport:
    report = VocabularyReport(anchor_sets=len(sets))
    for anchors in sets:
        job = Job(g, scope=scope, knowledge_scopes=knowledge_scopes, prefix=_PREFIX,
                  caps=_UNCAPPED, clock=clock)
        started = clock()

        def run(label: str, name: str, args: dict) -> str:
            before = clock()
            output = job.call(name, args)
            rows = len(_handles(output))
            report.calls[label].append(Sample(len(output) if rows else 0, rows,
                                              clock() - before))
            return output

        query = " ".join(anchors)
        seeds: list[tuple[str, str]] = []
        for kind in vocabulary.KINDS:
            output = run(f"lexical_by_kind:{kind}", "lexical_by_kind",
                         {"query": query, "kind": kind})
            first = next((line for line in output.splitlines()
                          if line.startswith(f"{_PREFIX}.")), "")
            handle = first.split(" · ", 1)[0]
            if first and handle not in {seed for seed, _ in seeds}:
                seeds.append((handle, _kind_of(first)))
        for handle, kind in seeds:
            for relation in vocabulary.RELATIONS:
                run(f"expand_one_hop:{relation}", "expand_one_hop",
                    {"handle": handle, "relation": relation})
            if kind == "session":
                run("session_claims", "session_claims", {"handle": handle})
            if kind in ("external", "chunk"):
                run("chunks_near_source", "chunks_near_source", {"handle": handle})
        for anchor in [a for a in anchors if any(h in a for h in _PATH_HINTS)][:2]:
            run("by_path", "by_path", {"path": anchor})
        run("threads_by_topic", "threads_by_topic", {"topic": query})

        report.jobs.append(Sample(job.row_chars, len(job.handles), clock() - started))
        report.job_calls.append(job.calls)
        report.job_nodes.append(len(job.handles))
    return report
