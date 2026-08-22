"""Is memory being written? — the one question the walkthrough could not answer.

Every other step in `docs/getting-started.md` has an observable result. The step the
product exists for did not. The SessionStart hook emits `additionalContext`, which
Claude Code hands to the *model*, not to the user, so whether anything is visible
depends on the model volunteering it; distillation runs detached and writes a
per-session log under `~/.thalamus/logs/` that no user-facing document points at.
After `thalamus init` and a relaunch, a first-time user had no documented way to
answer "did it work?" — which is the point at which they decide whether the project
functions at all.

`thalamus init --check` is the wrong instrument for that question and stays as it is.
It verifies *wiring*: hooks armed, skills readable, an MCP entry that matches this
checkout. All of that can be perfectly correct while nothing is being written, which
is exactly the latent failure the harness is built against. This reports the
*outcome* instead — sessions in the graph, the newest one, and whether the last
distillation run said anything went wrong.

Prior work. This is a convergence, not an invention: a post-install self-check is a
worn path (`brew doctor`, `flutter doctor`, `git fsck`), and the argument for making
it a documented step is measured. An evaluation of 100 ICSE replication packages
found that of five essential documentation components, "Validation Steps" was the one
supplied by only **6.25%** of packages, and reports a 14% full-reproducibility rate
among artifacts that executed at all — "running an artifact does not guarantee
credible or interpretable outcomes" (arXiv:2601.02066, ingested into scope `qe`). A
taxonomy of 1,168 README installation commits separately found help and
troubleshooting information updated at notably lower frequency than the instructions
themselves (arXiv:2312.03250, same scope). The extension over `--check` is that the
observable is the write path's output rather than its configuration.

Read-only by construction: one count, one ordered read, and two files off disk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path.home() / ".thalamus" / "logs"
HOOK_FAILURE_LOG = LOG_DIR / "hook-failures.log"

# `session-end-<sid8>.log`, which the SessionEnd hook opens before it forks and appends
# the detached block's whole output to. Its *mtime* is when distillation last finished
# writing, and its content is the only account of what happened.
SESSION_LOG = re.compile(r"session-end-[0-9a-f]{8}\.log$")


@dataclass
class Status:
    """What the command found. Rendered by `render`, asserted on by the tests."""

    graph_url: str
    graph_detail: str
    reachable: bool
    sessions: int = 0
    vertices: int = 0
    newest: dict | None = None
    last_distillation: tuple[str, str] | None = None   # (when, what the log ends with)
    hook_failures: list[str] | None = None


def _one(value):
    """value_map returns every property as a list; take the first or nothing."""
    if isinstance(value, list):
        return value[0] if value else ""
    return value if value is not None else ""


def read_graph(url: str) -> tuple[bool, str, int, int, dict | None]:
    """Counts and the newest Session, or the reason the graph could not answer.

    Deliberately not `install._probe_graph`: that one asks whether the graph is
    *reachable*, in a subprocess, because it must survive a peer that accepts a
    connection and never speaks. This one is a read the user asked for, so a
    `GraphUnavailable` is the answer rather than a hazard, and it is caught and
    rendered rather than raised.
    """
    from thalamus.substrate.writer import GraphUnavailable, close_connection, connect

    g = None
    try:
        g = connect(url)
        vertices = g.V().count().next()
        sessions = g.V().has_label("Session").count().next()
        newest = None
        if sessions:
            from gremlin_python.process.traversal import Order

            rows = (g.V().has_label("Session")
                    .order().by("timestamp", Order.desc).limit(1)
                    .value_map("session_id", "timestamp", "project", "scope", "tool")
                    .to_list())
            if rows:
                newest = {k: _one(v) for k, v in rows[0].items()}
        return True, "", vertices, sessions, newest
    except GraphUnavailable as exc:
        return False, str(exc), 0, 0, None
    finally:
        if g is not None:
            close_connection(g)


def last_distillation() -> tuple[str, str] | None:
    """When the most recent SessionEnd run finished, and how its log ends.

    The log is per-session and named after eight characters of a session id, so an
    operator cannot find the interesting one by looking; the newest by mtime is the
    one that answers "did the session I just closed distill?".
    """
    try:
        logs = [p for p in LOG_DIR.iterdir() if SESSION_LOG.search(p.name)]
    except OSError:
        return None
    if not logs:
        return None
    newest = max(logs, key=lambda p: p.stat().st_mtime)
    when = datetime.fromtimestamp(newest.stat().st_mtime, timezone.utc).isoformat(
        timespec="seconds")
    try:
        lines = [ln for ln in newest.read_text(errors="replace").splitlines() if ln.strip()]
    except OSError:
        lines = []
    return when, (lines[-1] if lines else f"{newest.name} is empty")


def recorded_hook_failures() -> list[str]:
    try:
        return [ln for ln in HOOK_FAILURE_LOG.read_text(errors="replace").splitlines()
                if ln.strip()]
    except OSError:
        return []


def collect(url: str | None = None) -> Status:
    from thalamus.harness.install import graph_url

    url = url or graph_url()
    reachable, detail, vertices, sessions, newest = read_graph(url)
    return Status(
        graph_url=url, graph_detail=detail, reachable=reachable,
        vertices=vertices, sessions=sessions, newest=newest,
        last_distillation=last_distillation(),
        hook_failures=recorded_hook_failures(),
    )


def render(status: Status) -> list[str]:
    """The report, as lines. Split from `run` so tests read it without capturing stdout."""
    lines = []
    if not status.reachable:
        lines.append(f"Graph         {status.graph_url}")
        lines.append(f"              {status.graph_detail}")
        return lines

    lines.append(f"Graph         {status.graph_url} — {status.vertices} vertices")

    if not status.sessions:
        # Not a fault, and said so plainly. A graph with nothing in it is what every
        # install starts as; the reason it is empty is almost always that no session
        # has *ended* yet, which is the part of the mechanism nobody guesses.
        lines.append("Memory        no sessions distilled yet — this is what a fresh "
                     "install looks like")
        lines.append("              Open a session in your editor, use it, then quit "
                     "the editor: distillation")
        lines.append("              runs when a session ends, not while it is open. "
                     "Then re-run this.")
    else:
        newest = status.newest or {}
        where = " ".join(part for part in (
            newest.get("project", ""),
            f"scope {newest.get('scope', '')}" if newest.get("scope") else "",
        ) if part)
        when = str(newest.get("timestamp", "?"))
        # The stored stamp is an isoformat with microseconds; seconds is what a person
        # reads, and the whole point of the line is recognising a session as their own.
        lines.append(f"Memory        {status.sessions} sessions distilled")
        lines.append(f"              newest {when[:19].replace('T', ' ')} "
                     f"({where or 'unknown project'})")

    if status.last_distillation:
        when, tail = status.last_distillation
        lines.append(f"Distillation  last ran {when[:19].replace('T', ' ')}")
        lines.append(f"              its log ends: {tail[:140]}")
    else:
        lines.append(f"Distillation  no run recorded in {LOG_DIR}")

    failures = status.hook_failures or []
    if failures:
        lines.append(f"Hook failures {len(failures)} session(s) ended undistilled — "
                     f"most recently:")
        lines.append(f"              {failures[-1][:160]}")
        lines.append(f"              (the record is {HOOK_FAILURE_LOG}; delete it to "
                     "clear this)")

    lines.append("")
    lines.append("This reports what was written. `thalamus init --check` reports the "
                 "wiring that writes it.")
    return lines


def run(url: str | None = None) -> int:
    """Exit 1 only when the graph could not be read.

    An empty graph is a pass, for the same reason it is one in `thalamus init
    --check`: every install starts empty, the graph is private to its operator and is
    never shipped. Recorded hook failures are history rather than a live fault and do
    not change the exit code either — they are printed because nothing else surfaces
    them where someone asking "did it work?" would look.
    """
    status = collect(url)
    for line in render(status):
        print(line)
    return 0 if status.reachable else 1
