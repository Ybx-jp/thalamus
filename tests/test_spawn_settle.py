"""
Spawn confirmation: whether a window that dies late is reported as a failure.

Interfaces: thalamus.harness.pin, thalamus.harness.launcher, thalamus.console.server
Infrastructure: a real tmux server on a private socket, named by
`THALAMUS_TMUX_SOCKET`, plus fake harness binaries that die on a schedule. No claude,
no `agent`, no network, no graph — and nothing that can see the operator's roster.
Scope: the one hazard where every layer below reports success. `tmux new-window`
exits 0 when it has forked, so a launch is only confirmed by a window that is still
alive later; how much later is a per-harness measurement (launcher's docstring), and
these tests are what stop that number from being decorative.

The private socket is the whole reason this can run at all. tmux ignores HOME, so it
is the one surface no environment redirection reaches — `harness/tmux.py` names the
server on every call it builds, and pointing that one variable somewhere else is what
keeps a test off the operator's live roster.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from thalamus.console import server
from thalamus.console.server import Config, do_spawn
from thalamus.harness import pin, tmux
from thalamus.harness.launcher import LAUNCH_SHAPES, settle_s

pytestmark = pytest.mark.skipif(shutil.which("tmux") is None,
                                reason="the control plane IS tmux")

# The settle window this file's late-death case is written against: the retired
# global constant. A harness whose deaths land past it is exactly what a single
# number could not cover.
RETIRED_GLOBAL_SETTLE_S = 1.2


@pytest.fixture
def private_tmux(tmp_path, monkeypatch):
    """A tmux server of our own, plus a `bin` directory that shadows PATH.

    The socket is set in the environment rather than by shimming the binary, so the
    code under test is the code that ships: `harness/tmux.py` reads
    `THALAMUS_TMUX_SOCKET` on every call and every argv in `src/` goes through it.

    Yields the bin directory: a test writes its fake harness binaries there, and
    `pin` finds them the same way a pane finds the real ones.
    """
    socket = f"thalamus-test-{os.getpid()}"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    monkeypatch.setenv("THALAMUS_TMUX_SOCKET", socket)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    yield bindir
    subprocess.run([shutil.which("tmux"), "-L", socket, "kill-server"],
                   capture_output=True)


def _fake_harness(bindir: Path, name: str, body: str) -> None:
    path = bindir / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def _windows(session: str) -> list[str]:
    # Through the same resolver the code under test uses, so the test and the code
    # cannot end up looking at two different servers.
    out = subprocess.run(tmux.argv("list-windows", "-t", session, "-F",
                                   "#{window_id} #{pane_dead}"),
                         capture_output=True, text=True)
    return out.stdout.split("\n") if out.returncode == 0 else []


def test_a_window_that_dies_after_the_old_settle_window_is_reported_failed(
        private_tmux, tmp_path):
    """
    Scenario: a Cursor spawn whose command runs for 2 s and then exits 1

    Verifications:
    - the spawn is reported as a failure, not the success tmux saw
    - it was still alive at the retired 1.2 s settle, so a single global constant
      would have called it started
    - what the dying window printed comes back with the failure

    This is the shape of Cursor's one measured fatal failure: a rejected API key,
    which is decided by a round trip to its API rather than locally. Measured at
    1.07-1.14 s on this box and 3.14-3.20 s with 2 s of added latency in front of
    the same call — a death whose timing is the network's, which is why the settle
    window is per-harness and generous there.
    """
    _fake_harness(private_tmux, "agent",
                  "printf 'Not logged in. Check CURSOR_API_KEY.\\n'\n"
                  "sleep 2\nexit 1")
    cfg = Config(project_root=tmp_path, session="settle-late")

    start = time.monotonic()
    ok, output = do_spawn(cfg, "main", tmp_path, "", "cursor")
    elapsed = time.monotonic() - start

    assert ok is False
    assert elapsed > RETIRED_GLOBAL_SETTLE_S
    # The epitaph, not the exit status. `_pane_state` documents two spellings of
    # death and says which one appears depends on timing: `remain-on-exit` leaves a
    # corpse carrying `pane_dead_status`, and a pane reaped before that option took
    # effect leaves no window to describe, so the status comes back empty and
    # `status_part` renders nothing. Measured 2026-08-15: this asserted `"exit 1"`
    # and failed 2 times in 18 on a loaded box — it was pinning the fast path's
    # spelling of a fact the code deliberately reports either way. What the operator
    # needs is which variable was read, and that survives both paths.
    assert "exited" in output
    assert "CURSOR_API_KEY" in output
    # The corpse is cleared, not left for the console's close and recycle paths to
    # read as a window still there.
    assert _windows("settle-late") == []


def test_the_exit_status_is_rendered_when_tmux_still_has_it(monkeypatch, tmp_path):
    """The half of the death message the timing-dependent test above cannot assert.

    Whether tmux still has an exit status is a race with the reaper, so the live test
    asserts only what survives both outcomes. That leaves the status rendering
    untested — and it is the more useful half when it is there, since `exit 1` and
    `exit 127` are different diagnoses. Driven here through `_pane_state` instead of
    through a real death, which makes both branches deterministic and asserts the
    thing the race obscures rather than a rewording of the other test.
    """
    monkeypatch.setattr(pin, "_pane_epitaph", lambda window_id: "Not logged in.")
    monkeypatch.setattr(pin, "_set_remain_on_exit", lambda window_id, mode: None)
    monkeypatch.setattr(pin.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))

    monkeypatch.setattr(pin, "_pane_state", lambda window_id: (True, "1"))
    with pytest.raises(pin.WindowDied) as carried:
        pin.confirm_started("@1", "cursor")
    assert "(exit 1)" in str(carried.value)
    assert "Not logged in." in str(carried.value)

    # And a corpse tmux can no longer describe says the same thing without inventing
    # a status. `exit 0` would be the dangerous invention: it reads as a clean exit.
    monkeypatch.setattr(pin, "_pane_state", lambda window_id: (True, ""))
    with pytest.raises(pin.WindowDied) as reaped:
        pin.confirm_started("@1", "cursor")
    assert "exit" not in str(reaped.value).split(" — ")[0].replace("exited", "")
    assert "Not logged in." in str(reaped.value)


def test_a_window_that_cannot_exec_at_all_is_reported_failed(private_tmux, tmp_path,
                                                             monkeypatch):
    """
    Scenario: the harness binary is not on PATH — the 2026-08-08 incident

    Verifications:
    - the failure is reported, and fast: no waiting out the settle window
    - the operator is pointed at PATH, which is the cause when nothing was printed

    A command that never execs prints nothing, so there is no epitaph to quote and
    the hint is all the operator gets. That is exactly the case it exists for.

    PATH is cut to the shim directory plus the system ones, which is the state a
    systemd user unit started at boot is actually in: no `~/.local/bin`, hence no
    harness binary, while `env` and the rest of the launch still resolve. No fake
    `claude` is written — this suite must never launch a real session.
    """
    monkeypatch.setenv("PATH", os.pathsep.join([str(private_tmux), "/usr/bin", "/bin"]))
    cfg = Config(project_root=tmp_path, session="settle-noexec")

    start = time.monotonic()
    ok, output = do_spawn(cfg, "main", tmp_path, "", "claude")
    elapsed = time.monotonic() - start

    assert ok is False
    assert "PATH" in output
    assert elapsed < settle_s("claude"), "a dead window is not worth waiting out"


def test_a_window_that_survives_its_settle_is_reported_started(private_tmux, tmp_path):
    """
    Scenario: a spawn whose command keeps running

    Verifications:
    - the spawn is reported started
    - the window is alive and `remain-on-exit` is back off

    The option is on only for the settle: a window that kept it would leave a
    corpse when its real session ends, and the console reads a corpse as a window
    that is still there.
    """
    _fake_harness(private_tmux, "claude", "sleep 60")
    cfg = Config(project_root=tmp_path, session="settle-live")

    ok, _ = do_spawn(cfg, "main", tmp_path, "", "claude")

    assert ok is True
    live = [w for w in _windows("settle-live") if w.endswith(" 0")]
    assert len(live) == 1
    window_id = live[0].split()[0]
    shown = subprocess.run(tmux.argv("show-options", "-w", "-t", window_id,
                                     "remain-on-exit"), capture_output=True, text=True)
    assert shown.stdout.split() == ["remain-on-exit", "off"]


def test_a_roster_window_that_cannot_exec_is_not_reported_as_a_roster(
        private_tmux, tmp_path, monkeypatch):
    """
    Scenario: `thalamus roster` on a box with no `claude` — the reported bug

    Verifications:
    - the bring-up is a failure, and points at PATH
    - the dead window is cleared, so nothing claims a roster is attachable
    - no "Roster running in tmux session" line is printed

    Driven through `roster_sync` because that is the surface the bug is worst on:
    the console answered `{"ok": true}`, then drew its no-session screen telling
    the operator to run the sync it had just told them worked.
    """
    monkeypatch.setenv("PATH", os.pathsep.join([str(private_tmux), "/usr/bin", "/bin"]))
    cfg = Config(project_root=tmp_path, session="settle-roster")

    ok, output = server.roster_sync(cfg)

    assert ok is False
    assert "PATH" in output
    assert "Roster running" not in output
    assert _windows("settle-roster") == []


def test_a_roster_window_that_survives_its_settle_is_reported_started(private_tmux,
                                                                     tmp_path):
    """The other half: a roster whose anchor comes up reports success, keeps the
    window, and turns `remain-on-exit` back off — the option is held only for the
    settle, and a window that kept it would leave a corpse the console's close and
    recycle paths read as a window still there."""
    _fake_harness(private_tmux, "claude", "sleep 60")
    cfg = Config(project_root=tmp_path, session="roster-live")

    ok, output = server.roster_sync(cfg)

    assert ok is True
    assert "Roster running in tmux session `roster-live`" in output
    live = [w for w in _windows("roster-live") if w.endswith(" 0")]
    assert len(live) == 1
    shown = subprocess.run(tmux.argv("show-options", "-w", "-t", live[0].split()[0],
                                     "remain-on-exit"), capture_output=True, text=True)
    assert shown.stdout.split() == ["remain-on-exit", "off"]


def test_the_settle_window_is_per_harness_and_no_harness_gets_less():
    """
    Scenario: the settle policy read straight off the launch shapes

    Verifications:
    - Cursor waits longer than Claude Code, and longer than the retired constant
    - an unknown harness gets the longest window rather than the shortest

    Claude Code decides everything that can kill it locally (0.010 s for a missing
    binary, 0.278 s for a rejected flag, and its trust and credential failures do
    not kill it at all — they park on a modal). Cursor's fatal case is decided
    across the network. One constant cannot be both.
    """
    assert settle_s("cursor") > settle_s("claude")
    assert settle_s("cursor") > RETIRED_GLOBAL_SETTLE_S
    assert settle_s("no-such-harness") == max(s.settle_s
                                              for s in LAUNCH_SHAPES.values())


def test_pin_owns_the_confirmation_so_every_surface_gets_the_same_verdict():
    """The console is not the only spawner: `thalamus spawn` and `thalamus pin` are
    the same launch from a terminal, and a window that died is a failure there too.

    Asserted over the module rather than by launching, because the point is *where*
    the check lives — a second copy in the console is how the CLI kept reporting a
    success the console had already learned to doubt.
    """
    assert "confirm_started" in pin.spawn.__code__.co_names
    assert "confirm_started" in pin.launch.__code__.co_names
    assert "confirm_started" in pin.roster.__code__.co_names
    assert not hasattr(server, "SPAWN_SETTLE_S")
