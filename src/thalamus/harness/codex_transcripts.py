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

**Recognition is complete and kept separate from processing**, on the same rule the
Cursor reader states: a record this grammar does not cover is counted in
`unrecognized` and surfaced by the sweep, never quietly dropped. That rule bites
harder here than it reads, and deliberately. Codex's own protocol layer admits
record kinds this module has never observed — a `function_call` from a
non-code-mode model, an `exec_command_end` event — and they are **not** pre-declared
as tolerated. A codex release that moves tool calls off code mode must arrive as a
loud `unrecognized` count and not as "those sessions touched no files" (RFC 9413's
virtuous intolerance; LangSec, Momot et al., IEEE SecDev 2016).

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
_RESPONSE_ITEMS = frozenset({"message", "reasoning",
                             "custom_tool_call", "custom_tool_call_output"})
_EVENT_MSGS = frozenset({"task_started", "task_complete", "user_message",
                         "agent_message", "token_count",
                         "patch_apply_end", "web_search_end"})

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
            facts.message_count += 1
        elif item == "patch_apply_end":
            _record_touches(facts, payload)
        elif item == "web_search_end":
            search_ends += 1

    # The code-mode count wins where it exists, because that is the surface whose
    # output carried the verbatim text into `external_texts`; `web_search_end` is the
    # fallback for a model that calls the tool directly and writes no such program.
    facts.ingress_detected = len(ingress_calls) or search_ends
    facts.repo_root = resolve_repo_root(facts.cwd)
    return facts


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
