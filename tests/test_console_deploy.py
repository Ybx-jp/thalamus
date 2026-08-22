"""
Deploy path: what the console reports about the code it is serving, and what
`deploy` will and will not do to the checkout it serves from.

Interfaces: thalamus.console.server.build_info / deploy / self_unit
Infrastructure: real `git` repositories under tmp_path, wired to a local bare
remote — no network, no systemd, no tmux.
Scope: the console is normally an editable install running out of a checkout, so
a merge on a remote reaches the phone only after two separate local moves. These
cover the reporting that makes the gap visible and the refusals that keep the
deploy from being the thing that loses work: a dirty tree, a detached HEAD, a
branch with no upstream, and a history that will not fast-forward all stop with
the checkout untouched. The restart half is systemd's and is verified live.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest

from thalamus.console import server
from thalamus.console.server import Config

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(("git", *args), cwd=str(cwd), capture_output=True, text=True,
                       check=True)
    return r.stdout.strip()


@pytest.fixture()
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A clone with an upstream, standing in for the box's checkout.

    `checkout_root()` is derived from the module's own `__file__`, so it is pointed
    at the fixture rather than the fixture being pointed at the repo — the code
    under test is the same either way, and the alternative is a test that mutates
    the tree it is running from.
    """
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(origin))
    git(tmp_path, "clone", "--quiet", str(origin), str(work))
    git(work, "config", "user.email", "t@example.invalid")
    git(work, "config", "user.name", "test")
    (work / "a.txt").write_text("one\n")
    git(work, "add", "a.txt")
    git(work, "commit", "--quiet", "-m", "first")
    git(work, "push", "--quiet", "-u", "origin", "main")

    monkeypatch.setattr(server, "checkout_root", lambda: work)
    server.build_info(force=True)
    return work


def push_from_elsewhere(tmp_path: Path, checkout: Path, message: str) -> str:
    """Land a commit on the remote the way a merged PR does — behind this checkout."""
    other = tmp_path / "other"
    if not other.exists():
        git(tmp_path, "clone", "--quiet", str(tmp_path / "origin.git"), str(other))
        git(other, "config", "user.email", "t@example.invalid")
        git(other, "config", "user.name", "test")
    git(other, "pull", "--quiet")
    (other / "b.txt").write_text(message + "\n")
    git(other, "add", "b.txt")
    git(other, "commit", "--quiet", "-m", message)
    git(other, "push", "--quiet")
    return git(other, "rev-parse", "--short", "HEAD")


def test_build_info_names_the_commit_being_served(checkout: Path):
    info = server.build_info(force=True)
    assert info["vcs"] is True
    assert info["branch"] == "main"
    assert info["sha"] == git(checkout, "rev-parse", "--short", "HEAD")
    assert info["subject"] == "first"
    assert info["upstream"] == "origin/main"
    assert info["dirty"] is False
    assert info["stale"] is False and info["reason"] == ""


@pytest.mark.parametrize("arrange", [
    pytest.param(lambda tp, co, mp: None, id="current"),
    pytest.param(lambda tp, co, mp: (push_from_elsewhere(tp, co, "merged"),
                                     git(co, "fetch", "--quiet")), id="behind"),
    pytest.param(lambda tp, co, mp: mp.setattr(
        server, "loaded_code_mtime", lambda: server.STARTED_AT + 1), id="old-process"),
    pytest.param(lambda tp, co, mp: (co / "a.txt").write_text("edited\n"), id="dirty"),
])
def test_reason_is_non_empty_exactly_when_stale(tmp_path, checkout: Path, arrange,
                                                monkeypatch: pytest.MonkeyPatch):
    """The client prints `reason` verbatim and branches only on `stale`.

    An empty reason under a true `stale` is a bar that appears saying nothing; a
    reason under a false `stale` is text nothing will ever show. One is a silent
    alarm and the other is a dead string, so the two fields are pinned together
    rather than left to agree by construction.
    """
    arrange(tmp_path, checkout, monkeypatch)
    info = server.build_info(force=True)
    assert info["stale"] is bool(info["reason"].strip())


def test_untracked_files_are_not_dirt(checkout: Path):
    """Editor state and build output do not block a fast-forward, so they are not
    the thing `dirty` reports — a tree that read as dirty forever would make the
    deploy's one real refusal unreadable."""
    (checkout / "scratch.log").write_text("noise\n")
    assert server.build_info(force=True)["dirty"] is False


def test_a_merge_the_checkout_has_not_pulled_reads_as_stale(tmp_path, checkout: Path):
    push_from_elsewhere(tmp_path, checkout, "merged upstream")
    git(checkout, "fetch", "--quiet")
    info = server.build_info(force=True)
    assert info["behind"] == 1 and info["ahead"] == 0
    assert info["stale"] is True
    assert "1 commit behind origin/main" in info["reason"]


def test_a_process_older_than_its_code_reads_as_stale(checkout: Path,
                                                      monkeypatch: pytest.MonkeyPatch):
    """The half a `git pull` cannot fix: `static/` is read per request but the
    Python is loaded once, so a current tree still serves the old API."""
    monkeypatch.setattr(server, "loaded_code_mtime", lambda: server.STARTED_AT + 1)
    info = server.build_info(force=True)
    assert info["process_stale"] is True and info["stale"] is True
    assert "older than the checkout" in info["reason"]


def test_deploy_fast_forwards_onto_the_upstream(tmp_path, checkout: Path):
    sha = push_from_elsewhere(tmp_path, checkout, "merged upstream")
    out = server.deploy(Config(project_root=checkout, services=[]))
    assert out["ok"] is True and out["moved"] is True
    assert out["to"] == sha and out["upstream"] == "origin/main"
    assert (checkout / "b.txt").exists()


def test_deploy_is_a_no_op_when_already_current(checkout: Path):
    out = server.deploy(Config(project_root=checkout, services=[]))
    assert out["ok"] is True and out["moved"] is False
    assert out["from"] == out["to"]


def test_deploy_refuses_a_dirty_tree_and_changes_nothing(tmp_path, checkout: Path):
    push_from_elsewhere(tmp_path, checkout, "merged upstream")
    (checkout / "a.txt").write_text("edited in place\n")
    before = git(checkout, "rev-parse", "HEAD")
    out = server.deploy(Config(project_root=checkout, services=[]))
    assert out["ok"] is False
    assert "uncommitted changes" in out["error"]
    assert "a.txt" in out["output"]
    assert git(checkout, "rev-parse", "HEAD") == before
    assert (checkout / "a.txt").read_text() == "edited in place\n"


def test_deploy_refuses_a_detached_head(checkout: Path):
    git(checkout, "checkout", "--quiet", "--detach", "HEAD")
    out = server.deploy(Config(project_root=checkout, services=[]))
    assert out["ok"] is False and "detached HEAD" in out["error"]


def test_deploy_refuses_a_branch_with_no_upstream(checkout: Path):
    git(checkout, "checkout", "--quiet", "-b", "local-only")
    out = server.deploy(Config(project_root=checkout, services=[]))
    assert out["ok"] is False and "no upstream" in out["error"]


def test_deploy_refuses_a_history_that_will_not_fast_forward(tmp_path, checkout: Path):
    """Diverged local work is not something a deploy is allowed to resolve: the
    only move it makes is the one `git pull --ff-only` would have made."""
    push_from_elsewhere(tmp_path, checkout, "merged upstream")
    (checkout / "c.txt").write_text("local\n")
    git(checkout, "add", "c.txt")
    git(checkout, "commit", "--quiet", "-m", "local work")
    before = git(checkout, "rev-parse", "HEAD")
    out = server.deploy(Config(project_root=checkout, services=[]))
    assert out["ok"] is False and "fast-forward" in out["error"]
    assert git(checkout, "rev-parse", "HEAD") == before


def test_deploy_names_only_a_unit_it_was_given(tmp_path, checkout: Path,
                                               monkeypatch: pytest.MonkeyPatch):
    """`--service` is the whitelist for restarts and stays the whitelist here: the
    console never restarts a unit it was not told it owns, even its own."""
    monkeypatch.setattr(server, "self_unit", lambda: "thalamus-console.service")

    push_from_elsewhere(tmp_path, checkout, "merged upstream")
    out = server.deploy(Config(project_root=checkout, services=[]))
    assert out["ok"] is True and out["restarting"] is None
    assert out["unit"] == "thalamus-console.service"


def test_deploy_names_the_unit_hosting_it(tmp_path, checkout: Path,
                                          monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server, "self_unit", lambda: "thalamus-console.service")

    push_from_elsewhere(tmp_path, checkout, "merged upstream")
    out = server.deploy(Config(project_root=checkout,
                               services=["thalamus-console.service"]))
    assert out["ok"] is True and out["restarting"] == "thalamus-console.service"


def test_deploy_itself_restarts_nothing(tmp_path, checkout: Path,
                                        monkeypatch: pytest.MonkeyPatch):
    """The restart is the caller's to perform, and the ordering is the reason.

    The unit being restarted is the one serving the request, so the process dies
    with the socket. Restarting inside `deploy` would race the response out, and a
    client that never hears back cannot tell a deploy in progress from a box that
    fell over."""
    restarted: list[str] = []
    monkeypatch.setattr(server, "service_restart", restarted.append)
    monkeypatch.setattr(server, "self_unit", lambda: "thalamus-console.service")

    push_from_elsewhere(tmp_path, checkout, "merged upstream")
    server.deploy(Config(project_root=checkout, services=["thalamus-console.service"]))
    assert restarted == []


def test_the_endpoint_answers_before_it_restarts(tmp_path, checkout: Path,
                                                 monkeypatch: pytest.MonkeyPatch):
    from test_console import _serving

    restarted: list[str] = []

    def slow_restart(unit: str) -> None:
        """Stands in for the real restart, which takes the process down with it.

        Blocking here is what makes the ordering observable from outside: if the
        restart ran before the response was written, the client would wait on it.
        """
        restarted.append(unit)
        time.sleep(3)

    monkeypatch.setattr(server, "self_unit", lambda: "thalamus-console.service")
    monkeypatch.setattr(server, "service_restart", slow_restart)

    push_from_elsewhere(tmp_path, checkout, "merged upstream")
    cfg = Config(project_root=checkout, services=["thalamus-console.service"])
    with _serving(cfg) as post:
        started = time.monotonic()
        status, body = post("/api/deploy", {})
        elapsed = time.monotonic() - started

    assert status == 200 and body["ok"] is True
    assert body["restarting"] == "thalamus-console.service"
    assert restarted == ["thalamus-console.service"]
    assert elapsed < 3, (
        f"the response waited {elapsed:.1f}s on the restart; a client cannot tell "
        "that apart from the box going down")


def test_a_current_tree_still_calls_for_a_restart(checkout: Path,
                                                  monkeypatch: pytest.MonkeyPatch):
    """Nothing to pull is not nothing to do. A tree already current in front of a
    process that predates it is the exact state a restart is the whole fix for."""
    monkeypatch.setattr(server, "self_unit", lambda: "thalamus-console.service")
    monkeypatch.setattr(server, "loaded_code_mtime", lambda: server.STARTED_AT + 1)

    out = server.deploy(Config(project_root=checkout,
                               services=["thalamus-console.service"]))
    assert out["ok"] is True and out["moved"] is False
    assert out["restarting"] == "thalamus-console.service"


@pytest.mark.parametrize("leaf, expected", [
    # A console started from a terminal sits under a `.scope` whose ancestors
    # include `user@1000.service`. Restarting that ends the login session.
    ("tmux-spawn-abc.scope", None),
    ("session-3.scope", None),
    ("thalamus-console.service", "thalamus-console.service"),
])
def test_self_unit_answers_the_leaf_or_nothing(tmp_path: Path, leaf, expected,
                                               monkeypatch: pytest.MonkeyPatch):
    cgroup = tmp_path / "cgroup"
    cgroup.write_text(
        f"0::/user.slice/user-1000.slice/user@1000.service/app.slice/{leaf}\n")
    monkeypatch.setattr(server, "CGROUP_PATH", cgroup)
    assert server.self_unit() == expected


@pytest.mark.parametrize("xpc, expected", [
    ("com.thalamus.console", "com.thalamus.console"),
    # What launchd leaves on a process it did not start as a job.
    ("0", None),
    ("", None),
    # A console started from a shell inherits the terminal's XPC name. Restarting
    # that closes the terminal the operator is sitting in — the mac's version of
    # the `.scope` leaf whose ancestor is the user manager.
    ("application.com.apple.Terminal.12345.67890", None),
])
def test_self_unit_under_launchd_reads_the_label_or_refuses(
        xpc, expected, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server, "service_manager", lambda: "launchd")
    monkeypatch.setenv("XPC_SERVICE_NAME", xpc)
    assert server.self_unit() == expected


def test_self_unit_under_launchd_never_reads_the_cgroup(tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch):
    """A mac has no `/proc`, and a stale CGROUP_PATH left readable in a test rig must
    not be able to name a unit on a box that has no systemd to run it."""
    cgroup = tmp_path / "cgroup"
    cgroup.write_text("0::/user.slice/thalamus-console.service\n")
    monkeypatch.setattr(server, "CGROUP_PATH", cgroup)
    monkeypatch.setattr(server, "service_manager", lambda: "launchd")
    monkeypatch.delenv("XPC_SERVICE_NAME", raising=False)
    assert server.self_unit() is None


def test_the_bar_and_the_sheet_read_the_same_build(checkout: Path):
    """The staleness bar polls `/api/build` and the INFRA sheet reads `/api/admin`.
    One source behind both, so they cannot disagree about whether the surface the
    operator is looking at is current."""
    from test_console import _serving

    with _serving(Config(project_root=checkout, services=[])) as post:
        build = post.get("/api/build")
        admin = post.get("/api/admin")

    assert build["sha"] == git(checkout, "rev-parse", "--short", "HEAD")
    assert admin["build"] == build
