"""Pinned sessions as tmux windows — what the console drives.

One window per pinned session, the window name being the scope. Coordination stays in
tmux, not in Thalamus: nothing here tracks the processes it starts, because the pin
ledger already records what actually ran. `launch` opens a window when called inside
tmux and otherwise hands off to `harness/pin.py`'s exec; `spawn` is the console's
button; `ensure_anchor` gives the console's session its `main` anchor window.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from thalamus_console import tmux
from thalamus_console.rooms import (
    _entered_room,
    _in_room,
    _room_env,
    _with_room,
    launch_flags,
)
from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.harness import pin

ROSTER_SESSION = "thalamus"


def _unleak_session_env(target: str | None, room: str,
                        harness: str = "claude") -> None:
    """Take the room back out of the tmux *session* environment after creating it.

    `new-session -e` applies the variables to the first window's process AND stores
    them in the session environment, where every later window inherits them — so a
    session that happened to be created for a room would silently enrol the next
    roomless window in it. The first window already has what it needs (and carries
    it in its own argv besides), so the stored copy is pure leak. Removed at the
    source; `_room_clear` is the second line of defence for sessions this launcher
    did not create.
    """
    if not (target and room):
        return
    for key, _ in _room_env(room, harness):
        subprocess.run(tmux.argv("set-environment", "-t", target, "-u", key),
                       capture_output=True)


def _tmux_windows(target: str | None) -> set[tuple[str, str]]:
    """Every window as (name, room) — the pair `ensure_anchor`'s idempotency keys on.

    The name alone is not the identity: a room's `main` and the console's own `main`
    are two sessions in two config dirs, so taking the first for the second would
    leave the console without its anchor.
    """
    cmd = tmux.argv("list-windows", *(["-t", target] if target else []),
                    "-F", "#{window_index}\t#{window_name}")
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        return set()
    rooms_by_index = window_room(target)
    found: set[tuple[str, str]] = set()
    for line in out.stdout.splitlines():
        index, _, name = line.partition("\t")
        if index.strip().isdigit():
            found.add((name, rooms_by_index.get(int(index), "")))
    return found


def _open_window(scope: str, argv: list[str], project_root: Path, target: str | None,
                 detached: bool = False, room: str = "",
                 harness: str = "claude") -> str:
    # detached (-d): don't switch the session's active window. Console additions run
    # underneath attached clients (/tty, PC attaches), which must not be yanked to
    # the new window; an interactive `thalamus pin` keeps the switch — the operator
    # asked for that window.
    #
    # Room variables go through both channels deliberately: `-e` so the window's own
    # environment agrees with what the process got, and the argv prefix so the room
    # survives a `respawn-window` recycle (see `_with_room`).
    #
    # `-P -F #{window_id}` returns the id of the window just made. Callers confirm
    # against that id rather than diffing the window list: the id names one window
    # for as long as it exists, while a diff can only ask whether *some* new window
    # is alive — which is the wrong question the moment two things create windows.
    room_flags = [f for k, v in _room_env(room, harness) for f in ("-e", f"{k}={v}")]
    cmd = tmux.argv("new-window", *(["-d"] if detached else []),
                    *(["-t", target] if target else []),
                    "-P", "-F", "#{window_id}", "-n", scope,
                    "-c", str(project_root), "-e", f"THALAMUS_SCOPE={scope}", *room_flags,
                    "--", *_with_room(argv, room, harness))
    # stdout only: tmux's own errors keep going to this process's stderr, where the
    # console's journal and an operator's terminal already read them.
    return subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                          text=True).stdout.strip()


class WindowDied(RuntimeError):
    """A pinned window was created and its command did not survive the settle window.

    Distinct from every other launch failure because it is the one that reports as a
    success everywhere else: tmux forked, so `new-window` exited 0, so the caller and
    its caller and the phone all saw a spawn that worked.
    """


def _pane_state(window_id: str) -> tuple[bool, str]:
    """(dead, exit status) for a window, where a window that is gone counts as dead.

    Both spellings of death are real and which one appears depends on timing:
    `remain-on-exit` leaves a corpse with `pane_dead` set, and anything that outran
    the option being set was reaped, leaving no window for tmux to describe.
    """
    out = subprocess.run(tmux.argv("display-message", "-p", "-t", window_id,
                                   "#{pane_dead}\t#{pane_dead_status}"),
                         capture_output=True, text=True)
    if out.returncode != 0:
        return True, ""
    dead, _, status = out.stdout.strip().partition("\t")
    return dead == "1", status.strip()


def _pane_epitaph(window_id: str) -> str:
    """The last thing a dead window printed, for the operator who is holding a phone.

    Worth the capture because the deaths that survive the exec-failure case are
    articulate: a rejected Cursor API key prints which variable it read the key from,
    which is the whole diagnosis. tmux's own "Pane is dead" banner is dropped — it is
    drawn into the corpse's viewport and says only what the caller already knows.

    `-S -` reaches into the history, and without it this returns nothing useful: when
    a pane dies, tmux pushes what it printed up out of the viewport and leaves the
    banner alone on the visible screen. A roster pane is WINDOW_ROWS lines tall, so
    a program that printed three lines and exited has all three in history and the
    rest of the viewport blank.

    `-J` rejoins the lines tmux wrapped. A roster pane is WINDOW_COLS columns wide,
    so a sentence of vendor English can span screen lines, and taking the last few
    without joining first quotes a fragment that starts mid-word.
    """
    out = subprocess.run(tmux.argv("capture-pane", "-p", "-J", "-S", "-",
                                   "-t", window_id), capture_output=True, text=True)
    lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    lines = [ln for ln in lines if not ln.startswith("Pane is dead")]
    return " ".join(lines[-3:])[:400]


def _set_remain_on_exit(window_id: str, value: str) -> None:
    subprocess.run(tmux.argv("set", "-w", "-t", window_id, "remain-on-exit", value),
                   capture_output=True)


def confirm_started(window_id: str, harness: str = "claude") -> None:
    """Hold a freshly created window to its harness's settle deadline, or raise.

    Polling rather than sleeping the deadline out: a window that dies at 20 ms is
    reported at 20 ms, and only a launch that succeeds pays the full wait. That
    matters because the deadline is no longer one number — `launcher.settle_s` sizes
    it per harness, and Cursor's is measured in seconds because its one fatal failure
    (a rejected API key) resolves after a round trip to its API.

    `remain-on-exit` is turned on for the duration so a death leaves a corpse to read
    the reason off, and turned back off the moment the window proves alive — a window
    that keeps the option would leave a corpse at the end of its real session, which
    the console's close and recycle paths read as a window still there.
    """
    from thalamus.harness.launcher import settle_s

    if not window_id:
        raise WindowDied("tmux created a window but reported no window id")
    _set_remain_on_exit(window_id, "on")
    deadline = time.monotonic() + settle_s(harness)
    while True:
        dead, status = _pane_state(window_id)
        if dead:
            detail = _pane_epitaph(window_id)
            subprocess.run(tmux.argv("kill-window", "-t", window_id), capture_output=True)
            status_part = f" (exit {status})" if status else ""
            raise WindowDied(
                f"the window was created and its command exited{status_part} before it "
                f"could be called started"
                + (f" — it printed: {detail}" if detail else "")
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _set_remain_on_exit(window_id, "off")
            return
        time.sleep(min(0.05, remaining))


# Every roster window's geometry, columns by rows. One tmux window has one width
# and every viewer — the console on a phone or a desktop, the /tty page, a desktop
# `tmux attach` — reads the same window, so the width is set for the viewer the
# console exists for: 60 columns is what a phone's auto-fit renders at a readable
# size with no horizontal scroll. A desktop attach gets a 60-column box; the rows
# and the history behind them are what a desktop was short of. Not read from
# tmux's `default-size`: that is 80x24 on any box without a hand-written
# tmux.conf, and this project ships none.
WINDOW_COLS = 60
WINDOW_ROWS = 50


def _pin_window_sizes(target: str | None) -> None:
    """Hold every roster window at WINDOW_COLS x WINDOW_ROWS, post-creation.

    `resize-window -x -y` sets the size and, as a side effect, the window's LOCAL
    `window-size manual`, which is wanted: the console has no tmux client of its
    own and reads whatever size the window has, so an attaching desktop or /tty
    client must not resize the windows out from under it. Running over every window
    in the session also corrects one created at the stock 80x24 by whichever unit
    made the session first — `tmux new -A -s thalamus` carries the stock size, and
    the roster is often spawned into a session it did not create.

    Per window and after creation, never as a global: tmux 3.4's server segfaults
    creating a window while the global window-size is manual and no client is
    attached (measured 2026-07-17; it took down the whole roster). Resizing each
    window once it exists is crash-free on the same version.
    """
    cmd = tmux.argv("list-windows", *(["-t", target] if target else []),
                    "-F", "#{window_id}")
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        return
    for window_id in out.stdout.split():
        subprocess.run(tmux.argv("resize-window", "-t", window_id,
                                 "-x", str(WINDOW_COLS), "-y", str(WINDOW_ROWS)))


def window_room(target: str | None) -> dict[int, str]:
    """The room each window in a tmux session is in, by window index.

    Read from `#{pane_start_command}`, which renders the command the window was
    created with — and `_with_room` put the room in that command's `env` prefix, so
    it is exactly as durable as the room itself and survives the respawn that drops
    `-e` (measured with the consultation `81176421bb8e409a`, which found
    this channel). The tmux *window name* stays the bare scope: it is the plane's
    established identity for a window, and a room is a second dimension over that
    set rather than a different naming of it.
    """
    fmt = "#{window_index}\t#{pane_start_command}"
    cmd = tmux.argv("list-windows", *(["-t", target] if target else []), "-F", fmt)
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        return {}
    found: dict[int, str] = {}
    for line in out.stdout.splitlines():
        index, _, command = line.partition("\t")
        match = re.search(r"THALAMUS_ROOM=(\S+)", command)
        if index.strip().isdigit():
            found[int(index)] = match.group(1) if match else ""
    return found


def launch(scope: str, project_root: Path, base: Path | None = None,
           room: str | None = None, harness: str = "claude") -> None:
    """Hand this terminal, or a new tmux window, to a pinned session, in a room if asked.

    Inside tmux the session gets a window of its own; outside it, `pin.launch` execs it
    here with the room's variables and flags added.
    """
    room = _entered_room(room, harness)
    if os.environ.get("TMUX"):
        argv = _member_argv(scope, project_root, base, room, harness)
        window_id = _open_window(scope, argv, project_root, target=None, room=room,
                                 harness=harness)
        confirm_started(window_id, harness)
        _pin_window_sizes(target=None)
        print(f"Pinned window `{scope}`{_in_room(room)} opened: {' '.join(argv)}")
        return
    pin.launch(scope, project_root, base, harness, env=tuple(_room_env(room, harness)),
               extra_argv=tuple(launch_flags(room, scope, harness)))


def _member_argv(scope: str, project_root: Path, base: Path | None, room: str,
                 harness: str = "claude") -> list[str]:
    """A pinned session's argv with the room's flags added — every window's command."""
    return [*pin.session_argv(scope, project_root, base, harness),
            *launch_flags(room, scope, harness)]


def spawn(scope: str, cwd: Path, session: str = ROSTER_SESSION,
          base: Path | None = None, room: str | None = None,
          harness: str = "claude") -> None:
    """Open ONE detached pinned window on demand — the plane's spawn button.

    Spawn creates a single expert window in a chosen directory: `cwd` becomes the
    window's working dir, so the session's work — and the memory it distills — is
    about that project while still pinned to `scope`. The derived agent files are
    written to USER_AGENTS_DIR first so `--agent` resolves regardless of `cwd`.
    Detached (`-d`) so an attached /tty or PC client is never yanked to the new window
    (same rule as `ensure_anchor`).
    """
    if not (tmux.inside() or shutil.which("tmux")):
        raise RuntimeError("spawn needs tmux (it IS the control plane)")
    cwd = Path(cwd).expanduser()
    if not cwd.is_dir():
        raise ValueError(f"not a directory: {cwd}")

    from thalamus.harness.launcher import launch_argv

    room = _entered_room(room, harness)
    manifest = pin.resolve(scope, base)  # validates scope; raises with available-scopes
    persona = None
    if manifest is not None:
        pin.write_all_agents(pin.USER_AGENTS_DIR, base)
        persona = pin.agent_name(scope)  # main has no manifest/agent by design
        if harness == "codex":
            pin.write_codex_profile(manifest, base=base)
    argv = [*launch_argv(harness, scope, persona=persona), *launch_flags(room, scope, harness)]

    # The session must exist (`thalamus console` creates it at startup, and the tty
    # unit's `tmux -L thalamus new -A -s thalamus` does on first connect); create it if
    # somehow absent so spawn never fails.
    # Create it *with* this scope's window, the way `ensure_anchor` does. A bare
    # `new-session` would leave a shell placeholder at the lowest index, and the
    # plane reads the lowest index as the anchor — the un-closable window whose cwd
    # is its reference for roster sync. A placeholder there outranks every real
    # session for the life of the tmux server, and `restart` on it types `/exit`
    # into a shell instead of a claude, so the recycle hangs out its whole grace.
    room_flags = [f for k, v in _room_env(room, harness) for f in ("-e", f"{k}={v}")]
    if subprocess.run(tmux.argv("has-session", "-t", session),
                      capture_output=True).returncode != 0:
        window_id = subprocess.run(
            tmux.argv("new-session", "-d", "-s", session,
                      "-P", "-F", "#{window_id}", "-n", scope,
                      "-c", str(cwd), "-e", f"THALAMUS_SCOPE={scope}", *room_flags,
                      "--", *_with_room(argv, room, harness)),
            check=True, stdout=subprocess.PIPE, text=True).stdout.strip()
        _unleak_session_env(session, room, harness)
    else:
        window_id = _open_window(scope, argv, cwd, target=session, detached=True,
                                 room=room, harness=harness)
    # A clean return from tmux is not evidence that anything is running: `new-window`
    # reports success once it has forked, before the command it was given has execed
    # or reached whatever it authenticates against. Confirmed here rather than in any
    # one caller, so the phone and the terminal get the same verdict.
    confirm_started(window_id, harness)
    _pin_window_sizes(target=session)
    print(f"Spawned `{scope}`{_in_room(room)} in {cwd}")


def ensure_anchor(project_root: Path, session: str = ROSTER_SESSION,
                  base: Path | None = None) -> None:
    """Make sure `session` exists and holds the `main` anchor window.

    Creates the session with `main` as its first window when the session is missing,
    opens `main` again in a session that has lost it, and leaves a session that already
    holds it alone. `thalamus console` calls it at startup for a missing session, and
    the admin sheet's roster sync calls it on demand.

    The anchor is the only window this opens. Experts open on demand from the console:
    an expert window nobody prompts writes a pin-ledger spawn with no engagement and
    inflates the `pinned, never retrieved` routing metric (measured 2026-07-19).

    Always roomless. The anchor is the console's own window, and this runs inside a
    long-lived server process, so taking the room from the environment would put the
    anchor in whatever room the server was started in. A room's `main` is a different
    session in a different config dir, so it does not count as the anchor here.

    Creating the session *with* `main` matters: whichever window is created first takes
    the lowest index, the console reads the lowest index as the anchor, and a bare
    `new-session` would put a shell there for the life of the tmux server.

    The window is held to its settle deadline, and a death raises `WindowDied` quoting
    what the pane printed.
    """
    if not shutil.which("tmux"):
        raise RuntimeError("the console needs tmux to hold its sessions")

    room = ""
    argv = _member_argv(MAIN_SCOPE, project_root, base, room)
    if subprocess.run(tmux.argv("has-session", "-t", session),
                      capture_output=True).returncode != 0:
        window_id = subprocess.run(
            tmux.argv("new-session", "-d", "-s", session,
                      "-P", "-F", "#{window_id}", "-n", MAIN_SCOPE,
                      "-c", str(project_root), "-e", f"THALAMUS_SCOPE={MAIN_SCOPE}",
                      "--", *_with_room(argv, room)),
            check=True, stdout=subprocess.PIPE, text=True,
        ).stdout.strip()
        _unleak_session_env(session, room)
    elif (MAIN_SCOPE, room) in _tmux_windows(session):
        print(f"`{MAIN_SCOPE}` already has a window in tmux session `{session}` — "
              f"attach with: {tmux.attach_hint(session)}")
        return
    else:
        window_id = _open_window(MAIN_SCOPE, argv, project_root, session,
                                 detached=True, room=room)
    # Held open from the moment the window exists: the deaths worth reading are exec
    # failures at tens of milliseconds, and a pane reaped before the option is set
    # leaves no epitaph to quote.
    _set_remain_on_exit(window_id, "on")
    _pin_window_sizes(session)

    # A clean return from tmux is not evidence that anything is running: `new-window`
    # reports success once it has forked, before its command has execed.
    try:
        confirm_started(window_id)
    except WindowDied as death:
        raise WindowDied(f"`{MAIN_SCOPE}` did not start: {death}") from None
    print(f"Pinned window `{MAIN_SCOPE}` opened in tmux session `{session}` — "
          f"attach with: {tmux.attach_hint(session)}")
