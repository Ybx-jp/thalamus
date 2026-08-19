"""Codex transcript discovery and deterministic extraction — the third harness.

Produces the same `TranscriptFacts` the Claude Code reader produces, so extraction,
merging, the ingress floor and provenance all stay unchanged downstream. One
intermediate, three harness dialects.

**Codex's rollout is the richest of the three, and that is the whole story here.**
Where `cursor_transcripts.py` is a long argument about what the format cannot carry,
this module is short because the format carries it. Measured 2026-08-17 against
codex-cli 0.147.0:

    <CODEX_HOME>/sessions/<YYYY>/<MM>/<DD>/rollout-<ISO-ts>-<uuid>.jsonl
    {"timestamp": "2026-08-18T06:50:36.964Z", "type": ..., "payload": {...}}

Every line is timestamped. `session_meta` carries the cwd. Tool calls and their
outputs are both in the file. So none of Cursor's three structural consequences
apply: there is no side store to read, anchors are real identifiers rather than row
indices, and the ingress floor is computable from the transcript alone.

Two things are genuinely different from Claude Code, and both are handled explicitly:

1. **The rollout is filed by date, not by project.** Claude Code's path names the
   cwd, which is what lets `discover()` return a project-keyed map and what the
   SessionEnd hook reads the project dir out of. Codex's path names the day. So a
   codex session is addressed by its **session id**, which is in the filename, in
   `session_meta.session_id`, and in the hook payload — and the cwd is read from the
   file's own first record instead of from its location. `discover()` therefore
   returns a flat list, and `thalamus extract --harness codex` sweeps by id.

2. **Tool calls arrive here as code mode — in the rollout, and only there.** The hook
   layer sees the same call under Claude Code's own names (`Bash` with a `command`,
   `apply_patch` with the patch envelope, `mcp__*`), which is why `hooks/codex/` needs
   no matcher of its own. This module reads the *rollout*, where the same call is
   written a different way, so nothing in `install.HOOK_WIRING`'s vocabulary applies
   below this line.

   A call is a `custom_tool_call` whose `name` is
   always `"exec"` and whose `input` is a *JavaScript program* —
   `tools.exec_command({"cmd": "...", "workdir": "..."})`,
   `tools.apply_patch("*** Begin Patch ...")`. There is no `file_path` field, so
   `transcripts._PATH_INPUTS` has no analogue, and recovering touched files by
   reading the shell line out of a JS program is exactly the inference the
   deterministic layer exists to refuse.

   It does not have to. Codex writes a **second, structured record of the same
   operation** as an `event_msg`: `patch_apply_end` carries
   `changes: {"<absolute path>": {"type": "add"|"update"|"delete", "unified_diff": ...}}`
   and `web_search_end` carries `results: [{url, title, snippet, ...}]`. Those are the
   facts, in a declared shape, with no program to parse. The JS layer is read only for
   *counting* calls and for recognising which tool a call invoked by its declared API
   name — `tools.web__run(` is a name in a documented namespace, not a word guessed
   out of a shell line.

**Two event grammars, and both are current.** codex-cli 0.148.0 replaced the flat
per-kind events above with a single `item_completed` carrying a typed `item`:
`UserMessage` and `AgentMessage` (text under `content: [{type, text}]` rather than a
plain `message` string), `CommandExecution`, `Reasoning`, and `Extension` — whose
`kind: "web.search"` is what `web_search_end` used to be. Codex's own built-ins also
moved to plain `function_call` alongside code mode. Both grammars are read, and the
older one is not a legacy path: rollouts written by every version the operator ever ran
sit in the same `sessions/` tree, so a reader that followed the CLI forward would stop
being able to distill that history.

The cost of learning this late is worth recording, because the recognition rule below
did fire and was still not enough. Records outside the grammar were counted, but the
sweep reports that count as a warning *beside* a session it then skips as empty — so a
68-tool-call session read as "no substantive exchange — nothing to distill", exit 0.
Completeness of recognition is not the same property as a break being visible.

**Recognition is complete and kept separate from processing**, on the same rule the
Cursor reader states: a record this grammar does not cover is counted in
`unrecognized` and surfaced by the sweep, never quietly dropped. That rule bites
harder here than it reads, and deliberately. Codex's own protocol layer admits
record kinds this module has never observed — an `exec_command_end` event, an
`item_completed` item type beyond the five measured — and they are **not**
pre-declared as tolerated. A codex release that changes the grammar again must arrive
as a loud `unrecognized` count and not as "those sessions touched no files" (RFC
9413's virtuous intolerance; LangSec, Momot et al., IEEE SecDev 2016).

**Distillation does not wait, and this is measured rather than assumed.** Cursor's
settle loop exists because Cursor is not documented to flush before firing
sessionEnd. Codex flushes deliberately — the binary carries the error string
`failed to flush transcript before SessionEnd hook` — and three live probes agreed
with it: the rollout was byte-identical at the hook and at process exit (19 lines /
40361 bytes in `codex exec`, 14 / 14 in the interactive TUI). So
`hooks/codex/session-end.sh` distills directly and detached, the way Claude Code's
does, and the sweep here exists only for backfill: every codex session that ran
before the hooks were armed.

**Scope comes from our own ledger, and can legitimately be missing.** Codex records
no scope anywhere, so `hooks/codex/session-start.sh` writes the pin ledger row that
routes the session. One measured wrinkle makes an absent row ordinary rather than
alarming: in the interactive TUI, `SessionStart` fires at the **first submitted
turn**, not at launch. A codex window that was opened and never used therefore has no
ledger row — and also nothing worth distilling, so the two absences coincide. A
session with real turns and no row is a session that predates the hooks, which is
what `--assign-scope` is for.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.harness.transcripts import (
    TranscriptFacts,
    resolve_repo_root,
    to_session_graph as _claude_session_graph,
)
from thalamus.substrate.schema import SessionGraph, Tool

# Codex's config root, and the one env var that moves it. Read at call time rather
# than bound at import, because a room member runs under a relocated `CODEX_HOME`
# the way a Claude Code room member runs under a relocated `CLAUDE_CONFIG_DIR`, and
# a module-level `Path.home()` capture would send every room's sweep at the
# operator's own sessions.
CODEX_HOME_VAR = "CODEX_HOME"

PIN_LEDGER = Path.home() / ".thalamus" / "pins" / "pins.jsonl"

# The same absence the Cursor reader names, for the same reason: defaulting an
# unattested session into the operator's own subgraph is a routing decision nobody
# made, and scope is part of the vertex ID, so it is unrecoverable once written.
UNRESOLVED_SCOPE = ""

# The prefix codex gives every rollout file, and the shape the session id sits in:
# `rollout-<ISO-8601 with ':' replaced by '-'>-<uuid>.jsonl`. The id is the last five
# hyphen-separated groups, which is why it is taken by UUID shape rather than by
# splitting on the first hyphen after the timestamp — the timestamp contains hyphens.
_ROLLOUT_PREFIX = "rollout-"
_UUID_GROUPS = (8, 4, 4, 4, 12)

# Rollout record kinds this grammar covers. Anything outside it is counted, not
# absorbed — see the module docstring on why the list is short on purpose.
_TOP_KINDS = frozenset({"session_meta", "turn_context", "world_state",
                        "response_item", "event_msg"})
# `function_call`/`function_call_output` are the plain function-calling shape, which
# codex uses alongside code mode for its own built-ins (`wait`). Observed on 0.148.0;
# the module docstring predicted them as the shape a non-code-mode model would send.
_RESPONSE_ITEMS = frozenset({"message", "reasoning",
                             "custom_tool_call", "custom_tool_call_output",
                             "function_call", "function_call_output"})
# `item_completed` is 0.148.0's envelope: the flat per-kind events below it
# (`user_message`, `agent_message`, `patch_apply_end`, `web_search_end`) were replaced
# by one event carrying a typed `item`. Both grammars are read, because rollouts
# written by either version sit in the same `sessions/` tree forever — a reader that
# followed the CLI would stop being able to distill the operator's own history.
_EVENT_MSGS = frozenset({"task_started", "task_complete", "user_message",
                         "agent_message", "token_count",
                         "patch_apply_end", "web_search_end",
                         "item_completed", "thread_settings_applied",
                         "turn_aborted"})
# The `item.type` values `item_completed` carries. `CommandExecution` and `Reasoning`
# are recognised and deliberately not counted: each is a second view of a
# `response_item` row that is already counted, and the tool-call total is taken there.
_COMPLETED_ITEMS = frozenset({"UserMessage", "AgentMessage", "CommandExecution",
                              "Reasoning", "Extension"})
# The `Extension` kind that means a fetch happened — 0.148.0's `web_search_end`.
_WEB_EXTENSION = "web.search"

# The declared API name of codex's web tool, as it appears in a code-mode call's
# JavaScript. Matching a namespaced function name is recognition, not the shell
# parsing this layer refuses: `tools.web__run(` either is or is not the call codex
# documents, and a miss costs a floored session rather than a wrong one.
_INGRESS_CALL = "tools.web__run("


def codex_home(home: Path | None = None) -> Path:
    """Codex's config root: `$CODEX_HOME`, else `~/.codex`."""
    if home is not None:
        return home
    override = os.environ.get(CODEX_HOME_VAR)
    return Path(override) if override else Path.home() / ".codex"


def sessions_root(home: Path | None = None) -> Path:
    return codex_home(home) / "sessions"


@dataclass
class CodexSession:
    """A distillable codex session, and where its scope came from."""

    session_id: str
    transcript_path: Path
    scope: str = UNRESOLVED_SCOPE
    started_at: datetime | None = None

    @property
    def exists(self) -> bool:
        return self.transcript_path.is_file()

    @property
    def scope_resolved(self) -> bool:
        """Did a hook actually resolve this session's scope?

        Consulted instead of reading `scope` for a truthy string, because the two
        failure modes differ: an unresolved scope is a decision to route to an
        operator, not a value to substitute.
        """
        return self.scope != UNRESOLVED_SCOPE


def session_id_of(path: Path) -> str:
    """The session id in a rollout filename, or `""` if it is not one.

    Read off the tail by UUID shape. The filename embeds an ISO timestamp whose own
    hyphens make any split-from-the-left rule wrong, and a rollout whose name this
    cannot read is one whose identity we do not know — which must be an empty string
    the caller can refuse, not a guess that becomes a vertex ID.
    """
    name = path.name
    if not name.startswith(_ROLLOUT_PREFIX) or not name.endswith(".jsonl"):
        return ""
    groups = name[len(_ROLLOUT_PREFIX):-len(".jsonl")].split("-")
    if len(groups) < len(_UUID_GROUPS):
        return ""
    tail = groups[-len(_UUID_GROUPS):]
    if [len(part) for part in tail] != list(_UUID_GROUPS):
        return ""
    if not all(all(c in "0123456789abcdefABCDEF" for c in part) for part in tail):
        return ""
    return "-".join(tail)


def discover(home: Path | None = None, *, ledger_path: Path | None = None) -> list[CodexSession]:
    """Every codex session on disk, newest first, with whatever scope the ledger holds.

    One surface, where Cursor needs three. Codex's rollout is written by the CLI
    itself for every session — interactive or `exec`, hooks armed or not — so the
    filesystem is complete by construction and the ledger is consulted only for the
    routing the file cannot carry. That is the opposite arrangement from Cursor,
    where the hook log is the primary surface and the filesystem is the backfill.
    """
    root = sessions_root(home)
    scopes = _ledger_scopes(ledger_path if ledger_path is not None else PIN_LEDGER)

    found: list[CodexSession] = []
    for path in sorted(root.glob("*/*/*/rollout-*.jsonl"), reverse=True):
        session_id = session_id_of(path)
        if not session_id:
            continue
        found.append(
            CodexSession(
                session_id=session_id,
                transcript_path=path,
                scope=scopes.get(session_id, UNRESOLVED_SCOPE),
            )
        )
    return found


def _ledger_scopes(path: Path) -> dict[str, str]:
    """session id -> scope, from the pin ledger. Last row wins.

    Last rather than first: a session that was rescoped mid-life has two rows, and
    the later one is the answer.
    """
    scopes: dict[str, str] = {}
    if not path or not path.is_file():
        return scopes
    with path.open(errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            session_id, scope = row.get("session_id"), row.get("scope")
            if session_id and scope:
                scopes[str(session_id)] = str(scope)
    return scopes


def ledger_scope(session_id: str, ledger_path: Path | None = None) -> str:
    """The scope a hook resolved for one session, or `UNRESOLVED_SCOPE`.

    The single-session form of what `discover()` does in bulk, for the path that
    already knows which transcript it wants and would otherwise have to sweep the
    whole tree to learn where the session was pinned.
    """
    path = ledger_path if ledger_path is not None else PIN_LEDGER
    return _ledger_scopes(path).get(session_id, UNRESOLVED_SCOPE)


def claim_unresolved(
    sessions: list[CodexSession], assign_scope: str = "",
) -> tuple[list[CodexSession], list[CodexSession]]:
    """Split sessions into those a sweep may distill and those it must refuse.

    `assign_scope` is the operator answering the question the ledger could not: it
    claims every unresolved session for one scope, and it is required rather than
    defaulted for the reason `UNRESOLVED_SCOPE` exists — `main` is a real subgraph
    and routing a stranger's session into it is not recoverable.
    """
    ready: list[CodexSession] = []
    refused: list[CodexSession] = []
    for session in sessions:
        if session.scope_resolved:
            ready.append(session)
        elif assign_scope:
            ready.append(
                CodexSession(
                    session_id=session.session_id,
                    transcript_path=session.transcript_path,
                    scope=assign_scope,
                    started_at=session.started_at,
                )
            )
        else:
            refused.append(session)
    return ready, refused


def parse(path: Path, *, session_id: str | None = None) -> TranscriptFacts:
    """Read a rollout and recover every fact that needs no inference."""
    facts = TranscriptFacts(
        session_id=session_id or session_id_of(path) or path.stem,
        path=path,
        harness="codex",
        # Codex embeds its tool results in the rollout, so an empty `external_texts`
        # here means nothing was fetched — the same thing it means on Claude Code,
        # and not the "we cannot know" it means on Cursor.
        ingress_verifiable=True,
        ingress_verdict="verified",
    )
    # call_id -> whether that call was external ingress. Populated from the call and
    # read at its output, because the two are separate rows and only the call names
    # the tool.
    ingress_calls: set[str] = set()
    # The two surfaces that can report a fetch, counted apart and reconciled at the
    # end. They are **alternatives, not additions**: one search writes both a
    # code-mode `tools.web__run(` call and a `web_search_end` event, so adding them
    # reports two fetches for one. Which surface exists depends on the model, so
    # neither can simply be ignored.
    search_ends = 0

    for record, decodable in _rows(path):
        if not decodable or not isinstance(record, dict):
            facts.unrecognized += 1
            continue

        kind = record.get("type")
        payload = record.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        if kind not in _TOP_KINDS:
            facts.unrecognized += 1
            continue

        timestamp = _timestamp(record.get("timestamp"))
        if timestamp:
            facts.started_at = min(facts.started_at or timestamp, timestamp)
            facts.ended_at = max(facts.ended_at or timestamp, timestamp)

        # FIRST cwd wins, matching the Claude Code reader: cwd answers "which project
        # is this session's", which is fixed when the session starts, and a session
        # that `cd`s into another checkout must not be re-attributed by where it
        # stopped. `session_meta` is line 1, so in practice this is that record.
        if payload.get("cwd") and not facts.cwd:
            facts.cwd = str(payload["cwd"])

        if kind in ("session_meta", "turn_context", "world_state"):
            continue

        item = payload.get("type")

        if kind == "response_item":
            if item not in _RESPONSE_ITEMS:
                facts.unrecognized += 1
                continue
            if item == "message":
                # `developer` is the harness's own scaffolding — skills instructions,
                # the permissions preamble — and `user` at this layer is the injected
                # `<environment_context>` block, not the operator. The operator's own
                # prompt arrives as an `event_msg`, which is why turns are counted
                # there and not here.
                if payload.get("role") == "assistant":
                    facts.message_count += 1
            elif item == "custom_tool_call":
                facts.tool_calls += 1
                call_id = payload.get("call_id")
                program = payload.get("input")
                if call_id and isinstance(program, str) and _INGRESS_CALL in program:
                    ingress_calls.add(str(call_id))
            elif item == "function_call":
                # Same event as a code-mode call — one tool invocation — so it is
                # counted in the same total and not in a second one.
                facts.tool_calls += 1
            elif item == "custom_tool_call_output":
                if payload.get("call_id") in ingress_calls:
                    text = _output_text(payload.get("output"))
                    if text:
                        facts.external_texts.append(text)
            continue

        # kind == "event_msg"
        if item not in _EVENT_MSGS:
            facts.unrecognized += 1
            continue

        if item == "user_message":
            text = payload.get("message")
            if isinstance(text, str) and text.strip():
                facts.user_turns += 1
                # No command/prompt split, because codex has nothing to split: its
                # slash commands are handled in the TUI and never reach the rollout,
                # so every `user_message` row is the operator typing. Claude Code
                # needs the distinction because `<command-name>` records land in the
                # transcript as user turns.
                facts.prompt_turns += 1
                if not facts.first_prompt:
                    facts.first_prompt = text.strip()
        elif item == "agent_message":
            # Recognised, not counted. The same reply is already counted as a
            # `response_item` message with `role: assistant` — measured 1:1 on both
            # grammars (2/2 on 0.147.0, 30/30 on 0.148.0). Counting both surfaces
            # reported every codex session as having twice the assistant turns it had,
            # the same alternatives-not-additions trap `search_ends` is reconciled for.
            pass
        elif item == "patch_apply_end":
            _record_touches(facts, payload)
        elif item == "web_search_end":
            search_ends += 1
        elif item == "item_completed":
            search_ends += _record_completed_item(facts, payload)

    # The code-mode count wins where it exists, because that is the surface whose
    # output carried the verbatim text into `external_texts`; `web_search_end` is the
    # fallback for a model that calls the tool directly and writes no such program.
    facts.ingress_detected = len(ingress_calls) or search_ends
    facts.repo_root = resolve_repo_root(facts.cwd)
    return facts


def _item_text(item: dict) -> str:
    """The text of an `item_completed` message item.

    0.148.0 carries it as `content: [{type: "text", text: ...}]` where the flat events
    carried a plain `message` string. Parts other than `text` are skipped rather than
    stringified — an image part rendered as its repr would land in `first_prompt`.
    """
    content = item.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [p.get("text") for p in content
             if isinstance(p, dict) and isinstance(p.get("text"), str)]
    return "\n".join(part for part in parts if part)


def _record_completed_item(facts: TranscriptFacts, payload: dict) -> int:
    """Fold one 0.148.0 `item_completed` event in. Returns fetches to add.

    Counts the two things this envelope is the *only* surface for — the operator's
    prompts and a `web.search` extension — and deliberately counts nothing else. Its
    `CommandExecution` and `Reasoning` items restate `response_item` rows that are
    already counted, so folding them in would inflate the same totals twice.

    An unknown `item.type` increments `unrecognized` rather than being ignored, on the
    module's standing rule: the next grammar change has to arrive as a number somebody
    reads. That rule is what surfaced this one — but only as a warning beside a session
    the sweep then skipped as empty, which is why the recognition count alone was not
    enough to make the break visible.
    """
    item = payload.get("item")
    if not isinstance(item, dict):
        facts.unrecognized += 1
        return 0
    kind = item.get("type")
    if kind not in _COMPLETED_ITEMS:
        facts.unrecognized += 1
        return 0

    if kind == "UserMessage":
        text = _item_text(item)
        if text.strip():
            facts.user_turns += 1
            # No command/prompt split, for the reason the flat grammar's branch gives:
            # codex handles slash commands in the TUI and they never reach the rollout.
            facts.prompt_turns += 1
            if not facts.first_prompt:
                facts.first_prompt = text.strip()
    elif kind == "Extension" and item.get("kind") == _WEB_EXTENSION:
        return 1
    return 0


def _record_touches(facts: TranscriptFacts, payload: dict) -> None:
    """Anchor every file a patch touched to the call that touched it.

    The anchor is codex's own `call_id`, not a synthesized row index: unlike Cursor,
    codex writes real identifiers, so the provenance walk lands on the exact call
    without this module inventing an addressing scheme for it.
    """
    changes = payload.get("changes")
    if not isinstance(changes, dict):
        # A `patch_apply_end` whose changes we cannot read is a recognised record
        # carrying an unreadable field — the case the count exists for.
        facts.unrecognized += 1
        return
    anchor = str(payload.get("call_id") or "")
    for identifier in changes:
        if not identifier:
            continue
        anchors = facts.touched.setdefault(str(identifier), [])
        if anchor and anchor not in anchors:
            anchors.append(anchor)


def _output_text(output) -> str:
    """The verbatim text of a tool output, whose blocks codex writes as a list.

    Joined rather than taking the first block: a codex tool output is a preamble
    block (`Script completed\\nWall time 1.0 seconds\\nOutput:`) followed by the
    payload, and the floor judges claims against what the model actually read.
    """
    if isinstance(output, str):
        return output
    if not isinstance(output, list):
        return ""
    parts = [
        block.get("text", "")
        for block in output
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    ]
    return "\n".join(part for part in parts if part)


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
    """The deterministic half, stamped as codex's.

    Delegates to the Claude Code builder and re-stamps `tool`: the three harnesses
    differ in what they record, not in what a session *is*, and forking the builder
    would fork the schema contract with it.
    """
    graph = _claude_session_graph(
        facts, content_hash=content_hash, uri=uri, byte_size=byte_size, scope=scope,
        room=room, forked_from=forked_from,
    )
    return graph.model_copy(update={"tool": Tool.CODEX})


def _rows(path: Path):
    """Yield (record, decodable) for every non-blank line, decode failures included.

    Decode failures are yielded rather than skipped so the parser can *count* what it
    could not read; a reader that silently drops them turns a format change into a
    session with fewer turns.
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


def _timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Live status
#
# Claude Code answers "what is this session doing" from a descriptor its own runtime
# writes; codex publishes nothing of the kind, and the repo's hook table has no
# turn-*end* event to synthesize one from — `SessionStart`, `SessionEnd`,
# `UserPromptSubmit`, `PreToolUse` and `PostToolUse` can all say a turn began and none
# can say it finished. A status bracketed by those events alone would enter `busy` and
# never leave it.
#
# The rollout carries the missing half. `task_started` and `task_complete` are
# `event_msg` rows codex writes from inside its own event loop, timestamped, one pair
# per turn — a first-party record of the turn boundary rather than a state we infer
# from the outside. Measured 2026-08-22 on codex-cli 0.148.0: a completed TUI turn ends
# `… token_count, task_complete`, and the pair brackets the turn exactly.
#
# So the reader here is not a heartbeat and not a screen read. It reports what codex
# recorded, and reports UNKNOWN whenever the record does not reach.

#: The status vocabulary, which is `harness/dispatch.py`'s and not a second one.
#: Spelled rather than imported because `dispatch` imports half the harness and this
#: module is on the extraction path; `tests/test_codex_liveness.py` asserts the two
#: agree, so the duplication cannot drift silently.
CODEX_IDLE = "idle"
CODEX_BUSY = "busy"

#: No turn boundary in reach. Distinct from `idle` on purpose: "codex recorded that it
#: finished" and "we could not find out" are different facts, and collapsing them is
#: the inversion the readiness design refuses — absence must never render as rest.
CODEX_UNKNOWN = ""

#: How much of the rollout's tail to read. A rollout runs to megabytes over a long
#: session and the console polls this per row per refresh, so the whole file is not an
#: option. 256 KiB clears the largest single turn observed on this box (a 2.6 MB
#: rollout whose final turn was 41 KiB) with room to spare; when it does not reach a
#: boundary the answer is UNKNOWN, which is the honest outcome rather than a fallback.
_TAIL_BYTES = 256 * 1024


def live_status(path: Path, *, tail_bytes: int = _TAIL_BYTES) -> tuple[str, datetime | None]:
    """(status, since) for a codex session, read from its rollout's tail.

    `status` is `busy` when the last turn boundary in reach is a `task_started`, `idle`
    when it is a `task_complete`, and `CODEX_UNKNOWN` when the tail holds neither — an
    unwritten rollout, a session still in its first turn, a file that is not there, or
    a turn longer than the window read. `since` is that boundary's timestamp, or None.

    Liveness is deliberately *not* answered here. Whether the process still exists is a
    question tmux already answers for the console (`#{pane_dead}`) and `/proc` answers
    for `quick.live_sessions`; a rollout is a record of what happened, and its last row
    says the same thing whether the session is running or was killed an hour ago. A
    caller that wants "alive and idle" must ask both, and the two must not be fused
    into one field that reads as either.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return CODEX_UNKNOWN, None

    try:
        with path.open("rb") as handle:
            if size > tail_bytes:
                handle.seek(size - tail_bytes)
                # The seek lands mid-record; that partial first line is dropped rather
                # than parsed, so a truncated row never decodes into a boundary.
                handle.readline()
            blob = handle.read()
    except OSError:
        return CODEX_UNKNOWN, None

    status, since = CODEX_UNKNOWN, None
    for line in blob.splitlines():
        if b"task_started" not in line and b"task_complete" not in line:
            # The substring test is a filter, never the decision: `task_complete` also
            # occurs inside message text, so a line that passes it is still parsed and
            # checked structurally below. It exists because JSON-decoding every row of
            # a 256 KiB tail on every console poll is the cost this avoids.
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(record, dict) or record.get("type") != "event_msg":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        kind = payload.get("type")
        if kind == "task_started":
            status, since = CODEX_BUSY, _timestamp(record.get("timestamp"))
        elif kind == "task_complete":
            status, since = CODEX_IDLE, _timestamp(record.get("timestamp"))
    return status, since


def rollout_path(session_id: str, home: Path | None = None) -> Path | None:
    """The rollout a codex session writes, located by id, or None.

    `console/transcript.transcript_path` answers the same question for Claude Code and
    cannot answer it here: it looks under `~/.claude/projects/<slug>/`, a tree keyed by
    the session's working directory. Codex partitions by *date* instead
    (`$CODEX_HOME/sessions/YYYY/MM/DD/`), and a session's cwd appears nowhere in the
    path — so the directory a caller knows is no help and the id in the filename is the
    whole of the join.

    The glob is bounded to the date layout rather than a full `rglob`: a session's
    rollout is always exactly three levels down, and walking the whole tree to find it
    would put every archived day on the path of a console poll.
    """
    if not session_id:
        return None
    root = sessions_root(home)
    if not root.is_dir():
        return None
    # Newest first: a resumed session can leave more than one rollout carrying the same
    # id, and the live one is the one still being appended to.
    found = sorted(root.glob(f"*/*/*/{_ROLLOUT_PREFIX}*{session_id}.jsonl"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return found[0] if found else None
