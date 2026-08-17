"""The gold label set — bounding the judge against truth instead of against chance.

A permutation null says how much of a used-rate is shared vocabulary. It cannot say
whether the verdicts are *right*: a judge could sit far above its null and still be
wrong about every individual case, and a judge at its null could still be right about
the few cases that matter. That question needs labels a human made, and this module
is the apparatus for getting them and for scoring against them.

**n = 256, and the number is derived rather than picked.** The estimand is
judge–human agreement. For κ with observed agreement p_o ≈ 0.80 against chance
p_e ≈ 0.50, SE(κ) ≈ √(p_o(1−p_o) / (n(1−p_e)²)) = √(0.64/n), so SE = 0.05 — a ±0.10
interval, enough to separate "substantial" from "moderate" agreement — needs 256
labelled node-verdicts. The 100 an earlier draft proposed gives SE = 0.08 and cannot make
that separation.

**The sample is stratified where the instrument is known to be non-uniform** — node
kind, retrieving tool, and window-length bucket — with Neyman allocation, so strata
whose verdicts are close to a coin flip get more of the budget than strata that are
nearly all one way. Proportional-to-size would spend most of the labels re-confirming
the easy majority.

**Labelling is blind.** The workbook shows the node and what the agent did next; it
never shows the judge's verdict, its matched terms, or its evidence string. A labeller
who can see the judge's answer is measuring their agreement with a suggestion.

**One annotator.** There is no inter-annotator agreement to report, and the honest
move is to say so in the write-up rather than to omit the line — the annotation
literature's own finding is that operational details get reported while reliability
details do not.
"""

from __future__ import annotations

import json
import math
import random
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

GOLD_DIR = Path.home() / ".thalamus" / "gold"

# Per-turn character budget in the workbook. Enough to see what the agent did,
# short enough that 30 turns fit in something a person will actually read.
TURN_CAP = 500
MAX_TURNS = 30
TARGET_N = 256

_LABEL_RE = re.compile(r"^label:\s*(used|unused|unclear)\s*$", re.IGNORECASE | re.MULTILINE)
_ID_RE = re.compile(r"^item:\s*(\S+)\s*$", re.MULTILINE)
_NOTE_RE = re.compile(r"^note:\s*(.*)$", re.MULTILINE)


@dataclass
class GoldItem:
    """One (retrieval, node) pair put to a human, and the strata it was drawn from."""

    item_id: str
    trace_id: str
    node_id: str
    session_id: str
    tool: str
    node_kind: str
    window_stratum: int
    node_text: str
    window_excerpt: str
    # Recorded at draw time so scoring cannot be accused of choosing the comparison
    # after seeing the labels. Never rendered into the workbook.
    judge_verdict: bool | None = None


@dataclass
class GoldLabel:
    item_id: str
    label: str  # used | unused | unclear
    note: str = ""
    labelled_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


@dataclass
class Agreement:
    """Judge against human, on the labelled subset."""

    n: int
    observed: float
    expected: float
    kappa: float
    se: float
    sensitivity: float
    specificity: float
    unclear: int

    @property
    def ci(self) -> tuple[float, float]:
        return (self.kappa - 1.96 * self.se, self.kappa + 1.96 * self.se)


def required_n(observed_agreement: float = 0.80, chance: float = 0.50, target_se: float = 0.05) -> int:
    """The n behind the 256. Exposed so the number can be re-derived, not trusted."""
    variance = observed_agreement * (1 - observed_agreement) / (1 - chance) ** 2
    return math.ceil(variance / target_se**2)


def stratum_of(item_kind: str, tool: str, window_stratum: int) -> str:
    return f"{item_kind}|{tool}|w{window_stratum}"


def draw(
    cases,
    verdicts: dict[str, dict[str, bool]],
    *,
    n: int = TARGET_N,
    seed: int = 20260730,
) -> list[GoldItem]:
    """A stratified sample of (retrieval, node) pairs, Neyman-allocated.

    Allocation is ∝ N_h·√(p_h(1−p_h)): strata where the judge is undecided carry more
    information per label than strata where it is nearly unanimous, and the budget
    should follow the information rather than the population.
    """
    pool: dict[str, list[GoldItem]] = {}
    for case in cases:
        judged = verdicts.get(case.trace_id, {})
        for node_id, used in judged.items():
            kind = node_id.split(":")[-2] if ":" in node_id else "unknown"
            key = stratum_of(kind, case.tool, case.stratum)
            pool.setdefault(key, []).append(
                GoldItem(
                    item_id=f"{case.trace_id.rsplit(':', 1)[-1][:12]}-{node_id.rsplit(':', 1)[-1][:12]}",
                    trace_id=case.trace_id,
                    node_id=node_id,
                    session_id=case.session_id,
                    tool=case.tool,
                    node_kind=kind,
                    window_stratum=case.stratum,
                    node_text=case.nodes.get(node_id, ""),
                    window_excerpt=excerpt(case),
                    judge_verdict=used,
                )
            )

    weights = {}
    for key, items in pool.items():
        p = sum(1 for i in items if i.judge_verdict) / len(items)
        weights[key] = len(items) * math.sqrt(max(p * (1 - p), 0.01))
    total_weight = sum(weights.values()) or 1.0

    rng = random.Random(seed)
    drawn: list[GoldItem] = []
    for key, items in sorted(pool.items()):
        take = min(len(items), max(1, round(n * weights[key] / total_weight)))
        drawn.extend(rng.sample(items, take))

    rng.shuffle(drawn)  # so a labeller cannot infer a stratum from position
    return drawn[:n]


def excerpt(case) -> str:
    """What the agent did next, trimmed to something a person will read.

    Whole windows run past 100k characters. Trimming loses evidence that lives late
    in a session — a real cost, and the reason the workbook says how much was cut
    rather than presenting the excerpt as the whole story.
    """
    parts = []
    for turn in case.window.turns[:MAX_TURNS]:
        text = turn.text().strip()
        if not text:
            continue
        clipped = text[:TURN_CAP]
        if len(text) > TURN_CAP:
            clipped += f" …[+{len(text) - TURN_CAP:,} chars]"
        parts.append(f"**turn {turn.index + 1}.** {clipped}")
    hidden = max(0, len(case.window.turns) - MAX_TURNS)
    if hidden:
        parts.append(f"_[{hidden} further turns not shown]_")
    return "\n\n".join(parts)


def workbook(items: list[GoldItem], *, batch: int, of: int) -> str:
    """One labelling batch as markdown, with the judge's answer withheld."""
    lines = [
        f"# Gold labels — batch {batch} of {of}",
        "",
        "For each item: did the agent's subsequent behaviour **use** this memory?",
        "",
        "- `used` — the agent's later prose or tool calls reflect this node's content:",
        "  it acted on it, referred to it, or was visibly steered by it.",
        "- `unused` — the agent did what it would have done without this node.",
        "- `unclear` — you cannot tell from what is shown. Not a failure; `unclear`",
        "  items are reported separately and never silently counted as either.",
        "",
        "Items start at `?`, which means *not yet judged*. An untouched workbook must",
        "not read as a workbook full of `unclear` decisions — those are different",
        "states and only one of them is data.",
        "",
        "Judge the *node against the behaviour*, not the node's quality. A correct,",
        "well-written memory the agent ignored is `unused`.",
        "",
        "Edit the `label:` line under each item. Leave `note:` for anything the",
        "categories cannot hold — those notes are where the next instrument comes from.",
        "",
        "---",
        "",
    ]
    for index, item in enumerate(items, start=1):
        lines += [
            f"## {index}. `{item.item_id}`",
            "",
            f"**The memory that was shown** ({item.node_kind}, via `{item.tool}`):",
            "",
            "> " + (item.node_text or "_(no text)_").replace("\n", "\n> "),
            "",
            "**What the agent did next:**",
            "",
            item.window_excerpt or "_(no output recorded)_",
            "",
            "```yaml",
            f"item: {item.item_id}",
            "label: ?",
            "note:",
            "```",
            "",
            "---",
            "",
        ]
    return "\n".join(lines)


def write_batches(items: list[GoldItem], *, base: Path | None = None, size: int = 32) -> list[Path]:
    """Split the sample into sittings and write the sample manifest beside them."""
    directory = base or GOLD_DIR
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "sample.jsonl").write_text(
        "".join(json.dumps(asdict(item)) + "\n" for item in items)
    )
    batches = [items[i : i + size] for i in range(0, len(items), size)]
    paths = []
    for number, batch in enumerate(batches, start=1):
        path = directory / f"batch-{number:02d}.md"
        path.write_text(workbook(batch, batch=number, of=len(batches)))
        paths.append(path)
    return paths


def read_labels(base: Path | None = None) -> dict[str, GoldLabel]:
    """Parse labels back out of the workbooks, plus any already-ingested ledger."""
    directory = base or GOLD_DIR
    labels: dict[str, GoldLabel] = {}
    ledger = directory / "labels.jsonl"
    if ledger.is_file():
        for line in ledger.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                labels[row["item_id"]] = GoldLabel(**row)

    for path in sorted(directory.glob("batch-*.md")):
        text = path.read_text()
        for block in text.split("```yaml")[1:]:
            body = block.split("```")[0]
            item = _ID_RE.search(body)
            label = _LABEL_RE.search(body)
            if not item or not label:
                continue
            note = _NOTE_RE.search(body)
            labels[item.group(1)] = GoldLabel(
                item_id=item.group(1),
                label=label.group(1).lower(),
                note=(note.group(1).strip() if note else ""),
            )
    return labels


def load_sample(base: Path | None = None) -> list[GoldItem]:
    path = (base or GOLD_DIR) / "sample.jsonl"
    if not path.is_file():
        return []
    return [GoldItem(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


def agreement(items: list[GoldItem], labels: dict[str, GoldLabel]) -> Agreement:
    """Cohen's κ between the judge and the human, on labelled, decidable items.

    `unclear` is excluded from κ and counted separately. Folding it into either
    class would manufacture agreement out of the labeller's own uncertainty, which
    is the one thing a gold set exists to avoid.
    """
    pairs = []
    unclear = 0
    for item in items:
        label = labels.get(item.item_id)
        if not label or item.judge_verdict is None:
            continue
        if label.label == "unclear":
            unclear += 1
            continue
        pairs.append((item.judge_verdict, label.label == "used"))

    n = len(pairs)
    if not n:
        return Agreement(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, unclear)

    both_used = sum(1 for j, h in pairs if j and h)
    judge_only = sum(1 for j, h in pairs if j and not h)
    human_only = sum(1 for j, h in pairs if not j and h)
    neither = sum(1 for j, h in pairs if not j and not h)

    observed = (both_used + neither) / n
    p_judge = (both_used + judge_only) / n
    p_human = (both_used + human_only) / n
    expected = p_judge * p_human + (1 - p_judge) * (1 - p_human)
    kappa = (observed - expected) / (1 - expected) if expected < 1 else 0.0
    se = math.sqrt(observed * (1 - observed) / (n * (1 - expected) ** 2)) if expected < 1 else 0.0

    sensitivity = both_used / (both_used + human_only) if (both_used + human_only) else 0.0
    specificity = neither / (neither + judge_only) if (neither + judge_only) else 0.0
    return Agreement(n, observed, expected, kappa, se, sensitivity, specificity, unclear)


def by_stratum(items: list[GoldItem], labels: dict[str, GoldLabel], key) -> dict[str, Agreement]:
    """Agreement split by any item dimension — where a judge is weak, not just how."""
    grouped: dict[str, list[GoldItem]] = {}
    for item in items:
        grouped.setdefault(str(key(item)), []).append(item)
    return {name: agreement(group, labels) for name, group in sorted(grouped.items())}
