"""Shared helpers for the console integration arm. Not a case.

The integration cases drive a real console (`_console_rig`) and then read what it did
through a *different* layer than the one it wrote through: tmux's own enumeration, the
core's own readers, the real `thalamus` CLI, the real SessionStart hook. This module is
the small set of those second channels, so each case states the property and not the
plumbing.

**What the rig cannot do for us, and what stands in.** The stub `claude` is a `cat`; it
runs no hooks and writes no session descriptor. The two things a real session leaves
behind are therefore reproduced by running the *real* writer where one exists —
`harness/hooks/claude-code/session-start.sh` for the pin-ledger row, fed the pane id the
console's own spawn produced — and by writing the harness's descriptor file by hand where
none does (`sessions/<id>.json` in the room's config root, which only Claude Code writes).
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from ._console_rig import REPO_ROOT, Rig, RigFailed, console_rig, thalamus_bin

ROSTER = "roster"

HOOK = REPO_ROOT / "src" / "thalamus" / "harness" / "hooks" / "claude-code" / "session-start.sh"


def child_env(rig: Rig) -> dict[str, str]:
    """The environment the rig's console runs in, for a sibling process of it.

    Same HOME, same tmux socket, same PATH — and nothing inherited from the session
    running the suite (it is itself pinned, and a pinned env would put a CLI call in the
    caller's room).
    """
    env = {k: os.environ[k] for k in ("LANG", "LC_ALL", "TERM", "TZ", "USER", "LOGNAME")
           if k in os.environ}
    env.setdefault("LANG", "C.UTF-8")
    env.update({
        "HOME": str(rig.home),
        # The rig's own bin first: the stub `claude`/`codex` are what make an extractor
        # CLI "reachable" to the core's readers, exactly as they do for the console.
        "PATH": os.pathsep.join([str(rig.root / "bin"), str(Path(sys.executable).parent),
                                 "/usr/local/bin", "/usr/bin", "/bin"]),
        "THALAMUS_TMUX_SOCKET": rig.socket,
    })
    if os.environ.get("QE_CONSOLE_SRC"):
        env["PYTHONPATH"] = os.environ["QE_CONSOLE_SRC"]
    return env


def thalamus(rig: Rig, *args: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    """The real `thalamus` CLI under the rig's HOME and tmux socket."""
    return subprocess.run([str(thalamus_bin()), *args], env=child_env(rig),
                          capture_output=True, text=True, timeout=timeout,
                          cwd=str(rig.root))


def py(rig: Rig, code: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    """Run `code` in the interpreter under test with the rig's HOME, so a core module's
    import-time `Path.home()` bindings land inside the rig."""
    return subprocess.run([sys.executable, "-c", code], env=child_env(rig),
                          capture_output=True, text=True, timeout=timeout,
                          cwd=str(rig.root))


def seed_credentials(rig: Rig) -> None:
    """A room member needs the operator's login to exist (`rooms.ensure_room`)."""
    creds = rig.home / ".claude" / ".credentials.json"
    creds.parent.mkdir(parents=True, exist_ok=True)
    creds.write_text("{}")


def pins_file(rig: Rig) -> Path:
    return rig.home / ".thalamus" / "pins" / "pins.jsonl"


def pin_rows(rig: Rig) -> list[dict]:
    try:
        text = pins_file(rig).read_text()
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def run_session_start_hook(rig: Rig, *, pane_id: str, scope: str, cwd: str,
                           session_id: str | None = None, room: str = "",
                           agent: str = "", from_pid: int = 0,
                           ) -> tuple[str, subprocess.CompletedProcess]:
    """Fire the real SessionStart hook as the harness would inside pane `pane_id`.

    Returns `(session_id, process)`. The hook is the only writer of the pin ledger, so a
    ledger the console reads is made by it or it is a fixture the case invented.

    With `from_pid` the hook's environment is the one tmux gave that pane's process
    (`/proc/<pid>/environ`) and `scope`/`room` are not supplied at all: whatever scope
    and room the console launched the window with is what the hook resolves.
    """
    session_id = session_id or str(uuid.uuid4())
    env = child_env(rig)
    if from_pid:
        # What the session would actually see: the environment tmux gave the pane's
        # process, so a scope or room the console failed to set is not papered over.
        raw = Path(f"/proc/{from_pid}/environ").read_bytes().split(b"\0")
        env = dict(e.decode(errors="replace").split("=", 1) for e in raw if b"=" in e)
        env.pop("TMUX", None)
        env["PATH"] = child_env(rig)["PATH"]
        env["CLAUDE_CODE_ENTRYPOINT"] = "cli"
    else:
        env.update({"TMUX_PANE": pane_id, "THALAMUS_SCOPE": scope,
                    "CLAUDE_CODE_ENTRYPOINT": "cli"})
        if room:
            env["THALAMUS_ROOM"] = room
    if agent:
        env["CLAUDE_CODE_AGENT"] = agent
    proc = subprocess.run(
        ["bash", str(HOOK)], env=env, capture_output=True, text=True, timeout=60,
        input=json.dumps({"session_id": session_id, "cwd": cwd, "source": "startup",
                          "hook_event_name": "SessionStart"}))
    return session_id, proc


def windows(rig: Rig) -> list[dict]:
    return rig.get("/api/panes").json()["windows"]


def tmux_rows(rig: Rig) -> list[dict]:
    """tmux's own account of the roster session, independent of the console."""
    fmt = "#{window_index}\t#{window_id}\t#{window_name}\t#{pane_id}\t#{pane_dead}"
    r = rig.tmux("list-windows", "-t", rig.session, "-F", fmt)
    out = []
    for line in r.stdout.splitlines():
        i, wid, name, pane, dead = line.split("\t")
        out.append({"index": int(i), "window_id": wid, "name": name, "pane_id": pane,
                    "dead": dead == "1"})
    return out


def alpha(rig: Rig) -> str:
    return str(rig.repos[0].resolve())


def spawn(rig: Rig, scope: str, *, room: str = "", harness: str = "",
          directory: str | None = None):
    body: dict = {"scope": scope, "dir": directory or alpha(rig)}
    if room:
        body["room"] = room
    if harness:
        body["harness"] = harness
    return rig.post("/api/spawn", body, timeout=60)


@contextlib.contextmanager
def integ_rig(**kw):
    """`console_rig` with the roster session named `roster`, not the rig's `qe`.

    The rig's default session name is also an expert scope's name, and a window named
    like its own session makes every later `new-window -t <session>` resolve to that
    window (see `console_integ_spawn_roundtrip`). Cases about anything else must not
    inherit that, so they run on a session no scope shares.
    """
    extra = tuple(kw.pop("extra_args", ())) + ("--session", ROSTER)
    with console_rig(extra_args=extra, **kw) as rig:
        rig.session = ROSTER
        if rig.get("/api/panes").json().get("session") != ROSTER:
            raise RigFailed("console did not take the --session override")
        yield rig
