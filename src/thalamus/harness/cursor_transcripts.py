"""Cursor transcript discovery and deterministic extraction — the second harness.

Closes lab/010's wall 2: `thalamus extract` parses Claude Code JSONL only, so a
Cursor session retrieved, traced and conditioned but left no episodic memory.
This module produces the same `TranscriptFacts` the Claude Code reader produces,
so extraction, merging, the ingress floor and provenance all stay unchanged
downstream. One intermediate, two harness dialects — the same shape the hook
adapters take.

**Cursor's format is thinner than Claude Code's, and the gaps are structural.**
Cursor publishes no schema; the shape below is the one its staff and users
describe (forum thread 166592, confirmed by Cursor staff 2026; read 2026-07-29):

    {"role": "user", "message": {"content": [{"type": "text", "text": "..."}]}}

- top level carries `role` and `message` only — **no timestamps, no type rows**
- `message` carries `content` only — no `id`, no `usage`, no model
- content blocks are `text` and `tool_use` only
- `tool_use` carries `type`, `name`, `input` — **no `id`**
- **`tool_result` blocks are absent entirely.** Cursor excludes tool outputs from
  transcripts deliberately, because they can be very large (Cursor staff, forum
  thread 157311). Extended thinking arrives as `[REDACTED]` when the provider
  redacts it.

Three consequences, each handled explicitly rather than papered over:

1. **The ingress floor cannot be computed from a Cursor transcript.** docs/05's
   mechanical floor — the layer no prompt content can lift — judges extracted
   claims against the verbatim text of external-ingress tool *results*. Those
   results do not exist here for any tool. An empty `external_texts` therefore
   does not mean "nothing was fetched", it means "we cannot know", and the two
   must never collapse: silently returning the empty list would delete the
   unliftable half of the laundering defence while appearing to apply it. So
   facts carry `ingress_verifiable=False` and `apply_ingress_floor` floors the
   whole session rather than trusting the extractor's self-marks alone. Down-tier
   is the only direction the floor moves, and docs/05 already prices that cost:
   first-party memory rendering as tier 2 informs, and costs nothing but
   emphasis.

2. **Touch anchors are positional, not identifiers.** Anchors let docs/03's
   provenance walk land on the exact tool call instead of handing the operator
   the whole transcript. Cursor writes no message ids, so anchors are synthesized
   as `cursor:msg:<row>` — namespaced precisely so a synthesized anchor can never
   be mistaken for a real UUID, and still resolvable, because the archived
   transcript is the retained bytes and the row index addresses it.

3. **Time and place come from our own ledgers, not the transcript.** No row
   carries a timestamp and no row carries a cwd. The session's sessionStart
   record in `~/.thalamus/pins/pins.jsonl` holds both, and its sessionEnd record
   in `~/.thalamus/logs/cursor-session-end.jsonl` holds the end. Those hooks have
   been writing since the port shipped, which is what makes backfill possible at
   all.

**Distillation is deliberately not run at sessionEnd.** Cursor is not documented
to flush the transcript before firing the hook — an open request asks it to
fsync first, or to add a `transcript_ready` field (forum thread 166592, no
implementation timeline) — so reading at sessionEnd races an async writer and can
silently distill a truncated session. Instead sessionEnd logs the pointer with
`distilled: false` and `thalamus extract --harness cursor` sweeps afterwards,
which also picks up everything logged before this module existed.

Reads are guarded, but **not tolerant**. Recognition is complete and kept
separate from processing: a record this grammar does not cover is counted in
`unrecognized` and surfaced by the sweep, never quietly dropped. Postel's law is
the wrong rule for a parser written against a format it has never observed —
silent tolerance would turn "Cursor changed the shape" into "that session had
fewer turns" (RFC 9413's virtuous intolerance; LangSec, Momot et al., IEEE SecDev
2016). Content *blocks* are the one pre-declared extension point, so an unknown
block is tolerated while an unknown record is not.

**Prior work.** Normalizing heterogeneous agent trajectories into one
intermediate is an established move, not an invention: HarnessFix compiles
traces into a harness-aware Trace Intermediate Representation that normalizes
trajectory evidence across harnesses (arXiv 2606.06324), and the Agent Data
Protocol positions itself as an interlingua unifying thirteen agent datasets held
in incompatible formats (arXiv 2510.24702). This module is an *instantiation*:
`TranscriptFacts` already existed and simply gains a second producing dialect,
and the adapter boundary is an Anti-Corruption Layer (Evans, *Domain-Driven
Design*, 2003) — the same framing docs/07 uses for the Cursor hook suite.
Targeting a published wire schema instead was considered and rejected on
documented grounds rather than effort: OpenTelemetry's GenAI conventions are
Development-status with no released schema URL to pin, carry no reasoning content
part, and Claude Code's own OTel export redacts extended thinking and truncates
tool content — so routing through it would *lower* the primary-evidence floor
docs/10 exists to raise. W3C PROV, extended to agents by PROV-AGENT (arXiv
2508.02866), is the right shape at the wrong granularity: a provenance
vocabulary, not a transcript format. For fields Cursor cannot supply, absence is
recorded with a *reason* rather than a sentinel, following the three-way
distinction FHIR's `dataAbsentReason` makes — `not-applicable`, `unknown`,
`unsupported` — where Cursor's missing tool results are `unsupported`: a value
exists and the format cannot carry it. Rubin's MCAR/MAR/MNAR is deliberately not
the frame, since each of its categories presupposes a latent value that could
have been observed. Backfilling sessions logged before this reader existed is
replay over an immutable log, which is the position docs/10 already takes as
"re-extract, not migrate".

Not found in the 2026 scan (see docs/11 §4): a per-record manifest of what a
source format could not carry, and any measurement of extraction quality as a
function of *which trace fields* are present.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.harness.transcripts import (
    EXTERNAL_INGRESS_TOOLS,
    TranscriptFacts,
    _PATH_INPUTS,
    to_session_graph as _to_session_graph,
)
from thalamus.substrate.schema import SessionGraph, Tool

CURSOR_SESSION_END_LOG = Path.home() / ".thalamus" / "logs" / "cursor-session-end.jsonl"
PIN_LEDGER = Path.home() / ".thalamus" / "pins" / "pins.jsonl"

# Cursor's own web tools, for the ingress *detection* half. Naming these is a
# guess — the tool roster is not documented and no live Cursor has been observed
# — so nothing depends on the guess being complete: `ingress_verifiable=False`
# already floors the session whether or not a name here matches. A hit only
# sharpens the reported reason from "unverifiable" to "unverifiable, and we can
# see it fetched something".
CURSOR_INGRESS_TOOLS = frozenset(
    {"web_search", "web", "search_web", "fetch", "fetch_url", "read_url", "browser"}
) | {name.lower() for name in EXTERNAL_INGRESS_TOOLS}


@dataclass
class EndedSession:
    """One row of the Cursor sessionEnd log — the pointer to a distillable session."""

    session_id: str
    scope: str
    transcript_path: Path
    ended_at: datetime | None
    distilled: bool = False

    @property
    def exists(self) -> bool:
        return bool(self.transcript_path) and self.transcript_path.is_file()


def discover(log_path: Path | None = None) -> list[EndedSession]:
    """Every Cursor session logged at sessionEnd, newest row per session wins.

    The log is the discovery surface rather than a path glob because it is the
    only place the session id, its resolved scope and its transcript path appear
    together — and because a scope resolved at session end is the one
    distillation must use (docs/07, ledger-first).
    """
    path = log_path or CURSOR_SESSION_END_LOG
    latest: dict[str, EndedSession] = {}
    for record in _records(path):
        session_id = str(record.get("session_id") or "")
        transcript = str(record.get("transcript_path") or "")
        if not session_id or not transcript:
            continue
        latest[session_id] = EndedSession(
            session_id=session_id,
            scope=str(record.get("scope") or MAIN_SCOPE),
            transcript_path=Path(transcript),
            ended_at=_timestamp(record.get("ts")),
            distilled=bool(record.get("distilled")),
        )
    return list(latest.values())


def session_context(session_id: str, ledger_path: Path | None = None) -> tuple[str, datetime | None]:
    """(cwd, started_at) for a session, from the tier-0 pin ledger.

    Cursor transcripts carry neither, and guessing a project from the transcript
    path would be inference this layer exists to avoid. The sessionStart hook
    recorded both at the time, which is strictly better evidence.
    """
    cwd, started_at = "", None
    for record in _records(ledger_path or PIN_LEDGER):
        if str(record.get("session_id") or "") != session_id:
            continue
        if record.get("cwd"):
            cwd = str(record["cwd"])
        stamp = _timestamp(record.get("ts"))
        if stamp and (started_at is None or stamp < started_at):
            started_at = stamp
    return cwd, started_at


def parse(
    path: Path,
    *,
    session_id: str = "",
    cwd: str = "",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> TranscriptFacts:
    """Recover every fact a Cursor transcript records exactly. No model involved.

    Everything the format carries is taken; everything it cannot carry is left at
    its default and reported through `ingress_verifiable`, never inferred.
    """
    facts = TranscriptFacts(session_id=session_id or path.stem, path=path)
    facts.harness = "cursor"
    # Structural, not incidental: no Cursor transcript of any session carries the
    # tool results the floor needs (see module docstring).
    facts.ingress_verifiable = False
    facts.cwd = cwd
    facts.started_at = started_at
    facts.ended_at = ended_at

    for row, (record, decodable) in enumerate(_rows(path)):
        # Recognition first, and completely — anything the grammar below does not
        # cover is counted, never quietly dropped (see TranscriptFacts.unrecognized).
        if not decodable or not isinstance(record, dict):
            facts.unrecognized += 1
            continue

        role = record.get("role")
        if role not in ("user", "assistant"):
            facts.unrecognized += 1
            continue

        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        # Cursor is documented to use a content-block list, but a bare string is
        # the shape every other harness also emits, so accept both.
        if isinstance(content, str):
            blocks = [{"type": "text", "text": content}]
        elif isinstance(content, list):
            blocks = [b for b in content if isinstance(b, dict)]
        else:
            facts.unrecognized += 1
            continue

        facts.message_count += 1

        if role == "user":
            text = " ".join(
                b.get("text", "").strip()
                for b in blocks
                if b.get("type") == "text" and b.get("text", "").strip()
            ).strip()
            if text:
                facts.user_turns += 1
                if not facts.first_prompt:
                    facts.first_prompt = text
            continue

        for block in blocks:
            if block.get("type") != "tool_use":
                continue
            facts.tool_calls += 1
            name = str(block.get("name") or "")
            if name.lower() in CURSOR_INGRESS_TOOLS:
                facts.ingress_detected += 1
            tool_input = block.get("input")
            if not isinstance(tool_input, dict):
                continue
            for key in _PATH_INPUTS:
                identifier = tool_input.get(key)
                if not identifier:
                    continue
                anchors = facts.touched.setdefault(str(identifier), [])
                # Positional, and namespaced so it cannot pass for a UUID.
                anchor = f"cursor:msg:{row}"
                if anchor not in anchors:
                    anchors.append(anchor)

    return facts


def to_session_graph(
    facts: TranscriptFacts,
    *,
    content_hash: str,
    uri: str,
    byte_size: int,
    scope: str = MAIN_SCOPE,
    room: str = "",
    forked_from: str = "",
) -> SessionGraph:
    """The deterministic half, stamped as Cursor's.

    Delegates to the Claude Code builder and re-stamps `tool`: the two harnesses
    differ in what they record, not in what a session *is*, and forking the
    builder would fork the schema contract with it.
    """
    graph = _to_session_graph(
        facts, content_hash=content_hash, uri=uri, byte_size=byte_size, scope=scope,
        room=room, forked_from=forked_from,
    )
    return graph.model_copy(update={"tool": Tool.CURSOR})


def _rows(path: Path):
    """Yield (record, decodable) for every non-blank line, decode failures included.

    Kept distinct from `_records`: the ledger readers genuinely want to skip junk,
    but the transcript parser must be able to *count* what it could not read.
    """
    if not path or not path.is_file():
        return
    with path.open(errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line), True
            except json.JSONDecodeError:
                yield None, False


def _records(path: Path):
    for record, decodable in _rows(path):
        if decodable and isinstance(record, dict):
            yield record


def _timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
