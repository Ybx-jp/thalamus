"""Memory reflex — retrieval triggered by a failed Bash result.

Every other recall surface is agent-initiated: the agent has to notice that a test
failure names a symbol the graph holds a decision about, and ask. The reflex makes the
harness notice instead. `hooks/claude-code/reflex.sh` matches a Bash result that reads
as a failure (a pytest `FAILED` line, a traceback, `command not found`, an exception
line) or one the harness interrupted, and hands the observed output here through
`thalamus reflex`. This module turns it into anchors, retrieves against them, and
renders what came back as a digest that says it arrived unsolicited.

This is the word-match plan — `recall()` fed with extracted anchors. No model is in
the loop: candidates are never paraphrased, so nothing here can re-voice a recorded
decision into an instruction for the reader. What enters the agent's context is a
digest: one line per candidate — a short handle (`R3.1`), its kind, tier, date, its
own first sentence and the anchors it matched — sized in characters under
`DIGEST_CHAR_CAP`. The candidates themselves are quoted verbatim through the reader's
own formatters into a pointer file the digest names. Claude Code hands a hook string
over 10,000 characters to the agent as a 2,000-character preview (#258), and a
candidate count does not bound a firing's size (#251); a digest is bounded by neither
problem. A served set is priced on the same surface as every `memory_recall` — one
line in the trace tap under `tool_name` `reflex_lexical`, carrying the pointer file as
the response so `eval sync` reads the vertex ids from it, the digest's length as the
characters that entered context, and the handle map so a cited handle resolves to
its node — and `thalamus eval reflex` reads the result by arm.

Three controls bound what a session pays for this, in strength order: per-anchor
dedup keyed on `(session, agent, normalised anchor)`, so the same failing test on a
rerun does not refire; a per-session injected-character budget, refused with the
arithmetic when crossed; and no time-based cooldown, which would suppress a genuinely
new anchor arriving inside the window while adding nothing the first two do not cover.

`harness` and not `substrate` because the extractor has to know which scope it is
retrieving for, and pin resolution is the harness's job; `substrate.reader.recall`
takes scope as a plain argument and that is the contract kept. No `eval` import:
`harness` sits below `eval`, so the trace line is a plain file write in the tap's own
schema, and the tap directory is named here as well as in `eval/traces.py`
(`tests/test_reflex.py` holds the two equal).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from thalamus.contract.manifest import available_scopes
from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.harness.extraction import _tokens
from thalamus.substrate.reader import STOPWORDS, recall

# The arm this rung writes into `tool_name`. Reading by arm is the whole instrument:
# `eval report` and `eval reflex` split on this string and enumerate nothing.
ARM_LEXICAL = "reflex_lexical"

# A read of a pointer file, recorded by `reflex-pointer-tap.sh`. Not an arm: it is a
# secondary use signal on a firing an arm already served, and `eval reflex` reads it
# beside the arms rather than as one of them.
POINTER_OPEN = "reflex_pointer_open"

# The failure test, as one POSIX ERE. `reflex.sh` greps the command's output with
# this exact string and `tests/test_reflex.py` reads it back out of the script, so the
# hook and this module cannot drift apart silently. The hook runs on both events a Bash
# call can end on and greps the output that event carries — a `PostToolUse` result's
# `stdout` then `stderr`, or a `PostToolUseFailure`'s `error`, which opens with the
# `Exit code N` line — so a non-zero exit qualifies only when its output matches here,
# the same as a zero one (A0165, cites-as-live). The interruption flag each event
# carries is read separately by the hook.
#
# Line-anchored where the shape allows it. `FAILED`/`ERROR` are pytest's short-summary
# prefixes; `E ` is its assertion-detail gutter; the exception line covers
# `AssertionError: …` and `ModuleNotFoundError: …` as well as a bare `Error: …`; the
# lowercase `error:` form is ruff, ty, tsc and cargo.
FAILURE_PATTERN = (
    r"^(FAILED|ERROR) |^Traceback \(most recent call last\)|: command not found"
    r"|^[A-Za-z_.]*(Error|Exception): |^error(\[[A-Za-z0-9_-]+\])?: |^E {2,}"
)

# How many anchors one firing may query with, and the `limit` it asks `recall()` for.
# `recall()`'s match floor requires a node to hit two distinct anchors, so the anchor
# cap bounds breadth, not precision. `limit` governs only the mixed session/knowledge
# window: the chunk tier is ranked apart under `_CHUNK_WINDOW_CAP` and appended outside
# it, so a firing selects up to MAX_CANDIDATES + 2 candidates (#251). What bounds what
# the agent is handed is `DIGEST_CHAR_CAP`, in characters.
#
# The anchor cap is the latency contract. `recall()` issues four scans per keyword and
# the chunk scan is unindexed (#112), so wall time is linear in anchors: measured
# 2026-09-13 on the live graph at 0.47 s per anchor (n=2 → 0.9 s, n=8 → 3.8 s,
# n=12 → 5.6 s). This rung is the synchronous arm — the agent waits on every firing —
# and process start plus connect cost ~0.55 s on top, so six anchors land at ~3.4 s.
# Raising this is a decision about how long a failed command may stall the session.
MAX_ANCHORS = 6
MAX_CANDIDATES = 3

# A firing needs this many unseen anchors before it retrieves. One new anchor would
# query below the reader's floor — a single-keyword recall is untouched by it — and a
# rerun that differs from the last by one incidental token is the rerun the dedup
# exists to suppress.
MIN_NEW_ANCHORS = 2

# What a session may spend on unsolicited context over its life, in digest characters
# — what entered context, not what the pointer files hold. ~4 chars/token (the dial
# `eval/report.py` prices with), so ~6k tokens. Every injected character rides every
# later call in the session, and the measured ignored share of injected retrieval is a
# third (`substrate/reader.py`), so the ceiling is deliberately low; `eval reflex`
# reports how often it is hit.
SESSION_CHAR_BUDGET = 24_000

# The most one digest may put in context. Claude Code writes a hook string over 10,000
# characters to a file and gives the agent its first 2,000 (#258: 12 of 30 served
# firings, 2026-09-14 to 09-23); the digest stays well under that line whatever the
# firing selected, because its size is set here in characters rather than by how many
# candidates `recall()` returned. A candidate that does not fit is counted in the
# digest and kept in the pointer file, never shortened.
DIGEST_CHAR_CAP = 4_000

# How much of a candidate's own text a digest line quotes to say what it is: its first
# sentence, cut at this many characters with an ellipsis. The line indexes the verbatim
# record; it is not the record.
_GIST_CHARS = 160

# Tokens that failure output carries on nearly every line and that discriminate
# nothing, on top of the reader's prose stopwords. Everything a traceback prints
# around the identifier that matters: the gutter words, the interpreter's paths, the
# test runner's vocabulary.
_NOISE = frozenset(
    {
        "file", "line", "module", "traceback", "most", "recent", "call", "last",
        "error", "errors", "exception", "failed", "failures", "failure", "passed",
        "warning", "warnings", "assert", "assertion", "raise", "return", "self",
        "none", "true", "false", "def", "class", "import", "from", "lambda", "args",
        "kwargs", "python", "python3", "site-packages", "packages", "lib", "usr",
        "bin", "home", "tmp", "src", "test", "tests", "pytest", "short", "summary",
        "info", "collected", "session", "starts", "platform", "linux", "rootdir",
        "plugins", "item", "items", "command", "found", "stdout", "stderr", "exit",
        "code", "status", "value", "values", "type", "object", "str", "int", "list",
        "dict", "print", "typing", "optional", "expected", "actual", "got", "want",
        "instead", "where", "with", "during", "handling", "above", "occurred",
        "another", "direct", "cause", "following",
    }
)

# Anchors are tokens the ingress floor's tokenizer produces (`extraction._tokens`), so
# `.`, `/`, `-` and `_` stay in-class and `harness/reflex.py` survives as one compound
# token with its parts emitted beside it. The dedup key is the sorted tuple of a
# token's word parts — `tool-calls` and `tool calls` both key as `calls tool`.
_WORD_RE = re.compile(r"[a-z0-9]+")
_ALPHA_RE = re.compile(r"[a-z]{3}")
_HEX_RE = re.compile(r"^[0-9a-f]{7,}$")
_NUMERIC_RE = re.compile(r"^[0-9._/-]+$")
# The interpreter's own frames. Every Python traceback walks through them and no
# claim in the graph is about them.
_INTERPRETER_RE = re.compile(r"site-packages|/python3?\.[0-9]|^_pytest|/_pytest/")


def extract_anchors(text: str) -> list[str]:
    """The identifiers in a failure's output worth retrieving on, strongest first.

    Deterministic and model-free. Compound tokens — paths, dotted names, test node
    ids, snake_case — rank ahead of bare words because they are what a claim about
    the same code spells the same way; bare words follow by length. Everything short,
    numeric, hash-shaped, or on the noise list is dropped. Lowercased before
    tokenising, so `AssertionError` is one token and never `assertion` + `error`.
    """
    # A separator left dangling by the character that cut the token — `).read_text()`
    # yields `.read_text` — is not part of the identifier.
    tokens = {token.strip("./-_") for token in _tokens(text)} - {""}
    # A path's last two segments beside the whole path: a claim names a file the way
    # a session spoke of it, which is `harness/reflex.py` far more often than the
    # absolute spelling a traceback prints.
    for token in list(tokens):
        if "/" in token:
            tail = "/".join(token.rstrip("/").split("/")[-2:])
            if tail != token:
                tokens.add(tail)
    seen: dict[str, None] = {}
    for token in sorted(tokens, key=lambda t: (-_compound(t), -len(t), t)):
        if not _worth_anchoring(token):
            continue
        seen.setdefault(token)
        if len(seen) >= MAX_ANCHORS:
            break
    return list(seen)


def _compound(token: str) -> int:
    return 1 if len(_WORD_RE.findall(token)) > 1 else 0


def _worth_anchoring(token: str) -> bool:
    if len(token) < 4 or token in STOPWORDS or token in _NOISE:
        return False
    if _NUMERIC_RE.match(token) or _HEX_RE.match(token) or _INTERPRETER_RE.search(token):
        return False
    # A path's extension and a version fragment are parts, not anchors; a compound
    # whose every part is noise (`site-packages/lib`) or digits (`0.31s`) says
    # nothing either. At least one part has to be a word.
    parts = _WORD_RE.findall(token)
    return any(_ALPHA_RE.search(part) and part not in _NOISE and part not in STOPWORDS
               for part in parts)


def anchor_key(anchor: str) -> str:
    """The spelling-invariant identity a firing is deduplicated on."""
    return " ".join(sorted(_WORD_RE.findall(anchor.lower())))


# Voice the envelope must not carry. The rendered blocks are quoted records — a past
# session's decision, a source's assertion — and the one thing that distinguishes a
# recalled "do not use bare git stash" from an instruction is that the reader is told
# it is a record. The scaffolding therefore never addresses the reader in the
# imperative, and a served block that does is counted and named in the header rather
# than dropped or rewritten: dropping would lose exactly the decisions the reflex
# exists to resurface, and rewriting is the paraphrase the design forbids.
_IMPERATIVE_RE = re.compile(
    # A line's lead-in: list and quote markers, then a formatter field label
    # (`**Summary:** `, `- **decision** `id`: `, `  - _rationale:_ `) if one is there.
    r"(?im)^(?:[-*>#\s]*)(?:\*\*[^*\n]{1,24}\*\*[^:\n]{0,40}:?\s*)?(?:_[a-z_]+:_\s*)?"
    r"(?:you (?:should|must|need to|have to|ought to)|"
    r"(?:now )?(?:fix|run|change|update|delete|remove|add|use|apply|make sure|"
    r"ensure|do not|don't|never|always|stop|start|try)\b)"
)


def imperative_voice(text: str) -> list[str]:
    """Every line of `text` that addresses its reader as an instruction."""
    return [match.group(0).strip() for match in _IMPERATIVE_RE.finditer(text)]


@dataclass(frozen=True)
class ReflexBudget:
    """What one more firing would spend against the session's ceiling.

    Held as a value so the refusal reports the same numbers the check computed —
    `delegate.DelegationPlan`'s shape, for the same reason.
    """

    spent: int
    cost: int
    budget: int = SESSION_CHAR_BUDGET

    @property
    def fits(self) -> bool:
        return self.spent + self.cost <= self.budget

    def refusal(self) -> str:
        return (
            f"reflex would inject {self.cost:,} chars on top of {self.spent:,} already "
            f"served this session, against a {self.budget:,}-char budget — over by "
            f"{self.spent + self.cost - self.budget:,}. Nothing served; the failure "
            "is recorded as budget-refused."
        )


@dataclass
class Firing:
    """One qualifying failure the hook handed over, and what the reflex did with it.

    One line per firing in `~/.thalamus/reflex/sessions/<session>.jsonl`, whether or
    not anything was served: the denominator of "firings per qualifying failure" is
    every invocation, and the trace tap only ever sees the ones that retrieved.
    """

    ts: str
    session_id: str
    agent_id: str
    outcome: str  # served | empty | deduped | refused | no_anchors
    arm: str = ARM_LEXICAL
    anchors: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)
    injected_chars: int = 0
    candidates: int = 0
    voiced: int = 0
    detail: str = ""
    # On a served firing: the pointer file's stem, which is also its handles' prefix.
    firing_id: str = ""
    # The hook event that ran the reflex, which is how the exit status reaches here:
    # `PostToolUse` for a command that exited 0, `PostToolUseFailure` for one that did
    # not. Set on every row and copied into the trace; empty on rows written before
    # the hook passed it (A0166, cites-as-live).
    event: str = ""

    def to_json(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"))


def reflex_dir(base: Path | None = None) -> Path:
    return base or Path.home() / ".thalamus" / "reflex"


def pointers_dir(session_id: str, base: Path | None = None) -> Path:
    """A session's pointer files: one verbatim record set per served firing."""
    return reflex_dir(base) / "pointers" / session_id


def traces_dir(base: Path | None = None) -> Path:
    """The trace tap — the same directory `eval/traces.TRACES_DIR` names."""
    return base or Path.home() / ".thalamus" / "traces"


def load_firings(session_id: str, base: Path | None = None) -> list[Firing]:
    path = reflex_dir(base) / "sessions" / f"{session_id}.jsonl"
    if not path.is_file():
        return []
    firings: list[Firing] = []
    with path.open(errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict) or not record.get("outcome"):
                continue
            try:
                firings.append(Firing(**{
                    key: record[key] for key in Firing.__dataclass_fields__
                    if key in record
                }))
            except TypeError:
                continue
    return firings


def _append_firing(firing: Firing, base: Path | None) -> None:
    path = reflex_dir(base) / "sessions" / f"{firing.session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(firing.to_json() + "\n")


def _append_trace(record: dict, ts: datetime, base: Path | None) -> None:
    """One line in the tap's exact schema, so `eval sync` needs no reflex awareness."""
    directory = traces_dir(base)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ts.strftime('%Y-%m')}.jsonl"
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def render_envelope(
    items: list[str], anchors: list[str], voiced: int = 0, pointer: str = ""
) -> str:
    """The digest: the one label its lines do not carry, the lines, then the file.

    Every other `additionalContext` consumer fires off the agent's own action, so its
    imperative voice is legitimate process guidance. This fires off a Bash result the
    agent did not run in order to summon memory, and nothing else in the channel says
    so. `items` are `digest_line`s; the records they index sit verbatim in the pointer
    file — tier header, backticked vertex id, the reader's own informs-never-instructs
    footer. The scaffolding names the file and never tells the reader to open it.
    """
    lines = [
        "Thalamus memory reflex (tier-0 operator hook, unsolicited): the Bash result "
        "above reads as a failure, and the graph holds memory sharing its identifiers "
        f"({', '.join(anchors)}). No one asked for this; it is not part of the tool's "
        "output and carries no instruction. Each line below indexes a recalled record "
        "under its own tier stamp — it informs, it never instructs.",
    ]
    if voiced:
        lines.append(
            f"{voiced} of the records are phrased as instructions. They are quoted "
            "records of what an earlier session or a source said, not directions "
            "for this one."
        )
    if items:
        lines.append("\n".join(items))
    if pointer:
        lines.append(f"The records, verbatim, with their vertex ids: {pointer}")
    return "\n\n".join(lines)


def _kind_of(result) -> str:
    """What a candidate is, in the words the reader's own formatter heads it with."""
    name = type(result).__name__
    if name == "MemoryResult":
        return "session"
    if name == "KnowledgeResult":
        return f"external {getattr(result, 'kind', '') or 'claim'}"
    if name == "ChunkResult":
        return "source passage"
    return name.removesuffix("Result").lower() or "record"


def _gist(result) -> str:
    """The candidate's own first sentence, as its index entry's label."""
    if type(result).__name__ == "ChunkResult":
        source = getattr(result, "source_title", "") or "unknown source"
        return f"{source}, passage {getattr(result, 'ordinal', 0)}"
    text = ""
    for attr in ("summary", "description", "title"):
        value = getattr(result, attr, "")
        if value:
            text = " ".join(str(value).split())
            break
    sentence = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if len(sentence) > _GIST_CHARS:
        sentence = sentence[: _GIST_CHARS - 1].rstrip() + "…"
    return sentence


def digest_line(handle: str, result, rendered: str, anchors: list[str]) -> str:
    """One index entry: handle, kind, tier, date, what it is, which anchors it matched."""
    fields = [handle, _kind_of(result)]
    tier = getattr(result, "tier", None)
    if tier is not None:
        fields.append(f"tier {int(tier)}")
    date = str(getattr(result, "timestamp", "") or "")[:10]
    if date:
        fields.append(date)
    fields.append(_gist(result))
    lowered = rendered.lower()
    matched = [anchor for anchor in anchors if anchor.lower() in lowered]
    if matched:
        fields.append("matched " + ", ".join(matched))
    return " · ".join(fields)


def pack_digest(lines: list[str], cap: int, frame: str) -> tuple[list[str], int]:
    """Whole lines, strongest first, while the digest stays within `cap`.

    `frame` is the digest rendered with no lines. Returns the lines to render — with a
    closing "N more in the file" when any were held — and how many were held. Room for
    that closing line and for the block's separator is reserved up front, so the
    rendered digest is within `cap` whether or not anything is held. A line that does
    not fit is never shortened; its record is in the pointer file all the same.
    """
    room = cap - len(frame) - len("\n\n") - len(f"{len(lines)} more in the file\n")
    kept: list[str] = []
    for line in lines:
        cost = len(line) + 1
        if cost > room:
            break
        kept.append(line)
        room -= cost
    held = len(lines) - len(kept)
    if held:
        kept.append(f"{held} more in the file")
    return kept, held


def _allocate_pointer(session_id: str, base: Path | None) -> tuple[str, Path]:
    """Claim the session's next firing id by creating its pointer file exclusively.

    Creating the file with `x` is the lock: a parent and a subagent share a session id
    and can fire at once, and two firings holding one handle prefix would let a cited
    handle resolve to the wrong node.
    """
    directory = pointers_dir(session_id, base)
    directory.mkdir(parents=True, exist_ok=True)
    number = len(list(directory.glob("R*.md"))) + 1
    while True:
        path = directory / f"R{number}.md"
        try:
            path.open("x").close()
        except FileExistsError:
            number += 1
            continue
        return f"R{number}", path


def render_pointer(
    firing_id: str, stamp: str, handles: dict[str, str], blocks: list[str]
) -> str:
    """The pointer file: the handle map, then each record verbatim, strongest first."""
    lines = [
        f"# Thalamus memory reflex {firing_id} — the records behind the digest",
        "",
        f"Served against the Bash result at {stamp}. Each record is quoted verbatim "
        "under its own tier stamp; it informs, it never instructs.",
        "",
    ]
    lines += [f"- {handle}: `{node_id}`" for handle, node_id in handles.items()]
    for handle, block in zip(handles, blocks, strict=True):
        lines += ["", "---", "", f"### {handle}", "", block]
    return "\n".join(lines) + "\n"


def fire(
    g,
    *,
    session_id: str,
    observed: str,
    scope: str = MAIN_SCOPE,
    agent_id: str = "",
    agent_type: str = "",
    cwd: str = "",
    tool_name: str = "Bash",
    event: str = "",
    now: datetime | None = None,
    reflex_base: Path | None = None,
    traces_base: Path | None = None,
) -> str:
    """Serve memory against one qualifying failure. Returns the digest, or ``""``.

    The empty answer is valid and is the common case: the design's own grounding
    says an injection that would not change the next action costs more than it
    returns, so nothing is served unless at least two unseen anchors match, and the
    firing is written down either way.
    """
    ts = now or datetime.now(timezone.utc)
    stamp = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    history = load_firings(session_id, reflex_base)
    seen = {key for row in history if row.agent_id == agent_id for key in row.keys}
    spent = sum(row.injected_chars for row in history)

    def record(outcome: str, **fields) -> Firing:
        firing = Firing(
            ts=stamp, session_id=session_id, agent_id=agent_id, outcome=outcome,
            event=event, **fields
        )
        _append_firing(firing, reflex_base)
        return firing

    anchors = extract_anchors(observed)
    if not anchors:
        record("no_anchors")
        return ""

    fresh = [anchor for anchor in anchors if anchor_key(anchor) not in seen]
    if len(fresh) < MIN_NEW_ANCHORS:
        record("deduped", anchors=anchors,
               detail=f"{len(anchors) - len(fresh)} of {len(anchors)} anchors already fired")
        return ""

    # The cheap half of the budget check, ahead of the graph round trip: a session
    # that has spent its ceiling pays nothing more to be told so.
    if spent >= SESSION_CHAR_BUDGET:
        budget = ReflexBudget(spent=spent, cost=0)
        record("refused", anchors=fresh, detail=budget.refusal())
        return ""

    query = " ".join(fresh)
    knowledge = [s for s in available_scopes() if s != scope]
    results = recall(g, query, limit=MAX_CANDIDATES, scope=scope, knowledge_scopes=knowledge)
    blocks = [result.format() for result in results]
    keys = sorted({anchor_key(anchor) for anchor in fresh})

    # `query` is what `TraceEvent.query_text()` labels the Trace with; the rest is the
    # reflex's own record of why this firing asked what it asked, and on a served
    # firing what it handed over.
    tool_input: dict[str, object] = {
        "query": query, "trigger": tool_name, "event": event, "anchors": fresh,
        "keys": keys,
    }
    trace = {
        "ts": stamp,
        "session_id": session_id,
        "scope": scope,
        "cwd": cwd,
        "tool_name": ARM_LEXICAL,
        "tool_input": tool_input,
        "tool_response": "",
        "agent_id": agent_id,
        "agent_type": agent_type,
    }

    if not blocks:
        # A miss is a real event — "the graph had nothing" is the signal that grades
        # the trigger — and nothing was injected, so the response is empty rather than
        # the recall tools' miss sentence: `injected_chars` must price what the agent
        # saw, and `eval report` reads `returned_count == 0` as the miss.
        _append_trace(trace, ts, traces_base)
        record("empty", anchors=fresh, keys=keys)
        return ""

    voiced = sum(1 for block in blocks if imperative_voice(block))
    firing_id, pointer = _allocate_pointer(session_id, reflex_base)
    handles = {
        f"{firing_id}.{index}": str(getattr(result, "node_id", "") or "")
        for index, result in enumerate(results, start=1)
    }
    lines = [
        digest_line(handle, result, block, fresh)
        for handle, result, block in zip(handles, results, blocks, strict=True)
    ]
    frame = render_envelope([], fresh, voiced=voiced, pointer=str(pointer))
    kept, _ = pack_digest(lines, DIGEST_CHAR_CAP, frame)
    # Strongest last, nearest the agent's next turn.
    digest = render_envelope(kept[::-1], fresh, voiced=voiced, pointer=str(pointer))
    budget = ReflexBudget(spent=spent, cost=len(digest))
    if not budget.fits:
        pointer.unlink(missing_ok=True)
        record("refused", anchors=fresh, candidates=len(blocks), detail=budget.refusal())
        return ""

    records = render_pointer(firing_id, stamp, handles, blocks)
    pointer.write_text(records, encoding="utf-8")

    trace["tool_response"] = records
    tool_input.update(
        firing_id=firing_id,
        pointer=str(pointer),
        handles=handles,
        # What entered the agent's context. `tool_response` is the pointer file, read
        # for its vertex ids; pricing it would charge the agent for records it has not
        # opened.
        delivered_chars=len(digest),
    )
    _append_trace(trace, ts, traces_base)
    record(
        "served",
        anchors=fresh,
        keys=keys,
        injected_chars=len(digest),
        candidates=len(blocks),
        voiced=voiced,
        firing_id=firing_id,
    )
    return digest
