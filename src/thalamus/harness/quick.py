"""The quick protocol — the second consultation tier (docs/02).

Inside a room, a caller blocked on a question answers it by **forking the expert's
own live session** (`claude -p --resume <sid> --fork-session`) instead of spawning a
cold subagent that must recall its way to competence. The parent is never signalled
and keeps working; non-interruption is why this forks rather than messaging the live
expert (arXiv 2505.02279).

The tier is defined by what it **keeps** — the exchange record in full, the citation
gate unchanged, and at least one fresh in-ticket recall — and by what it **drops**:
the brief, whose absence is recorded as a fact rather than left as silence. The grant
is not dropped but degenerate: a compact assertion that this fork inherits parent P's
scope S as of fork point F.

Everything the launcher is obliged to do here was measured, not reasoned
(`lab/049-the-fork-is-the-whole-conversation.md`):

- **`--agent thalamus-<scope>` is a launcher obligation.** `--resume` restores the
  conversation, not the launch flags, so a fork of a `homelab` parent arrives at
  `scope=main, agent=""` while holding the expert's full context — right voice, wrong
  record, no symptom in the answer text. Matching the parent's agent is also free
  against the prompt cache; mismatching it costs a full miss.
- **`THALAMUS_FORKED_FROM` is the other one.** Without it a fork files as an
  independent witness of what is really its parent's episode.
- **Targets resolve from the live roster, never the pin ledger.** The ledger has no
  exit event, so its newest row is a birth certificate that can name a dead session.
- **The fork runs in the parent's cwd**, or its transcript lands somewhere
  `transcripts.discover()` withholds and the distillation fails in a detached log.
- **Both cache fields are recorded.** A cost table without `cache_read_input_tokens`
  is what produced a 16× wrong price once already.

The fork is also not reliably a well-behaved answerer: one measured fork read an
appended question as a prompt injection into the parent's frame and declined it. So
the question is delivered inside an explicit frame break, and "the fork answered the
parent's question" is handled as an outcome rather than an anomaly.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from thalamus.harness import agents, pin

PINS_FILE = Path.home() / ".thalamus" / "pins" / "pins.jsonl"

# The fork answers from memory; it does not go inspect the box. Restricting the
# toolset is the tier's own shape (docs/02) and it is also the cheaper arm: the
# unrestricted cold comparator in lab/049 spent 21 of 31 tool calls on discovery.
DEFAULT_ALLOWED_TOOLS = "mcp__thalamus"

# Long enough for a real call (52–122 s warm, and the mandated fresh recall adds
# ~40 s), short enough that a wedged fork does not hold the caller forever.
DEFAULT_TIMEOUT = 600

# A `claude -p` that cannot authenticate exits 0 with a well-formed envelope whose
# `result` is the login notice. Found by accident (lab/049): the result string needs
# checking, not just the exit code.
_NOT_AN_ANSWER = re.compile(r"\bnot logged in\b|/login\b", re.IGNORECASE)


class QuickRefused(RuntimeError):
    """The protocol declined before spending anything. The message is the reason."""


@dataclass(frozen=True)
class LiveSession:
    """One entry of `$CLAUDE_CONFIG_DIR/sessions/<pid>.json`, liveness already checked."""

    session_id: str
    pid: int
    proc_start: str
    cwd: str
    agent: str
    name: str
    status: str
    updated_at: int
    descriptor: Path

    @property
    def scope(self) -> str:
        """The expert this session is pinned to, from its launch agent."""
        if self.agent.startswith(pin.AGENT_PREFIX):
            return self.agent[len(pin.AGENT_PREFIX):]
        return ""

    @property
    def between_turns(self) -> bool:
        """Not mid-turn — the cheap moment to fork, and never a precondition for it.

        A mid-turn fork costs 13× the post-turn price, because a truncated
        conversation lands on no cached block boundary (lab/049), and it also misses
        the message body the parent is still writing. Both are recorded on the
        exchange and neither gates the call: forking a *busy* expert without
        disturbing it is what this tier is for. The harness writes several resting
        states (`idle`, `waiting`) and one working one, so the test is `busy`-or-not
        rather than an allow-list.
        """
        return self.status != "busy"

    @property
    def age_seconds(self) -> float:
        """Since the harness last touched this descriptor — the cost predictor.

        Warmth decays well inside the nominal 1-hour TTL: 44.8% of the parent's
        prefix at 38 minutes.
        """
        if not self.updated_at:
            return float("inf")
        return max(0.0, datetime.now(timezone.utc).timestamp() - self.updated_at / 1000)


def config_dir(env: dict[str, str] | None = None) -> Path:
    """The config dir *this process* is in — the room's, when it is in one.

    Deliberately not `pin.host_config_dir()`, which refuses a room dir because it
    answers a different question (what a new room is provisioned *from*). Discovery
    is the room boundary: a caller inside a room must see its room-mates and nobody
    else, which is exactly what reading its own `CLAUDE_CONFIG_DIR` gives (lab/045).
    """
    env = os.environ if env is None else env
    value = env.get("CLAUDE_CONFIG_DIR", "")
    return Path(value).expanduser() if value else Path.home() / ".claude"


def _proc_start(pid: int) -> str:
    """Field 22 of `/proc/<pid>/stat`, or "" if the process is gone.

    Split on `") "` first: `comm` is parenthesised and may contain spaces, so a
    naive whitespace split shifts every field after it.
    """
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return ""
    _, _, rest = stat.partition(") ")
    fields = rest.split()
    return fields[19] if len(fields) > 19 else ""


def live_sessions(config_dir_override: Path | None = None) -> list[LiveSession]:
    """Every session the harness currently has registered in this config dir.

    Entries are removed on clean exit, so the directory is close to the truth — but
    only close: a killed session leaves its file behind. Liveness is `pid` *plus*
    `procStart` against `/proc`, which defeats pid reuse.
    """
    root = Path(config_dir_override) if config_dir_override else config_dir()
    sessions_dir = root / "sessions"
    if not sessions_dir.is_dir():
        return []
    found: list[LiveSession] = []
    for descriptor in sorted(sessions_dir.glob("*.json")):
        try:
            data = json.loads(descriptor.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        pid = int(data.get("pid") or 0)
        proc_start = str(data.get("procStart") or "")
        if not pid or not data.get("sessionId"):
            continue
        if proc_start and _proc_start(pid) != proc_start:
            continue  # dead, or the pid was reused by something else
        found.append(
            LiveSession(
                session_id=str(data["sessionId"]),
                pid=pid,
                proc_start=proc_start,
                cwd=str(data.get("cwd") or ""),
                agent=str(data.get("agent") or ""),
                name=str(data.get("name") or ""),
                status=str(data.get("status") or ""),
                updated_at=int(data.get("updatedAt") or 0),
                descriptor=descriptor,
            )
        )
    return found


def resolve_target(scope: str, config_dir_override: Path | None = None) -> LiveSession:
    """The one live session pinned to `scope`, or a refusal naming what it found.

    Zero and two both refuse rather than pick. Forking a dead session's transcript
    asks a snapshot while closing an exchange that reads as a live consultation; and
    two same-scope members of one room share a `<room>-<scope>` name, so a caller
    cannot address them apart anyway.
    """
    candidates = [s for s in live_sessions(config_dir_override) if s.scope == scope]
    if not candidates:
        seen = sorted({s.scope for s in live_sessions(config_dir_override) if s.scope})
        known = ", ".join(seen) or "(none)"
        raise QuickRefused(
            f"no live session is pinned to scope `{scope}` — the quick tier forks a "
            f"running expert, so open one first (`thalamus spawn {scope}`) or use the "
            f"full ticket. Live expert scopes: {known}."
        )
    if len(candidates) > 1:
        rows = ", ".join(f"{s.session_id[:8]} (pid {s.pid})" for s in candidates)
        raise QuickRefused(
            f"{len(candidates)} live sessions are pinned to scope `{scope}` — refusing "
            f"to pick between them: {rows}. Close one, or consult by full ticket."
        )
    return candidates[0]


def await_target(
    scope: str,
    wait: int = 0,
    config_dir_override: Path | None = None,
    poll: float = 2.0,
    sleeper=time.sleep,
) -> LiveSession:
    """Resolve the target, optionally holding for a mid-turn parent to land its turn.

    **A busy parent is not refused.** Non-interruption is the reason this tier forks
    rather than messaging the live expert — an expert that has to be free before it can
    be consulted is an expert you interrupted (docs/02). A mid-turn fork costs ~13× and
    misses the message body its parent is still writing, and both are recorded on the
    exchange; neither is a reason to send a blocked caller away.

    Waiting is therefore the *optimisation*, offered and never imposed: it spends the
    caller's latency, which is the endpoint the tier is justified on, to save the
    fork's dollars. `wait=0` — fork now — is the default for that reason. The deadline
    expiring is not a failure either; it just forks.
    """
    target = resolve_target(scope, config_dir_override)
    if wait <= 0 or target.between_turns:
        return target
    deadline = datetime.now(timezone.utc).timestamp() + wait
    while datetime.now(timezone.utc).timestamp() < deadline:
        sleeper(poll)
        # Re-resolved rather than re-read: a parent can exit inside the wait, and a
        # second same-scope session can appear, both of which change the answer.
        target = resolve_target(scope, config_dir_override)
        if target.between_turns:
            return target
    return target


def grant_text(target: LiveSession, scope: str, fork_point: datetime) -> str:
    """The degenerate grant: format thinned to one assertion, presence kept.

    The delegation literature's own tiering splits a credential's format, never its
    presence (arXiv 2510.19619), and this is the same field set the keyed-answerer
    minimum for replay consistency requires (arXiv 2604.14022) — who is answering,
    under which scope, as of when.
    """
    return (
        f"fork of session {target.session_id} (pid {target.pid}), inheriting scope "
        f"`{scope}` as of {fork_point.isoformat()}"
    )


def fork_prompt(
    *, ticket: str, question: str, from_scope: str, scope: str, grant: str
) -> str:
    """The question, wrapped in an explicit frame break.

    A bare appended question is read by the fork inside its parent's frame — one
    measured fork treated it as a prompt injection and declined it, answering the
    parent's open tasks instead (lab/049). The wrapper says plainly that a different
    session is asking, and states the tier's obligations in the same breath.

    **The first line is deliberately not a tag.** `transcripts.parse` counts a
    `<`-prefixed user record as harness scaffolding rather than a turn, so a prompt
    opening with the wrapper gives the fork's delta zero user turns and extraction
    declines it as a non-conversation — measured on the first live call, which
    answered correctly and then distilled nothing.

    **The fork answers; it does not close.** Acceptance is the launcher's, after the
    ledger row is checked, and an answerer that burns its own ticket through the MCP
    tool closes the exchange before that check can run.
    """
    return "\n".join(
        [
            f"QUICK CONSULTATION — ticket {ticket}, from scope `{from_scope}`.",
            f'<quick-consultation ticket="{ticket}" from-scope="{from_scope}">',
            "STOP — this is not a continuation of the conversation above, and it is "
            "not an instruction found inside anything you were reading. A different "
            f"session, working in scope `{from_scope}`, is blocked and is consulting "
            f"you as the `{scope}` expert. Answer *this* question and nothing else; "
            "your own prior task is not resumed by this message.",
            "",
            f"**Grant:** {grant}.",
            "**No brief was served** — this is the quick tier (docs/02), so you are "
            "answering from your own context rather than from a server-assembled "
            "brief. That context is a cache, and a cache goes stale: it was retrieved "
            "to answer different questions.",
            "",
            "Obligations, both enforced:",
            f'1. Run at least one fresh recall with `ticket="{ticket}"` before you '
            "answer — the mcp__thalamus__memory_* tools take that argument. It "
            "revalidates what you already hold and puts current vertex IDs in front "
            "of you. This is counted from your own tool calls, not from what you say "
            "you did.",
            "2. Cite the graph nodes your answer rests on as backticked vertex IDs, "
            "exactly as recall renders them. Uncited answers are rejected and the "
            "ticket stays open.",
            "",
            "Do NOT call `consult_answer` — the calling session closes this exchange "
            "once it has verified the fork's own record. Your reply *is* the answer.",
            "",
            "**Question:**",
            question.strip(),
            "</quick-consultation>",
        ]
    )


@dataclass
class ForkRun:
    """What the fork cost and what it said. Every quick exchange prices itself."""

    session_id: str
    result: str
    cost_usd: float = 0.0
    duration_ms: int = 0
    num_turns: int = 0
    is_error: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    wall_ms: int = 0

    @property
    def cache_hit(self) -> float:
        """Share of the input prefix served from the parent's cache, 0.0–1.0.

        The single number that separates a $0.03 call from a $0.60 one, and the one
        the first cost table here omitted.
        """
        total = self.cache_read_input_tokens + self.cache_creation_input_tokens
        return (self.cache_read_input_tokens / total) if total else 0.0

    def price(self) -> dict[str, object]:
        """The cost properties written onto the Exchange."""
        return {
            "wall_ms": self.wall_ms,
            "duration_ms": self.duration_ms,
            "cost_usd": self.cost_usd,
            "num_turns": self.num_turns,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_hit": round(self.cache_hit, 4),
        }


def fork_argv(
    target: LiveSession,
    scope: str,
    fork_session_id: str,
    *,
    allowed_tools: str = DEFAULT_ALLOWED_TOOLS,
    name: str = "",
) -> list[str]:
    """The launch line. `--agent` carries the *parent's* scope, never the caller's."""
    argv = [
        agents.cli_for("claude").binary,
        "-p",
        "--output-format", "json",
        "--resume", target.session_id,
        "--fork-session",
        "--session-id", fork_session_id,
        "--agent", pin.agent_name(scope),
    ]
    if allowed_tools:
        argv += ["--allowedTools", allowed_tools]
    if name:
        argv += ["--name", name]
    return argv


def fork_env(target: LiveSession, base: dict[str, str] | None = None) -> dict[str, str]:
    """The parent's identity, handed forward.

    `THALAMUS_FORKED_FROM` is the launcher's alone to set: the harness mints a new
    session id and tells the forked process nothing about the old one, and recovering
    the link from transcript content afterwards would be inference over model-written
    text. `CLAUDE_CONFIG_DIR` is deliberately left as inherited — a caller inside a
    room already carries the room's, and that is how a fork lands in the room's
    `projects/` with the launcher doing nothing.
    """
    env = dict(os.environ if base is None else base)
    env["THALAMUS_FORKED_FROM"] = target.session_id
    return env


def run_fork(
    target: LiveSession,
    scope: str,
    prompt: str,
    *,
    fork_session_id: str = "",
    allowed_tools: str = DEFAULT_ALLOWED_TOOLS,
    timeout: int = DEFAULT_TIMEOUT,
    name: str = "",
    env: dict[str, str] | None = None,
    runner=subprocess.run,
) -> ForkRun:
    """Fork the expert's live session and block on its answer.

    `--resume` takes no lock and does not perturb a parent that is mid-turn: the fork
    is a point-in-time snapshot of what is *written*, not of what the parent believes.
    """
    fork_session_id = fork_session_id or str(uuid.uuid4())
    argv = fork_argv(
        target, scope, fork_session_id, allowed_tools=allowed_tools, name=name
    )
    started = datetime.now(timezone.utc)
    try:
        proc = runner(
            argv,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=target.cwd or None,
            env=fork_env(target, env),
        )
    except FileNotFoundError as exc:
        raise QuickRefused("`claude` CLI not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise QuickRefused(f"the fork did not answer within {timeout}s") from exc
    wall_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

    if proc.returncode != 0 and not (proc.stdout or "").strip():
        raise QuickRefused(
            f"claude -p exited {proc.returncode}: {(proc.stderr or '').strip()[:300]}"
        )
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise QuickRefused(f"unparseable claude -p output: {proc.stdout[:200]}") from exc

    usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
    run = ForkRun(
        # The envelope's own id is authoritative over the one we asked for: if the
        # harness ever ignored --session-id, the delta distillation would otherwise
        # be computed against a transcript that does not exist.
        session_id=str(envelope.get("session_id") or fork_session_id),
        result=str(envelope.get("result") or ""),
        cost_usd=float(envelope.get("total_cost_usd") or 0.0),
        duration_ms=int(envelope.get("duration_ms") or 0),
        num_turns=int(envelope.get("num_turns") or 0),
        is_error=bool(envelope.get("is_error")),
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_read_input_tokens=int(usage.get("cache_read_input_tokens") or 0),
        cache_creation_input_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        wall_ms=wall_ms,
    )
    if _NOT_AN_ANSWER.search(run.result) and run.num_turns <= 1:
        raise QuickRefused(
            "the fork returned a login notice instead of an answer — the launcher is "
            "shelling into a config dir it is not authenticated for: "
            f"{run.result.strip()[:200]}"
        )
    return run


@dataclass
class LedgerRow:
    """The fork's own SessionStart record — the launcher's obligations, verified."""

    found: bool
    scope: str = ""
    agent: str = ""
    forked_from: str = ""
    room: str = ""


def ledger_row(session_id: str, pins_file: Path | None = None) -> LedgerRow:
    """The last *pin* row for a session. Last-wins, as every reader here does.

    Lifecycle rows share the ledger and must be skipped, not merged: `pin-engaged.sh`
    appends `{event: "engaged", session_id, scope, ts}` after the pin row, carrying no
    `agent` and no `forked_from`. Last-wins across both reads those two as empty and
    reports a launcher that met every obligation as having met none — measured on the
    first live quick call, whose row was correct and whose assertion was not.
    """
    path = pins_file or PINS_FILE
    row = LedgerRow(found=False)
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return row
    for line in lines:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("session_id") != session_id or data.get("event"):
            continue
        row = LedgerRow(
            found=True,
            scope=str(data.get("scope") or ""),
            agent=str(data.get("agent") or ""),
            forked_from=str(data.get("forked_from") or ""),
            room=str(data.get("room") or ""),
        )
    return row


def assert_ledger(
    fork_session_id: str,
    scope: str,
    parent_session_id: str,
    pins_file: Path | None = None,
) -> list[str]:
    """Divergences between what the launcher promised and what the fork recorded.

    Empty means the fork armed the expert's scope and filed as its parent's
    dependent. This is the check with no other symptom: a fork launched without
    `--agent` still reads the *pinned* prefix and answers in the expert's voice while
    its ledger row says `scope=main, agent=""`, so nothing in the answer text shows
    the divergence and no historical row would flag the regression.
    """
    row = ledger_row(fork_session_id, pins_file)
    if not row.found:
        return [
            f"no pin-ledger row for fork `{fork_session_id[:8]}` — SessionStart did "
            "not fire for it, so neither its scope nor its parent is recorded"
        ]
    issues: list[str] = []
    if row.scope != scope:
        issues.append(
            f"fork filed as scope `{row.scope or '(none)'}`, not `{scope}` — it "
            "answered in the expert's voice and recorded someone else's"
        )
    if row.agent != pin.agent_name(scope):
        issues.append(
            f"fork recorded agent `{row.agent or '(none)'}`, not "
            f"`{pin.agent_name(scope)}`"
        )
    if row.forked_from != parent_session_id:
        issues.append(
            f"fork recorded forked_from `{row.forked_from or '(none)'}`, not "
            f"`{parent_session_id}` — its agreement with its parent would read as "
            "independent corroboration"
        )
    return issues


# ---------------------------------------------------------------------------
# The delta: a fork's transcript is its parent's, restamped.
# ---------------------------------------------------------------------------

# Where a fork's own records are materialized for distillation. Durable rather than
# temporary, and deliberately so: the delta is the evidence for an answer whose claim
# survives in the caller's memory, and the sandbox guard — the other way to keep a
# headless run from becoming memory — would have discarded exactly that.
FORKS_DIR = Path.home() / ".thalamus" / "forks"


def _uuids(transcript: Path) -> set[str]:
    seen: set[str] = set()
    try:
        lines = transcript.read_text(errors="replace").splitlines()
    except OSError:
        return seen
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("uuid"):
            seen.add(str(record["uuid"]))
    return seen


def delta_records(fork: Path, parent: Path) -> list[str]:
    """The fork's own records: those whose UUIDs the parent's transcript lacks.

    A fork's JSONL is the parent's whole conversation restamped with the fork's
    `sessionId`, with the parent's message UUIDs preserved verbatim (562/562
    measured). Distilling it whole mints a second Session re-asserting the parent's
    episode and archives a second near-identical Source that the archive cannot
    dedup, because `archive_bytes` is content-addressed and every `sessionId` line
    differs. An exact set difference, never a timestamp heuristic: the fork's own
    turn is not reliably the newest thing in the file.
    """
    parent_uuids = _uuids(parent)
    kept: list[str] = []
    for line in fork.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        record_uuid = record.get("uuid")
        if record_uuid and str(record_uuid) in parent_uuids:
            continue
        kept.append(line)
    return kept


def find_transcript(session_id: str, projects_dir: Path) -> Path | None:
    """`<projects_dir>/*/<session_id>.jsonl`, wherever the session was filed."""
    for candidate in sorted(projects_dir.glob(f"*/{session_id}.jsonl")):
        return candidate
    return None


def has_conversation(session_id: str, projects_root: Path | None = None) -> bool:
    """Is there anything for `--resume` to restore?

    A session registers in the live roster the moment it starts, but the harness files
    no transcript until its first turn — so a freshly spawned expert is *live* and not
    *forkable*, and `claude --resume` exits 1 with `No conversation found with session
    ID`. Measured while verifying this launcher against a session spawned seconds
    earlier. Checked before the mint, so an unforkable parent costs nothing.
    """
    root = projects_root if projects_root is not None else config_dir() / "projects"
    return find_transcript(session_id, root) is not None


def materialize_delta(
    fork_transcript: Path, parent_transcript: Path, dest_root: Path
) -> Path:
    """Write the delta under a second projects root, ready for `thalamus extract`.

    The project *dir name* is preserved, so `extract --projects-dir <root> -- <dir>`
    distills the delta through the ordinary pipeline — same parse, same archive, same
    write path — and the archived Source is the delta's bytes rather than a second
    copy of the parent's conversation.
    """
    project_dir = dest_root / fork_transcript.parent.name
    project_dir.mkdir(parents=True, exist_ok=True)
    out = project_dir / fork_transcript.name
    records = delta_records(fork_transcript, parent_transcript)
    out.write_text("".join(line + "\n" for line in records))
    return out


def stage_delta(
    transcript: Path, parent_session_id: str, dest_base: Path | None = None
) -> Path:
    """Stage a fork's own records for distillation; return the projects root to use.

    The parent is looked for beside the fork, under the same projects root — which is
    the room's when the fork ran in one, since `--projects-dir` is derived from the
    transcript's own path rather than from a registry.

    A missing parent transcript is a **refusal**, not a fallback: distilling the fork
    whole would mint a second Session re-asserting the parent's episode and archive a
    near-identical Source the archive cannot dedup, which is a worse outcome than not
    distilling at all.
    """
    projects_root = transcript.parent.parent
    parent = find_transcript(parent_session_id, projects_root)
    if parent is None:
        raise QuickRefused(
            f"no transcript for parent session `{parent_session_id}` under "
            f"{projects_root} — refusing to distill the fork whole, which would "
            "re-assert the parent's episode as a second Session"
        )
    root = (dest_base or FORKS_DIR) / transcript.stem
    materialize_delta(transcript, parent, root)
    return root


def count_fresh_recalls(records: list[str], ticket: str) -> int:
    """In-ticket recalls in the fork's own delta — the tier's third obligation, counted.

    Asserted in the prompt and *verified* here, because an obligation nobody counts is
    a decorated snapshot: warmth without revalidation is exactly the failure mode the
    fresh recall exists to prevent. Reads the fork's records rather than the answer
    text, so it cannot be satisfied by claiming to have recalled.
    """
    count = 0
    for line in records:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = record.get("message") if isinstance(record, dict) else None
        content = (message or {}).get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if not str(block.get("name") or "").startswith("mcp__thalamus__"):
                continue
            if str((block.get("input") or {}).get("ticket") or "") == ticket:
                count += 1
    return count


@dataclass
class QuickResult:
    """One quick exchange, start to finish — what it cost, and whether it stands."""

    ticket: str
    exchange_vid: str
    target: LiveSession
    grant: str
    run: ForkRun | None = None
    accepted: bool = False
    close_report: str = ""
    ledger_issues: list[str] = field(default_factory=list)
    fresh_recalls: int = 0
    delta_records: int = 0

    @property
    def answer(self) -> str:
        return self.run.result if self.run else ""


def consult(
    g,
    expert: str,
    question: str,
    from_scope: str,
    *,
    allowed_tools: str = DEFAULT_ALLOWED_TOOLS,
    timeout: int = DEFAULT_TIMEOUT,
    config_dir_override: Path | None = None,
    pins_file: Path | None = None,
    runner=subprocess.run,
) -> QuickResult:
    """One quick consultation, end to end: mint, fork, verify, price, close.

    The order is load-bearing. The exchange is minted *before* the fork runs, so a
    fork that dies or refuses leaves an open exchange rather than no record at all.
    The ledger is asserted *before* the answer is accepted, because a fork that armed
    the wrong scope produces a perfectly good-looking answer. And the close goes
    through `consult_answer` unchanged — the lighter tier does not get to bend the
    audit (arXiv 2606.04329).
    """
    from thalamus.harness import consultation
    from thalamus.substrate.reader import load_exchange
    from thalamus.substrate.writer import close_exchange

    refused = consultation.refuse_reason(expert, question, from_scope)
    if refused:
        raise QuickRefused(refused)

    target = resolve_target(expert, config_dir_override)
    projects = (
        Path(config_dir_override) if config_dir_override else config_dir()
    ) / "projects"
    if not has_conversation(target.session_id, projects):
        raise QuickRefused(
            f"`{expert}` session {target.session_id[:8]} is live but has no "
            "conversation yet — `--resume` has nothing to restore, so there is "
            "nothing to fork. A session becomes forkable on its first turn."
        )
    fork_point = datetime.now(timezone.utc)
    grant = grant_text(target, expert, fork_point)
    fork_session_id = str(uuid.uuid4())

    ticket, vertex_id = consultation.open_exchange(
        g,
        expert,
        question,
        from_scope,
        protocol="quick",
        extra={
            # Silence and "no brief served" are the same bytes, and only one of them
            # is auditable (docs/02). Dropping the brief is a lossy but well-defined
            # projection of the exchange record; it is legitimate only while the
            # record says which projection it is.
            "brief_served": False,
            "grant": grant,
            "parent_session": target.session_id,
            "fork_session": fork_session_id,
            "room": pin.resolve_room(),
            # The cost predictor, recorded at fork point rather than inferred later:
            # `updatedAt` is what separates a $0.03 call from a $0.60 one, and the
            # descriptor is gone once the parent exits.
            "parent_between_turns": target.between_turns,
            "parent_status": target.status,
            "parent_age_s": round(target.age_seconds, 1),
        },
    )
    result = QuickResult(
        ticket=ticket, exchange_vid=vertex_id, target=target, grant=grant
    )

    prompt = fork_prompt(
        ticket=ticket,
        question=question,
        from_scope=from_scope,
        scope=expert,
        grant=grant,
    )
    try:
        result.run = run_fork(
            target,
            expert,
            prompt,
            fork_session_id=fork_session_id,
            allowed_tools=allowed_tools,
            timeout=timeout,
            name=f"quick-{ticket[:8]}",
            runner=runner,
        )
    except QuickRefused as exc:
        # The exchange was minted before the fork ran, so a fork that dies leaves an
        # open exchange either way. What it must not leave is an *unexplained* one:
        # "never answered" and "answered by a login notice" are the same row
        # otherwise, and only one of them is a bug in the launcher.
        close_exchange(g, vertex_id, {"fork_error": str(exc)}, citation_refs=[])
        raise

    # The delta is read here for the same reason it is distilled later: the fork's
    # transcript is its parent's conversation restamped, so its *own* records are the
    # only place the tier's third obligation is visible.
    fork_transcript = find_transcript(result.run.session_id, projects)
    parent_transcript = find_transcript(target.session_id, projects)
    if fork_transcript and parent_transcript:
        records = delta_records(fork_transcript, parent_transcript)
        result.delta_records = len(records)
        result.fresh_recalls = count_fresh_recalls(records, ticket)

    result.ledger_issues = assert_ledger(
        result.run.session_id, expert, target.session_id, pins_file
    )

    price = result.run.price()
    price["fresh_recalls"] = result.fresh_recalls
    price["fork_session"] = result.run.session_id
    if result.ledger_issues:
        price["ledger_assert"] = "; ".join(result.ledger_issues)
    close_exchange(g, vertex_id, price, citation_refs=[])

    if result.ledger_issues:
        result.close_report = (
            "The answer is NOT accepted: the fork's own ledger row diverges from what "
            "the launcher promised, so this exchange would record a witness that is "
            "not the one that answered. The exchange stays open."
        )
        return result

    # The prompt tells the fork not to close, because closing is acceptance and
    # acceptance is downstream of the ledger check. A fork that closes anyway has
    # burned the ticket before the check could gate it, so the answer stands but the
    # order did not hold — recorded, not silently blessed.
    exchange = load_exchange(g, vertex_id)
    if (exchange or {}).get("status") == "answered":
        result.accepted = True
        result.close_report = (
            "The fork closed the exchange itself through consult_answer, ahead of the "
            "launcher's ledger check. Citations validated; the ordering did not."
        )
        close_exchange(g, vertex_id, {"closed_by": "fork"}, citation_refs=[])
        return result

    report = consultation.consult_answer(g, ticket, result.run.result)
    result.close_report = report
    result.accepted = not report.startswith("Rejected")
    if result.accepted:
        close_exchange(g, vertex_id, {"closed_by": "launcher"}, citation_refs=[])
    return result
