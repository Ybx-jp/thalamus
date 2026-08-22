"""
`thalamus status` — the step that answers "is memory being written?".

Interfaces: thalamus.harness.status.
Infrastructure: a stubbed graph read and tmp_path log directories. No live graph:
the traversal itself is validated against the real one and recorded in the
gremlin-python skill's RECIPES.md; what needs pinning here is what the command
*says*, which is the half a first-time user acts on.
Scope: the three states a reader has to be able to tell apart — a graph that will
not answer, a graph that answers and is empty, and one with sessions in it. The
empty one is the trap: it is the normal shape of a fresh install and reads as a
broken one, and it is reached at exactly the moment someone decides whether the
project works.
"""

import time
from pathlib import Path

import pytest

from thalamus.harness import status as status_module
from thalamus.harness.status import Status, render, run


@pytest.fixture
def logs(tmp_path, monkeypatch):
    """Redirect the two log paths the command reads off disk."""
    directory = tmp_path / "logs"
    directory.mkdir()
    monkeypatch.setattr(status_module, "LOG_DIR", directory)
    monkeypatch.setattr(status_module, "HOOK_FAILURE_LOG", directory / "hook-failures.log")
    return directory


def _graph(monkeypatch, *, reachable=True, detail="", vertices=0, sessions=0, newest=None):
    monkeypatch.setattr(status_module, "read_graph",
                        lambda url: (reachable, detail, vertices, sessions, newest))


# ---- the three states ----


def test_a_graph_that_will_not_answer_is_the_only_nonzero_exit(logs, monkeypatch, capsys):
    """The one thing that stops the question being answerable at all."""
    _graph(monkeypatch, reachable=False,
           detail="nothing listening on localhost:9 — start it with `docker compose up -d`")

    code = run("ws://localhost:9/gremlin")

    assert code == 1
    assert "docker compose up -d" in capsys.readouterr().out


def test_an_empty_graph_is_a_pass_and_says_what_to_do_next(logs, monkeypatch, capsys):
    """Zero sessions is what every install starts as, not a fault.

    And the reason it is empty is the part nobody guesses: distillation runs when a
    session *ends*. A user who opened a session, saw nothing, and ran this while the
    session was still open has to be told that, or the empty report reads as a
    verdict on the install.
    """
    _graph(monkeypatch, vertices=0, sessions=0)

    code = run("ws://localhost:8182/gremlin")
    out = capsys.readouterr().out

    assert code == 0
    assert "fresh install" in out
    assert "quit the editor" in out and "when a session ends" in out


def test_sessions_are_reported_with_the_newest_one_named(logs, monkeypatch, capsys):
    """A count alone does not let anyone recognise their own session in it."""
    _graph(monkeypatch, vertices=34313, sessions=303,
           newest={"session_id": "d47288c9", "timestamp": "2026-08-22T00:59:56.339000+00:00",
                   "project": "thalamus", "scope": "designer", "tool": "claude_code"})

    run("ws://localhost:8182/gremlin")
    out = capsys.readouterr().out

    assert "303 sessions distilled" in out
    assert "2026-08-22 00:59:56" in out, "the microseconds are not for a person to read"
    assert "thalamus" in out and "designer" in out


# ---- what the logs contribute ----


def test_the_newest_session_log_is_the_one_reported(logs):
    """Per-session logs are named after eight characters of a session id, so the
    operator cannot pick the interesting one by looking. Newest by mtime is the one
    that answers "did the session I just closed distill?"."""
    old = logs / "session-end-aaaaaaaa.log"
    old.write_text("wrote 1 session\n")
    new = logs / "session-end-bbbbbbbb.log"
    new.write_text("wrote 2 sessions\nsynced 4 traces\n")
    import os
    os.utime(old, (time.time() - 600, time.time() - 600))

    when, tail = status_module.last_distillation()

    assert tail == "synced 4 traces"
    assert when.startswith("20")


def test_a_directory_with_no_session_logs_reports_that_rather_than_guessing(logs, monkeypatch,
                                                                           capsys):
    (logs / "hook-failures.log").write_text("")
    _graph(monkeypatch, vertices=1, sessions=1, newest={"timestamp": "2026-08-22T00:00:00"})

    run("ws://localhost:8182/gremlin")

    assert "no run recorded" in capsys.readouterr().out


def test_recorded_hook_failures_surface_here_because_nothing_else_shows_them(logs, monkeypatch,
                                                                            capsys):
    """The failure record is written by the hooks and read back by `init --check`.

    It belongs on this surface too: a session lost to a missing binary is exactly the
    thing someone asking "is memory being written?" needs told, and the file it lives
    in is named nowhere they would look.
    """
    (logs / "hook-failures.log").write_text(
        "2026-08-15T09:00:00Z session-end.sh: thalamus extract exited 3 for session "
        "abcd1234 — this session was not distilled.\n")
    _graph(monkeypatch, vertices=1, sessions=1, newest={"timestamp": "2026-08-22T00:00:00"})

    code = run("ws://localhost:8182/gremlin")
    out = capsys.readouterr().out

    assert "1 session(s) ended undistilled" in out
    assert "thalamus extract exited 3" in out
    # History, not a live fault — it must not turn a working install into a failure.
    assert code == 0


def test_a_missing_log_directory_is_not_an_error(tmp_path, monkeypatch):
    """A box that has installed but never ended a session has no logs directory."""
    monkeypatch.setattr(status_module, "LOG_DIR", tmp_path / "nope")
    monkeypatch.setattr(status_module, "HOOK_FAILURE_LOG", tmp_path / "nope" / "h.log")

    assert status_module.last_distillation() is None
    assert status_module.recorded_hook_failures() == []


# ---- the boundary with `init --check` ----


def test_the_report_points_at_the_command_that_covers_the_other_half():
    """Two questions, two commands, and neither answers the other's.

    `init --check` verifies wiring, all of which can be correct while nothing is
    written; this reports what was written and cannot tell you why it was not.
    """
    lines = render(Status(graph_url="ws://x/gremlin", graph_detail="", reachable=True,
                          vertices=5, sessions=1, newest={"timestamp": "2026-01-01T00:00:00"}))

    assert any("thalamus init --check" in line for line in lines)


def test_it_reads_and_never_writes():
    """Ad-hoc traversals are read-only by contract; this one ships, so it is pinned."""
    source = Path(status_module.__file__).read_text()

    for mutation in ("add_v", "add_e", "merge_v", "merge_e", ".drop(", ".property("):
        assert mutation not in source, f"{mutation} on a read-only surface"
