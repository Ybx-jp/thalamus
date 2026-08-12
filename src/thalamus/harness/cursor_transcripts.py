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
- **`tool_result` blocks are absent from this file.** Cursor excludes tool outputs
  from transcripts deliberately, because they can be very large (Cursor staff,
  forum thread 157311). They are retained elsewhere — see consequence 1. Extended
  thinking arrives as `[REDACTED]` when the provider redacts it.

Three consequences, each handled explicitly rather than papered over:

1. **The ingress floor cannot be computed from a Cursor transcript.** docs/05's
   mechanical floor — the layer no prompt content can lift — judges extracted
   claims against the verbatim text of external-ingress tool *results*, and no
   transcript carries them. An empty `external_texts` therefore does not mean
   "nothing was fetched", it means "we cannot know", and the two must never
   collapse: silently returning the empty list would delete the unliftable half
   of the laundering defence while appearing to apply it. So facts carry
   `ingress_verifiable=False` and `apply_ingress_floor` floors the whole session
   rather than trusting the extractor's self-marks alone. Down-tier is the only
   direction the floor moves, and docs/05 already prices that cost: first-party
   memory rendering as tier 2 informs, and costs nothing but emphasis.

   The results themselves are retained by Cursor, in a per-session
   content-addressed SQLite store, `~/.cursor/chats/<hash>/<id>/store.db`: an
   ingress result verbatim in `result`, joined to its call by `toolCallId`, under
   the same `WebFetch`/`WebSearch` names Claude Code uses (lab/060). This module
   does not read it. Reading it is not sufficient either — a check that asks only
   whether some external text was found passes a partial read as readily as a
   whole one, which is the same collapse in a new place.

2. **Touch anchors are positional, not identifiers.** Anchors let docs/03's
   provenance walk land on the exact tool call instead of handing the operator
   the whole transcript. Cursor writes no message ids, so anchors are synthesized
   as `cursor:msg:<row>` — namespaced precisely so a synthesized anchor can never
   be mistaken for a real UUID, and still resolvable, because the archived
   transcript is the retained bytes and the row index addresses it.

3. **Time and place come from our own ledgers.** No row carries a timestamp field
   and no row carries a cwd, so the session's sessionStart record in
   `~/.thalamus/pins/pins.jsonl` holds both and its sessionEnd record in
   `~/.thalamus/logs/cursor-session-end.jsonl` holds the end. Those hooks have
   been writing since the port shipped, which is what makes backfill possible.

   The ledgers are not the *only* source, which matters for anything they never
   saw. Cursor writes a `<timestamp>` element into the user query text itself, and
   `~/.cursor/chats/<hash>/<session-id>/meta.json` carries `cwd`, `createdAtMs`
   and `updatedAtMs` (lab/054). So a session that ran before the hooks were
   installed — every Cursor session on a machine Thalamus reaches late — is
   reached by `discover()`'s filesystem surface and dated from Cursor's own
   record, with its scope left `UNRESOLVED_SCOPE` for an operator to assign.

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
recorded with a *reason* rather than a sentinel, borrowing codes from FHIR R4's
`DataAbsentReason` — a 15-concept, two-level value set, Normative since R4, not a
three-way split. Cursor's missing tool results are `unsupported`: a value exists
and the format cannot carry it. An unresolved scope is a different code in the
same set, `not-asked` ("the workflow didn't lead to this value being known"),
which is why it is refused rather than defaulted — see `UNRESOLVED_SCOPE`. Rubin's
MCAR/MAR/MNAR is deliberately not the frame, since each of its categories
presupposes a latent value that could have been observed. Backfilling sessions logged before this reader existed is
replay over an immutable log, which is the position docs/10 already takes as
"re-extract, not migrate".

Not found in the 2026 scan (see docs/11 §4): a per-record manifest of what a
source format could not carry, and any measurement of extraction quality as a
function of *which trace fields* are present.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.harness.agents import is_sandbox_cwd
from thalamus.harness.transcripts import (
    EXTERNAL_INGRESS_TOOLS,
    TranscriptFacts,
    _PATH_INPUTS,
    is_sandbox_project,
    to_session_graph as _to_session_graph,
)
from thalamus.substrate.schema import SessionGraph, Tool

CURSOR_SESSION_END_LOG = Path.home() / ".thalamus" / "logs" / "cursor-session-end.jsonl"
PIN_LEDGER = Path.home() / ".thalamus" / "pins" / "pins.jsonl"
CURSOR_PROJECTS = Path.home() / ".cursor" / "projects"
CURSOR_CHATS = Path.home() / ".cursor" / "chats"

# How a session came to our attention. Set-valued on the record rather than an
# enum, because the two surfaces are not exclusive: a session that ended after
# the hooks were installed is seen by both, and an enum would force one of those
# two true facts to be written as false. It is deliberately not called an
# *attestation* — AuditWeave reserves that word for an actor signing off on a
# record (arXiv 2607.09682), and nothing here signs anything. A hook row records
# that our hook observed the session end; it does not vouch for the transcript.
DISCOVERED_BY_HOOK = "hook"
DISCOVERED_BY_FILESYSTEM = "filesystem"

# A scope that no hook ever resolved. Not `main`: defaulting an unattested
# session into the operator's own subgraph is a routing decision nobody made,
# and it is unrecoverable once written, because scope is part of the vertex ID.
# FHIR R4's `DataAbsentReason` names this exact case `not-asked` — "the workflow
# didn't lead to this value being known" — and it is a different absence from the
# `unsupported` this module records for Cursor's missing tool results, where a
# value existed and the format could not carry it. The distinction decides the
# handling: an `unsupported` field is recorded absent and the session distills
# anyway, while a `not-asked` one has to wait for someone to ask.
UNRESOLVED_SCOPE = ""

# Cursor's own web tools, for the ingress *detection* half. Naming these is still
# a guess — the tool roster is undocumented, and the live sessions observed so far
# exercised only `Shell`, so no web-tool name has been seen in a transcript yet —
# so nothing depends on the guess being complete: `ingress_verifiable=False`
# already floors the session whether or not a name here matches. A hit only
# sharpens the reported reason from "unverifiable" to "unverifiable, and we can
# see it fetched something".
CURSOR_INGRESS_TOOLS = frozenset(
    {"web_search", "web", "search_web", "fetch", "fetch_url", "read_url", "browser"}
) | {name.lower() for name in EXTERNAL_INGRESS_TOOLS}


@dataclass
class EndedSession:
    """A distillable Cursor session, and how it came to our attention."""

    session_id: str
    scope: str
    transcript_path: Path
    ended_at: datetime | None
    distilled: bool = False
    found_by: frozenset[str] = frozenset({DISCOVERED_BY_HOOK})
    cwd: str = ""

    @property
    def exists(self) -> bool:
        return bool(self.transcript_path) and self.transcript_path.is_file()

    @property
    def scope_resolved(self) -> bool:
        """Did a hook actually resolve this session's scope?

        Distillation must consult this rather than reading `scope` and finding a
        truthy string, because the two failure modes differ: an unresolved scope
        is a decision to route to an operator, not a value to substitute.
        """
        return self.scope != UNRESOLVED_SCOPE


def discover(
    log_path: Path | None = None, projects_dir: Path | None = None
) -> list[EndedSession]:
    """Every Cursor session either surface can see, merged.

    Two surfaces, because each sees what the other cannot. The **hook log** is
    the only place a session's *resolved scope* appears at all — no filesystem
    read can recover a routing decision that a hook made. The **filesystem** is
    the only surface that sees a session which ran before the hooks existed,
    which on a machine Thalamus reaches late is every session on it (lab/054).
    Reading only the log made those unrecoverable by policy rather than by
    format, since their transcripts were on disk the whole time.

    **Merging is per-field, not per-record.** Where both surfaces see a session,
    the hook row supplies `scope` — a fixed rule tied to which surface can know
    the field, which is TOKI's `PerRule` policy and specifically *not*
    last-writer-wins (arXiv 2606.06240); LWW here would let a filesystem row's
    absent scope overwrite a resolved one. Provenance semirings are deliberately
    not the frame: Green et al.'s construction is conditional on the operations
    being positive relational algebra (PODS 2007), and a field-level preference
    between two records that disagree is not in that algebra — the semiring also
    never ranks its sources, which is the entire content of the rule here.
    `found_by` records which surfaces saw the session, and *that* field is a plain
    set union, the one part of this the semiring framing would describe exactly.
    """
    hook = _hook_sessions(log_path or CURSOR_SESSION_END_LOG)
    merged = dict(hook)
    for session_id, found in _filesystem_sessions(projects_dir or CURSOR_PROJECTS).items():
        attested = merged.get(session_id)
        if attested is None:
            merged[session_id] = found
            continue
        merged[session_id] = replace(
            attested,
            found_by=attested.found_by | found.found_by,
            # Only ever fills a gap: the ledger's cwd is our own hook's record and
            # outranks Cursor's, and neither is inference from a path.
            cwd=attested.cwd or found.cwd,
            ended_at=attested.ended_at or found.ended_at,
        )
    return list(merged.values())


def _hook_sessions(path: Path) -> dict[str, EndedSession]:
    """Sessions our sessionEnd hook logged, newest row per session winning.

    Newest by the row's own `ts`, not by position in the file. Those coincide
    only while the log is append-ordered by time, and nothing enforces that —
    a hand-edited or concatenated log silently elected a different winner, and
    with a second surface merging into the same map the tie-break would have
    become iteration order.
    """
    latest: dict[str, EndedSession] = {}
    for record in _records(path):
        session_id = str(record.get("session_id") or "")
        transcript = str(record.get("transcript_path") or "")
        if not session_id or not transcript:
            continue
        candidate = EndedSession(
            session_id=session_id,
            scope=str(record.get("scope") or MAIN_SCOPE),
            transcript_path=Path(transcript),
            ended_at=_timestamp(record.get("ts")),
            distilled=bool(record.get("distilled")),
            found_by=frozenset({DISCOVERED_BY_HOOK}),
        )
        held = latest.get(session_id)
        if held is None or _not_older(candidate.ended_at, held.ended_at):
            latest[session_id] = candidate
    return latest


def _not_older(candidate: datetime | None, held: datetime | None) -> bool:
    """Should `candidate` replace `held`? Undated rows lose to dated ones.

    An undated row replacing a dated one would discard the only ordering
    evidence there is; two undated rows keep the later-read one, which is the
    old positional behaviour and the best available when nothing is stamped.
    """
    if candidate is None:
        return held is None
    return held is None or candidate >= held


def _filesystem_sessions(projects_dir: Path) -> dict[str, EndedSession]:
    """Sessions found by globbing Cursor's own transcript tree.

    Nothing here is inferred from a path. The session id is the directory Cursor
    named after it, and `cwd` is read from Cursor's `meta.json`; un-sanitizing
    the project directory name back into a path is the one route deliberately not
    taken, since the flattening is not known to be injective and a wrong answer
    from it would arrive with no error signal.

    Scope is `UNRESOLVED_SCOPE` for every session found this way, and that is a
    property of the surface rather than of any session: no hook ran, so no scope
    was ever resolved to be recovered.
    """
    found: dict[str, EndedSession] = {}
    if not projects_dir.is_dir():
        return found
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir() or is_sandbox_project(project_dir.name):
            continue
        for session_dir in sorted((project_dir / "agent-transcripts").glob("*")):
            transcript = session_dir / f"{session_dir.name}.jsonl"
            if not transcript.is_file():
                continue
            cwd, _created, updated = _chat_meta(session_dir.name)
            # Defence in depth, and the reason recovering a real `cwd` is
            # load-bearing rather than cosmetic: an extraction sandbox reached by
            # a project dir this test does not recognise is still refused here.
            if cwd and is_sandbox_cwd(cwd):
                continue
            found[session_dir.name] = EndedSession(
                session_id=session_dir.name,
                scope=UNRESOLVED_SCOPE,
                transcript_path=transcript,
                ended_at=updated,
                found_by=frozenset({DISCOVERED_BY_FILESYSTEM}),
                cwd=cwd,
            )
    return found


def _chat_meta(session_id: str) -> tuple[str, datetime | None, datetime | None]:
    """(cwd, created, updated) from Cursor's own per-session `meta.json`.

    Lives at `~/.cursor/chats/<hash>/<session-id>/meta.json`, where the hash is
    not the session and not derivable from it, so the session directory is
    globbed for rather than addressed. Cursor writes `cwd`, `createdAtMs` and
    `updatedAtMs` there (lab/054) — evidence it recorded at the time, which is
    what makes this a read rather than a guess.
    """
    for meta_path in sorted(CURSOR_CHATS.glob(f"*/{session_id}/meta.json")):
        try:
            meta = json.loads(meta_path.read_text(errors="ignore") or "{}")
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(meta, dict):
            return (
                str(meta.get("cwd") or ""),
                _epoch_ms(meta.get("createdAtMs")),
                _epoch_ms(meta.get("updatedAtMs")),
            )
    return "", None, None


def _epoch_ms(value) -> datetime | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def claim_unresolved(
    sessions: list[EndedSession], assign_scope: str = ""
) -> tuple[list[EndedSession], list[EndedSession]]:
    """Split into (distillable, refused) on whether a scope was ever resolved.

    The two answers to an unresolved scope are the same design at two layers, not
    alternatives: the session has to be *discoverable while unassigned* for an
    operator to be able to assign it at all, and distillation has to *wait* until
    one does. So a refused session is returned rather than dropped — the caller
    names it, and `assign_scope` is how the operator claims it.

    An empty `assign_scope` claims nothing. It cannot mean `main`, because the
    whole point is that no default may stand in for a routing decision nobody
    made; a scope written into the graph is not retractable, since vertex IDs
    carry it.
    """
    if not assign_scope:
        return ([s for s in sessions if s.scope_resolved],
                [s for s in sessions if not s.scope_resolved])
    return ([s if s.scope_resolved else replace(s, scope=assign_scope) for s in sessions], [])


def session_context(session_id: str, ledger_path: Path | None = None) -> tuple[str, datetime | None]:
    """(cwd, started_at) for a session — our own ledger first, Cursor's second.

    Cursor transcripts carry neither, and guessing a project from the transcript
    path would be inference this layer exists to avoid. The sessionStart hook
    recorded both at the time, which is strictly better evidence.

    Cursor's own `meta.json` is the fallback rather than the primary for the same
    ordering reason the merge uses: the pin ledger is our tier-0 record of what a
    hook observed, so where both speak the ledger is preferred. Where no hook ever
    ran the ledger is silent, and `meta.json` is still evidence Cursor wrote at the
    time rather than something reconstructed from a directory name.
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
    if cwd and started_at:
        return cwd, started_at
    meta_cwd, created, _updated = _chat_meta(session_id)
    return cwd or meta_cwd, started_at or created


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
    # Structural to this file, not incidental: no Cursor transcript of any session
    # carries the tool results the floor needs. They exist in the session's
    # store.db, which this parser does not open (see module docstring).
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

        # Cursor closes each turn with a `{"type": "turn_ended", "status": ...}`
        # row carrying no `role`. It is structure, not a message, so it is neither
        # a turn to count nor a record we failed to read — recognised and skipped.
        # Measured on the first live Cursor session (lab/054); before it was named
        # here, every real session reported at least one unreadable record, which
        # is the signal that a format change would have to raise.
        if record.get("type") == "turn_ended":
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
                # Cursor's transcript carries no slash-command scaffolding, so every
                # user turn it records is the operator typing. Setting both keeps
                # `has_substance` meaningful on this reader instead of making a
                # Cursor session look command-only and skipping all of them.
                facts.prompt_turns += 1
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
