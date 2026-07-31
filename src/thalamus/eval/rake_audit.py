"""Class A stage 0.5 — the hand-audited precision estimate for the rake queue.

Stage 0 (`rakes.py`) emits candidate (rake, later-session) pairs and claims no
outcome: a candidate is proximity, never an encounter. Nothing in the corpus labels
an encounter, so the queue's precision is unknown, and a stage-2 adjudicator built
on an unmeasured queue would silently inherit whatever the proximity rule's error
rate turns out to be. This module draws the sample a human labels, and scores the
labels when they come back.

Three properties come from the literature rather than from taste:

- **The draw is uniform over the specific-key stratum, seeded before any pair is
  read.** Judging the most convincing candidates first — the active-selection shape —
  biases the estimate toward the system that built the pool (arXiv 1709.01709). The
  stratum boundary is `rakes.HOT_ARTIFACT_SESSIONS`, published before the sample
  existed, not a line drawn after seeing it.

- **The worksheet withholds the shared artifact keys.** Those keys are the proximity
  rule's own evidence; printing them asks the annotator to ratify the system instead
  of judging the sessions. Each item renders what the later session did and nothing
  about why the queue paired it.

- **Decoys are rendered indistinguishably.** `DECOY_SHARE` of items are (rake, later
  same-project session) pairs the queue did *not* emit — inside the observation
  window, sharing no artifact. They measure the annotator, not the queue. A decoy
  labelled `hit` is not automatically an error: a session can meet a problem without
  touching the artifact the problem was recorded against. The decoy rate is therefore
  an upper bound on annotator laxity, and is reported as one.

A single annotator has no inter-annotator agreement to report, which is exactly the
case arXiv 2606.02255 finds least documented across NLP. What it says to disclose
instead is what this module emits: the rubric ships inline with the items (guideline
availability), and the score reports volume, the abstain count, and the decoy rate
rather than dropping any of them — `unclear` is a third bucket, never folded into
either side of the ratio (the flag-never-drop rule of arXiv 2111.03382, and the same
discipline layer-1 attribution applies to empty windows).
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

# wilson_interval has one definition, in eval/rates.py, so a fix reaches every
# rate; re-exported here because this module's callers have always found it here.
from thalamus.eval.rates import wilson_interval  # noqa: F401
from thalamus.eval.rakes import (
    Candidate,
    Rake,
    RakeReport,
    SessionRow,
    in_window,
    observation_window,
)

# Dials — arbitrary, here to be pressure-tested, same posture as HOT_ARTIFACT_SESSIONS.
#
# 40 labels put the 95% half-width near ±0.14 at p≈0.3 on a 278-pair stratum: enough
# to separate "the queue is mostly noise" from "the queue is mostly real", which is
# the decision stage 2 is waiting on. It is not enough to rank two detectors against
# each other, and the score says so rather than implying more resolution than 40
# hand judgments can carry.
SAMPLE_SIZE = 40
DECOY_SHARE = 0.25  # decoys as a fraction of the real sample
ARTIFACT_PREVIEW = 12  # later-session artifacts rendered per item, before truncation

LABELS = ("hit", "miss", "unclear")

# `[ \t]*`, never `\s*`: `\s` crosses newlines, so an unfilled `- **label**: ` line
# would match the `-` starting the line below it and every item would read as a
# malformed label instead of an empty one.
_LABEL_LINE = re.compile(r"^-[ \t]*\*\*label\*\*:[ \t]*(\S*)", re.IGNORECASE | re.MULTILINE)
_ITEM_HEAD = re.compile(r"^##\s+Item\s+(\d+)\b", re.MULTILINE)


@dataclass(frozen=True)
class AuditItem:
    """One pair put in front of the annotator, real or decoy, rendered identically."""

    number: int
    rake_vid: str
    session_vid: str
    decoy: bool
    problem: str = ""
    solution: str = ""
    category: str = ""
    project: str = ""
    registered: str = ""
    later_ts: str = ""
    later_summary: str = ""
    later_artifacts: tuple[str, ...] = ()
    later_artifact_total: int = 0


@dataclass
class AuditSample:
    seed: int
    items: list[AuditItem] = field(default_factory=list)
    stratum_size: int = 0  # specific-key candidates the real items were drawn from
    distinct_rakes: int = 0  # in the real sample — the clustering the CI has to answer for
    decoys_requested: int = 0
    decoys_drawn: int = 0  # rakes with no non-sharing later session yield none

    @property
    def real(self) -> list[AuditItem]:
        return [i for i in self.items if not i.decoy]


def draw_sample(
    report: RakeReport,
    rakes: list[Rake],
    sessions: dict[str, SessionRow],
    *,
    seed: int,
    size: int = SAMPLE_SIZE,
    decoy_share: float = DECOY_SHARE,
) -> AuditSample:
    """Draw the audit sample: uniform over specific-key candidates, plus decoys.

    Uniform rather than adaptive on purpose. The adaptive half of arXiv 1709.01709
    varies a distribution over *systems*; there is one system here — stage 0's
    proximity rule — so there is nothing to vary over, and what carries across is
    its warning about which candidates get judged.
    """
    rng = random.Random(seed)
    by_vid = {r.vid: r for r in rakes}

    stratum = sorted(
        report.specific_candidates, key=lambda c: (c.rake_vid, c.session_vid)
    )
    real = rng.sample(stratum, min(size, len(stratum)))

    decoys_requested = int(round(len(real) * decoy_share))
    decoys = _draw_decoys(real, by_vid, sessions, rng, decoys_requested)

    drawn = [(c, False) for c in real] + [(c, True) for c in decoys]
    rng.shuffle(drawn)

    items = [
        _build_item(number, candidate, decoy, by_vid, sessions)
        for number, (candidate, decoy) in enumerate(drawn, start=1)
    ]
    return AuditSample(
        seed=seed,
        items=items,
        stratum_size=len(stratum),
        distinct_rakes=len({c.rake_vid for c in real}),
        decoys_requested=decoys_requested,
        decoys_drawn=len(decoys),
    )


def _draw_decoys(
    real: list[Candidate],
    by_vid: dict[str, Rake],
    sessions: dict[str, SessionRow],
    rng: random.Random,
    wanted: int,
) -> list[Candidate]:
    """Pairs inside the observation window that share no artifact with the rake.

    Drawn from the same rakes as the real sample so a decoy cannot be spotted by its
    problem statement being unfamiliar — only the pairing is different.
    """
    if wanted <= 0:
        return []
    pool: list[Candidate] = []
    for rake_vid in sorted({c.rake_vid for c in real}):
        rake = by_vid.get(rake_vid)
        if rake is None:
            continue
        window = observation_window(rake, sessions)
        if window is None:
            continue
        sharing = {c.session_vid for c in real if c.rake_vid == rake_vid}
        for vid in sorted(sessions):
            if vid in sharing or not in_window(window, sessions[vid]):
                continue
            pool.append(Candidate(rake_vid=rake_vid, session_vid=vid, artifacts=()))
    return rng.sample(pool, min(wanted, len(pool)))


def _build_item(
    number: int,
    candidate: Candidate,
    decoy: bool,
    by_vid: dict[str, Rake],
    sessions: dict[str, SessionRow],
) -> AuditItem:
    rake = by_vid.get(candidate.rake_vid)
    later = sessions.get(candidate.session_vid)
    window = observation_window(rake, sessions) if rake else None
    artifacts = tuple(sorted(later.artifacts)) if later else ()
    return AuditItem(
        number=number,
        rake_vid=candidate.rake_vid,
        session_vid=candidate.session_vid,
        decoy=decoy,
        problem=rake.description if rake else "",
        solution=rake.solution if rake else "",
        category=rake.category if rake else "",
        project=(later.project if later else ""),
        registered=window.registered if window else "",
        later_ts=later.ts if later else "",
        later_summary=later.summary if later else "",
        later_artifacts=artifacts[:ARTIFACT_PREVIEW],
        later_artifact_total=len(artifacts),
    )


RUBRIC = """\
## How to label

For each item you are shown a **problem that was already solved** in one session,
and a **later session in the same project**. One question:

> Did the later session run into that same problem again?

- `hit` — the later session hit this problem again: re-diagnosed it, re-debugged it,
  worked around it, or was slowed by it. It counts even if it was solved faster the
  second time. The problem recurring is the event, not whether it cost much.
- `miss` — the later session did not meet this problem. It worked in the same area,
  or on something else entirely, but this specific problem never came up.
- `unclear` — you cannot tell from what is shown. Use this freely; it is reported as
  its own number and is not counted against either side.

Two things to keep in mind:

- **Judge the later session, not the pairing.** Some items are deliberately paired at
  random as a control on the labelling. You are not being asked to guess which.
- **Same problem, not same file.** Two sessions touching one module is not a
  recurrence. The problem itself has to have come back.

Write your answer on the `- **label**:` line under each item. Leave the rest alone —
scoring joins on the item numbers, so renumbering or deleting an item silently
misaligns the labels (it will complain, but only if the counts stop matching).
"""


def render_worksheet(sample: AuditSample) -> str:
    """The annotator's file: rubric, then items, with nothing identifying the decoys."""
    # Seed only. The composition — how many items are decoys — stays out, because an
    # annotator who knows the count can calibrate to it, which is the same failure as
    # being able to spot them individually.
    lines = [
        f"<!-- audit seed={sample.seed} -->",
        "# Rake queue precision audit",
        "",
        f"{len(sample.items)} items, drawn against a {sample.stratum_size}-pair "
        f"stratum (seed {sample.seed}). Roughly an hour of labelling.",
        "",
        RUBRIC,
        "---",
        "",
    ]
    for item in sample.items:
        lines.append(f"## Item {item.number}")
        lines.append("")
        lines.append(f"**The problem** ({item.category or 'uncategorized'}):")
        lines.append(f"> {item.problem or '(no description recorded)'}")
        lines.append("")
        if item.solution:
            lines.append("**How it was solved:**")
            lines.append(f"> {item.solution}")
            lines.append("")
        lines.append(
            f"**Solved** {item.registered[:10] or '(undated)'} · "
            f"**later session** {item.later_ts[:10] or '(undated)'} · "
            f"{item.project or '(no project)'}"
        )
        lines.append("")
        lines.append("**What the later session did:**")
        lines.append(f"> {item.later_summary or '(no summary recorded)'}")
        lines.append("")
        if item.later_artifacts:
            shown = ", ".join(f"`{a}`" for a in item.later_artifacts)
            more = item.later_artifact_total - len(item.later_artifacts)
            suffix = f" (+{more} more)" if more > 0 else ""
            lines.append(f"**Files it touched:** {shown}{suffix}")
            lines.append("")
        lines.append("- **label**: ")
        lines.append("- **note**: ")
        lines.append("")
    return "\n".join(lines)


def parse_worksheet(text: str) -> tuple[dict[int, str], list[str]]:
    """Read labels back by item number. Returns (labels, problems-found)."""
    labels: dict[int, str] = {}
    problems: list[str] = []
    numbers = [int(m.group(1)) for m in _ITEM_HEAD.finditer(text)]
    raw = [m.group(1).strip().lower() for m in _LABEL_LINE.finditer(text)]
    if len(numbers) != len(raw):
        problems.append(
            f"{len(numbers)} item heading(s) but {len(raw)} label line(s) — "
            "an item was renumbered or a label line deleted; the join is not trustworthy"
        )
    for number, value in zip(numbers, raw):
        if not value:
            continue  # left blank — reported below as unlabelled, not as malformed
        if value not in LABELS:
            problems.append(
                f"item {number}: unrecognized label {value!r} (expected one of {', '.join(LABELS)})"
            )
            continue
        labels[number] = value
    missing = [n for n in numbers if n not in labels]
    if missing:
        shown = ", ".join(str(n) for n in missing[:10])
        more = f", +{len(missing) - 10} more" if len(missing) > 10 else ""
        problems.append(f"{len(missing)} item(s) left unlabelled: {shown}{more}")
    return labels, problems




def cluster_interval(
    per_rake: dict[str, list[bool]], rng: random.Random, draws: int = 5000
) -> tuple[float, float]:
    """Bootstrap resampling *rakes*, not pairs.

    Pairs sharing a rake are not independent — one rake contributes up to 8 pairs to
    the stratum — so the Wilson interval on pairs is optimistic. Resampling whole
    rakes prices that clustering in.
    """
    keys = sorted(per_rake)
    if not keys:
        return (0.0, 1.0)
    estimates = []
    for _ in range(draws):
        picked = [rng.choice(keys) for _ in keys]
        flat = [v for k in picked for v in per_rake[k]]
        if flat:
            estimates.append(sum(flat) / len(flat))
    if not estimates:
        return (0.0, 1.0)
    estimates.sort()
    lo = estimates[int(0.025 * (len(estimates) - 1))]
    hi = estimates[int(0.975 * (len(estimates) - 1))]
    return (lo, hi)


@dataclass
class AuditScore:
    seed: int = 0
    counts: Counter = field(default_factory=Counter)  # real items, by label
    decoy_counts: Counter = field(default_factory=Counter)
    labelled: int = 0
    stratum_size: int = 0
    distinct_rakes: int = 0
    wilson: tuple[float, float] = (0.0, 1.0)
    clustered: tuple[float, float] = (0.0, 1.0)
    parse_problems: list[str] = field(default_factory=list)

    @property
    def decided(self) -> int:
        return self.counts["hit"] + self.counts["miss"]

    @property
    def precision(self) -> float:
        return self.counts["hit"] / self.decided if self.decided else 0.0

    def render(self) -> str:
        lines = [
            "Rake queue precision audit — Class A stage 0.5",
            f"  sample: seed {self.seed}, {self.labelled} label(s) over a "
            f"{self.stratum_size}-pair specific-key stratum",
            "  annotator: the operator, single-annotator (no inter-annotator "
            "agreement exists to report — arXiv 2606.02255)",
            "",
        ]
        if self.parse_problems:
            lines.append("worksheet problems:")
            lines.extend(f"  ! {p}" for p in self.parse_problems)
            lines.append("")
        if not self.decided:
            lines.append("No decided labels — nothing to estimate.")
            return "\n".join(lines)

        lines.append(
            f"queue precision: {self.precision:.0%}  "
            f"({self.counts['hit']} hit / {self.decided} decided)"
        )
        lines.append(
            f"  unclear:  {self.counts['unclear']} — reported apart, in neither "
            "numerator nor denominator"
        )
        lines.append(f"  95% CI (Wilson, over pairs):     {self.wilson[0]:.0%}–{self.wilson[1]:.0%}")
        lines.append(
            f"  95% CI (bootstrap, over rakes):  {self.clustered[0]:.0%}–{self.clustered[1]:.0%}"
            f"  — {self.distinct_rakes} distinct rake(s); this is the honest one"
        )
        decoy_decided = self.decoy_counts["hit"] + self.decoy_counts["miss"]
        lines.append("")
        if decoy_decided:
            rate = self.decoy_counts["hit"] / decoy_decided
            lines.append(
                f"decoy hit rate: {rate:.0%} "
                f"({self.decoy_counts['hit']}/{decoy_decided}) — an *upper* bound on "
                "annotator laxity: a decoy can be a real recurrence the artifact key missed"
            )
        else:
            lines.append("decoy hit rate: no decided decoys")
        lines.append("")
        lines.append(
            "This estimates the precision of stage 0's proximity rule, not the recall "
            "of the rake registry, and it cannot rank two detectors — 40 hand judgments "
            "do not carry that resolution."
        )
        return "\n".join(lines)


def score_sample(sample: AuditSample, labels: dict[int, str], problems: list[str]) -> AuditScore:
    """Join labels back onto the regenerated sample and estimate precision."""
    score = AuditScore(
        seed=sample.seed,
        stratum_size=sample.stratum_size,
        distinct_rakes=sample.distinct_rakes,
        parse_problems=list(problems),
    )
    per_rake: dict[str, list[bool]] = defaultdict(list)
    for item in sample.items:
        label = labels.get(item.number)
        if label is None:
            continue
        score.labelled += 1
        if item.decoy:
            score.decoy_counts[label] += 1
            continue
        score.counts[label] += 1
        if label in ("hit", "miss"):
            per_rake[item.rake_vid].append(label == "hit")

    score.wilson = wilson_interval(score.counts["hit"], score.decided)
    score.clustered = cluster_interval(per_rake, random.Random(sample.seed))
    return score


def sample_to_jsonl(sample: AuditSample) -> str:
    """The key: a meta record, then one record per item.

    Written at draw time and read back at score time rather than regenerating the
    sample from its seed. The stratum is a function of the live graph, so a session
    distilled between drawing and labelling would silently reshuffle a regenerated
    sample and join the labels onto the wrong pairs. The seed reproduces a draw; only
    the key reproduces *this* draw.
    """
    head = json.dumps(
        {
            "meta": True,
            "seed": sample.seed,
            "stratum_size": sample.stratum_size,
            "distinct_rakes": sample.distinct_rakes,
            "decoys_drawn": sample.decoys_drawn,
        }
    )
    rows = [
        json.dumps(
            {
                "item": i.number,
                "rake": i.rake_vid,
                "session": i.session_vid,
                "decoy": i.decoy,
            }
        )
        for i in sample.items
    ]
    return "\n".join([head, *rows]) + "\n"


def sample_from_jsonl(text: str) -> AuditSample:
    """Rebuild the sample from its key — enough to score, no graph read needed."""
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or not records[0].get("meta"):
        raise ValueError("key file has no meta record — was it written by --draw?")
    meta, rows = records[0], records[1:]
    return AuditSample(
        seed=int(meta["seed"]),
        items=[
            AuditItem(
                number=int(r["item"]),
                rake_vid=str(r["rake"]),
                session_vid=str(r["session"]),
                decoy=bool(r["decoy"]),
            )
            for r in rows
        ],
        stratum_size=int(meta.get("stratum_size", 0)),
        distinct_rakes=int(meta.get("distinct_rakes", 0)),
        decoys_drawn=int(meta.get("decoys_drawn", 0)),
    )
