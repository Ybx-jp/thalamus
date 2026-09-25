"""The memory reflex's queue — where a firing that needs the local model waits.

Word match and propagation serve from the trigger hook itself. A firing assigned the
agentic plan (`harness/agentic.py`) cannot: a model loop takes tens of seconds, and a
synchronous hook holds the agent for as long as it runs. The trigger hook appends a
job here and returns; a detached worker (`harness/reflex_worker.py`) runs it; the
result waits in a ready directory until the agent's next tool call, where the carrier
hook delivers it.

Layout under `~/.thalamus/reflex/queue/<session>/<agent>/`, one directory per agent
because subagents share their parent's session id and a digest must reach the agent
whose call fired it: `pending.jsonl` (the job being built, one line per absorbed
trigger), `lock`, `ready/` (results awaiting the carrier) and `delivered/`. At most one
pending job per key: a trigger arriving while one waits is appended to it, and the
worker sees every absorbed trigger when it claims the job.

Every line is appended under an exclusive `flock` on the key's `lock`, with an
`fsync` before the lock drops (`ci_triage.py`'s idiom, for #169's reason: a torn line
merges the next writer's row into it).

Two ledgers sit beside the queue: `deliveries/<session>.jsonl`, the characters the
carrier put in context, which the session's budget is charged with alongside the
synchronous firings; and `jobs/<month>.jsonl`, one row per job with how it ended.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# The agent key of a firing from the session itself, which carries no `agent_id`.
SESSION_AGENT = "session"

# How a job ended, as `jobs/<month>.jsonl` records it. `delivered` reached the agent;
# every other value is a job that did not, with its reason.
#   empty        the plan kept nothing
#   timeout      the job's deadline expired before the plan kept anything
#   died         the worker that claimed it is gone
#   session_end  the session had ended before or while it ran
#   budget       delivering it would have crossed the session's budget
#   undelivered  it was ready and the agent made no further call before its session ended
#   error        the model server or the graph could not be reached
JOB_OUTCOMES = (
    "delivered", "empty", "timeout", "died", "session_end", "budget", "undelivered",
    "error",
)


def queue_root(root: Path) -> Path:
    return root / "queue"


def key_dir(root: Path, session_id: str, agent_id: str) -> Path:
    return queue_root(root) / session_id / (agent_id or SESSION_AGENT)


def worker_lock_path(root: Path) -> Path:
    return root / "worker.lock"


@contextmanager
def locked(directory: Path):
    """An exclusive `flock` on `directory/lock` for the duration of the block."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "lock").open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _append_line(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def enqueue(root: Path, job: dict) -> bool:
    """Append one trigger to its key's pending job. True when it joined one already waiting."""
    directory = key_dir(root, job["session_id"], job.get("agent_id", ""))
    with locked(directory):
        pending = directory / "pending.jsonl"
        absorbed = pending.is_file() and pending.stat().st_size > 0
        _append_line(pending, job)
    return absorbed


def worker_running(root: Path) -> bool:
    """Whether a worker holds the global lock right now."""
    path = worker_lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return False


def spawn_worker(root: Path, *, url: str = "", log: Path | None = None) -> bool:
    """Start a detached worker unless one is running. True when one was started.

    A worker started between the check and the spawn is harmless: the second finds the
    lock held and exits. A job appended after a running worker last looked is picked
    up by that worker's rescan after it releases the lock (`reflex_worker.work`).
    """
    if worker_running(root):
        return False
    binary = Path(sys.executable).parent / "thalamus"
    argv = [str(binary) if binary.exists() else "thalamus", "reflex", "--work",
            "--reflex-dir", str(root)]
    if url:
        argv += ["--url", url]
    log = log or Path.home() / ".thalamus" / "logs" / "reflex-worker.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as stderr:
        subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=stderr,
            start_new_session=True, close_fds=True,
        )
    return True


def append_delivery(root: Path, session_id: str, record: dict) -> None:
    _append_line(root / "deliveries" / f"{session_id}.jsonl", record)


def delivered_chars(root: Path, session_id: str) -> int:
    """What the carrier has put in this session's context, in digest characters."""
    return sum(int(row.get("chars") or 0) for row in _read_lines(
        root / "deliveries" / f"{session_id}.jsonl"
    ))


def append_outcome(root: Path, record: dict, now: datetime | None = None) -> None:
    ts = now or datetime.now(timezone.utc)
    record = {"ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), **record}
    _append_line(root / "jobs" / f"{ts.strftime('%Y-%m')}.jsonl", record)


def load_outcomes(root: Path) -> list[dict]:
    """Every job outcome row, oldest first."""
    directory = root / "jobs"
    if not directory.is_dir():
        return []
    rows: list[dict] = []
    for path in sorted(directory.glob("*.jsonl")):
        rows.extend(_read_lines(path))
    return rows


def _read_lines(path: Path) -> list[dict]:
    """The file's complete JSON-object lines; a torn or foreign line is skipped."""
    if not path.is_file():
        return []
    rows: list[dict] = []
    with path.open(errors="ignore") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                rows.append(record)
    return rows
