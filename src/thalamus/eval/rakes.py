"""Rake registry and the adjudication window — Class A, stage 0 (lab/024 §2.1).

A **rake** is a `problem` Claim carrying a `SOLVED_BY` edge: a mistake already made
and already resolved, registered by ordinary distillation rather than by anyone
authoring a fixture. lab/024 §2.1 proposes scoring whether later real sessions step
on them again — an in-deployment measurement over the operator's own traffic, where
the demand is real because work was happening, not because a task presented it.

**This module is stage 0 and deliberately claims no outcome.** It builds the registry,
decides which rakes are even *observable*, and emits the (rake, later-session) pairs a
future adjudicator would have to judge. It never says a rake was hit. Proximity is not
an encounter, and the gap between them is the whole of stages 1-3.

Three findings from the first run against the live graph shaped the design, and each
is reported rather than hidden:

- **Claim identity does not detect recurrence.** Claims are content-addressed on
  (kind, normalized description), so a re-asserted problem is supposed to converge onto
  one vertex with two CONTAINS edges. Across 125 sessions that fired 4 times in 504.
  `converged` is reported every run so the number stays visible instead of being
  assumed; a detector keyed on it would score ~1% of the corpus.
- **Unobservable is not "never hit."** A rake whose artifacts no later session ever
  touched offers no encounter to observe. It is bucketed apart and never folded into a
  denominator — the same discipline layer-1 attribution already applies to empty
  windows (`attribution.outputs_after`), where "no window" and "ignored" are different
  verdicts.
- **Artifact identifiers collide across projects.** Artifact is global and keyed on
  `identifier`, so one `README.md` / `pyproject.toml` / `CLAUDE.md` vertex is shared by
  every project that touched it. Pairs are therefore gated on the later session sharing
  the rake's originating project, and the cross-project pairs that gate drops are
  counted and disclosed rather than silently discarded.

Prior work. Deciding whether a later failure is *the same* failure is the duplicate /
false-alert classification problem, and the field's discipline is to classify from
failure properties and flag rather than exclude: Fair (arXiv 2111.03382) separates
legitimate failures from false alerts without repeated reruns, and arXiv 2605.05564
names repeated error messages as a discriminating feature for unrelated build failures
— the same flag-never-exclude rule the infra classifier and the escape detector already
follow (docs/11 §2a). Scoring an obligation discharged or violated rather than answer
quality is AOEP-v0 (`scope:literature:claim:db78a71b570e17ce`). The measurement is
observational: it can establish recurrence rates and their trend, never causation.
Randomization is lab/024 §2.4 (arXiv 2009.00148 switchback, 2309.07353 anytime-valid);
the quasi-experimental alternative is interrupted time series with a second control
group (arXiv 2603.17281), and layer 2b has no control series at all, since every real
session ran with memory on.

Deciding "same failure, different text" is duplicate-bug-report retrieval and crash
deduplication (docs/11 §2e). Both point stage 2's adjudicator at the simple end:
aggregate similarity over the rake's whole group plus timestamps rather than a single
nearest neighbour, with kNN competitive against the fuller method (arXiv 2205.00212),
and a simpler technique beating sophisticated ones on a debiased benchmark (arXiv
2212.00548). That paper's other finding binds this module: **detector accuracy is
sensitive to data age**, so a validation is a rolling check, never a one-time result.
The open blocker is ground truth — those fields grade against human-labelled duplicate
links and nothing labels a rake encounter, so a hand-audited precision estimate on the
candidate queue precedes any adjudicator.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from gremlin_python.process.graph_traversal import GraphTraversalSource, __
from gremlin_python.process.traversal import T

# Dials — arbitrary, here to be pressure-tested (the same posture as the attribution
# thresholds in docs/04 and the pin-report floors in eval/pins.py).
#
# An artifact touched by very many sessions is a weak key: "a later session opened
# README.md" carries almost no evidence that it met a specific rake. Pairs keyed on
# one are counted apart so a handful of hot files cannot silently dominate the
# adjudication queue. They are flagged, never dropped (arXiv 2111.03382).
HOT_ARTIFACT_SESSIONS = 10


@dataclass(frozen=True)
class SessionRow:
    """One Session, as the window calculation needs it."""

    vid: str
    session_id: str = ""
    project: str = ""
    ts: str = ""  # ISO-8601; lexical compare is chronological


@dataclass(frozen=True)
class Rake:
    """A `problem` Claim with a `SOLVED_BY` edge, plus the keys it can be matched on."""

    vid: str
    description: str
    category: str = ""
    scope: str = ""
    artifacts: tuple[str, ...] = ()
    sessions: tuple[str, ...] = ()  # Session vids containing this claim


@dataclass(frozen=True)
class Candidate:
    """A (rake, later session) pair a future adjudicator would have to judge.

    A candidate is *proximity*: the later session touched an artifact the rake names.
    It asserts nothing about whether the rake was met, which is why nothing in this
    module reads `hit`.
    """

    rake_vid: str
    session_vid: str
    artifacts: tuple[str, ...]  # the shared keys that generated the pair
    hot: bool = False  # every shared key is a low-specificity (hot) artifact


@dataclass
class RakeReport:
    problems: int = 0
    rakes: int = 0
    converged: int = 0  # rakes asserted in >=2 sessions — the identity detector's yield
    unkeyable: int = 0  # no TOUCHES artifact at all
    unobservable: int = 0  # keyed, but no later same-project session touched it
    observable: int = 0
    candidates: list[Candidate] = field(default_factory=list)
    cross_project_dropped: int = 0  # pairs the project gate removed
    hot_artifacts: dict[str, int] = field(default_factory=dict)  # identifier -> sessions
    categories: Counter = field(default_factory=Counter)  # observable rakes by category
    projects: Counter = field(default_factory=Counter)  # observable rakes by origin

    @property
    def specific_candidates(self) -> list[Candidate]:
        return [c for c in self.candidates if not c.hot]

    def render(self) -> str:
        lines = [
            "Rake registry — Class A stage 0 (lab/024 §2.1)",
            "  candidates are proximity, not encounters: no rake is scored hit or missed here",
            f"  dial: artifacts touched by >{HOT_ARTIFACT_SESSIONS} sessions are low-specificity keys",
            "",
            f"problem Claims: {self.problems}",
            f"  with SOLVED_BY (rakes): {self.rakes}",
        ]
        if not self.rakes:
            lines.append("")
            lines.append("No rakes registered — distillation has extracted no solved problems.")
            return "\n".join(lines)

        pct = 100.0 * self.observable / self.rakes
        lines.append("")
        lines.append("window:")
        lines.append(f"  unkeyable (no artifact):        {self.unkeyable}")
        lines.append(
            f"  unobservable (no later session): {self.unobservable}"
            "  — not 'never hit'; there was nothing to observe"
        )
        lines.append(f"  observable:                     {self.observable} ({pct:.0f}%)")
        lines.append("")
        specific = self.specific_candidates
        lines.append(
            f"adjudication queue: {len(self.candidates)} (rake, later-session) pair(s) — "
            f"{len(specific)} on specific keys, {len(self.candidates) - len(specific)} "
            "on hot artifacts only"
        )
        if self.cross_project_dropped:
            lines.append(
                f"  excluded: {self.cross_project_dropped} cross-project pair(s) — Artifact "
                "is global, so relative paths (README.md, pyproject.toml) collide between "
                "projects"
            )
        lines.append(
            f"  identity-converged rakes: {self.converged}/{self.rakes} — the "
            "content-addressed recurrence detector's entire yield"
        )
        if self.hot_artifacts:
            lines.append("")
            lines.append("low-specificity keys (flagged, not dropped):")
            for identifier, count in sorted(
                self.hot_artifacts.items(), key=lambda kv: (-kv[1], kv[0])
            )[:10]:
                lines.append(f"  {count:3d} sessions  {identifier}")
        if self.categories:
            lines.append("")
            lines.append(
                "observable rakes by category: "
                + ", ".join(f"{c} {n}" for c, n in self.categories.most_common())
            )
        if self.projects:
            lines.append(
                "observable rakes by origin project: "
                + ", ".join(f"{p or '(none)'} {n}" for p, n in self.projects.most_common())
            )
        return "\n".join(lines)


def build_rake_report(
    rakes: list[Rake],
    sessions: dict[str, SessionRow],
    artifact_sessions: dict[str, list[str]],
    problems: int | None = None,
) -> RakeReport:
    """Pure aggregation — the graph reader feeds this; tests exercise it directly.

    `artifact_sessions` maps an Artifact identifier to the Session vids that touched it.
    A rake is *observable* when some session outside its own, later than the one that
    registered it and in the same project, touched an artifact it names.
    """
    report = RakeReport(problems=problems if problems is not None else len(rakes))
    report.rakes = len(rakes)

    touch_counts = {a: len(set(s)) for a, s in artifact_sessions.items()}

    for rake in rakes:
        own = [sessions[v] for v in rake.sessions if v in sessions]
        if len(rake.sessions) >= 2:
            report.converged += 1
        if not rake.artifacts:
            report.unkeyable += 1
            continue

        # Registered when the earliest session asserting it ran. A rake with no
        # resolvable session has no registration time and cannot bound "later" —
        # it is unobservable rather than silently compared against the empty string.
        dated = sorted((s.ts for s in own if s.ts))
        if not dated:
            report.unobservable += 1
            continue
        registered = dated[0]
        origin_projects = {s.project for s in own}
        own_vids = set(rake.sessions)

        shared: dict[str, list[str]] = {}
        for identifier in rake.artifacts:
            for vid in artifact_sessions.get(identifier, ()):
                if vid in own_vids:
                    continue
                later = sessions.get(vid)
                if later is None or not later.ts or later.ts <= registered:
                    continue
                if origin_projects and later.project not in origin_projects:
                    report.cross_project_dropped += 1
                    continue
                shared.setdefault(vid, []).append(identifier)

        if not shared:
            report.unobservable += 1
            continue

        report.observable += 1
        report.categories[rake.category or "(none)"] += 1
        for project in sorted(origin_projects):
            report.projects[project] += 1
            break
        for vid, identifiers in shared.items():
            keys = tuple(sorted(set(identifiers)))
            report.candidates.append(
                Candidate(
                    rake_vid=rake.vid,
                    session_vid=vid,
                    artifacts=keys,
                    hot=all(touch_counts.get(k, 0) > HOT_ARTIFACT_SESSIONS for k in keys),
                )
            )
        for identifier in rake.artifacts:
            if touch_counts.get(identifier, 0) > HOT_ARTIFACT_SESSIONS:
                report.hot_artifacts[identifier] = touch_counts[identifier]

    report.candidates.sort(key=lambda c: (c.rake_vid, c.session_vid))
    return report


def _vid(row: dict) -> str:
    return str(row.get(T.id) or row.get("id") or "")


def read_rakes(g: GraphTraversalSource) -> tuple[list[Rake], dict[str, SessionRow], dict[str, list[str]], int]:
    """Read the registry, the session timeline, and the artifact touch index."""
    sessions = {
        _vid(row): SessionRow(
            vid=_vid(row),
            session_id=str(row.get("session_id") or ""),
            project=str(row.get("project") or ""),
            ts=str(row.get("ts") or ""),
        )
        for row in g.V()
        .has_label("Session")
        .project("id", "session_id", "project", "ts")
        .by(__.id_())
        .by(__.coalesce(__.values("session_id"), __.constant("")))
        .by(__.coalesce(__.values("project"), __.constant("")))
        .by(__.coalesce(__.values("timestamp"), __.values("ingested_at"), __.constant("")))
        .to_list()
    }

    artifact_sessions = {
        str(row["id"]): [str(v) for v in row["sessions"]]
        for row in g.V()
        .has_label("Artifact")
        .project("id", "sessions")
        .by("identifier")
        .by(__.in_("TOUCHES").in_("CONTAINS").has_label("Session").id_().dedup().fold())
        .to_list()
    }

    problems = g.V().has_label("Claim").has("kind", "problem").count().next()

    rakes = [
        Rake(
            vid=str(row["id"]),
            description=str(row["description"]),
            category=str(row["category"]),
            scope=str(row["scope"]),
            artifacts=tuple(str(a) for a in row["artifacts"]),
            sessions=tuple(str(s) for s in row["sessions"]),
        )
        for row in g.V()
        .has_label("Claim")
        .has("kind", "problem")
        .where(__.out("SOLVED_BY"))
        .project("id", "description", "category", "scope", "artifacts", "sessions")
        .by(__.id_())
        .by(__.coalesce(__.values("description"), __.constant("")))
        .by(__.coalesce(__.values("category"), __.constant("")))
        .by(__.coalesce(__.values("scope"), __.constant("")))
        .by(__.out("TOUCHES").has_label("Artifact").values("identifier").dedup().fold())
        .by(__.in_("CONTAINS").has_label("Session").id_().dedup().fold())
        .to_list()
    ]
    return rakes, sessions, artifact_sessions, int(problems)


def rake_report(g: GraphTraversalSource) -> RakeReport:
    rakes, sessions, artifact_sessions, problems = read_rakes(g)
    return build_rake_report(rakes, sessions, artifact_sessions, problems=problems)
