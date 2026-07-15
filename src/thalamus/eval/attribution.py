"""Used-vs-ignored attribution — crude on purpose (docs/04).

A retrieved node was *used* if its content is reflected in what the agent actually did
after the retrieval: cited by ID, or lexically echoed in the assistant's text and tool
calls. This is post-hoc matching against the retained transcript, and it is deliberately
the dumbest thing that produces a number — a crude measure beats no measure, and every
way lexical matching misleads is lab-notebook material for refining it. No model is in
this loop: attribution must stay cheap enough to run after every session, or it will
not be run.

Verdicts are facts about one retrieval of one node, so they land as properties on the
Trace -[RETURNS]-> node edge, never on the node itself.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from thalamus.substrate.reader import _extract_keywords

# A node is "used" when at least this many of its distinctive terms — and this fraction
# of them — appear in the session's subsequent output. Two dials, both arbitrary, both
# honest: they are the starting point the eval loop exists to pressure-test.
MIN_MATCHED_TERMS = 2
MIN_MATCHED_RATIO = 0.3

_TOKEN_RE = re.compile(r"[a-z0-9_./-]+")


@dataclass
class Verdict:
    node_id: str
    used: bool
    evidence: str


def outputs_after(transcript: bytes, after: datetime) -> str:
    """Everything the agent *did* after a moment: assistant text plus tool-call inputs.

    User turns are excluded — the question is whether retrieval changed the agent's
    behavior, not whether the operator happened to mention the same words. Sidechains
    are excluded for the same reason they are excluded from extraction: they are their
    own episodes.
    """
    outputs: list[str] = []

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

        content = (record.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                outputs.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                outputs.append(json.dumps(block.get("input") or {}))

    return "\n".join(outputs)


def attribute(returned: dict[str, str], outputs: str) -> list[Verdict]:
    """Judge each returned node against the session's subsequent outputs.

    `returned` maps vertex ID -> the node's retrievable text (summary, description,
    title — whatever the graph holds for it).
    """
    output_lower = outputs.lower()
    output_tokens = set(_TOKEN_RE.findall(output_lower))

    verdicts: list[Verdict] = []
    for node_id, content in returned.items():
        verdicts.append(_judge(node_id, content, output_lower, output_tokens))
    return verdicts


def _judge(node_id: str, content: str, output_lower: str, output_tokens: set[str]) -> Verdict:
    # Strongest signal first: the agent quoted the node's identity itself. The reader
    # renders vertex IDs precisely so this becomes possible.
    if node_id.lower() in output_lower:
        return Verdict(node_id, True, "cited by vertex ID")

    # Threads have human-legible slugs the agent tends to repeat verbatim.
    local_id = node_id.rsplit(":", 1)[-1].lower()
    if node_id.split(":")[-2:-1] == ["thread"] and len(local_id) > 3 and local_id in output_lower:
        return Verdict(node_id, True, f"thread slug `{local_id}` referenced")

    terms = sorted(set(_extract_keywords(content)))
    if not terms:
        return Verdict(node_id, False, "no distinctive terms to match on")

    matched = [term for term in terms if term in output_tokens]
    needed = min(len(terms), MIN_MATCHED_TERMS)
    used = len(matched) >= needed and len(matched) / len(terms) >= MIN_MATCHED_RATIO

    detail = ", ".join(matched[:6]) if matched else "none"
    return Verdict(
        node_id,
        used,
        f"matched {len(matched)}/{len(terms)} terms: {detail}",
    )


def _timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
