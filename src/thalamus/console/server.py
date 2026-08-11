"""The console — a tiny tmux bridge, so the roster is drivable from a phone.

A pinned session is an OS process in a tmux window (docs/07, "the process is the
pin"), which makes tmux the one place all of them are addressable. This server
reads each window's live screen with `tmux capture-pane` and sends input with
`tmux send-keys`, always targeting windows *by index* so the session's active
window — and any terminal attached to it — is never disturbed. The browser client
in `static/` is a PWA over the same JSON: tabs for windows, a composer, terminal
keycaps, and an admin sheet that can restart a pinned process or spawn a new one.

Two properties are load-bearing:

- **Every tmux call is an argv list, never a shell string.** Pane text and typed
  input are data, so nothing captured or composed can become a command.
- **It binds loopback by default.** There is no authentication here and none is
  pretended; reaching it from a phone is a job for whatever already authenticates
  your network (a VPN/overlay network, an authenticating reverse proxy, an SSH
  tunnel). See docs/console.md.

The bridge itself is stdlib-only, unlike the FastAPI surfaces in `pulse/` and
`viewer/`: one of its jobs is restarting the systemd unit that hosts it, so the
fewer moving parts between a tap and a tmux call, the better. The expert layer —
the scope list, spawn, roster sync — is the one part that needs the rest of the
package, so those imports are deferred to the call that uses them. Run this
module with a bare `python3` and you get the tmux bridge and the whole client;
the expert controls report themselves unavailable instead of failing to import.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote

STATIC_DIR = Path(__file__).with_name("static")
DEFAULT_PORT = 8378

# Defaults for a console running without the rest of Thalamus importable. `pin` owns
# the real ones; these only have to be sane enough to bridge a tmux session.
FALLBACK_SESSION = "thalamus"

# The expert layer — scopes, spawn, roster sync, rooms — is the only part of this
# module that needs the package. It is imported on use, not at module scope, so the
# bridge runs under a bare `python3` with no yaml and no pydantic installed. Import
# failure is a fact about this deployment, not an error: it means the expert controls
# are unavailable, which the client renders as their absence.
_PIN_UNSET = object()
_pin_cache: object = _PIN_UNSET


def pin_module():
    """`thalamus.harness.pin`, or None if this console has no package around it."""
    global _pin_cache
    if _pin_cache is _PIN_UNSET:
        try:
            from thalamus.harness import pin
        except Exception:  # noqa: BLE001 — any import failure means "not available"
            _pin_cache = None
        else:
            _pin_cache = pin
    return _pin_cache


def has_experts() -> bool:
    """Whether the expert controls (scope list, spawn, roster, rooms) can work."""
    return pin_module() is not None


_read_cache: object = _PIN_UNSET
_speech_cache: object = _PIN_UNSET


def transcript_module():
    """`.transcript`, or None if this console has no package around it.

    Deferred for the same reason the expert layer is: the read view reuses the
    harness's transcript parsing, so importing it at module scope would drag the
    package into a bridge that is documented to run under a bare `python3`. A
    console without it keeps the pane mirror and reports the read view
    unavailable, which the client renders as the absence of the toggle.
    """
    global _read_cache
    if _read_cache is _PIN_UNSET:
        try:
            from . import transcript
        except Exception:  # noqa: BLE001 — any import failure means "not available"
            _read_cache = None
        else:
            _read_cache = transcript
    return _read_cache


def speech_module():
    """`.speech`, or None under a bare `python3` with no package around it.

    Deferred for the same reason `.transcript` is — the bridge is documented to
    run without the package, and a console that cannot import the transform
    simply has no voice rather than no console.
    """
    global _speech_cache
    if _speech_cache is _PIN_UNSET:
        try:
            from . import speech
        except Exception:  # noqa: BLE001 — any import failure means "not available"
            _speech_cache = None
        else:
            _speech_cache = speech
    return _speech_cache


# The voice service is a separate unit on loopback: it holds a GPU-resident model
# and this process restarts itself on edit, which are incompatible lifecycles.
VOICE_URL = os.environ.get("THALAMUS_VOICE_URL", "http://127.0.0.1:8380")

# Spoken when the transform drops something it promised to keep. A listener who
# hears nothing knows to go and look; a listener fed a fluent sentence with the
# wrong number in it has no way to know at all, and no way to rewind and check.
WITHHELD_NOTICE = (
    "This update was withheld. The spoken summary lost a value it was required "
    "to keep, so it was not read out. Check the console."
)


def synthesise_update(source: str, timeout: float = 60.0):
    """Raw turn text to wav bytes, via the transform and the voice service.

    Returns `(audio, error)`. The protected-token contract is enforced here
    rather than in the client: a summary that lost a number is replaced by a
    notice saying so, because the failure it guards against is audio that sounds
    entirely correct.
    """
    speech = speech_module()
    if speech is None:
        return None, "speech transform unavailable"

    update = speech.spoken_update(source)
    if not update.faithful:
        lost = ", ".join(token.literal for token in update.missing)
        print(f"say: withheld — protected tokens lost: {lost}", file=sys.stderr, flush=True)
        spoken = WITHHELD_NOTICE
    else:
        spoken = update.text
    if not spoken.strip():
        return None, "nothing to say"
    return _post_to_voice(spoken, timeout)


def _post_to_voice(text: str, timeout: float):
    """The transport half, separate so the gate above can be tested without one."""
    import urllib.error
    import urllib.parse
    import urllib.request

    url = f"{VOICE_URL}/say?" + urllib.parse.urlencode({"text": text})
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read(), None
    except urllib.error.HTTPError as exc:
        # The service answered and refused. Reporting that as "unreachable" sends
        # the next reader to check whether it is running, which it is.
        print(f"say: voice service refused: {exc}", file=sys.stderr, flush=True)
        return None, f"voice service refused: {exc.code}"
    except urllib.error.URLError as exc:
        print(f"say: voice service unreachable at {VOICE_URL}: {exc}",
              file=sys.stderr, flush=True)
        return None, "voice service unreachable"
    except Exception as exc:  # noqa: BLE001 — the console must survive this
        print(f"say: synthesis failed: {exc}", file=sys.stderr, flush=True)
        return None, "synthesis failed"


# One ledger index and one feed store for the process, both stateful across polls
# so a poll reads only the bytes appended since the last one. ThreadingHTTPServer
# serves requests concurrently and a phone plus a desktop on the same window is the
# normal case, so every touch of that shared state is serialized.
READ_LOCK = threading.Lock()
_LEDGER = None
_FEEDS = None


def read_feed(cfg: Config, idx: int):
    """(window, feed, reason) for a roster window.

    `reason` is None when a feed came back, and otherwise names which failure it
    was: `unresolved` (cannot tell which session is here) or `pending` (we know
    exactly which session, it has not written its first turn). They read very
    differently to whoever is holding the phone.
    """
    tr = transcript_module()
    window = next((w for w in list_windows(cfg) if w["index"] == idx), None)
    if tr is None or window is None:
        return window, None, "no-package" if window is not None else "unresolved"
    global _LEDGER, _FEEDS
    with READ_LOCK:
        if _LEDGER is None:
            _LEDGER, _FEEDS = tr.LedgerIndex(), tr.FeedStore()
        # The window name is the scope: the roster names a window for the expert
        # pinned in it, and the fallback route needs that to join the ledger.
        got = tr.resolve(window.get("pane_id", ""), window.get("name", ""),
                         window.get("cwd", ""), window.get("pane_pid", 0), _LEDGER)
        if got is None:
            return window, None, "unresolved"
        session_id, path, launch_cwd = got
        if path is None:
            return window, None, "pending"
        return window, _FEEDS.get(session_id, path, launch_cwd), None

# One watcher for the process. `.distill` is stdlib-only, but it is still reached
# through an accessor like the rest of the package: a console run as a bare script
# has no package to do a relative import from, and a missing widget is a better
# failure than a missing console.
_DISTILL_UNSET = object()
_distill_cache: object = _DISTILL_UNSET


def distill_watch():
    """The `DistillWatch` singleton, or None if this console has no package."""
    global _distill_cache
    if _distill_cache is _DISTILL_UNSET:
        try:
            from .distill import DistillWatch
        except Exception:  # noqa: BLE001 — any import failure means "not available"
            _distill_cache = None
        else:
            _distill_cache = DistillWatch()
    return _distill_cache


def distill_rows() -> list[dict]:
    watch = distill_watch()
    return watch.rows() if watch is not None else []


# Graceful-exit budget before force-respawning a window. SessionEnd runs
# `thalamus extract` (distillation), which can take a while; killing early loses it.
RECYCLE_GRACE_S = 240

# On-demand spawn is serialized and confirmed. Confirmation works by diffing the
# window list around the spawn, so two concurrent spawns would scramble each other's
# before-picture; the lock keeps that diff meaningful.
SPAWN_LOCK = threading.Lock()

# How long to let a freshly spawned window prove it is really running. The failure
# being caught is an exec failure, which is immediate — see do_spawn.
SPAWN_SETTLE_S = 1.2

# Shown when a spawn produced no living window. The overwhelmingly likely cause is
# that the window's command could not be executed at all, and the overwhelmingly
# likely reason for THAT is PATH: a pane inherits the PATH of the client that created
# it (this server), so a console started without ~/.local/bin on PATH cannot find the
# `claude` that every expert window runs. Systemd user units get no login shell, and
# at boot the user manager's PATH is barer than the one a desktop login later
# imports — so this bites after a reboot and not before.
SPAWN_FAILED_HINT = (
    "the window was created but exited immediately — its command probably could not "
    "be executed. Check that `claude` is on this server's PATH; a systemd user unit "
    "started at boot does not inherit ~/.local/bin unless the unit sets PATH itself."
)

# What every expert control reports when the console is running without the package.
EXPERTS_UNAVAILABLE = (
    "this console is running without Thalamus importable, so the expert controls "
    "(spawn, roster sync, rooms) are unavailable. The tmux bridge is unaffected."
)

# send-keys accepts these named keys (the client sends the left value — it names a
# key, it never hands us a tmux argument).
KEYMAP = {
    "enter": "Enter", "escape": "Escape", "up": "Up", "down": "Down",
    "pageup": "PageUp", "pagedown": "PageDown", "tab": "Tab",
    # Shift+Tab (CSI Z) — Claude Code's permission-mode cycle (normal → auto-accept
    # edits → plan).
    "shift-tab": "BTab",
    # The editing keys a real terminal has, for desktop keystroke passthrough.
    "left": "Left", "right": "Right", "home": "Home", "end": "End",
    "backspace": "BSpace", "delete": "DC", "space": "Space",
}
# Ctrl-<letter>, generated rather than hand-listed.
KEYMAP.update({f"ctrl-{c}": f"C-{c}" for c in "abcdefghijklmnopqrstuvwxyz"})

# Ceiling on the repeat count one `/api/key` request may carry. Matches the client's
# own cap; enforced here because the client is not the only thing that can post.
KEY_REPEAT_CAP = 64

# Slash commands built into the claude CLI itself (not discoverable on disk).
BUILTIN_COMMANDS = [
    ("clear", "Start a fresh session (fires SessionEnd → thalamus extract)"),
    ("compact", "Compact the conversation, keeping a summary"),
    ("model", "Switch model"),
    ("resume", "Resume a previous session"),
    ("status", "Show session status"),
    ("cost", "Show token/cost usage for this session"),
    ("config", "Open settings"),
    ("permissions", "View or update tool permissions"),
    ("agents", "Manage agent definitions"),
    ("mcp", "Show MCP server status"),
    ("memory", "Edit memory files"),
    ("init", "Generate a CLAUDE.md for the repo"),
    ("help", "List available commands"),
]

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/sw.js": ("sw.js", "application/javascript; charset=utf-8"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
}


@dataclass
class Config:
    """Everything about one operator's machine, in one object.

    Nothing here is hardcoded elsewhere in the module: the console is the same
    program on every box, and this is the whole of what differs between them.
    """

    # Both default from `pin` when the package is importable, and to a bare tmux
    # session in the checkout-less case — resolved in __post_init__ rather than here,
    # because a dataclass default is evaluated at class-definition time and would
    # drag the import back to module scope.
    session: str = ""
    project_root: Path | str = ""
    # Directory picker for on-demand spawn. `favorites` are shown first, starred;
    # `scan_roots` are globbed one level deep for git repos.
    favorites: list[Path] = field(default_factory=list)
    scan_roots: list[Path] = field(default_factory=list)
    # systemd --user units the admin sheet may restart. Empty (the default) hides
    # the section entirely — the console never invents units it might not own.
    services: list[str] = field(default_factory=list)
    # Frame-theme definitions (see `frames`). None — the default — means no frame
    # themes: the feature is opt-in because it names image paths on this machine.
    frames_file: Path | None = None

    def __post_init__(self) -> None:
        pin = pin_module()
        if not self.session:
            self.session = pin.ROSTER_SESSION if pin else FALLBACK_SESSION
        if not self.project_root:
            self.project_root = pin.PROJECT_ROOT if pin else Path.cwd()
        self.project_root = Path(self.project_root).expanduser().resolve()
        if not self.favorites:
            self.favorites = [self.project_root]
        if not self.scan_roots:
            self.scan_roots = [self.project_root.parent]
        self.favorites = [Path(p).expanduser() for p in self.favorites]
        self.scan_roots = [Path(p).expanduser() for p in self.scan_roots]
        if self.frames_file:
            self.frames_file = Path(self.frames_file).expanduser()


# ---- Frame themes ----
# A desktop client can render the pane inside a panel drawn in a background image —
# the same look a terminal emulator paints as GPU background art. That art never
# crosses the wire from the emulator, so what is ported is the *data*: a frame file
# holds {name, path, panel fractions} and this server reads it. The file is a
# contract, not a dependency on any particular emulator — anything that emits the
# shape works, and hand-authoring it is supported (docs/frame-themes.md).
#
# There is no default location and no art in this package. `--frames PATH` opts in;
# without it `frames()` is empty, the deskbar says so, and nothing is offered. A
# shipping package has no business reading another application's config directory
# unasked.
_FRAME_RE = re.compile(
    r'\{\s*name\s*=\s*"(?P<name>[^"]+)"\s*,\s*path\s*=\s*"(?P<path>[^"]+)"\s*,\s*'
    r'panel\s*=\s*\{\s*left\s*=\s*(?P<left>[-\d.]+)\s*,\s*right\s*=\s*(?P<right>[-\d.]+)\s*,\s*'
    r'top\s*=\s*(?P<top>[-\d.]+)\s*,\s*bottom\s*=\s*(?P<bottom>[-\d.]+)',
    re.S,
)
IMAGE_TYPES = {".png": "image/png", ".gif": "image/gif", ".jpg": "image/jpeg",
               ".jpeg": "image/jpeg", ".webp": "image/webp"}

# Parsed frames, keyed by (path, mtime) so an edit is picked up without a restart.
_FRAMES_CACHE: dict[str, object] = {"key": None, "frames": []}
_FRAMES_LOCK = threading.Lock()


def frames(cfg: Config) -> list[dict]:
    """Parse the frame file → [{name, path, panel}], cached by mtime.

    Every degradation is silent and total: no file configured, no file on disk, an
    unreadable file, an entry whose image is missing or whose extension isn't an
    image — each just means fewer frames, never an exception and never a broken
    background. A frame theme is decoration; it must not be able to take down the
    surface an operator reaches for when something else is already wrong.
    """
    if not cfg.frames_file:
        return []
    path = str(cfg.frames_file)
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return []
    with _FRAMES_LOCK:
        if _FRAMES_CACHE["key"] == key:
            return _FRAMES_CACHE["frames"]
        try:
            raw = Path(path).read_text()
        except OSError:
            return []
        out = []
        for m in _FRAME_RE.finditer(raw):
            image = m.group("path")
            if os.path.splitext(image)[1].lower() not in IMAGE_TYPES:
                continue
            if not os.path.isfile(image):
                continue
            out.append({
                "name": m.group("name"),
                "path": image,
                "panel": {k: float(m.group(k)) for k in ("left", "right", "top", "bottom")},
            })
        _FRAMES_CACHE["key"] = key
        _FRAMES_CACHE["frames"] = out
        return out


def frame_bytes(cfg: Config, name: str) -> tuple[bytes | None, str | None]:
    """Image bytes + content type for a frame, or (None, None).

    The request contributes a *name*, matched for equality against the parsed list;
    the path served is the one the frame file recorded. No request-supplied string
    ever becomes a path component, so traversal is not expressible even though these
    files live outside the package.

    The trust boundary is therefore the frame file, not the request: whoever writes
    it can name any absolute path with an image extension, and this will serve it.
    That is the same trust already given to `--dir`, and it is why there is no
    default frame file.
    """
    for f in frames(cfg):
        if f["name"] == name:
            try:
                return (Path(f["path"]).read_bytes(),
                        IMAGE_TYPES[os.path.splitext(f["path"])[1].lower()])
            except OSError:
                return None, None
    return None, None


# Window indexes with a restart in flight, and windows being closed (graceful
# /exit → distill → window removed). Exposed in /api/panes so the client can show
# "restarting…" / "distilling…" before the tab changes under the operator.
RECYCLING: set[int] = set()
RECYCLING_LOCK = threading.Lock()
CLOSING: set[int] = set()
CLOSING_LOCK = threading.Lock()


def tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=5)


def _tildify(path: str) -> str:
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path == home or path.startswith(home + "/") else path


def window_path(cfg: Config, idx: int | None = None) -> str:
    """A window's cwd, by index.

    Falls back to the anchor's (the lowest index) when the index is unknown or
    unspecified — windows don't share one cwd, so anything reading "the project"
    has to say which window it means.
    """
    r = tmux("list-windows", "-t", cfg.session, "-F",
             "#{window_index}\t#{pane_current_path}")
    if r.returncode != 0:
        return ""
    paths: dict[int, str] = {}
    for line in r.stdout.splitlines():
        i, _, p = line.partition("\t")
        try:
            paths[int(i)] = p.strip()
        except ValueError:
            continue
    if not paths:
        return ""
    return paths.get(idx) or paths[min(paths)]


def parse_windows(raw: str) -> list[dict]:
    """The tab-separated `list-windows` output, as the JSON the client consumes.

    Split out from the tmux call so the projection the frontend trusts blind is
    testable without a tmux server.

    The anchor — the lowest-indexed window — is the one on-demand spawn must never
    close: it is the console's reference cwd for roster sync and slash-command
    scanning, and it keeps the console from going empty. Lowest index is robust to
    tmux's base-index setting and can't be confused with a second window that
    happens to share the anchor's name, since new windows take higher indexes.
    """
    with RECYCLING_LOCK:
        recycling = set(RECYCLING)
    with CLOSING_LOCK:
        closing = set(CLOSING)
    out = []
    for line in raw.splitlines():
        parts = (line.split("\t") + [""] * 11)[:11]
        idx, name, active, cmd, width, height, dead, cwd, start, pane_id, pane_pid = parts
        try:
            index = int(idx)
        except ValueError:
            continue
        room = re.search(r"THALAMUS_ROOM=(\S+)", start)
        out.append({
            "index": index, "name": name,
            # The read view's join key. A window *index* renumbers when a window
            # closes and is shared by name/scope/cwd with its neighbours, so it
            # identifies a window only for as long as nobody touches the roster;
            # the pane id is stable for the window's life and survives the
            # respawn a recycle performs. pid is the fallback route's only input,
            # for sessions launched before the ledger recorded pane ids.
            "pane_id": pane_id,
            "pane_pid": int(pane_pid) if pane_pid.isdigit() else 0,
            "active": active == "1", "command": cmd,
            "width": int(width or 0), "height": int(height or 0),
            "dead": dead == "1",
            "recycling": index in recycling, "closing": index in closing,
            # Scope alone doesn't identify a session: the same expert can be
            # spawned in several directories. cwd is what tells `homelab in
            # thalamus` from `homelab in some-other-repo`.
            "cwd": cwd, "cwd_label": os.path.basename(cwd.rstrip("/")) or cwd,
            "cwd_short": _tildify(cwd),
            # Which collaboration this window is in, read from the command it was
            # created with. The launcher puts the room in an `env` prefix on that
            # argv (so it survives the respawn a recycle runs), which makes the
            # start command the one field that cannot disagree with the process —
            # the window *name* stays the bare scope.
            "room": room.group(1) if room else "",
        })
    anchor_idx = min((w["index"] for w in out), default=None)
    for w in out:
        w["anchor"] = w["index"] == anchor_idx
    return out


def list_windows(cfg: Config) -> list[dict]:
    r = tmux("list-windows", "-t", cfg.session, "-F",
             "#{window_index}\t#{window_name}\t#{window_active}\t#{pane_current_command}"
             "\t#{window_width}\t#{window_height}\t#{pane_dead}\t#{pane_current_path}"
             "\t#{pane_start_command}\t#{pane_id}\t#{pane_pid}")
    return parse_windows(r.stdout) if r.returncode == 0 else []


def read_skill_meta(skill_dir: str) -> tuple[str, str] | None:
    """Name + description from a SKILL.md frontmatter block. Best-effort."""
    path = os.path.join(skill_dir, "SKILL.md")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(4096)
    except OSError:
        return None
    name = os.path.basename(skill_dir)
    desc = ""
    if head.startswith("---"):
        for line in head.splitlines()[1:]:
            if line.strip() == "---":
                break
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                desc = line.split(":", 1)[1].strip().strip('"')
    return (name, desc)


def list_commands(cfg: Config, idx: int | None = None) -> list[dict]:
    """Slash commands a pinned session understands: CLI built-ins + user skills +
    the project skills of THAT window's cwd. Windows sit in different directories,
    so the hint strip is per-window, not global."""
    cmds = dict(BUILTIN_COMMANDS)
    project = window_path(cfg, idx)
    roots = [os.path.expanduser("~/.claude/skills")]
    if project:
        roots.append(os.path.join(project, ".claude", "skills"))
    for root in roots:
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            meta = read_skill_meta(os.path.join(root, entry))
            if meta:
                cmds[meta[0]] = meta[1]
    return [{"name": n, "description": (d[:140] + "…") if len(d) > 140 else d}
            for n, d in sorted(cmds.items())]


def capture(cfg: Config, idx: int) -> str:
    # -S -1000: for a plain-shell window this pulls scrollback; for a full-screen
    # TUI (claude uses the alternate screen, which has no history) it returns just
    # the current viewport. Either way, no truncation beyond what the program
    # itself keeps on screen.
    r = tmux("capture-pane", "-p", "-S", "-1000", "-t", f"{cfg.session}:{idx}")
    return r.stdout if r.returncode == 0 else ""


# ---- Admin actions ----


def recycle_window(cfg: Config, idx: int) -> None:
    """Restart the pinned claude process in a window — the MCP/hook re-arm.

    The MCP server and hooks arm per *process* (docs/07, lab/001), so wiring
    changes need a fresh claude. Graceful path: `remain-on-exit on` (the window
    survives the exit), Escape + C-u (dismiss any dialog, clear the composer),
    `/exit` (fires SessionEnd → distillation), wait for pane death, then
    `tmux respawn-window` — which re-runs the window's CREATION command
    (`claude --agent thalamus-<scope>`).

    What survives that is the ARGV, not the environment. `-e` on `new-window` sets
    only the initial process env and is never stored in the session env, so a
    respawn re-executes the creation command with those variables gone (measured,
    tmux 3.4; `new-session -e` does survive, because that one populates the session
    env). The pin is unaffected because it rides the argv — `--agent
    thalamus-<scope>` — and `resolve_pin` prefers the picked agent over
    THALAMUS_SCOPE anyway. Anything whose only channel is `-e` is lost here, which
    is why `pin` wraps a room member's command in an `env` prefix rather than
    trusting `-e`.

    If the session won't die within the grace budget, force with
    `respawn-window -k`, which skips distillation. Runs in a background thread.
    """
    target = f"{cfg.session}:{idx}"
    try:
        tmux("set", "-w", "-t", target, "remain-on-exit", "on")
        tmux("send-keys", "-t", target, "Escape")
        time.sleep(0.3)
        tmux("send-keys", "-t", target, "C-u")
        tmux("send-keys", "-t", target, "-l", "/exit")
        tmux("send-keys", "-t", target, "Enter")
        deadline = time.time() + RECYCLE_GRACE_S
        dead = False
        while time.time() < deadline:
            r = tmux("display", "-p", "-t", target, "#{pane_dead}")
            if r.returncode != 0:
                return  # window vanished entirely; roster sync recreates it
            if r.stdout.strip() == "1":
                dead = True
                break
            time.sleep(1)
        tmux("respawn-window", *([] if dead else ["-k"]), "-t", target)
        tmux("set", "-w", "-u", "-t", target, "remain-on-exit")
    finally:
        with RECYCLING_LOCK:
            RECYCLING.discard(idx)


def close_window(cfg: Config, idx: int) -> None:
    """Graceful close: /exit fires SessionEnd → distillation, then claude exits and
    tmux removes the window on its own (no remain-on-exit, unlike recycle). Force
    `kill-window` only if it outlives the grace budget — that path skips
    distillation, the same tradeoff as a recycle timeout."""
    target = f"{cfg.session}:{idx}"
    try:
        tmux("send-keys", "-t", target, "Escape")
        time.sleep(0.3)
        tmux("send-keys", "-t", target, "C-u")
        tmux("send-keys", "-t", target, "-l", "/exit")
        tmux("send-keys", "-t", target, "Enter")
        deadline = time.time() + RECYCLE_GRACE_S
        while time.time() < deadline:
            r = tmux("display", "-p", "-t", target, "#{pane_dead}")
            if r.returncode != 0:
                return  # window already gone: claude exited and tmux closed it
            time.sleep(1)
        tmux("kill-window", "-t", target)  # hung past the grace budget
    finally:
        with CLOSING_LOCK:
            CLOSING.discard(idx)


def _run_capturing(fn, *args, **kwargs) -> tuple[bool, str]:
    """Call a `harness.pin` entry point and hand its console output to the client.

    pin's launchers report by printing and by raising, and the operator is holding
    a phone — both halves have to reach the admin log or a failed spawn reads as
    nothing happening at all.
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 — the message is the product here
        return False, (buf.getvalue() + f"\n{type(e).__name__}: {e}").strip()
    return True, buf.getvalue().strip() or "done."


def roster_sync(cfg: Config) -> tuple[bool, str]:
    """Recreate any missing roster window. Idempotent, so it only opens what isn't
    there (e.g. the anchor after an uncaught exit).

    Explicitly roomless: the anchor is the roster's own window, and leaving the room
    to the environment would put it in whatever room this long-lived server process
    was started in — where it would stop being the roster's anchor at all.
    """
    pin = pin_module()
    if pin is None:
        return False, EXPERTS_UNAVAILABLE
    return _run_capturing(pin.roster, cfg.project_root, session=cfg.session, room="")


def do_spawn(cfg: Config, scope: str, directory: Path, room: str = "") -> tuple[bool, str]:
    """Open one on-demand pinned window. `harness.pin` owns the mechanics: derived
    agent write, detached create, window-size pin, room provisioning.

    `room` is always passed explicitly, never left to the environment: this server
    is a long-lived process, and letting it fall through to `resolve_room()` would
    put every spawn in whatever room the *server* happened to be started in.

    A clean return from `pin.spawn` is NOT evidence that a window exists.
    `tmux new-window` reports success once it has forked, before the command it was
    given has execed, so a command that cannot start at all leaves a window that
    dies instantly and is reaped — while tmux, `pin`, and this function all still
    see success. Measured 2026-08-08: with `claude` off the server's PATH every
    spawn answered `{"ok": true}` and produced nothing, which reads on the phone as
    a button that does nothing. So the window is confirmed alive here, and the spawn
    is reported failed if it is not.
    """
    pin = pin_module()
    if pin is None:
        return False, EXPERTS_UNAVAILABLE
    with SPAWN_LOCK:
        before = {w["index"] for w in list_windows(cfg)}
        ok, output = _run_capturing(pin.spawn, scope, directory,
                                    session=cfg.session, room=room)
        if not ok:
            return False, output

        # Settle before judging: an exec failure is immediate, so a window still
        # alive after this has really started.
        time.sleep(SPAWN_SETTLE_S)
        fresh = [w for w in list_windows(cfg) if w["index"] not in before]
        if any(not w["dead"] for w in fresh):
            return True, output
        return False, "\n\n".join(x for x in (output, SPAWN_FAILED_HINT) if x)


def known_scopes() -> list[str]:
    """Spawnable scopes: `main` plus every expert manifest in the checkout.

    Empty without the package — the client hides the spawn sheet rather than
    offering a picker whose every choice would fail.
    """
    if not has_experts():
        return []
    from thalamus.contract.manifest import available_scopes
    from thalamus.contract.ontology import MAIN_SCOPE
    return [MAIN_SCOPE, *available_scopes()]


def spawn_dirs(cfg: Config) -> tuple[list[dict], set[str]]:
    """The directory picker: favorites first, then git repos one level under each
    scan root. Deduped by resolved path; the label defaults to the basename.

    Returns (dirs, allowed) — `allowed` is the whitelist a spawn request must fall
    inside, so the client can never spawn an arbitrary path.
    """
    seen: set[str] = set()
    dirs: list[dict] = []

    def add(path: Path, favorite: bool) -> None:
        real = os.path.realpath(os.path.expanduser(str(path)))
        if real in seen or not os.path.isdir(real):
            return
        seen.add(real)
        dirs.append({"label": os.path.basename(real) or real,
                     "path": real, "favorite": favorite})

    for fav in cfg.favorites:
        add(fav, True)
    for root in cfg.scan_roots:
        try:
            entries = sorted(os.listdir(root))
        except OSError:
            continue
        for entry in entries:
            p = Path(root) / entry
            if (p / ".git").exists():
                add(p, False)
    return dirs, seen


def service_status(cfg: Config) -> list[dict]:
    out = []
    for unit in cfg.services:
        r = subprocess.run(["systemctl", "--user", "is-active", unit],
                           capture_output=True, text=True)
        out.append({"unit": unit, "state": (r.stdout.strip() or "unknown")})
    return out


def service_restart(unit: str) -> None:
    # systemd-run: the transient unit escapes this service's cgroup, so the restart
    # survives even when the unit being restarted is the one serving this request.
    subprocess.run(["systemd-run", "--user", "--collect", "--",
                    "systemctl", "--user", "restart", unit],
                   capture_output=True, text=True)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def cfg(self) -> Config:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json", cache=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache or
                         ("no-store" if ctype.startswith("application/json") else "no-cache"))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or "{}") if n else {}

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/api/commands":
            # ?index=N scopes project skills to that window's cwd; absent → anchor.
            raw = parse_qs(query).get("index", [""])[0]
            idx = int(raw) if raw.lstrip("-").isdigit() else None
            return self._send(200, {"commands": list_commands(self.cfg, idx)})
        if path == "/api/panes":
            windows = list_windows(self.cfg)
            for w in windows:
                w["lines"] = capture(self.cfg, w["index"])
            # Distillation outlives the window that triggered it, so it rides the
            # poll the client already runs rather than getting a loop of its own.
            return self._send(200, {"session": self.cfg.session, "windows": windows,
                                    "distill": distill_rows()})
        if path == "/api/read":
            # The read view: this window's session as prose and collapsed tool
            # calls, read from the transcript rather than the pane. `since` is the
            # highest seq the client already holds; 0 means a cold open, which is
            # the only case that gets truncated to a tail.
            q = parse_qs(query)
            raw = q.get("index", [""])[0]
            if not raw.lstrip("-").isdigit():
                return self._send(400, {"error": "index required"})
            since = q.get("since", ["0"])[0]
            since = int(since) if since.isdigit() else 0
            tr = transcript_module()
            if tr is None:
                return self._send(200, {"available": False, "reason": "no-package"})
            window, feed, reason = read_feed(self.cfg, int(raw))
            if window is None:
                return self._send(404, {"error": "no such window"})
            if feed is None:
                # `unresolved` is a refusal: resolution declines to guess when a
                # pre-ledger session shares a scope and cwd with another window,
                # and it fixes itself on recycle. `pending` is not a failure at
                # all — the session is identified and has not written its first
                # turn, which is where every freshly spawned window starts.
                return self._send(200, {"available": False, "reason": reason})
            with READ_LOCK:
                return self._send(200, {
                    "available": True,
                    "session_id": feed.session_id,
                    "seq": feed.seq,
                    "items": tr.wire(feed.since(since, tr.COLD_OPEN_ITEMS if not since else 0)),
                    "mode": feed.mode,
                    "permission_mode": feed.permission_mode,
                    "agent": feed.agent,
                })
        if path == "/api/read/body":
            # A tool result, fetched only when the reader expands that call.
            q = parse_qs(query)
            raw = q.get("index", [""])[0]
            item = q.get("item", [""])[0]
            if not raw.lstrip("-").isdigit() or not item.isdigit():
                return self._send(400, {"error": "index and item required"})
            _, feed, reason = read_feed(self.cfg, int(raw))
            if feed is None:
                return self._send(404, {"error": reason or "unresolved"})
            with READ_LOCK:
                body = feed.body(int(item))
            if body is None:
                return self._send(404, {"error": "no such item"})
            return self._send(200, {"body": body})
        if path == "/api/say":
            # Tap-to-listen: this window's latest turn, rewritten for the ear and
            # synthesised by the voice service. Audio is returned inline so the
            # client can set an <audio> src and play it in the same click — a
            # phone will not autoplay anything that arrives after an await.
            q = parse_qs(query)
            raw = q.get("index", [""])[0]
            if not raw.lstrip("-").isdigit():
                return self._send(400, {"error": "index required"})
            _, feed, reason = read_feed(self.cfg, int(raw))
            if feed is None:
                return self._send(404, {"error": reason or "unresolved"})
            with READ_LOCK:
                source = feed.latest_turn_prose()
            if not source.strip():
                return self._send(404, {"error": "nothing to say yet"})
            audio, err = synthesise_update(source)
            if err:
                return self._send(502, {"error": err})
            return self._send(200, audio, "audio/wav", cache="no-store")
        if path == "/api/admin":
            with RECYCLING_LOCK:
                recycling = sorted(RECYCLING)
            return self._send(200, {"services": service_status(self.cfg),
                                    "recycling": recycling})
        if path == "/api/spawn-options":
            pin = pin_module()
            dirs, _ = spawn_dirs(self.cfg)
            return self._send(200, {"scopes": known_scopes(), "dirs": dirs,
                                    "rooms": pin.rooms() if pin else [],
                                    "experts": pin is not None})
        if path == "/api/frames":
            # Absolute paths stay server-side; the client addresses a frame by name.
            return self._send(200, {"frames": [{"name": f["name"], "panel": f["panel"]}
                                               for f in frames(self.cfg)]})
        if path.startswith("/frame/"):
            blob, ctype = frame_bytes(self.cfg, unquote(path[len("/frame/"):]))
            if blob is None:
                return self._send(404, {"error": "unknown frame"})
            # Multi-MB art, addressed by name; let the browser keep it rather than
            # refetching on every theme toggle.
            return self._send(200, blob, ctype, cache="public, max-age=86400")
        if path in STATIC:
            fname, ctype = STATIC[path]
            fpath = STATIC_DIR / fname
            if fpath.exists():
                return self._send(200, fpath.read_bytes(), ctype)
            return self._send(404, {"error": "not found"})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            data = self._body()
        except Exception:
            return self._send(400, {"error": "bad json"})

        if path == "/api/roster":
            ok, output = roster_sync(self.cfg)
            return self._send(200 if ok else 500, {"ok": ok, "output": output})

        if path == "/api/service":
            unit = data.get("unit")
            if unit not in self.cfg.services:
                return self._send(400, {"error": "unknown unit"})
            service_restart(unit)
            return self._send(200, {"ok": True})

        if path == "/api/distill-dismiss":
            # Clears one error row. Not a window operation — the window whose
            # session this was is long gone — so it returns before the handler
            # below starts insisting on a live window index.
            session = data.get("session")
            watch = distill_watch()
            if watch is None:
                return self._send(503, {"error": "no distillation watcher on this "
                                                 "console — see /api/panes"})
            if not isinstance(session, str) or not re.fullmatch(r"[0-9a-f]{8}", session):
                return self._send(400, {"error": "session must be an 8-hex-digit id"})
            return self._send(200, {"ok": watch.dismiss(session)})

        if path == "/api/spawn":
            scope = data.get("scope")
            directory = data.get("dir")
            room = data.get("room") or ""
            pin = pin_module()
            if pin is None:
                return self._send(503, {"error": EXPERTS_UNAVAILABLE})
            if scope not in known_scopes():
                return self._send(400, {"error": "unknown scope"})
            # Validated rather than matched against the existing list: naming a new
            # room IS how one is created, and `pin.ensure_room` builds it. The
            # charset check is the security-relevant half — the name reaches a path
            # and the guard's roommate pattern.
            if room and not pin.valid_room(room):
                return self._send(400, {"error": "invalid room name"})
            # The directory must be one the picker offered — recomputed here, never
            # trusted from the request.
            _, allowed = spawn_dirs(self.cfg)
            if not isinstance(directory, str) or os.path.realpath(directory) not in allowed:
                return self._send(400, {"error": "directory not in the allowed list"})
            ok, output = do_spawn(self.cfg, scope, Path(os.path.realpath(directory)), room)
            return self._send(200 if ok else 500, {"ok": ok, "output": output})

        windows = list_windows(self.cfg)
        idx = data.get("index")
        if not isinstance(idx, int) or not any(w["index"] == idx for w in windows):
            return self._send(400, {"error": "unknown window"})
        target = f"{self.cfg.session}:{idx}"

        if path == "/api/recycle":
            with RECYCLING_LOCK:
                already = idx in RECYCLING
                RECYCLING.add(idx)
            if not already:
                threading.Thread(target=recycle_window, args=(self.cfg, idx),
                                 daemon=True).start()
            return self._send(200, {"ok": True, "already": already})

        if path == "/api/close":
            win = next((w for w in windows if w["index"] == idx), None)
            if win and win.get("anchor"):
                return self._send(400, {"error": "the anchor window can't be closed"})
            with CLOSING_LOCK:
                already = idx in CLOSING
                CLOSING.add(idx)
            if not already:
                threading.Thread(target=close_window, args=(self.cfg, idx),
                                 daemon=True).start()
            return self._send(200, {"ok": True, "already": already})

        if path == "/api/send":
            text = data.get("text", "")
            if not isinstance(text, str):
                return self._send(400, {"error": "text must be a string"})
            if text:
                tmux("send-keys", "-t", target, "-l", text)
            if data.get("submit", True):
                tmux("send-keys", "-t", target, "Enter")
            return self._send(200, {"ok": True})

        if path == "/api/key":
            key = KEYMAP.get(data.get("key", ""))
            if not key:
                return self._send(400, {"error": "unknown key"})
            # A held key arrives as one request carrying its repeat count, not as one
            # request per repeat — `tmux send-keys -N` replays it without paying for
            # a process launch each time. Clamped because the count is client-supplied
            # and this server has no authentication: nothing reachable here should be
            # able to ask for an unbounded amount of work.
            try:
                count = int(data.get("count", 1))
            except (TypeError, ValueError):
                count = 1
            count = max(1, min(count, KEY_REPEAT_CAP))
            if count > 1:
                tmux("send-keys", "-N", str(count), "-t", target, key)
            else:
                tmux("send-keys", "-t", target, key)
            return self._send(200, {"ok": True})

        return self._send(404, {"error": "not found"})


def serve(cfg: Config, host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.config = cfg  # type: ignore[attr-defined]
    print(f"Control plane on http://{host}:{port}  (tmux session `{cfg.session}`)")
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("  ! bound off-loopback and this server has NO authentication — "
              "anything that can reach it can drive your sessions.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()
