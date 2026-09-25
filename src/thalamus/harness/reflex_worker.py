"""The memory reflex's worker and carrier — the agentic plan's path to the agent.

`thalamus reflex --work` is the worker: a detached process `reflex_queue.spawn_worker`
starts from the trigger hook. It takes one global lock (`~/.thalamus/reflex/worker.lock`),
because the local model serves one request at a time, and holds it while it claims
jobs oldest-first across every `(session, agent)` key, runs each, and exits when none
remain. The kernel releases the lock when the process dies, so there is no stale lock
to clear; a job a dead worker had claimed is found by the sweep and recorded `died`.

Each job runs under one wall clock from its claim, `DEADLINE_SECONDS`, enforced by a
timer around the whole loop rather than by the model or a socket timeout alone. A job
the clock ends packs what its completed calls returned and is recorded `timeout`,
never `empty`. Before every model turn the worker checks the session is still live
(`quick.live_sessions`, pid plus process start time): an interactive `/exit` does not
stop a running hook's children, so a job that outlives its session would otherwise
keep spending the model's one slot on an agent that is gone.

`thalamus reflex --deliver` is the carrier's delivery half, run by
`reflex-pointer-tap.sh` on any tool call whose agent has a result ready. It delivers
the oldest ready results for that agent, charges the session's budget with the
digest's characters, and writes the trace line then — `ts` is the delivery time,
because attribution reads the agent's output after `ts` and output produced before the
agent saw the digest is not a use of it. The line carries the depth at delivery: the
tool calls the agent made after the one that fired the job.
"""

from __future__ import annotations

import fcntl
import json
import os
import signal
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from gremlin_python.process.graph_traversal import GraphTraversalSource

from thalamus.contract.manifest import available_scopes
from thalamus.harness import agentic, quick, reflex_note, reflex_queue
from thalamus.harness.agents import cli_for
from thalamus.harness.extraction import ExtractionError
from thalamus.harness.reflex import (
    ARM_AGENTIC,
    ReflexBudget,
    _allocate_pointer,
    _append_trace,
    digest_line,
    imperative_voice,
    load_firings,
    pack_digest,
    render_envelope,
    render_pointer,
    DIGEST_CHAR_CAP,
)
from thalamus.harness.reflex_queue import SESSION_AGENT, append_outcome, key_dir, locked
from thalamus.harness.retrieval import Job
from thalamus.harness.transcripts import excerpt_for_job, tool_calls_after, trigger_text
from thalamus.substrate import vocabulary

# One job's wall clock from its claim: a cold load of the model (~20 s measured on the
# box), one extraction queued ahead of it on the same slot, and the plan's turns at
# 1–3 s each warm. Provisional until queue wait is measured with the plan live.
DEADLINE_SECONDS = 120.0

# How long a dead session's queue state is kept before the sweep counts it and removes
# it. A session can be between its last hook and its registry entry's removal.
SWEEP_GRACE_SECONDS = 600

# The anchors one job searches from: its triggers' anchors, first-seen order.
MAX_JOB_ANCHORS = 12


def _stamp(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def session_alive(session_id: str) -> bool:
    """Whether the harness still has this session registered and its process running.

    A box with no registry directory cannot say, and is answered True: the job runs
    rather than being discarded on an absence nobody measured.
    """
    if not (quick.config_dir() / "sessions").is_dir():
        return True
    return any(s.session_id == session_id for s in quick.live_sessions())


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class _Claimed:
    def __init__(self, directory: Path, path: Path, lines: list[dict], torn: int):
        self.directory = directory
        self.path = path
        self.lines = lines
        self.torn = torn


def _pending(root: Path) -> list[Path]:
    return sorted(reflex_queue.queue_root(root).glob("*/*/pending.jsonl"))


def _first_ts(path: Path) -> str:
    try:
        with path.open(errors="ignore") as handle:
            return str(json.loads(handle.readline()).get("ts") or "")
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""


def _read_job(path: Path) -> tuple[list[dict], int]:
    lines: list[dict] = []
    torn = 0
    with path.open(errors="ignore") as handle:
        for raw in handle:
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                torn += 1
                continue
            if isinstance(record, dict) and record.get("session_id"):
                lines.append(record)
            else:
                torn += 1
    return lines, torn


def claim_next(root: Path) -> _Claimed | None:
    """Claim the oldest pending job by renaming it under its key's lock."""
    for path in sorted(_pending(root), key=_first_ts):
        directory = path.parent
        with locked(directory):
            if not path.is_file():
                continue
            claimed = directory / f"pending.{os.getpid()}.claimed"
            path.rename(claimed)
        lines, torn = _read_job(claimed)
        return _Claimed(directory, claimed, lines, torn)
    return None


def work(
    root: Path,
    *,
    connect_graph: Callable[[], GraphTraversalSource],
    close_graph: Callable[[GraphTraversalSource], None] = lambda g: None,
    cli=None,
    model: str = "",
    alive: Callable[[str], bool] = session_alive,
) -> int:
    """Run every pending job, then exit. Returns how many ran; 0 when another worker holds the lock."""
    cli = cli or cli_for("local")
    model = model or cli.default_model
    ran = 0
    lock_path = reflex_queue.worker_lock_path(root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        with lock_path.open("a") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return ran
            g = None
            try:
                sweep(root, alive=alive)
                while (claimed := claim_next(root)) is not None:
                    if g is None:
                        g = connect_graph()
                    try:
                        run_job(claimed, g=g, root=root, cli=cli, model=model, alive=alive)
                    except Exception as exc:  # noqa: BLE001 — one job's fault ends that job, not the queue
                        # A clock that fired mid-request can leave the graph client in
                        # a state no later call should inherit, so the next job
                        # reconnects.
                        first = claimed.lines[0] if claimed.lines else {}
                        append_outcome(root, {
                            "session_id": str(first.get("session_id") or ""),
                            "agent_id": str(first.get("agent_id") or ""),
                            "plan": ARM_AGENTIC, "triggers": len(claimed.lines),
                            "outcome": "error", "detail": f"{type(exc).__name__}: {exc}"[:300],
                        })
                        claimed.path.unlink(missing_ok=True)
                        close_graph(g)
                        g = None
                    ran += 1
            finally:
                if g is not None:
                    close_graph(g)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        # A trigger that found the lock held started no worker; it relies on this
        # rescan, made after the lock is released, to be seen.
        if not _pending(root):
            return ran


class _Clock:
    """The job's wall clock: a timer that raises `JobTimeout` into whatever is running."""

    def __init__(self, seconds: float):
        self.seconds = seconds

    def __enter__(self):
        def expire(signum, frame):
            raise agentic.JobTimeout
        self.previous = signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, self.seconds)
        return self

    def __exit__(self, *exc):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.previous)
        return False


def _transcript_for(line: dict) -> tuple[Path | None, bool]:
    """The transcript the job's agent writes, and whether it is a subagent's file."""
    transcript = line.get("transcript") or ""
    if not transcript:
        return None, False
    path = Path(transcript)
    agent = line.get("agent_id") or ""
    if agent:
        return path.with_suffix("") / "subagents" / f"agent-{agent}.jsonl", True
    return path, False


def run_job(
    claimed: _Claimed,
    *,
    g,
    root: Path,
    cli,
    model: str,
    alive: Callable[[str], bool] = session_alive,
    deadline_seconds: float = DEADLINE_SECONDS,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> str:
    """Run one claimed job and leave its result ready, or record why there is none.

    Returns the job's outcome: `ready`, or one of `reflex_queue.JOB_OUTCOMES`.
    """
    lines = claimed.lines
    if not lines:
        claimed.path.unlink(missing_ok=True)
        return "empty"
    first = lines[0]
    session_id = str(first["session_id"])
    agent_id = str(first.get("agent_id") or "")
    scope = str(first.get("scope") or "main")
    claimed_at = now()
    enqueued = _parse(str(first.get("ts") or ""))
    queued_ms = (
        round((claimed_at - enqueued).total_seconds() * 1000) if enqueued else None
    )
    row = {
        "session_id": session_id, "agent_id": agent_id, "plan": ARM_AGENTIC,
        "triggers": len(lines), "torn": claimed.torn, "queued_ms": queued_ms,
    }

    def finish(outcome: str, **fields) -> str:
        append_outcome(root, {**row, "outcome": outcome, **fields})
        claimed.path.unlink(missing_ok=True)
        return outcome

    if not alive(session_id):
        return finish("session_end", detail="session gone before the job was claimed")

    anchors: list[str] = []
    for line in lines:
        for anchor in line.get("anchors") or []:
            if anchor not in anchors:
                anchors.append(anchor)
    anchors = anchors[:MAX_JOB_ANCHORS]

    transcript, sidechain = _transcript_for(first)
    triggers = {str(line.get("tool_use_id") or "") for line in lines} - {""}
    excerpt = (
        excerpt_for_job(transcript, triggers, sidechain=sidechain)
        if transcript else None
    )
    text = excerpt.text if excerpt else ""
    found = excerpt.found if excerpt else set()
    for line in lines:
        if line.get("tool_use_id") and line["tool_use_id"] in found:
            continue
        text += ("\n[tool_result: Bash, the result that fired this job]\n"
                 + trigger_text(str(line.get("observed") or "")))

    firing_id, pointer = _allocate_pointer(session_id, root)
    knowledge = [s for s in available_scopes() if s != scope]
    job = Job(g, scope=scope, knowledge_scopes=knowledge, prefix=firing_id,
              caps=agentic.CAPS)
    result = agentic.AgenticResult()
    started = time.monotonic()
    try:
        with _Clock(deadline_seconds):
            agentic.run(
                job, cli=cli, model=model, anchors=anchors, excerpt=text,
                deadline=started + deadline_seconds, result=result,
                alive=lambda: alive(session_id),
            )
    except agentic.JobTimeout:
        result.stopped = "timeout"
        result.kept = agentic.returned_in_order(job)
    except (ExtractionError, OSError, RuntimeError) as exc:
        pointer.unlink(missing_ok=True)
        return finish("error", detail=str(exc)[:300], **_effort(job, result, started))
    effort = _effort(job, result, started)

    if result.stopped == "session_end":
        pointer.unlink(missing_ok=True)
        return finish("session_end", detail="session ended while the job ran", **effort)
    timed_out = result.stopped in ("timeout", "deadline")
    results = []
    for node in result.kept:
        rendered = vocabulary.resolve(g, node, scope, knowledge)
        if rendered is not None:
            results.append((node, rendered))
    if not results:
        pointer.unlink(missing_ok=True)
        return finish("timeout" if timed_out else "empty", **effort)

    handles = {job.handle_for(node): node for node, _ in results}
    blocks = [rendered.format() for _, rendered in results]
    # A kept claim renders as the session holding it, so its line is written from the
    # row the model chose it by — kind, tier, date, its own first sentence — and not
    # from the rendering, which would label a problem and its solution as one session
    # twice.
    rows = {row.vid: row for row in vocabulary.rows_for(g, list(handles.values()), scope,
                                                        knowledge)}
    digest_lines = [
        _row_line(handle, rows[node], block, anchors) if node in rows
        else digest_line(handle, rendered, block, anchors)
        for (handle, node), (_, rendered), block in zip(
            handles.items(), results, blocks, strict=True
        )
    ]
    voiced = sum(1 for block in blocks if imperative_voice(block))
    trigger_ts = str(lines[-1].get("ts") or first.get("ts") or "")
    # The note may cite only what this digest serves, and one that passes is delivered
    # or withheld by its own balanced assignment, over the same records either way.
    note_check = reflex_note.check_note(result.note, set(handles))
    note_arm = (
        reflex_note.assign_note_arm(root, session_id, firing_id) if note_check.valid else ""
    )
    shown_note = result.note if note_arm == reflex_note.SHOWN else ""
    frame = render_envelope([], anchors, voiced=voiced, pointer=str(pointer),
                            trigger=trigger_ts, note=shown_note)
    kept, _held = pack_digest(digest_lines, DIGEST_CHAR_CAP, frame)
    # Strongest last, nearest the agent's next turn.
    digest = render_envelope(kept[::-1], anchors, voiced=voiced, pointer=str(pointer),
                             trigger=trigger_ts, note=shown_note)
    ready_ts = now()
    pointer.write_text(render_pointer(firing_id, trigger_ts, handles, blocks),
                       encoding="utf-8")
    ready = {
        "firing_id": firing_id, "digest": digest, "chars": len(digest),
        "pointer": str(pointer), "handles": handles, "anchors": anchors,
        "session_id": session_id, "agent_id": agent_id,
        "agent_type": str(first.get("agent_type") or ""), "scope": scope,
        "cwd": str(first.get("cwd") or ""), "event": str(first.get("event") or ""),
        "trigger": str(first.get("trigger") or "Bash"),
        "trigger_ts": str(first.get("ts") or ""), "last_trigger_ts": trigger_ts,
        "tool_use_id": str(first.get("tool_use_id") or ""),
        "transcript": str(transcript or ""), "sidechain": sidechain,
        "ready_ts": _stamp(ready_ts), "voiced": voiced,
        "outcome": "timeout" if timed_out else "served",
        # The note as written, whether or not it was delivered: a withheld note is the
        # comparison the shown one is read against.
        "note": result.note, "note_status": note_check.status, "note_arm": note_arm,
        "note_cited": note_check.cited,
        **{key: value for key, value in row.items() if key not in ("session_id", "agent_id")},
        **effort,
    }
    ready_dir = claimed.directory / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)
    temporary = ready_dir / f".{firing_id}.json.tmp"
    temporary.write_text(json.dumps(ready, sort_keys=True), encoding="utf-8")
    temporary.rename(ready_dir / f"{firing_id}.json")
    claimed.path.unlink(missing_ok=True)
    return "ready"


def _row_line(handle: str, row: vocabulary.Row, block: str, anchors: list[str]) -> str:
    """A digest line from the row the model chose: its line, then the anchors its record matched."""
    lowered = block.lower()
    matched = [anchor for anchor in anchors if anchor.lower() in lowered]
    line = row.line(handle)
    return f"{line} · matched {', '.join(matched)}" if matched else line


def _effort(job: Job, result: agentic.AgenticResult, started: float) -> dict:
    """What the plan did — the manipulation check — and where its time went."""
    turns = result.turns
    totals = [t.total_ms for t in turns if t.total_ms is not None]
    return {
        "calls": job.calls, "nodes": len(job.handles),
        "turns": len(turns),
        "ms": round((time.monotonic() - started) * 1000),
        "load_ms": sum(t.load_ms or 0 for t in turns),
        # Time the requests waited for the server's one slot: wall minus the server's
        # own time, per turn.
        "slot_wait_ms": sum(t.wall_ms for t in turns) - sum(totals) if totals else None,
        "stop": result.stop_log(),
    }


def deliver(
    root: Path,
    *,
    session_id: str,
    agent_id: str,
    event: str = "",
    traces_base: Path | None = None,
    now: datetime | None = None,
) -> str:
    """Hand over every ready result for this agent, oldest first. Returns the digests."""
    directory = key_dir(root, session_id, agent_id)
    ready_dir = directory / "ready"
    if not ready_dir.is_dir():
        return ""
    ts = now or datetime.now(timezone.utc)
    stamp = _stamp(ts)
    digests: list[str] = []
    with locked(directory):
        ready = sorted(ready_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for path in ready:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                path.unlink(missing_ok=True)
                continue
            delivered = directory / "delivered"
            delivered.mkdir(exist_ok=True)
            spent = sum(row.injected_chars for row in load_firings(session_id, root))
            spent += reflex_queue.delivered_chars(root, session_id)
            budget = ReflexBudget(spent=spent, cost=int(data.get("chars") or 0))
            base = {
                "session_id": session_id, "agent_id": agent_id, "plan": ARM_AGENTIC,
                "firing_id": data.get("firing_id", ""), "triggers": data.get("triggers"),
                "queued_ms": data.get("queued_ms"),
            }
            if not budget.fits:
                Path(str(data.get("pointer") or "")).unlink(missing_ok=True)
                append_outcome(root, {**base, "outcome": "budget",
                                      "detail": budget.refusal()}, now=ts)
                path.rename(delivered / path.name)
                continue
            transcript = Path(data["transcript"]) if data.get("transcript") else None
            depth = (
                tool_calls_after(transcript, data.get("tool_use_id", ""),
                                 sidechain=bool(data.get("sidechain")))
                if transcript and data.get("tool_use_id") else None
            )
            pointer = Path(str(data.get("pointer") or ""))
            records = pointer.read_text(encoding="utf-8") if pointer.is_file() else ""
            tool_input = {
                "query": " ".join(data.get("anchors") or []),
                "trigger": data.get("trigger", "Bash"), "event": data.get("event", ""),
                "anchors": data.get("anchors") or [],
                "firing_id": data.get("firing_id", ""), "pointer": str(pointer),
                "handles": data.get("handles") or {},
                "delivered_chars": int(data.get("chars") or 0),
                "delivered_on": event,
                "depth": depth, "trigger_ts": data.get("trigger_ts", ""),
                "ready_ts": data.get("ready_ts", ""), "outcome": data.get("outcome", ""),
                **{key: data.get(key) for key in (
                    "triggers", "queued_ms", "calls", "nodes", "turns", "ms",
                    "load_ms", "slot_wait_ms", "stop", "note", "note_status", "note_arm",
                    "note_cited",
                )},
            }
            _append_trace({
                "ts": stamp, "session_id": session_id, "scope": data.get("scope", ""),
                "cwd": data.get("cwd", ""), "tool_name": ARM_AGENTIC,
                "tool_input": tool_input, "tool_response": records,
                "agent_id": agent_id, "agent_type": data.get("agent_type", ""),
            }, ts, traces_base)
            reflex_queue.append_delivery(root, session_id, {
                "ts": stamp, "firing_id": data.get("firing_id", ""),
                "chars": int(data.get("chars") or 0), "depth": depth,
            })
            append_outcome(root, {**base, "outcome": "delivered", "depth": depth,
                                  "stopped": (data.get("stop") or {}).get("stopped", ""),
                                  "served_as": data.get("outcome", ""),
                                  "note_status": data.get("note_status", ""),
                                  "note_arm": data.get("note_arm", "")}, now=ts)
            path.rename(delivered / path.name)
            digests.append(str(data.get("digest") or ""))
    return "\n\n".join(d for d in digests if d)


def sweep(
    root: Path,
    *,
    alive: Callable[[str], bool] = session_alive,
    grace_seconds: float = SWEEP_GRACE_SECONDS,
    now: float | None = None,
) -> dict[str, int]:
    """Count and clear what no worker or carrier will reach. Idempotent.

    A claimed job whose worker is gone is `died`. In a session that is no longer live,
    past the grace period: a result still ready is `undelivered`, and a job still
    pending is `session_end`. A dead session's directory is removed once empty.
    """
    counts = {"died": 0, "undelivered": 0, "session_end": 0}
    current = now if now is not None else time.time()
    queue = reflex_queue.queue_root(root)
    for claimed in queue.glob("*/*/pending.*.claimed"):
        try:
            pid = int(claimed.name.split(".")[1])
        except (IndexError, ValueError):
            pid = 0
        if pid == os.getpid() or (pid and _pid_alive(pid)):
            continue
        lines, torn = _read_job(claimed)
        _discard(root, claimed, lines, "died", counts, torn=torn)
    for session_dir in sorted(p for p in queue.glob("*") if p.is_dir()):
        if alive(session_dir.name):
            continue
        for agent_dir in sorted(p for p in session_dir.glob("*") if p.is_dir()):
            with locked(agent_dir):
                for ready in agent_dir.glob("ready/*.json"):
                    if current - ready.stat().st_mtime < grace_seconds:
                        continue
                    append_outcome(root, {
                        "session_id": session_dir.name,
                        "agent_id": "" if agent_dir.name == SESSION_AGENT else agent_dir.name,
                        "plan": ARM_AGENTIC, "firing_id": ready.stem,
                        "outcome": "undelivered",
                    })
                    ready.unlink(missing_ok=True)
                    counts["undelivered"] += 1
                pending = agent_dir / "pending.jsonl"
                if pending.is_file() and current - pending.stat().st_mtime >= grace_seconds:
                    lines, torn = _read_job(pending)
                    _discard(root, pending, lines, "session_end", counts, torn=torn)
        if not any(session_dir.glob("*/ready/*.json")) and not any(
            session_dir.glob("*/pending*")
        ) and all(
            current - p.stat().st_mtime >= grace_seconds for p in session_dir.rglob("*")
        ):
            for path in sorted(session_dir.rglob("*"), reverse=True):
                if path.is_dir():
                    path.rmdir()
                else:
                    path.unlink()
            session_dir.rmdir()
    return counts


def _discard(root: Path, path: Path, lines: list[dict], outcome: str,
             counts: dict[str, int], *, torn: int) -> None:
    first = lines[0] if lines else {}
    append_outcome(root, {
        "session_id": str(first.get("session_id") or path.parent.parent.name),
        "agent_id": str(first.get("agent_id") or ""), "plan": ARM_AGENTIC,
        "triggers": len(lines), "torn": torn, "outcome": outcome,
    })
    path.unlink(missing_ok=True)
    counts[outcome] += 1
