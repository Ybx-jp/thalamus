"""Used-vs-ignored attribution — crude on purpose.

A retrieved node was *used* if its content is reflected in what the agent actually did
after the retrieval: cited by ID, or lexically echoed in the assistant's text and tool
calls. This is post-hoc matching against the retained transcript, and it is deliberately
the dumbest thing that produces a number — a crude measure beats no measure, and every
way lexical matching misleads is lab-notebook material for refining it. No model is in
this loop: attribution must stay cheap enough to run after every session, or it will
not be run.

**How crude, measured.** Judging a retrieval's nodes against a *different*
same-project session's output scores 58-61% used, against 62.9% for the real output
window — so within a project this instrument carries roughly **4 points of
discrimination on a 59-point floor**. Across projects it is nearly perfect (63% vs
5%): it is a topic detector, accurate at a granularity coarser than the question
being asked of it. Two structural causes, both here in `_judge`: term membership is
tested anywhere in the window with no proximity, so long windows match more (used%
51.7% at 20-100k chars vs 69.7% at 100k+), and same-project sessions share
vocabulary by definition. Read every used% as ~59 points of overlap plus ~4 of
utility until a permuted baseline is reported beside it.

**The ratio floor is load-bearing, measured.** `MIN_MATCHED_RATIO`'s denominator is
the node's own term count, so a longer node must match more of itself to clear the
same bar — the verdict is anti-correlated with node length and with whatever length
tracks. That is a real defect and every correction to it costs more than it fixes.
Scored on the v3 window (730 cases, 59 sessions, 200 rotations, 2026-08-29), against
`shipped` at 79.8% used / 69.2% null / **10.6 points of separation** / kappa 0.345:

    capped-ratio (denominator capped at 10)   96.5 / 93.5 / 3.0 / 0.465
    half-ratio   (0.15)                       96.1 / 92.2 / 3.9 / 0.502
    count-only   (no proportional test)       98.5 / 96.9 / 1.5 / 0.504

Every relaxation raises kappa and *lowers* separation, monotonically, because
loosening admits more rotated nodes than real ones: most nodes clear a two-term bar
against any window drawn from the same project's vocabulary. Kappa divides by the
headroom `1 - null`, which collapses along with the discrimination, so it rewards a
judge that calls everything used. **Read separation beside kappa, never kappa alone**,
and do not move this dial to fix the length bias. The axis with room left is the one
no variant explores: weighting a term by its rarity, which attacks the vocabulary
floor rather than trading against it.

Verdicts are facts about one retrieval of one node, so they land as properties on the
Trace -[RETURNS]-> node edge, never on the node itself.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from thalamus.substrate.reader import (
    MIN_MATCHED_RATIO,
    MIN_MATCHED_TERMS,
    STOPWORDS,
    _extract_keywords,
)

# Bump when a dial above moves, or when the term extraction under it changes, so the
# fingerprint moves even if two dials cancel out numerically.
#
# v2 adopted the `aligned` term extraction as what `shipped` means (see
# thread attribution-aligned-judge-adoption-pending): kappa moved 0.2391 -> 0.3101
# over 999 cases, 8,446 verdicts, 25 rotations. `split` — the v1 reading — survives
# as a named variant for retrospective comparison against verdicts stored before
# the switch.
JUDGE_VERSION = "2"

_TOKEN_RE = re.compile(r"[a-z0-9_./-]+")


def judge_fingerprint(name: str = "shipped") -> str:
    """A compact, legible identity for the judging dials a verdict was reached under.

    `judged_terms` records the instrument's *inputs*; this records its *settings*. Both
    are needed to call a stored verdict a record: the same term set under a different
    threshold is a different verdict, and without this a dial change silently
    re-attributes every historical judgement to settings that never produced it.

    The ranker solved this identical problem one property over (`Trace.ranker_config`)
    and the judge had no equivalent. Legible rather than hashed, for the same
    reason: a window straddling `j1:t2-r0.3` and `j1:t3-r0.3` says *which* dial moved.
    """
    judge = JUDGES.get(name)
    ratio = judge.ratio if judge else MIN_MATCHED_RATIO
    cap = f"-c{judge.ratio_cap}" if judge and judge.ratio_cap else ""
    return f"j{JUDGE_VERSION}:{name}-t{MIN_MATCHED_TERMS}-r{ratio}{cap}"


@dataclass
class Verdict:
    node_id: str
    used: bool
    evidence: str


@dataclass
class OutputTurn:
    """One assistant turn after a retrieval, with its parts kept apart.

    `parts` holds (kind, text) in emission order — "prose" for a text block,
    "tool" for a tool-call input — so the flat window can be rebuilt exactly while
    a judge that wants only one kind can still have it. The two are different
    evidence: shared project vocabulary is a *prose* phenomenon, while a path or a
    parameter appearing in a tool call after a retrieval is a much narrower
    coincidence.
    """

    index: int
    parts: list[tuple[str, str]]

    def text(self, *, prose: bool = True, tools: bool = True) -> str:
        kinds = {"prose"} if prose and not tools else {"tool"} if tools and not prose else None
        return "\n".join(t for kind, t in self.parts if kinds is None or kind in kinds)


@dataclass
class OutputWindow:
    """Everything the agent did after a retrieval, addressable by distance.

    The flat string the shipped judge uses is `text()` with no bounds. Bounding it
    matters because the unbounded window re-measures session length: used% moves
    51.7% → 69.7% between 20-100k-char and 100k+ windows on the same instrument,
    so the metric partly reports how long the session ran. Utility
    should decay with distance from the retrieval; vocabulary overlap should not —
    a difference the unbounded window cannot see.
    """

    turns: list[OutputTurn]

    def text(self, *, turns: int | None = None, prose: bool = True, tools: bool = True) -> str:
        # Nothing is filtered, including empty parts: the unbounded, both-kinds
        # call must reproduce the shipped window exactly, and an empty text block
        # contributed a blank line there.
        selected = self.turns if turns is None else self.turns[:turns]
        return "\n".join(t.text(prose=prose, tools=tools) for t in selected)

    def __len__(self) -> int:
        return len(self.turns)


def output_window(transcript: bytes, after: datetime) -> OutputWindow:
    """Parse the post-retrieval assistant turns out of a retained transcript.

    User turns are excluded — the question is whether retrieval changed the agent's
    behavior, not whether the operator happened to mention the same words. Sidechains
    are excluded for the same reason they are excluded from extraction: they are their
    own episodes.
    """
    turns: list[OutputTurn] = []

    for line in transcript.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("type") != "assistant":
            continue
        if record.get("isSidechain") or record.get("isMeta"):
            continue

        timestamp = _timestamp(record.get("timestamp"))
        if timestamp is None or timestamp <= after:
            continue

        parts: list[tuple[str, str]] = []
        content = (record.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(("prose", block.get("text") or ""))
            elif block.get("type") == "tool_use":
                parts.append(("tool", json.dumps(block.get("input") or {})))
        if parts:
            turns.append(OutputTurn(index=len(turns), parts=parts))

    return OutputWindow(turns=turns)


def outputs_after(transcript: bytes, after: datetime) -> str:
    """The flat window the shipped verdict is computed against.

    Kept as the one the graph's `used` properties mean, byte-for-byte: changing it
    would silently redefine every stored verdict. New judges are variants scored
    beside it (`JUDGES`), never a quiet substitution.
    """
    return output_window(transcript, after).text()


def node_terms(content: str) -> list[str]:
    """The pre-adoption (`split`) reading: `_extract_keywords` splits on whitespace and
    keeps punctuation attached, while the window it is matched against is tokenised by
    `_TOKEN_RE`, which strips it. That mismatch is a floor on false negatives that has
    nothing to do with whether a node was used — measured on a 13-term sample, 4 terms
    could not match even when the window was byte-identical to the node's own text:
    `"write-path".`, `(see`, `lab/029),`, `parser;`.

    `aligned_node_terms` is what `shipped` means as of JUDGE_VERSION 2. This is kept as
    the `split` variant so verdicts stored before the switch stay reproducible against
    the reading that actually produced them.
    """
    return sorted(set(_extract_keywords(content)))


def aligned_node_terms(content: str) -> list[str]:
    """The node's distinctive terms, tokenised the way the output window is.

    What `shipped` means as of JUDGE_VERSION 2 (see `node_terms` for the defect this
    corrects). Only the tokenizer changes from the pre-adoption reading: the stopword
    list and length cut are `_extract_keywords`' own, and compound splitting is
    deliberately *not* borrowed from the ingress floor — that floor wants to over-catch
    because down-tiering is its safe direction, while a judge that matches more terms
    reports more use, which is the direction this instrument is least able to afford.
    """
    tokens = _TOKEN_RE.findall(content.lower())
    return sorted({t for t in tokens if len(t) > 2 and t not in STOPWORDS})


def prepare(outputs: str) -> tuple[str, set[str]]:
    """The two derived forms every verdict against this window needs.

    Split out because calibration judges the same window tens of thousands of times
    (200 rotations × every case), and re-lowercasing and re-tokenising a 100k-char
    window each time is the difference between a minute and an hour.
    """
    output_lower = outputs.lower()
    return output_lower, set(_TOKEN_RE.findall(output_lower))


# How a node's text becomes the terms a verdict matches on. `aligned` is what every
# stored verdict means as of JUDGE_VERSION 2; `split` is the pre-adoption reading, kept
# for retrospective comparison. Named rather than passed as a function so a judge stays
# a comparable configuration and a fingerprint can say which reading produced a number.
TERM_EXTRACTORS = {"split": node_terms, "aligned": aligned_node_terms}


def attribute(
    returned: dict[str, str],
    outputs: str,
    *,
    terms_from: str = "aligned",
    ratio: float = MIN_MATCHED_RATIO,
    ratio_cap: int | None = None,
) -> list[Verdict]:
    """Judge each returned node against the session's subsequent outputs.

    `returned` maps vertex ID -> the node's retrievable text (summary, description,
    title — whatever the graph holds for it).
    """
    output_lower, output_tokens = prepare(outputs)
    return attribute_prepared(
        returned, output_lower, output_tokens,
        terms_from=terms_from, ratio=ratio, ratio_cap=ratio_cap,
    )


def attribute_prepared(
    returned: dict[str, str],
    output_lower: str,
    output_tokens: set[str],
    terms: dict[str, list[str]] | None = None,
    *,
    terms_from: str = "aligned",
    ratio: float = MIN_MATCHED_RATIO,
    ratio_cap: int | None = None,
) -> list[Verdict]:
    """`attribute` with the window — and optionally the nodes' terms — precomputed."""
    extract = TERM_EXTRACTORS[terms_from]
    return [
        _judge(
            node_id,
            content,
            output_lower,
            output_tokens,
            terms=None if terms is None else terms.get(node_id),
            extract=extract,
            ratio=ratio,
            ratio_cap=ratio_cap,
        )
        for node_id, content in returned.items()
    ]


def _judge(
    node_id: str,
    content: str,
    output_lower: str,
    output_tokens: set[str],
    terms: list[str] | None = None,
    extract=aligned_node_terms,
    ratio: float = MIN_MATCHED_RATIO,
    ratio_cap: int | None = None,
) -> Verdict:
    # Strongest signal first: the agent quoted the node's identity itself. The reader
    # renders vertex IDs precisely so this becomes possible.
    if node_id.lower() in output_lower:
        return Verdict(node_id, True, "cited by vertex ID")

    # Threads have human-legible slugs the agent tends to repeat verbatim.
    local_id = node_id.rsplit(":", 1)[-1].lower()
    if node_id.split(":")[-2:-1] == ["thread"] and len(local_id) > 3 and local_id in output_lower:
        return Verdict(node_id, True, f"thread slug `{local_id}` referenced")

    terms = terms if terms is not None else extract(content)
    if not terms:
        return Verdict(node_id, False, "no distinctive terms to match on")

    matched = [term for term in terms if term in output_tokens]
    needed = min(len(terms), MIN_MATCHED_TERMS)
    # The ratio's denominator is the node's *own* term count, so a longer node must
    # match proportionally more of itself to clear the same bar. That makes the
    # verdict anti-correlated with node length, and therefore with anything length
    # tracks — tier, kind, how much a node says. `ratio=0.0` drops the proportional
    # test and leaves the absolute floor, which is the variant that isolates it.
    # `ratio_cap` bounds that denominator. Removing the proportional test outright
    # (`ratio=0.0`) does fix the anti-correlation and destroys the instrument doing
    # it — measured on the v3 window it calls 98.5% of nodes used and 96.9% of nodes
    # judged against an *unrelated* session used, collapsing discrimination from
    # 10.6 points to 1.6 while κ rises, because κ's headroom denominator collapses
    # with it. Capping keeps a floor for short nodes and stops the bar climbing with
    # length above the cap.
    denominator = min(len(terms), ratio_cap) if ratio_cap else len(terms)
    used = len(matched) >= needed and (
        ratio <= 0.0 or len(matched) / denominator >= ratio
    )

    detail = ", ".join(matched[:6]) if matched else "none"
    return Verdict(
        node_id,
        used,
        f"matched {len(matched)}/{len(terms)} terms: {detail}",
    )


@dataclass(frozen=True)
class Judge:
    """One way of deciding whether a retrieved node was used.

    A judge is a *named* configuration rather than a code path so that variants can
    be scored against the same permutation null and against the same gold labels,
    and so a published number can say which one produced it. `shipped` is the one
    the graph's stored verdicts mean; adopting another is a measured decision, not
    an edit.
    """

    name: str
    turns: int | None = None
    prose: bool = True
    tools: bool = True
    # Which side of the match this judge varies. Every variant above narrows the
    # *window*; this one narrows nothing and instead fixes the node side, which is the
    # only axis on which `shipped` is not merely a choice but a defect.
    terms_from: str = "split"
    # The proportional floor, denominated in the node's own term count. `shipped`
    # carries the module default; a variant setting it lower — or to 0.0, dropping
    # the proportional test entirely — is the only way to read the length
    # anti-correlation apart from everything else the judge does.
    ratio: float = MIN_MATCHED_RATIO
    # Bound on the ratio's denominator. `None` leaves it as the node's own term
    # count, which is the defect; a cap makes the bar length-independent above it.
    ratio_cap: int | None = None
    description: str = ""

    def __call__(self, returned: dict[str, str], window: OutputWindow) -> list[Verdict]:
        return attribute(
            returned,
            window.text(turns=self.turns, prose=self.prose, tools=self.tools),
            terms_from=self.terms_from,
            ratio=self.ratio,
            ratio_cap=self.ratio_cap,
        )


# The variants worth separating, and why each exists. Every one of them is
# computable over retained data, so they can be compared retroactively across the
# whole corpus rather than only going forward.
JUDGES: dict[str, Judge] = {
    j.name: j
    for j in (
        Judge(
            "shipped",
            terms_from="aligned",
            description="the flat, unbounded window the stored verdicts mean, as of "
            "JUDGE_VERSION 2 — node terms tokenised the way the window is",
        ),
        Judge(
            "prose",
            tools=False,
            description="assistant prose only — where shared project vocabulary lives",
        ),
        Judge(
            "tool",
            prose=False,
            description="tool-call inputs only — a path or parameter echoed after a "
            "retrieval is a narrower coincidence than a word",
        ),
        Judge("bounded-1", turns=1, description="the next assistant turn only"),
        Judge("bounded-3", turns=3, description="the next three assistant turns"),
        Judge("bounded-10", turns=10, description="the next ten assistant turns"),
        Judge(
            "tool-bounded-3",
            turns=3,
            prose=False,
            description="both narrowings at once: near, and acted on",
        ),
        Judge(
            "split",
            terms_from="split",
            description="the pre-adoption reading (JUDGE_VERSION 1) — node terms kept "
            "whitespace-split with punctuation attached, mismatched against the "
            "window's tokeniser. Kept for retrospective comparison against verdicts "
            "stored before the switch, not because it is a defensible choice.",
        ),
        Judge(
            "count-only",
            terms_from="aligned",
            ratio=0.0,
            description="`shipped` with the proportional floor removed, so a node "
            "clears on the absolute term count alone. One dial from `shipped`, and "
            "the only variant that touches the length anti-correlation rather than "
            "the window",
        ),
        Judge(
            "half-ratio",
            terms_from="aligned",
            ratio=0.15,
            description="half the proportional floor — separates the ratio's *level* "
            "from its existence, so a gain under `count-only` can be read as the "
            "threshold being too high rather than the test being wrong",
        ),
        Judge(
            "capped-ratio",
            terms_from="aligned",
            ratio_cap=10,
            description="the proportional test kept, but its denominator bounded at "
            "10 terms, so a node stops being penalised for saying more. The variant "
            "that targets the length anti-correlation without surrendering the floor "
            "that `count-only` gives up",
        ),
        Judge(
            "aligned-tool-bounded-3",
            turns=3,
            prose=False,
            terms_from="aligned",
            description="the narrowest window with the corrected term side, so the two "
            "kinds of change can be read apart from their combination",
        ),
    )
}


def _timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
