"""The control plane — a tiny tmux bridge, so the roster is drivable from a phone.

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
  tunnel). See docs/control-plane.md.

Deliberately stdlib-only, unlike the FastAPI surfaces in `pulse/` and `plane/`:
one of its jobs is restarting the systemd unit that hosts it, so the fewer moving
parts between a tap and a tmux call, the better.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from thalamus.contract.manifest import available_scopes
from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.harness import pin

STATIC_DIR = Path(__file__).with_name("static")
DEFAULT_PORT = 8378

# Graceful-exit budget before force-respawning a window. SessionEnd runs
# `thalamus extract` (distillation), which can take a while; killing early loses it.
RECYCLE_GRACE_S = 240

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

    session: str = pin.ROSTER_SESSION
    project_root: Path = pin.PROJECT_ROOT
    # Directory picker for on-demand spawn. `favorites` are shown first, starred;
    # `scan_roots` are globbed one level deep for git repos.
    favorites: list[Path] = field(default_factory=list)
    scan_roots: list[Path] = field(default_factory=list)
    # systemd --user units the admin sheet may restart. Empty (the default) hides
    # the section entirely — the console never invents units it might not own.
    services: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.project_root = Path(self.project_root).expanduser().resolve()
        if not self.favorites:
            self.favorites = [self.project_root]
        if not self.scan_roots:
            self.scan_roots = [self.project_root.parent]
        self.favorites = [Path(p).expanduser() for p in self.favorites]
        self.scan_roots = [Path(p).expanduser() for p in self.scan_roots]


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
    scanning, and it keeps the plane from going empty. Lowest index is robust to
    tmux's base-index setting and can't be confused with a second window that
    happens to share the anchor's name, since new windows take higher indexes.
    """
    with RECYCLING_LOCK:
        recycling = set(RECYCLING)
    with CLOSING_LOCK:
        closing = set(CLOSING)
    out = []
    for line in raw.splitlines():
        parts = (line.split("\t") + [""] * 9)[:9]
        idx, name, active, cmd, width, height, dead, cwd, start = parts
        try:
            index = int(idx)
        except ValueError:
            continue
        room = re.search(r"THALAMUS_ROOM=(\S+)", start)
        out.append({
            "index": index, "name": name,
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
             "\t#{pane_start_command}")
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
    (`claude --agent thalamus-<scope>`) with its env (THALAMUS_SCOPE) intact. If
    the session won't die within the grace budget, force with `respawn-window -k`,
    which skips distillation. Runs in a background thread.
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
    return _run_capturing(pin.roster, cfg.project_root, session=cfg.session, room="")


def do_spawn(cfg: Config, scope: str, directory: Path, room: str = "") -> tuple[bool, str]:
    """Open one on-demand pinned window. `harness.pin` owns the mechanics: derived
    agent write, detached create, window-size pin, room provisioning.

    `room` is always passed explicitly, never left to the environment: this server
    is a long-lived process, and letting it fall through to `resolve_room()` would
    put every spawn in whatever room the *server* happened to be started in.
    """
    return _run_capturing(pin.spawn, scope, directory, session=cfg.session, room=room)


def known_scopes() -> list[str]:
    """Spawnable scopes: `main` plus every expert manifest in the checkout."""
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
            return self._send(200, {"session": self.cfg.session, "windows": windows})
        if path == "/api/admin":
            with RECYCLING_LOCK:
                recycling = sorted(RECYCLING)
            return self._send(200, {"services": service_status(self.cfg),
                                    "recycling": recycling})
        if path == "/api/spawn-options":
            dirs, _ = spawn_dirs(self.cfg)
            return self._send(200, {"scopes": known_scopes(), "dirs": dirs,
                                    "rooms": pin.rooms()})
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

        if path == "/api/spawn":
            scope = data.get("scope")
            directory = data.get("dir")
            room = data.get("room") or ""
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
