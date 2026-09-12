"""Read the attribution subgraphs back out of the graph.

A claim's attribution subgraph is what `USES` records: the nodes it reasoned with
(`role: reason`) and the alternatives the decision turned down (`role: rejected`).
The edge landed 2026-09-02 and wrote its first live edge the next day. For the nine
days after that the only way to see what it had produced was an ad-hoc traversal,
which is how a landed feature stays flat without anyone noticing — the graph held 54
reason edges, none of which reached a claim that cites anything itself, and no
surface said so.

Four questions, deliberately not pooled into one number:

- **Reach** — of the sessions that were offered handles to cite, how many cited any.
- **Shape** — whether attribution *compounds*. An edge onto a claim that is itself a
  citer is the two-hop structure the edge exists for; a graph of one-hop stars is a
  citation log with no lineage in it.
- **The stamp** — `verified` is `eval sync`'s served-by-trace mark and it governs
  `role: reason`. Pooled across roles it reports on a rule that cannot apply to most
  of its own denominator, so the roles are rendered apart.
- **Targets** — what gets cited: own-scope experience or another scope's knowledge,
  Claim or Chunk.

None of this is a utility claim. A cited node is one the model named, which is
weaker evidence than ablation (ContextCite's LDS and top-k logprob drop, arXiv
2409.00729) and stronger than lexical overlap, which is what the used/ignored judge
in `report.py` has. The survey that catalogues these families rates evidence
attribution an established evaluation area and *dependency coverage* — the shape
half of this report — a proposed one, with metrics that are "desiderata without
agreed definitions" (arXiv 2606.04990). The depth figures here are one instantiation
of that desideratum, not a standard anyone else computes the same way.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from gremlin_python.process.graph_traversal import GraphTraversalSource, __
from gremlin_python.process.traversal import T

from thalamus.eval.rates import Rate, wilson_interval
from thalamus.eval.report import parse_window_bound

# The stamping rule `eval sync` writes, and the only role it can speak about. A
# rejected alternative is minted by the extraction that rejected it, so no trace ever
# served it and "not served" is the rule reporting on a case outside itself.
STAMPED_ROLE = "reason"

# How `verified` reads on the line. Absent is its own state: sync has not visited the
# session, which is not the same as having looked and found nothing.
_STAMP_LABELS = {"true": "served", "false": "not served", "": "unchecked"}

_COVERAGE_NULL_REASON = (
    "citation coverage is a census of a write path, not a discrimination test — "
    "there is no chance model under which a session cites an offered handle, so the "
    "figure to read this against is the same window later, not a null"
)

_OFFERED_CAVEAT = (
    "offered = the session has a landed Trace returning a Claim or Chunk. The digest "
    "reads its own offer list from the trace tap at distillation time and caps it at "
    "120 entries, so this denominator is a proxy for what was actually offered, not a "
    "copy of it"
)

_STAMP_CAVEAT = (
    "near-constant by construction: the handles a claim may cite are drawn from the "
    "same retrievals the stamp checks, so this verifies the write path and that the "
    "traces landed — not that the node was reasoned with"
)


@dataclass
class UsesReport:
    """The attribution surface for one scope, or for every scope at once."""

    scope: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    # Sessions by what they did with what they were offered.
    cited: int = 0
    offered_uncited: int = 0
    unoffered: int = 0
    undated: int = 0
    out_of_window: int = 0
    # Earliest session that cited anything — a data-derived proxy for when the write
    # path started producing, so a lifetime denominator can say what it is holding.
    first_cited: datetime | None = None
    # scope -> [cited, offered]
    by_scope: dict[str, list[int]] = field(default_factory=dict)
    # Edge-level, `role: reason` only unless the name says otherwise.
    roots: int = 0
    reason_edges: int = 0
    both_ends: int = 0
    longest_chain: int = 0
    # role -> stamp label -> count
    stamps: dict[str, Counter] = field(default_factory=dict)
    target_labels: Counter = field(default_factory=Counter)
    target_reach: Counter = field(default_factory=Counter)
    # The extract half of stage 1, censused rather than measured.
    rejected_claims: int = 0
    outcome_kinds: Counter = field(default_factory=Counter)

    @property
    def offered(self) -> int:
        return self.cited + self.offered_uncited

    def _coverage(self) -> Rate:
        return Rate(
            label="citation coverage",
            hits=self.cited,
            total=self.offered,
            unit="session(s)",
            interval=wilson_interval(self.cited, self.offered) if self.offered else None,
            interval_reason=(
                "no sessions were offered anything in this window" if not self.offered else ""
            ),
            null=None,
            null_reason=_COVERAGE_NULL_REASON,
            note=_OFFERED_CAVEAT,
        )

    def render(self) -> str:
        where = f"scope `{self.scope}`" if self.scope else "all scopes"
        lines = [f"Attribution subgraphs — {where} (stage-1 `USES`)"]
        if self.since or self.until:
            window = f"{self.since or 'start'} .. {self.until or 'now'}"
            lines.append(f"  window: {window} (by containing-session timestamp)")
        if self.out_of_window or self.undated:
            lines.append(
                f"  {self.out_of_window} session(s) outside the window, "
                f"{self.undated} with no parseable timestamp — both excluded, not assumed in"
            )

        lines.append(
            f"  reach: {self.offered} session(s) were offered handles and {self.cited} "
            f"cited one; {self.unoffered} more had no retrieval to offer"
        )
        lines.append("    " + self._coverage().render())
        if self.first_cited and not (self.since or self.until):
            lines.append(
                f"    ^ the earliest session that cited anything is "
                f"{self.first_cited.date()}. A session that ran before the write path "
                "existed could not have cited, and this denominator holds all of them "
                "— narrow with `--since` to read coverage over the period the edge has "
                "been writable"
            )
        offering = {
            scope: counts for scope, counts in self.by_scope.items() if counts[1]
        }
        if offering:
            per = " · ".join(
                f"{scope} {counts[0]}/{counts[1]}"
                for scope, counts in sorted(
                    offering.items(), key=lambda kv: (-kv[1][1], kv[0])
                )
            )
            lines.append(f"    by scope (cited/offered): {per}")
            silent = sorted(set(self.by_scope) - set(offering))
            if silent:
                lines.append(
                    "    offered nothing in this window: " + ", ".join(silent)
                )

        if self.reason_edges:
            per_root = self.reason_edges / self.roots if self.roots else 0.0
            lines.append(
                f"  shape: {self.roots} root claim(s), {self.reason_edges} reason edge(s), "
                f"{per_root:.1f} target(s) per root"
            )
            lines.append("    " + self._depth_line())
        else:
            lines.append("  shape: no reason edges here — nothing has been cited yet")

        if self.stamps:
            lines.append("  the stamp (`served-by-trace/1`), by role:")
            for role in sorted(self.stamps, key=lambda r: (r != STAMPED_ROLE, r)):
                counts = self.stamps[role]
                spread = ", ".join(
                    f"{counts[label]} {label}"
                    for label in ("served", "not served", "unchecked")
                    if counts[label]
                )
                lines.append(f"    {role}: {spread}")
                if role == STAMPED_ROLE:
                    lines.append(f"    ^ {_STAMP_CAVEAT}")
                else:
                    lines.append(
                        f"    ^ the rule does not apply to `{role}` — the target is minted "
                        "by the same extraction and was never served, so these values "
                        "report on a case outside the rule (issue #202)"
                    )

        if self.target_labels:
            labels = " · ".join(
                f"{count} {label}" for label, count in self.target_labels.most_common()
            )
            lines.append(f"  targets: {labels}")
            if not self.target_labels.get("Chunk"):
                lines.append(
                    "    ^ Chunks are offered in every digest and have never been cited"
                )
            reach = " · ".join(
                f"{count} {kind}" for kind, count in self.target_reach.most_common()
            )
            lines.append(f"    reach: {reach}")

        lines.append(
            f"  extract half: {self.rejected_claims} `*/rejected` claim(s); "
            f"outcome_kind on {sum(self.outcome_kinds.values())}"
            + (
                " — " + " · ".join(
                    f"{kind} {count}" for kind, count in self.outcome_kinds.most_common()
                )
                if self.outcome_kinds
                else ""
            )
        )
        return "\n".join(lines)

    def _depth_line(self) -> str:
        if self.longest_chain < 0:
            return "depth: the reason relation has a cycle, so no longest chain is defined"
        if self.longest_chain <= 1:
            return (
                "depth: 1 hop — no cited claim cites anything itself, so every subgraph "
                "is a star and nothing has compounded yet"
            )
        return (
            f"depth: {self.longest_chain} hops; {self.both_ends} claim(s) both cite and "
            "are cited"
        )


def uses_report(
    g: GraphTraversalSource,
    scope: str | None = None,
    since: str | datetime | None = None,
    until: str | datetime | None = None,
) -> UsesReport:
    """Census the `USES` edges and the sessions that had the chance to write one.

    Scope narrows the *root* of a subgraph, never its reach: an edge from a `main`
    claim into a literature claim belongs to main's attribution, and filtering by the
    target's scope would hide the cross-scope citations the edge is allowed to make.

    The window is applied to the containing session's timestamp, because a claim
    carries none of its own — it is content-addressed and can be contained by several
    sessions, in which case the earliest one dates it.
    """
    since_ts = parse_window_bound(since)
    until_ts = parse_window_bound(until, end_of_day=True)
    report = UsesReport(scope=scope, since=since_ts, until=until_ts)

    dated: dict[str, datetime | None] = {}
    for row in _session_rows(g, scope):
        stamp = _stamp(row.get("ts"))
        vid = str(row.get("id") or "")
        if since_ts or until_ts:
            if stamp is None:
                report.undated += 1
                continue
            if (since_ts and stamp < since_ts) or (until_ts and stamp > until_ts):
                report.out_of_window += 1
                continue
        dated[vid] = stamp
        session_scope = str(row.get("scope") or "")
        counts = report.by_scope.setdefault(session_scope, [0, 0])
        if _as_int(row.get("reason_edges")):
            report.cited += 1
            counts[0] += 1
            counts[1] += 1
            if stamp and (report.first_cited is None or stamp < report.first_cited):
                report.first_cited = stamp
        elif _as_int(row.get("offered")):
            report.offered_uncited += 1
            counts[1] += 1
        else:
            report.unoffered += 1

    in_window = _claims_in_window(g, dated) if (since_ts or until_ts) else None
    pairs: list[tuple[str, str]] = []
    roots: set[str] = set()
    for row in _edge_rows(g, scope):
        root = str(row.get("root") or "")
        if in_window is not None and root not in in_window:
            continue
        role = str(row.get("role") or "")
        stamp = _stamp_label(row.get("verified"))
        report.stamps.setdefault(role, Counter())[stamp] += 1
        if role != STAMPED_ROLE:
            continue
        target = str(row.get("target") or "")
        report.reason_edges += 1
        roots.add(root)
        pairs.append((root, target))
        report.target_labels[str(row.get("target_label") or "")] += 1
        report.target_reach[_reach(row)] += 1

    report.roots = len(roots)
    report.both_ends = len(roots & {target for _root, target in pairs})
    report.longest_chain = _longest_chain(pairs)
    report.rejected_claims = _rejected_claims(g, scope)
    report.outcome_kinds = _outcome_kinds(g, scope)
    return report


def _session_rows(g: GraphTraversalSource, scope: str | None) -> list[dict]:
    """One row per session: did it cite, and was it offered anything to cite.

    `offered` is capped at one by `limit(1)`: the question is whether the session had
    a handle at all, and counting every returned node would walk the whole RETURNS
    population to answer a boolean.
    """
    traversal = g.V().has_label("Session")
    if scope:
        traversal = traversal.has("scope", scope)
    try:
        return (
            traversal.project("id", "scope", "ts", "reason_edges", "offered")
            .by(T.id)
            .by(__.coalesce(__.values("scope"), __.constant("")))
            .by(__.coalesce(__.values("timestamp"), __.constant("")))
            .by(__.out("CONTAINS").out_e("USES").has("role", STAMPED_ROLE).count())
            .by(__.out("QUERIES").out("RETURNS").has_label("Claim", "Chunk").limit(1).count())
            .to_list()
        )
    except Exception:
        return []


def _edge_rows(g: GraphTraversalSource, scope: str | None) -> list[dict]:
    """Every `USES` edge, with what the report needs to place its target."""
    traversal = g.E().has_label("USES")
    try:
        rows = (
            traversal.project(
                "root",
                "root_scope",
                "target",
                "target_label",
                "target_scope",
                "target_contained",
                "role",
                "verified",
            )
            .by(__.out_v().id_())
            .by(__.out_v().coalesce(__.values("scope"), __.constant("")))
            .by(__.in_v().id_())
            .by(__.in_v().label())
            .by(__.in_v().coalesce(__.values("scope"), __.constant("")))
            .by(__.in_v().in_e("CONTAINS").count())
            .by(__.coalesce(__.values("role"), __.constant("")))
            .by(__.coalesce(__.values("verified"), __.constant("")))
            .to_list()
        )
    except Exception:
        return []
    if not scope:
        return rows
    return [row for row in rows if str(row.get("root_scope") or "") == scope]


def _claims_in_window(g: GraphTraversalSource, dated: dict[str, datetime | None]) -> set[str]:
    """Claims contained by a session inside the window.

    A converged claim sits in several sessions; one of them being in the window puts
    the claim in it. Dating it by the earliest instead would drop an edge whose claim
    first appeared before the window and was re-asserted inside it.
    """
    try:
        if not dated:
            return set()
        rows = g.V(*list(dated)).out("CONTAINS").has_label("Claim").id_().to_list()
    except Exception:
        return set()
    return {str(vid) for vid in rows}


def _rejected_claims(g: GraphTraversalSource, scope: str | None) -> int:
    """Claims minted as a scope-namespaced `<scope>/rejected` alternative.

    The kinds are read back and matched here rather than filtered with a text
    predicate, so the count does not depend on which `TextP` the server dialect
    supports.
    """
    traversal = g.V().has_label("Claim")
    if scope:
        traversal = traversal.has("scope", scope)
    try:
        kinds = traversal.values("kind").to_list()
    except Exception:
        return 0
    return sum(1 for kind in kinds if str(kind).endswith("/rejected"))


def _outcome_kinds(g: GraphTraversalSource, scope: str | None) -> Counter:
    traversal = g.V().has_label("Claim").has("outcome_kind")
    if scope:
        traversal = traversal.has("scope", scope)
    try:
        return Counter(str(kind) for kind in traversal.values("outcome_kind").to_list())
    except Exception:
        return Counter()


def _reach(row: dict) -> str:
    """Where an edge lands, in the terms the write path enforces."""
    root_scope = str(row.get("root_scope") or "")
    target_scope = str(row.get("target_scope") or "")
    if target_scope == root_scope:
        return "within the root's own scope"
    if _as_int(row.get("target_contained")):
        return "into another scope's episodic memory (the write path drops these)"
    return "into another scope's knowledge"


def _longest_chain(pairs: list[tuple[str, str]]) -> int:
    """Longest run of reason edges, in hops. 1 means every subgraph is a star.

    Returns -1 when the relation has a cycle, which has no longest path. A cycle is
    possible in principle — two claims each citing the other across sessions — and
    saying so beats reporting a number computed over an arbitrary cut of it.
    """
    outgoing: dict[str, list[str]] = defaultdict(list)
    indegree: Counter = Counter()
    nodes: set[str] = set()
    for source, target in pairs:
        outgoing[source].append(target)
        indegree[target] += 1
        nodes |= {source, target}
    queue = [node for node in nodes if not indegree[node]]
    distance = dict.fromkeys(nodes, 0)
    visited = 0
    while queue:
        node = queue.pop()
        visited += 1
        for nxt in outgoing[node]:
            distance[nxt] = max(distance[nxt], distance[node] + 1)
            indegree[nxt] -= 1
            if not indegree[nxt]:
                queue.append(nxt)
    if visited != len(nodes):
        return -1
    return max(distance.values(), default=0)


def _stamp_label(raw: object) -> str:
    return _STAMP_LABELS.get(str(_first(raw)).lower(), "unchecked")


def _stamp(raw: object) -> datetime | None:
    try:
        return parse_window_bound(str(_first(raw)) or None)
    except ValueError:
        return None


def _first(value: object) -> object:
    return value[0] if isinstance(value, list) and value else value


def _as_int(value: object) -> int:
    try:
        return int(str(_first(value)))
    except (TypeError, ValueError):
        return 0
