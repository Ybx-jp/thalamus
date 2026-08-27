"""The console — a tiny tmux bridge, so the roster is drivable from a phone.

A pinned session is an OS process in a tmux window ("the process is the
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
  tunnel).

The bridge itself is stdlib-only, unlike the FastAPI surface in `pulse/`: one of
its jobs is restarting the service unit that hosts it, so the
fewer moving parts between a tap and a tmux call, the better. The expert layer —
the scope list, spawn, roster sync — is the one part that needs the rest of the
package, so those imports are deferred to the call that uses them. Run this
module with a bare `python3` and you get the tmux bridge and the whole client;
the expert controls report themselves unavailable instead of failing to import.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlsplit

# Imported at module scope, unlike this module's other Thalamus imports: these two
# names are re-exported below, and `panes` reaches nothing but the standard library.
from thalamus.harness import panes
from thalamus.harness.tmux import argv as tmux_argv
from thalamus.harness.tmux import socket_name as tmux_socket

STATIC_DIR = Path(__file__).with_name("static")
DEFAULT_PORT = 8378

# When this process started. The console is normally an editable install served out
# of a checkout, which puts two clocks between a commit and the phone: `static/` is
# read from disk per request and tracks the working tree instantly, while the Python
# is loaded once and tracks it only as far as this timestamp. `build_info` below
# reads both so the surface can say which one is behind.
STARTED_AT = time.time()


class PortInUse(RuntimeError):
    """The console's port is held by something else.

    Its own class so the CLI can print the sentence and exit rather than showing a
    traceback for the one environment difference that is not a defect: an operator
    who already has a console running, which on this port is the usual reason.
    """

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


_dispatch_cache: object = _PIN_UNSET


def dispatch_module():
    """`thalamus.harness.dispatch`, or None when the package is absent.

    Deferred for the same reason as the expert layer. Kept as its own accessor rather
    than reached through `pin_module()` because the console is a *thin client* over
    the verb: every refusal, the whole-fan-out pre-flight and the row writing live in
    `harness/dispatch.py`, and a second implementation here — even a small one — would
    be a second policy about when it is safe to type into somebody's session.
    """
    global _dispatch_cache
    if _dispatch_cache is _PIN_UNSET:
        try:
            from thalamus.harness import dispatch
        except Exception:  # noqa: BLE001 — any import failure means "not available"
            _dispatch_cache = None
        else:
            _dispatch_cache = dispatch
    return _dispatch_cache


_read_cache: object = _PIN_UNSET


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


# One ledger index and one feed store for the process, both stateful across polls
# so a poll reads only the bytes appended since the last one. ThreadingHTTPServer
# serves requests concurrently and a phone plus a desktop on the same window is the
# normal case, so every touch of that shared state is serialized.
READ_LOCK = threading.Lock()
_LEDGER = None
_FEEDS = None


def _ledger_epoch(ts: str) -> float | None:
    """The ledger's `ts` — ISO-8601 UTC, second resolution — as epoch seconds.

    The ledger keeps the ISO string: sixteen readers parse that file and changing
    its format on them buys nothing. The wire speaks one time idiom, so the
    conversion happens at the boundary. An unparseable stamp is None, not now():
    a fabricated start time reads as a fact and would be one more absence drawn as
    a value.
    """
    if not ts:
        return None
    try:
        parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc).timestamp()


def attach_ledger_facts(windows: list[dict]) -> None:
    """Join each window to its pin-ledger row, in place.

    tmux knows a pane's cwd and nothing else about the agent inside it — not the
    repository that cwd sits in, not the project name that repository answers to,
    not when the session started. All three are launch facts, and the pin ledger is
    the only place they are recorded, which is why a console that reads tmux alone
    renders three windows named `main` in one checkout byte-identically.

    Absent is served as absent. A window whose row predates these fields gets `""`
    and None rather than a value inferred from the cwd — inferring from the cwd is
    exactly what these fields exist to stop doing, and a guess here would be
    indistinguishable on the wire from a recorded fact.
    """
    tr = transcript_module()
    if tr is None:
        for w in windows:
            w.update(session_id="", project="", repo_root="", started=None)
        return
    global _LEDGER, _FEEDS
    with READ_LOCK:
        if _LEDGER is None:
            _LEDGER, _FEEDS = tr.LedgerIndex(), tr.FeedStore()
        _LEDGER.refresh()
        for w in windows:
            row = _LEDGER.by_pane(w.get("pane_id", ""))
            if row is None and w.get("pane_pid"):
                # Same fallback the read view uses, and it refuses rather than
                # guesses when two windows share a scope and a directory.
                row = _LEDGER.legacy_match(w.get("name", ""), w.get("cwd", ""),
                                           tr.pane_started_at(w["pane_pid"]))
            row = row or {}
            w["session_id"] = row.get("session_id") or ""
            w["project"] = row.get("project") or ""
            w["repo_root"] = row.get("repo_root") or ""
            w["started"] = _ledger_epoch(row.get("ts") or "")


def _pinned_session(cfg: Config, idx: int) -> dict:
    """The identity of the session in a window, from the pin ledger.

    Read *before* the destructive act, while the window is still alive: afterwards
    the pane is gone and there is nothing left to join against. Everything a
    killed-window record needs to name itself, because that record outlives its
    window by construction — it is written as the window is destroyed.
    """
    window = next((w for w in list_windows(cfg) if w["index"] == idx), None)
    if window is None:
        return {}
    rows = [dict(window)]
    attach_ledger_facts(rows)
    return {"session": rows[0]["session_id"], "scope": window.get("name", ""),
            "cwd": window.get("cwd", ""), "project": rows[0]["project"],
            "repo_root": rows[0]["repo_root"]}


def _record_forced_kill(who: dict, op: str) -> None:
    """Say that this window died without distilling, because nothing else can.

    SessionEnd is what launches `thalamus extract`, and both force paths skip it —
    so no log is created, and the log scan that reports distillation state has
    nothing to find. The console is the only witness to a distillation that never
    started, and it is the only witness because it is the thing that prevented it.
    """
    watch = distill_watch()
    if watch is None or not who:
        return
    try:
        from .distill import record_kill
        record_kill(who["session"], who["scope"], who["cwd"], op,
                    path=watch.kills, project=who["project"],
                    repo_root=who["repo_root"])
    except Exception:  # noqa: BLE001 — never let bookkeeping break a teardown
        pass


#: session_id -> its rollout path, so the console's poll does not re-glob the codex
#: sessions tree once per codex row per refresh. A rollout's path is fixed for the
#: life of the session, so a hit never goes stale; a miss is not cached, because the
#: file a session has not written yet is one a later poll must be able to find.
_CODEX_ROLLOUTS: dict[str, Path] = {}


def _attach_codex_activity(windows: list[dict]) -> None:
    """Fill the liveness half of every codex row from its rollout, in place.

    Codex is the harness that publishes no session descriptor, which is why these rows
    read `not in reach` on a console that only knows how to look for one. Its rollout
    carries the same fact in a different place: `task_started` and `task_complete` are
    written by codex from inside its own event loop, one pair per turn, so the last
    boundary in the file is what the session is doing.

    Only `activity` is filled. `blocked` stays None — see `attach_blocked` on why that
    is *not known* rather than *not blocked*, and on why the record's own shape keeps
    the gap from reading as reassurance.

    A row is left untouched — and so keeps `observed=False` — whenever the rollout does
    not answer: no package to read it with, no session id, no file yet (codex's
    SessionStart fires at the first submitted turn, so a spawned-but-unused window has
    written nothing), or a tail holding no turn boundary. Absence is never rendered as
    rest.
    """
    codex_rows = [w for w in windows if w.get("harness") == "codex"]
    if not codex_rows:
        return
    try:
        from thalamus.harness import codex_transcripts
    except ImportError:
        return  # no package around this console: the rows stay unobserved
    for w in codex_rows:
        session_id = w.get("session_id") or ""
        if not session_id:
            continue
        path = _CODEX_ROLLOUTS.get(session_id)
        if path is None or not path.is_file():
            try:
                path = codex_transcripts.rollout_path(session_id)
            except OSError:
                path = None
            if path is None:
                continue
            _CODEX_ROLLOUTS[session_id] = path
        try:
            status, since = codex_transcripts.live_status(path)
        except OSError:
            continue
        if not status:
            continue  # the tail reached no boundary: we could not find out
        w["observed"] = True
        w["activity"] = status
        if status == codex_transcripts.CODEX_BUSY and since is not None:
            # The same rule the descriptor path follows: only `busy` carries a clock,
            # because an elapsed on every idle row is motion on most rows at once.
            w["activity_since"] = since.timestamp()


def _live_descriptors(dispatch, room: str, harness: str) -> dict:
    """Session descriptors visible from the config dir a window's own session runs in.

    Session descriptors are partitioned by config dir, and a room member writes its
    own into the room's. Reading only this process's dir is what made every row in a
    room render `not in reach` — measured 2026-08-25 on a two-member room whose
    sessions were publishing healthy `busy`/`idle` status the whole time, one
    directory over.

    Widening the console's read is **not** widening the boundary the partition
    exists for. That boundary is agent-to-agent: `quick.live_sessions` defaults to the
    caller's own dir so a session inside a room discovers its room-mates and nobody
    else, and the fork/target path (`quick.py`) still gets exactly that. The console
    is not a session — it already spawns into rooms, lists them, and prints which room
    a window is in — and `dispatch` already reads a room's dir from outside to address
    one. What the operator may see of his own sessions is a different axis from what a
    room member may reach.

    Per-call rather than cached: a descriptor's status is the thing being read, and
    the room set changes under a long-lived server. `live_sessions` is a directory
    glob over a handful of small files, and the poll already globs more than this.
    """
    if not room:
        return _descriptors_at(dispatch, None)
    pin = pin_module()
    if pin is None or not pin.valid_room(room):
        # An unvalidated name reaches a path join. Falling back to the host dir keeps
        # the row honestly unobserved rather than trusting the name.
        return _descriptors_at(dispatch, None)
    return _descriptors_at(dispatch, pin.room_config_dir(room, harness))


def _descriptors_at(dispatch, config_dir) -> dict:
    try:
        return {s.session_id: s for s in dispatch.quick.live_sessions(config_dir)}
    except Exception:  # noqa: BLE001 — an unreadable sessions dir is "we cannot know"
        return {}


def attach_blocked(windows: list[dict]) -> None:
    """Mark the windows whose session is stopped waiting on a human, in place.

    A session sitting at a permission prompt is the one state the system cannot
    leave without the operator, and it is the state with no cost ceiling: two
    literature threads record windows dispatched 2026-08-01 that stopped at a prompt
    and were still stopped thirteen days later. Measured on this box 2026-08-15, a
    live session had been blocked for 6 h 38 m with nothing on any console surface
    saying so.

    The status is *read*, never derived here. `dispatch` owns what the words mean —
    the constants are imported rather than spelled — and the harness's own session
    descriptor owns the value. This function joins the two to a window and reduces
    them to a tri-state, two stamps and one display word, which is deliberately all
    that reaches the wire: the client is told *that* a session needs a human, and
    handed the word to draw for one that does not, never the status field it would
    need in order to decide either for itself. One owner computes, the client renders.

    `activity` is that word — `idle`, `busy`, or empty when the status is neither. It
    travels under a display name rather than as `status` because the row's whole job
    is to print it: a field named for the policy value invites a second reading of
    the thing this function exists to reduce. `activity_since` carries the transition
    stamp only where a clock earns its place, so *which* states are worth timing is
    decided here and the client draws the elapsed exactly when the stamp is present.

    Whether the session could be observed at all is **one fact per row**, `observed`,
    and it is the field a reader keys on. Session descriptors are partitioned by
    config dir: a session launched into a collaboration writes its descriptor under
    that collaboration's dir. Each row is therefore looked up in **its own** session's
    config dir, resolved from the `room` the window already carries
    (`_live_descriptors`), not in this process's. Reading only this process's dir made
    every row in a room unobservable, which cost the `needs you` indicator on exactly
    the sessions least watched — measured 2026-08-15 as 7 of 9 windows resolving from
    the host dir and the complementary 2 of 9 only from inside the collaboration, and
    again 2026-08-25 on a two-member room publishing healthy status one directory over
    while the console drew `not in reach` on both.

    Reporting an unobserved window as "not stuck" would state a fact on exactly the
    evidence that says nothing at all — the failure this row exists to remove,
    reintroduced by the indicator meant to remove it. So `observed=False` disclaims
    the whole liveness half of the row rather than one pill inside it: nothing here
    knows anything about that session's state, and the row's confident half is what
    the pin ledger supplies (name, project, `started`).

    `activity` is empty on every unobserved row, and `blocked` is None there too.
    Observability travels as one fact about the row rather than as an absence repeated
    across each field: they are one lookup written from a single branch and cannot
    disagree, so `observed` is the one to branch on. A client that had to reconcile
    them would be a client computing state.

    **`blocked` is None on an observed codex row, and that is not a contradiction.**
    The two halves come from different evidence and only Claude Code publishes both.
    Its descriptor carries `status`, which its runtime writes from inside its own event
    loop and which names `waiting` directly. Codex publishes no descriptor at all, so a
    codex row's activity is read from the turn boundaries in its own rollout
    (`codex_transcripts.live_status`) — a first-party record of when a turn began and
    ended, and silent on whether an approval prompt is up inside one. So `blocked` on
    such a row means *not known*, never *not blocked*, and only a truthy `blocked` is
    ever a claim.

    What keeps that gap from being a false reassurance is the shape of the record
    rather than a promise: an approval prompt can only be up *mid-turn*, and mid-turn
    is exactly when the last boundary is a `task_started` — so a codex session holding
    one renders `busy`, and the elapsed beside it is the finding. It cannot render
    `idle`, because `idle` requires a `task_complete` that a held prompt has not
    reached. The row understates a stuck session as a long-running one; it never
    reports it as resting.
    """
    for w in windows:
        w["observed"] = False
        w["blocked"] = None
        w["blocked_since"] = None
        w["activity"] = ""
        w["activity_since"] = None
    dispatch = dispatch_module()
    if dispatch is None:
        return
    _attach_codex_activity(windows)
    for w in windows:
        if w["observed"]:
            continue  # already answered from the rollout: codex writes no descriptor
        session = _live_descriptors(dispatch, w.get("room") or "",
                                    w.get("harness") or "claude").get(
            w.get("session_id") or "")
        if session is None:
            continue  # no descriptor in reach: the row stays unobserved
        w["observed"] = True
        w["blocked"] = session.status == dispatch.WAITING_STATUS
        if w["blocked"]:
            # Milliseconds on the descriptor, epoch seconds on the wire — the same
            # idiom `started` and the lifecycle stamps already speak.
            w["blocked_since"] = (session.status_updated_at / 1000) or None
        elif session.status in dispatch.DELIVERABLE_STATUSES:
            w["activity"] = session.status
            if session.status == dispatch.BUSY_STATUS:
                # Only `busy` is worth a clock. `busy 14:32` on a session you thought
                # had finished is a finding; an elapsed on every idle row is motion on
                # most rows at once, which costs the loud channel what it is worth.
                w["activity_since"] = (session.status_updated_at / 1000) or None


# The vocabulary of `permission_mode_read`, the read-status field `/api/read`
# stamps on every response. `ok` means the console read this session; the other
# three name which read failed, and are exactly the failures `read_feed` reports.
#
# It is a separate field from `permission_mode` because "this session has written
# no permission-mode record" and "we could not read this session" are different
# facts. `permission_mode` is `""` for the first and absent for the second, and a
# client with only that field would have to read absence as a mode to tell them
# apart — the one thing it must never do.
PERMISSION_MODE_READ = ("ok", "unresolved", "pending", "no-package")


def read_feed(cfg: Config, idx: int):
    """(window, feed, reason) for a roster window.

    `reason` is None when a feed came back, and otherwise names which failure it
    was: `unresolved` (cannot tell which session is here), `pending` (we know
    exactly which session, it has not written its first turn), or `no-package`
    (this console has no transcript parser at all). They read very differently to
    whoever is holding the phone, and each is a value of `PERMISSION_MODE_READ`.
    """
    tr = transcript_module()
    window = next((w for w in list_windows(cfg) if w["index"] == idx), None)
    if tr is None or window is None:
        return window, None, "no-package" if window is not None else "unresolved"
    global _LEDGER, _FEEDS
    with READ_LOCK:
        if _LEDGER is None or _FEEDS is None:
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

# On-demand spawn is serialized. Two spawns arriving while the roster session does
# not exist would both find it missing and both try to create it; serializing is
# cheaper than reasoning about which one won.
SPAWN_LOCK = threading.Lock()

# Appended when a spawned window died without saying anything the operator can act
# on. The overwhelmingly likely cause is that the window's command could not be
# executed at all, and the overwhelmingly likely reason for THAT is PATH: a pane
# inherits the PATH of the client that created it (this server), so a console started
# without ~/.local/bin on PATH cannot find the CLI every expert window runs — and a
# command that never execs prints nothing to quote. Systemd user units get no login
# shell, and at boot the user manager's PATH is barer than the one a desktop login
# later imports — so this bites after a reboot and not before.
SPAWN_FAILED_HINT = (
    "if nothing above says why, the likeliest cause is that the command could not be "
    "executed at all. Check that the harness binary is on this server's PATH; a "
    "systemd user unit started at boot does not inherit ~/.local/bin unless the unit "
    "sets PATH itself."
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
    # IBM Plex, subset to what this surface draws. Self-hosted rather than fetched
    # from a CDN: the client must work with no route off the tailnet, and the service
    # worker caches the shell for exactly that case.
    "/plex-mono-400.woff2": ("plex-mono-400.woff2", "font/woff2"),
    "/plex-mono-600.woff2": ("plex-mono-600.woff2", "font/woff2"),
    "/plex-sans-400.woff2": ("plex-sans-400.woff2", "font/woff2"),
    "/plex-sans-600.woff2": ("plex-sans-600.woff2", "font/woff2"),
    # The OFL requires the licence travel with the fonts.
    "/PLEX-OFL.txt": ("PLEX-OFL.txt", "text/plain; charset=utf-8"),
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
    # How often the console fetches the checkout's remote, in seconds. Nothing about
    # the working tree changes — a fetch moves remote-tracking refs only — but it is
    # what makes "N commits behind" a fact rather than a report on whenever somebody
    # last happened to fetch. 0 disables the thread and the count then means only
    # that much.
    fetch_interval_s: float = 600.0
    # Origins accepted on a write besides the request's own `Host` (see
    # `same_origin`). Empty — the default — is right for every deployment in
    # docs/console.md, all of which reach the console at the host the browser
    # addressed. It exists for the proxy that rewrites `Host` to the upstream, where
    # same-origin is true of the page and unprovable from the headers.
    allowed_origins: list[str] = field(default_factory=list)

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
# shape works, and hand-authoring it is supported.
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
_FRAMES_CACHE: tuple[tuple[str, float] | None, list[dict]] = (None, [])
_FRAMES_LOCK = threading.Lock()


def frames(cfg: Config) -> list[dict]:
    """Parse the frame file → [{name, path, panel}], cached by mtime.

    Every degradation is silent and total: no file configured, no file on disk, an
    unreadable file, an entry whose image is missing or whose extension isn't an
    image — each just means fewer frames, never an exception and never a broken
    background. A frame theme is decoration; it must not be able to take down the
    surface an operator reaches for when something else is already wrong.
    """
    global _FRAMES_CACHE
    if not cfg.frames_file:
        return []
    path = str(cfg.frames_file)
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return []
    with _FRAMES_LOCK:
        cached_key, cached_frames = _FRAMES_CACHE
        if cached_key == key:
            return cached_frames
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
            # `[-\d.]+` matches things float() will not take — `1.2.3`, a bare `-`,
            # `..` — so a typo'd fraction would raise out of here, out of do_GET
            # (which has no blanket handler) and 500 the endpoint. That is exactly
            # the "never an exception" this function's docstring promises, so a
            # malformed entry is dropped like a missing image is.
            try:
                panel = {k: float(m.group(k)) for k in ("left", "right", "top", "bottom")}
            except ValueError:
                continue
            out.append({
                "name": m.group("name"),
                "path": image,
                "panel": panel,
            })
        _FRAMES_CACHE = (key, out)
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
# /exit → distill → window removed), each mapped to the epoch second the operation
# started. Exposed in /api/panes so the client can show "restarting…" /
# "distilling…" before the tab changes under the operator.
#
# The stamp rather than bare membership, for two reasons. The RECYCLE_GRACE_S
# deadline lives inside the worker thread, so without it the client renders a word
# with no duration while the worker silently races a clock the operator cannot see.
# And the entry is dropped in the worker's `finally`, so a worker that dies takes
# the row's exit with it: bare membership leaves "restarting…" on screen forever
# with nothing to contradict it, while a stamp makes a leaked flag self-reporting.
#
# A float is truthy for every value time.time() returns, so a reader that only asks
# whether an operation is in flight keeps working unchanged.
RECYCLING: dict[int, float] = {}
RECYCLING_LOCK = threading.Lock()
CLOSING: dict[int, float] = {}
CLOSING_LOCK = threading.Lock()


def tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(tmux_argv(*args), capture_output=True, text=True, timeout=5)


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


def parse_windows(raw: str, expected: dict[str, tuple[str, ...]] | None = None) -> list[dict]:
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
        recycling = dict(RECYCLING)
    with CLOSING_LOCK:
        closing = dict(CLOSING)
    out = []
    indexes: list[int] = []
    for line in raw.splitlines():
        parts = (line.split("\t") + [""] * 11)[:11]
        idx, name, active, cmd, width, height, dead, cwd, start, pane_id, pane_pid = parts
        try:
            index = int(idx)
        except ValueError:
            continue
        indexes.append(index)
        room = re.search(r"THALAMUS_ROOM=(\S+)", start)
        harness = window_harness(start)
        want = (expected or {}).get(harness)
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
            # The epoch second the operation started, or None. Truthy exactly when
            # the operation is in flight, so a reader asking only that is unaffected;
            # a reader that wants the duration subtracts. Nothing here computes an
            # elapsed number or a fraction: the deadline is knowable but the finish
            # is not, and a progress figure nobody can compute must not be drawn.
            "recycling": recycling.get(index), "closing": closing.get(index),
            # Scope alone doesn't identify a session: the same expert can be
            # spawned in several directories. cwd is what tells `architect in
            # thalamus` from `architect in some-other-repo`.
            "cwd": cwd, "cwd_label": os.path.basename(cwd.rstrip("/")) or cwd,
            "cwd_short": _tildify(cwd),
            # Which collaboration this window is in, read from the command it was
            # created with. The launcher puts the room in an `env` prefix on that
            # argv (so it survives the respawn a recycle runs), which makes the
            # start command the one field that cannot disagree with the process —
            # the window *name* stays the bare scope.
            "room": room.group(1) if room else "",
            # Which harness this window runs, from the same start command and for the
            # same reason: `pane_current_command` shows whatever is in the foreground,
            # so a window shelling out reads as `bash` for as long as that lasts.
            "harness": harness,
            # A launch flag rides the argv, and the argv is fixed when the window is
            # created — `respawn-window` re-executes the *creation* command. So a posture
            # change cannot reach a running session, and without this the divergence is
            # silent. The restart button already beside it is the fix.
            "policy_stale": bool(
                harness and want is not None and not _contains_run(start.split(), want)
            ),
        })
    anchor_idx = min(indexes, default=None)
    for w in out:
        w["anchor"] = w["index"] == anchor_idx
    return out


def list_windows(cfg: Config) -> list[dict]:
    r = tmux("list-windows", "-t", cfg.session, "-F",
             "#{window_index}\t#{window_name}\t#{window_active}\t#{pane_current_command}"
             "\t#{window_width}\t#{window_height}\t#{pane_dead}\t#{pane_current_path}"
             "\t#{pane_start_command}\t#{pane_id}\t#{pane_pid}")
    return parse_windows(r.stdout, policy_expected()) if r.returncode == 0 else []


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


def screen_rev(text: str) -> str:
    """An opaque change token for one window's screen.

    The only promise is the one the rail's pulse needs: the value differs when
    the pane text differs, and holds when it holds. Nothing about its format is
    promised, so the client compares it to the previous poll's for equality and
    never parses it — a hash, a byte count and a counter are all valid answers,
    and swapping one for another must not be a client change.

    Derived from the capture the poll already holds, so it costs a digest over
    text that has been read anyway, not a second trip to tmux. A failed capture
    is the empty string, which is a stable token: no text is not a change.
    """
    return hashlib.blake2b(text.encode("utf-8", "surrogatepass"),
                           digest_size=8).hexdigest()


# ---- Admin actions ----


def recycle_window(cfg: Config, idx: int) -> None:
    """Restart the pinned claude process in a window — the MCP/hook re-arm.

    The MCP server and hooks arm per *process*, so wiring
    changes need a fresh agent. Graceful path: `remain-on-exit on` (the window
    survives the exit), Escape + C-u (dismiss any dialog, clear the composer),
    `/exit` (fires SessionEnd — a command on both harnesses), wait for pane death,
    then `tmux respawn-window` — which re-runs the window's CREATION command
    (`claude --agent thalamus-<scope>`, or `env THALAMUS_SCOPE=<scope> agent` for a
    Cursor window; either way the pin rides that argv).

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
    # Identify the session while it is still alive; after the respawn the pane holds
    # a different one and there is nothing left to name.
    who = _pinned_session(cfg, idx)
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
        if not dead:
            # Forced: SessionEnd never ran, so this session's distillation never
            # started and the window is about to come back looking healthy.
            _record_forced_kill(who, "recycle")
        tmux("respawn-window", *([] if dead else ["-k"]), "-t", target)
        tmux("set", "-w", "-u", "-t", target, "remain-on-exit")
    finally:
        with RECYCLING_LOCK:
            RECYCLING.pop(idx, None)


def close_window(cfg: Config, idx: int) -> None:
    """Graceful close: `/exit` fires SessionEnd, then the agent exits and tmux
    removes the window on its own (no remain-on-exit, unlike recycle). Force
    `kill-window` only if it outlives the grace budget — that path skips SessionEnd,
    the same tradeoff as a recycle timeout.

    `/exit` is a command on both harnesses (measured on Cursor 2026.08.11-e8db854),
    so this path is harness-neutral — but what SessionEnd *does* is not. Claude Code
    distills there; Cursor's hook only logs a pointer, because Cursor is not
    documented to flush its transcript first, and the sweep distills later
    (`harness/cursor_transcripts.py`). So a forced close costs a Claude Code session
    its distillation and costs a Cursor session only its ledger row, which the pin
    ledger then covers for scope."""
    target = f"{cfg.session}:{idx}"
    who = _pinned_session(cfg, idx)
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
        # Hung past the grace budget. The kill skips SessionEnd, so nothing will
        # ever write a distillation log for this session — and a scan over logs
        # cannot report a log that was never created.
        _record_forced_kill(who, "close")
        tmux("kill-window", "-t", target)
    finally:
        with CLOSING_LOCK:
            CLOSING.pop(idx, None)


def _run_capturing(fn, *args, **kwargs) -> tuple[bool, str, Exception | None]:
    """Call a `harness.pin` entry point and hand its console output to the client.

    pin's launchers report by printing and by raising, and the operator is holding
    a phone — both halves have to reach the admin log or a failed spawn reads as
    nothing happening at all. The exception comes back alongside its message so a
    caller can tell *which* failure it was without reading the prose.
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 — the message is the product here
        return False, (buf.getvalue() + f"\n{type(e).__name__}: {e}").strip(), e
    return True, buf.getvalue().strip() or "done.", None


def roster_sync(cfg: Config) -> tuple[bool, str]:
    """Recreate any missing roster window. Idempotent, so it only opens what isn't
    there (e.g. the anchor after an uncaught exit).

    Explicitly roomless: the anchor is the roster's own window, and leaving the room
    to the environment would put it in whatever room this long-lived server process
    was started in — where it would stop being the roster's anchor at all.

    `pin.roster` holds each window it opens to its settle deadline, so a window that
    was created and died reports here as a failure rather than as a sync that worked
    and produced nothing — the state in which the client draws its no-session screen
    and tells the operator to run the sync they just ran.
    """
    pin = pin_module()
    if pin is None:
        return False, EXPERTS_UNAVAILABLE
    ok, output, error = _run_capturing(pin.roster, cfg.project_root,
                                       session=cfg.session, room="")
    if isinstance(error, pin.WindowDied):
        return False, "\n\n".join(x for x in (output, SPAWN_FAILED_HINT) if x)
    return ok, output


def do_spawn(cfg: Config, scope: str, directory: Path, room: str = "",
             harness: str = "claude") -> tuple[bool, str]:
    """Open one on-demand pinned window. `harness.pin` owns the mechanics: derived
    agent write, detached create, window-size pin, room provisioning.

    `room` is always passed explicitly, never left to the environment: this server
    is a long-lived process, and letting it fall through to `resolve_room()` would
    put every spawn in whatever room the *server* happened to be started in.

    A clean return from `tmux new-window` is NOT evidence that a window exists, so
    `pin.spawn` holds the new window to its harness's settle deadline and raises
    `pin.WindowDied` if it does not survive. Measured 2026-08-08: with `claude` off
    the server's PATH every spawn answered `{"ok": true}` and produced nothing, which
    reads on the phone as a button that does nothing. Only a death is a failure here
    — a window that is still alive at the deadline is reported started, and one that
    dies after it is visible only in the window list.
    """
    pin = pin_module()
    if pin is None:
        return False, EXPERTS_UNAVAILABLE
    with SPAWN_LOCK:
        ok, output, error = _run_capturing(pin.spawn, scope, directory,
                                           session=cfg.session, room=room,
                                           harness=harness)
        if ok:
            return True, output
        # The PATH hint belongs to exactly one failure. A window that died is
        # overwhelmingly a window whose command could not be executed; a scope that
        # does not exist or a directory that is not one has already said so itself.
        if isinstance(error, pin.WindowDied):
            return False, "\n\n".join(x for x in (output, SPAWN_FAILED_HINT) if x)
        return False, output


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


def spawn_harnesses() -> list[dict]:
    """The harnesses a window can be pinned on, and what a pin means on each.

    `persona` is the difference the operator is picking between, not a detail: a
    Claude Code pin fuses persona, MCP arming and routing onto `--agent` and a codex
    pin carries the first two on `--profile`, while a Cursor pin routes and is bounded
    with no carrier for a charter at all (`harness/launcher.py`). Offering all three as
    the same object would make the sheet claim the last is something it is not, so the
    flag rides the payload and the client says so at the point of choosing.

    First entry is the default the endpoint falls back to. Empty without the
    package, like every other expert-layer option — the client then offers the one
    harness it can name rather than a picker whose choices it cannot check.
    """
    if not has_experts():
        return []
    from thalamus.harness.launcher import LAUNCH_SHAPES
    return [{"harness": s.harness, "persona": s.persona_flag is not None}
            for s in LAUNCH_SHAPES.values()]


def launch_policy_view() -> list[dict]:
    """Every harness's postures and current selection, for the gear panel.

    Empty without the package, like every other expert-layer option: a panel that
    cannot read the registry must offer nothing rather than a control whose effect it
    cannot name.
    """
    if not has_experts():
        return []
    from thalamus.harness.launch_policy import describe
    from thalamus.harness.launcher import LAUNCH_SHAPES
    return [
        {"harness": harness, "capabilities": describe(harness)}
        for harness in LAUNCH_SHAPES
        # A harness with nothing configurable is omitted rather than rendered as an
        # empty card, which would read as "no posture" instead of "no choice here".
        if describe(harness)
    ]


def policy_expected() -> dict[str, tuple[str, ...]]:
    """What the *current* policy would contribute to a launch, per harness.

    Asked of the launcher rather than re-derived here, so the staleness badge and the
    next launch cannot disagree about what the posture is.
    """
    if not has_experts():
        return {}
    from thalamus.harness.launch_policy import effective
    from thalamus.harness.launcher import LAUNCH_SHAPES, capability_argv
    return {h: tuple(capability_argv(h, effective(h))) for h in LAUNCH_SHAPES}


_extractor_policy_cache: object = _PIN_UNSET


def extractor_policy_module():
    """`thalamus.harness.extractor_policy`, or None when the package is absent.

    Deliberately *not* behind `has_experts()`, unlike the launch-posture panel. That
    one reads the expert launch registry and has nothing to say without it; this one
    reads `harness/agents.py`, which is core — a console on a box with no roster still
    distills, and the CLI that pays for the pass is still worth choosing.
    """
    global _extractor_policy_cache
    if _extractor_policy_cache is _PIN_UNSET:
        try:
            from thalamus.harness import extractor_policy
        except Exception:  # noqa: BLE001 — any import failure means "not available"
            _extractor_policy_cache = None
        else:
            _extractor_policy_cache = extractor_policy
    return _extractor_policy_cache


def extractor_policy_view() -> list[dict]:
    """Every extraction pass, which CLI and model runs it, and what the alternatives cost.

    A list rather than one object because the passes are two independent budgets — a
    payload carrying only the one the operator last asked about would let the panel
    render a stale card for the other.
    """
    module = extractor_policy_module()
    return module.describe_all() if module else []


# Reading a harness off a start command is the control plane's own question, and it is
# now dispatch's too — a Cursor room member is addressed by the pane its start command
# created. It lives with the rest of that reading in `harness/panes.py`; re-exported
# here because this module's callers and its tests know it by this name.
HARNESS_BINARIES = panes.HARNESS_BINARIES
window_harness = panes.harness_of


def _contains_run(tokens: list[str], want: tuple[str, ...]) -> bool:
    """Does `want` appear as a contiguous run in `tokens`?

    Contiguous rather than "every token present": `--permission-mode` and `auto` both
    appearing somewhere does not mean they appear together, and a flag paired with the
    wrong value is exactly the drift worth catching.
    """
    if not want:
        return True
    span = len(want)
    return any(tuple(tokens[i:i + span]) == want for i in range(len(tokens) - span + 1))


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


# ---- Service management: two supervisors, one vocabulary ----
#
# The console drives the units it was given (`--service`) through whatever
# supervises processes on this box — systemd on Linux, launchd on macOS. The
# translation happens *here*. The sheet renders `active` as a good row and every
# other word as a bad one, so a client that had to know which supervisor produced a
# word would be a second policy about one fact; launchd's answers are reduced into
# systemd's vocabulary on the way out, and the client is unchanged by this file.

# What the Services section reports on a host with no supervisor the console can
# drive. Reachable only with `--service`, since nothing named means no section at
# all — so this reads as a status rather than as the section having failed to load.
NO_SUPERVISOR = "no service manager"

NO_SUPERVISOR_DETAIL = (
    "this host has no service manager the console can drive — no `systemd-run` on "
    "Linux, no `launchctl` on macOS. Start `--service` units by whatever supervises "
    "them here."
)


def service_manager() -> str:
    """Which supervisor drives `--service` units: `"launchd"` or `"systemd"`.

    Keyed on the platform, not on which binary is on PATH. A Linux container without
    systemd is not a launchd box — it is a box whose restarts refuse — and that
    refusal already has a route: every call below reports an absent binary as
    `FileNotFoundError`, which is one answer for all the ways a supervisor can be
    missing.
    """
    return "launchd" if sys.platform == "darwin" else "systemd"


def _launchd_state(unit: str) -> str:
    """One launchd job's state, in systemd's words.

    `launchctl list <label>` answers in the caller's own domain — the domain the
    documented LaunchAgent is loaded into — and prints a job dictionary whose two
    load-bearing keys are `PID`, present only while it runs, and `LastExitStatus`.
    A loaded job that is not running either stopped cleanly or died, which are
    `inactive` and `failed` to a reader of the sheet, and nothing on this side tells
    them apart but that exit status.

    A label the domain does not carry is `not loaded`, deliberately not `inactive`:
    `--service` names a job the operator claims exists, so a label with no job behind
    it is a configuration mistake, and `inactive` would spell it as an ordinary
    stopped service. That verdict is read off the refusal rather than assumed from a
    non-zero exit, because `list` is a legacy subcommand: the day it stops existing,
    every managed job would otherwise be reported as a label naming nothing, which is
    a confident wrong answer where `unknown` is the true one.
    """
    r = subprocess.run(["launchctl", "list", unit], capture_output=True, text=True)
    if r.returncode != 0:
        refusal = (r.stderr + r.stdout).lower()
        return "not loaded" if "could not find" in refusal else "unknown"
    if re.search(r'^\s*"PID"\s*=\s*\d+;', r.stdout, re.M):
        return "active"
    exited = re.search(r'^\s*"LastExitStatus"\s*=\s*(-?\d+);', r.stdout, re.M)
    return "failed" if exited and exited.group(1) != "0" else "inactive"


def service_status(cfg: Config) -> list[dict]:
    launchd = service_manager() == "launchd"
    out = []
    for unit in cfg.services:
        try:
            if launchd:
                state = _launchd_state(unit)
            else:
                r = subprocess.run(["systemctl", "--user", "is-active", unit],
                                   capture_output=True, text=True)
                state = r.stdout.strip() or "unknown"
        except FileNotFoundError:
            out.append({"unit": unit, "state": NO_SUPERVISOR})
            continue
        out.append({"unit": unit, "state": state})
    return out


def service_restart(unit: str) -> str | None:
    """Restart a managed unit. Returns an error sentence, or None on success."""
    try:
        if service_manager() == "launchd":
            # `kickstart -k` hands launchd the kill and the start, so the work
            # outlives this process — the property `systemd-run` buys on the other
            # platform, where the transient unit escapes the cgroup of the service
            # being restarted. `start_new_session` is the rest of it: the unit being
            # restarted is usually the one serving this request, and a client left in
            # the dying job's process group can be signalled along with it before the
            # request reaches launchd. `gui/<uid>` is the domain a LaunchAgent in
            # `~/Library/LaunchAgents` loads into, which is what docs/console.md
            # tells the operator to write.
            subprocess.Popen(
                ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{unit}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
        else:
            # systemd-run: the transient unit escapes this service's cgroup, so the
            # restart survives even when the unit being restarted is the one serving
            # this request.
            subprocess.run(["systemd-run", "--user", "--collect", "--",
                            "systemctl", "--user", "restart", unit],
                           capture_output=True, text=True)
    except FileNotFoundError:
        return NO_SUPERVISOR_DETAIL
    return None


CGROUP_PATH = Path("/proc/self/cgroup")


def _self_launchd_label() -> str | None:
    """The launchd job this process runs under, read from its own environment.

    launchd stamps `XPC_SERVICE_NAME` with the job's label on every process it
    starts. Two answers are refused, for the reason the cgroup side refuses a
    `.scope` leaf: a console started from a shell inherits the *terminal's* XPC
    name — an `application.` label — and restarting that closes the terminal the
    operator is sitting in, while `0` is what launchd leaves on a process it did not
    start as a job at all.
    """
    label = os.environ.get("XPC_SERVICE_NAME", "").strip()
    if not label or label == "0" or label.startswith("application."):
        return None
    return label


def self_unit() -> str | None:
    """The unit this process is running under, or None.

    The console is told which units it may restart (`--service`), but not which of
    them is itself, and a deploy has to reload the one hosting it. Under launchd the
    job stamps its own label into the environment; under systemd it is read from the
    cgroup, where only the *leaf* counts: `user@1000.service` is an ancestor of
    everything a user runs, so scanning rightwards for any `*.service` would name the
    user manager for a console started from a terminal, and restarting that ends the
    login session. A leaf that is a `.scope` — a terminal, a tmux pane — is not a
    unit anyone should restart, and returns None so the deploy says what to restart
    by hand instead.
    """
    if service_manager() == "launchd":
        return _self_launchd_label()
    try:
        text = CGROUP_PATH.read_text().strip()
    except OSError:
        return None
    if not text:
        return None
    leaf = text.splitlines()[-1].rsplit("/", 1)[-1]
    return leaf if leaf.endswith(".service") else None


# ---- What this process is serving ----
#
# Merging a PR changes a remote. It does not change this box, and nothing about a
# console rendered on a phone says which commit it came from — the failure it
# produces is a merged change that appears not to have happened. These read the
# two clocks that decide what is on the surface and name the gap.


def _git_run(cwd: Path | str, *args: str) -> subprocess.CompletedProcess | None:
    """`git <args>` in `cwd`. None when git is not installed or cannot be run."""
    try:
        return subprocess.run(("git", *args), cwd=str(cwd), capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None


def _git(cwd: Path | str, *args: str) -> str | None:
    """Stripped stdout of a successful `git <args>`, else None."""
    r = _git_run(cwd, *args)
    return r.stdout.strip() if r and r.returncode == 0 else None


def checkout_root() -> Path | None:
    """The git checkout this module is being imported from, if it is in one.

    Deliberately derived from `__file__` rather than from `Config.project_root`:
    the root roster sync runs against is a separate setting and may point somewhere
    else entirely, while the question here is which tree produced the code now
    answering the request. None under a wheel install — there is no tree to be
    behind, and the running code is the only code there is.
    """
    top = _git(Path(__file__).resolve().parent, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def loaded_code_mtime() -> float:
    """Newest mtime among the package files this process has already imported.

    Exactly the files whose contents are frozen in memory. A module not yet
    imported will be read fresh when it is, so a newer mtime there is not
    staleness; one of *these* newer than `STARTED_AT` means the running server no
    longer matches the tree it is served from, and an endpoint the client was built
    against may simply not exist here.
    """
    newest = 0.0
    for name, mod in list(sys.modules.items()):
        if not name.startswith("thalamus"):
            continue
        path = getattr(mod, "__file__", None)
        if not path or not path.endswith(".py"):
            continue
        try:
            newest = max(newest, os.stat(path).st_mtime)
        except OSError:
            continue
    return newest


BUILD_TTL_S = 5.0
_BUILD_CACHE: dict = {"at": 0.0, "info": None}
_BUILD_LOCK = threading.Lock()


def build_info(force: bool = False) -> dict:
    """What this process is serving, and whether anything about it is out of date.

    Cached briefly: it costs five `git` calls and several clients may be polling
    it, but it must not be cached long enough to still say "current" after a
    deploy the operator is watching.
    """
    with _BUILD_LOCK:
        cached = _BUILD_CACHE["info"]
        if not force and cached and time.time() - float(_BUILD_CACHE["at"]) < BUILD_TTL_S:
            return cached
    info = _read_build()
    with _BUILD_LOCK:
        _BUILD_CACHE.update(at=time.time(), info=info)
    return info


def _read_build() -> dict:
    process_stale = loaded_code_mtime() > STARTED_AT
    root = checkout_root()
    info: dict = {"started": STARTED_AT, "process_stale": process_stale,
                  "root": str(root) if root else None, "vcs": root is not None}
    reasons: list[str] = []
    if process_stale:
        reasons.append("this process is running code older than the checkout")

    if root is not None:
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        committed = _git(root, "log", "-1", "--format=%ct")
        ahead = behind = 0
        if upstream:
            counts = _git(root, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
            parts = (counts or "").split()
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                ahead, behind = int(parts[0]), int(parts[1])
        info.update(
            branch=branch, sha=_git(root, "rev-parse", "--short", "HEAD"),
            subject=_git(root, "log", "-1", "--format=%s"),
            committed=int(committed) if committed and committed.isdigit() else None,
            # `-uno`: dirty means tracked files modified, which is the condition that
            # blocks a fast-forward. Untracked build output and editor state do not,
            # and counting them would leave the tree reading as dirty forever.
            dirty=bool(_git(root, "status", "--porcelain", "-uno")),
            upstream=upstream, ahead=ahead, behind=behind,
            fetched=_last_fetch(root),
        )
        if behind:
            reasons.append(f"the checkout is {behind} commit{'' if behind == 1 else 's'} "
                           f"behind {upstream}")

    info["stale"] = bool(reasons)
    info["reason"] = "; ".join(reasons)
    return info


def _last_fetch(root: Path) -> float | None:
    """When the checkout last heard from its remote, for reading `behind` honestly."""
    path = _git(root, "rev-parse", "--git-path", "FETCH_HEAD")
    if not path:
        return None
    try:
        return (root / path).stat().st_mtime
    except OSError:
        return None


def deploy(cfg: Config) -> dict:
    """Fast-forward the checkout this code is served from, and say what to reload.

    The two halves of a deploy have to move together: the pull is what updates
    `static/`, and the restart is what updates the Python. Doing either alone is the
    state where the phone shows a client and a server built against different
    commits. This does the pull and names the unit in `restarting`; the caller
    performs the restart, because it is the caller that has a response to deliver
    first and the restart kills the process that would deliver it.

    It refuses rather than improvises. A dirty tree, a detached HEAD, a branch with
    no upstream, or a history that will not fast-forward all stop here carrying
    git's own message — nothing is stashed, discarded or merged, and the only move
    made is the one `git pull --ff-only` would have made.
    """
    root = checkout_root()
    if root is None:
        return {"ok": False, "error": "this console is not running from a git checkout"}
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":
        return {"ok": False, "error": f"{root} is on a detached HEAD; check out a branch"}
    upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not upstream:
        return {"ok": False, "error": f"branch `{branch}` has no upstream to pull from"}
    dirty = _git(root, "status", "--porcelain", "-uno")
    if dirty:
        return {"ok": False, "output": dirty,
                "error": f"{root} has uncommitted changes to tracked files — "
                         "commit or restore them first"}

    fetched = _git_run(root, "fetch", "--quiet", "--prune")
    if fetched is None or fetched.returncode != 0:
        detail = (fetched.stderr or fetched.stdout).strip() if fetched else "git not runnable"
        return {"ok": False, "error": f"could not reach the remote: {detail}"}
    before = _git(root, "rev-parse", "--short", "HEAD")
    ff = _git_run(root, "merge", "--ff-only", upstream)
    if ff is None or ff.returncode != 0:
        detail = (ff.stderr or ff.stdout).strip() if ff else "git not runnable"
        return {"ok": False, "output": detail,
                "error": f"`{branch}` will not fast-forward onto {upstream}"}
    after = _git(root, "rev-parse", "--short", "HEAD")

    info = build_info(force=True)
    unit = self_unit()
    moved = after != before
    # Restarting when nothing moved would blip the console for no reason; not
    # restarting when the process is already behind the tree would leave the half
    # this cannot fix any other way. `--service` stays the whitelist it is for the
    # admin sheet: a console never restarts a unit it was not told it owns, its own
    # included.
    restarting = None
    if (moved or info.get("process_stale")) and unit and unit in cfg.services:
        restarting = unit
    return {"ok": True, "moved": moved, "from": before, "to": after, "branch": branch,
            "upstream": upstream, "unit": unit, "restarting": restarting}


def _fetch_loop(interval_s: float) -> None:
    """Keep `behind` truthful without anyone having to ask.

    A fetch moves remote-tracking refs and touches nothing else — no working tree,
    no branch, no index. Without it the console can only compare the checkout
    against whenever somebody last fetched by hand, which is the state in which a
    merged PR sits invisible for a day.
    """
    first = True
    while True:
        # A short first delay rather than the full interval: at boot the network
        # may not be up yet, and the answer should still be current within a minute.
        time.sleep(30 if first else interval_s)
        first = False
        root = checkout_root()
        if root is None:
            return
        _git_run(root, "fetch", "--quiet", "--prune")
        with contextlib.suppress(Exception):
            build_info(force=True)


# ---- Where a request came from ----
# The console has no authentication, and that is deliberate: it is fronted by
# something that already authenticates (see docs/console.md). What that reasoning
# does not cover is a request the operator's *own* browser is tricked into sending.
# A page on any other origin can POST here cross-site — `_body()` reads JSON whatever
# the declared content type, so `text/plain` makes it a CORS *simple* request that is
# delivered without a preflight — and while the reply is unreadable to that page, the
# write has already landed on the tmux session. Loopback binding is no defence: the
# request originates inside the boundary, carrying whatever the proxy granted.
#
# So the one thing checked on a state-changing request is where the browser says it
# came from, per OWASP's CSRF Prevention Cheat Sheet ("Verifying Origin With Standard
# Headers"): compare the request's `Origin` against its `Host`. Both are set by the
# browser and neither is settable from script.
#
# `Host` is the right thing to compare against because the deployments this repo
# recommends preserve it. Measured against this console's own published surface:
# `tailscale serve --set-path` forwards `Host: <machine>.<tailnet>.ts.net` with a
# matching `Origin`, and Caddy's `reverse_proxy` preserves `Host` by default. nginx
# does not unless told (`proxy_set_header Host $host`), which is what
# `--allow-origin` is for.

DEFAULT_PORTS = {"http": "80", "https": "443"}


def same_origin(origin: str, host_header: str) -> bool:
    """Does `origin` name the same host:port the request was addressed to?

    `Host` carries no scheme, so its port is compared only when it states one — a
    TLS-terminating proxy on 443 sends a bare hostname, and the origin's own default
    port is then the only port either side could mean.
    """
    parts = urlsplit(origin)
    if not parts.scheme or not parts.hostname:
        return False  # "null" (sandboxed frame, file://) and anything unparseable
    origin_port = str(parts.port) if parts.port else DEFAULT_PORTS.get(parts.scheme)
    # `Host` is authority-only, and urlsplit needs a scheme to read one as authority.
    target = urlsplit(f"//{host_header}")
    if not target.hostname or target.hostname.lower() != parts.hostname.lower():
        return False
    return target.port is None or str(target.port) == origin_port


def origin_key(origin: str) -> str | None:
    """`scheme://host:port` with the default port spelled out, or None if unparseable.

    Two origins are the same one when these agree. This is the comparison for
    `--allow-origin`, where both sides are full origins and the scheme is known on
    each — unlike the `Host` comparison above, which has a scheme on one side only.
    """
    parts = urlsplit(origin)
    port = str(parts.port) if parts.port else DEFAULT_PORTS.get(parts.scheme)
    if not parts.hostname or not port:
        return None
    return f"{parts.scheme}://{parts.hostname.lower()}:{port}"


class ConsoleServer(ThreadingHTTPServer):
    """The server object that carries this console's `Config` to every handler."""

    config: Config


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def cfg(self) -> Config:
        return cast("ConsoleServer", self.server).config

    def log_message(self, format: str, *args: Any) -> None:  # quiet
        pass

    def _send(self, code, body, ctype="application/json", cache=None):
        self._responded = True
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

    def _origin_ok(self) -> bool:
        """Is this write coming from the console's own page?

        A non-browser client — curl, a script, a test — sends neither header and is
        allowed through: this closes the browser vector, it does not invent an
        authentication the module docstring promises is absent. Browsers send
        `Origin` on every cross-site POST, so nothing this is meant to stop can reach
        the routes by leaving it off.
        """
        claimed = self.headers.get("Origin") or self.headers.get("Referer")
        if not claimed:
            return True
        if same_origin(claimed, self.headers.get("Host", "")):
            return True
        key = origin_key(claimed)
        return key is not None and any(key == origin_key(allowed)
                                       for allowed in self.cfg.allowed_origins)

    def do_GET(self):
        """Route a GET, and answer with a 500 rather than a dropped connection.

        Every reader below shells out to something — tmux, git, systemd — and the
        environment differences that make one of them absent are not defects in the
        console. Unwrapped, the exception kills the handler thread and the browser
        sees a connection that closed, which is the least diagnosable failure the
        surface has. The message goes to stderr as well: `log_message` is silenced,
        so without it a journal would hold nothing at all.
        """
        self._responded = False
        try:
            self._route_get()
        except Exception as exc:  # noqa: BLE001 — the message is the product here
            print(f"! GET {self.path}: {type(exc).__name__}: {exc}", file=sys.stderr)
            if not self._responded:
                with contextlib.suppress(Exception):
                    self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def _route_get(self):
        path, _, query = self.path.partition("?")
        if path == "/api/commands":
            # ?index=N scopes project skills to that window's cwd; absent → anchor.
            raw = parse_qs(query).get("index", [""])[0]
            idx = int(raw) if raw.lstrip("-").isdigit() else None
            return self._send(200, {"commands": list_commands(self.cfg, idx)})
        if path == "/api/panes":
            windows = list_windows(self.cfg)
            for w in windows:
                text = capture(self.cfg, w["index"])
                w["lines"] = text
                w["screen_rev"] = screen_rev(text)
            # The launch facts tmux cannot know: which project and repository this
            # session belongs to, and when it started. Without them the roster is a
            # list that cannot group and cannot tell its own rows apart.
            attach_ledger_facts(windows)
            # Depends on the join above: the descriptor is keyed by session id, and
            # the session id is a ledger fact.
            attach_blocked(windows)
            # Distillation outlives the window that triggered it, so it rides the
            # poll the client already runs rather than getting a loop of its own.
            #
            # `grace_s` is the deadline the recycle and close workers race. It rides
            # the same payload because the client renders elapsed time against it,
            # and a client holding its own copy would be a second statement of a
            # policy the server owns — wrong the first time this is tuned.
            #
            # `tmux_socket` rides it for the same reason: the empty-roster screen
            # prints a command the operator is meant to paste, and the server is the
            # only side that knows which tmux server this console drives.
            return self._send(200, {"session": self.cfg.session, "windows": windows,
                                    "distill": distill_rows(),
                                    "tmux_socket": tmux_socket(),
                                    "grace_s": RECYCLE_GRACE_S})
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
            # `permission_mode_read` rides every response this endpoint can serve,
            # including the ones that already carry `reason`. The client should
            # never have to combine `available` and `reason` to learn whether the
            # instrument worked — one field, always present, four values.
            tr = transcript_module()
            if tr is None:
                return self._send(200, {"available": False, "reason": "no-package",
                                        "permission_mode_read": "no-package"})
            window, feed, reason = read_feed(self.cfg, int(raw))
            if window is None:
                return self._send(404, {"error": "no such window"})
            if feed is None:
                # `unresolved` is a refusal: resolution declines to guess when a
                # pre-ledger session shares a scope and cwd with another window,
                # and it fixes itself on recycle. `pending` is not a failure at
                # all — the session is identified and has not written its first
                # turn, which is where every freshly spawned window starts.
                #
                # No `permission_mode` here, deliberately. An empty one would say
                # "no record exists", which is a claim about the session; what we
                # have is a failure to read it, and that is what the field says.
                return self._send(200, {"available": False, "reason": reason,
                                        "permission_mode_read": reason})
            with READ_LOCK:
                return self._send(200, {
                    "available": True,
                    "session_id": feed.session_id,
                    "seq": feed.seq,
                    "items": tr.wire(feed.since(since, tr.COLD_OPEN_ITEMS if not since else 0)),
                    "mode": feed.mode,
                    # `""` means the transcript carries no permission-mode record,
                    # and the parse covers the whole file — absence of a record,
                    # not absence of a read. `permission_mode_read` is what
                    # separates the two, so it is stamped even on success.
                    "permission_mode": feed.permission_mode,
                    "permission_mode_read": "ok",
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
        if path == "/api/admin":
            with RECYCLING_LOCK:
                recycling = sorted(RECYCLING)
            return self._send(200, {"services": service_status(self.cfg),
                                    "recycling": recycling,
                                    "build": build_info()})
        if path == "/api/build":
            # Its own endpoint as well as a field on /api/admin: the staleness
            # banner has to be answerable without opening the admin sheet, which is
            # the place an operator goes only once he already suspects something.
            return self._send(200, build_info())
        if path == "/api/launch-policy":
            return self._send(200, {"harnesses": launch_policy_view()})
        if path == "/api/extractor-policy":
            return self._send(200, {"passes": extractor_policy_view()})
        if path == "/api/cursor-sweep":
            from thalamus.console import sweep
            return self._send(200, sweep.status())
        if path == "/api/spawn-options":
            pin = pin_module()
            dirs, _ = spawn_dirs(self.cfg)
            return self._send(200, {"scopes": known_scopes(), "dirs": dirs,
                                    "rooms": pin.rooms() if pin else [],
                                    "harnesses": spawn_harnesses(),
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
        if not self._origin_ok():
            # Refused before the body is read, so a rejected request costs nothing.
            return self._send(403, {"error": "cross-origin request refused"})
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
            error = service_restart(unit)
            if error:
                return self._send(200, {"ok": False, "error": error})
            return self._send(200, {"ok": True})

        if path == "/api/deploy":
            # A refusal is a 200 carrying the reason. Every way this stops is a fact
            # about the checkout the operator has to read and act on — a dirty tree,
            # a branch that will not fast-forward — and a status code the client
            # renders as "request failed" throws that away.
            result = deploy(self.cfg)
            # Answer *before* restarting. The unit being restarted is the one
            # serving this request, so the process dies with the socket: restarting
            # first leaves the client unable to tell a deploy in progress from a box
            # that fell over. `wfile` is unbuffered here (`wbufsize = 0`), so the
            # body is on the wire by the time this returns.
            self._send(200, result)
            if result.get("restarting"):
                service_restart(result["restarting"])
            return

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
            # Defaulted rather than required: the sheet names the chip that was
            # tapped, but this endpoint is also driven by hand over the tailnet, and
            # a client older than the harness row sends nothing at all. A request
            # that names no harness gets the one whose pin carries everything.
            harness = data.get("harness") or "claude"
            pin = pin_module()
            if pin is None:
                return self._send(503, {"error": EXPERTS_UNAVAILABLE})
            if scope not in known_scopes():
                return self._send(400, {"error": "unknown scope"})
            from thalamus.harness.launcher import LAUNCH_SHAPES
            if harness not in LAUNCH_SHAPES:
                return self._send(400, {"error": "unknown harness"})
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
            ok, output = do_spawn(self.cfg, scope, Path(os.path.realpath(directory)),
                                  room, harness)
            return self._send(200 if ok else 500, {"ok": ok, "output": output})

        if path == "/api/dispatch":
            # Addressed to a *room*, so it is deliberately above the window-index gate
            # below: a dispatch fans out to members the operator is not looking at,
            # which is the entire difference from /api/send.
            room = data.get("room") or ""
            message = data.get("message") or ""
            pin = pin_module()
            dispatch = dispatch_module()
            if pin is None or dispatch is None:
                return self._send(503, {"error": EXPERTS_UNAVAILABLE})
            if not isinstance(room, str) or not pin.valid_room(room):
                return self._send(400, {"error": "invalid room name"})
            if not isinstance(message, str) or not message.strip():
                return self._send(400, {"error": "nothing to dispatch"})
            scopes = data.get("to")
            if scopes is not None and (
                not isinstance(scopes, list)
                or not all(isinstance(s, str) for s in scopes)
            ):
                return self._send(400, {"error": "`to` must be a list of scopes"})
            try:
                result = dispatch.dispatch(
                    room,
                    message,
                    sender=str(data.get("sender") or "console"),
                    # `""`, never omitted: the server is long-lived and belongs to no
                    # room, and the room is named per request. Omitting this reads the
                    # *server process's* environment, so a console started from inside
                    # a member's shell would authenticate as that member for its whole
                    # life and refuse every other room — naming, in the refusal, a room
                    # the operator is not in and cannot see. The same reasoning already
                    # makes `do_spawn` and `roster_sync` pass `room=""` explicitly.
                    caller_room="",
                    scopes=scopes or None,
                    partial=bool(data.get("partial")),
                    dry_run=bool(data.get("dryRun")),
                )
            except dispatch.DispatchRefused as e:
                # 409, not 400: the request was well-formed and the room said no. The
                # client renders the reason, which names the target that refused.
                return self._send(409, {"error": str(e)})
            return self._send(200, {
                "ok": result.performed > 0,
                "handle": result.handle,
                "delivered": result.performed,
                "targets": [
                    {
                        "scope": delivery.target.scope,
                        "name": delivery.target.name,
                        "status": delivery.target.status,
                        "performed": delivery.performed,
                        "refusal": delivery.target.refusal or delivery.error,
                    }
                    for delivery in result.deliveries
                ],
                "undelivered": list(result.undelivered),
                "note": result.note(),
            })

        if path == "/api/cursor-sweep":
            if not has_experts():
                return self._send(503, {"error": "the expert layer is not importable"})
            from thalamus.console import sweep
            started, message = sweep.start()
            # 409 rather than 500: a sweep already running is the request being refused
            # on state, not the server failing, and the phone shows the sentence either
            # way.
            return self._send(200 if started else 409,
                              {"ok": started, "message": message, **sweep.status()})

        if path == "/api/launch-policy":
            if not has_experts():
                return self._send(503, {"error": "the expert layer is not importable"})
            from thalamus.harness.launch_policy import PolicyRefused, select
            try:
                ttl = data.get("ttl_hours")
                row = select(
                    str(data.get("harness", "")),
                    str(data.get("capability", "")),
                    str(data.get("value", "")),
                    ttl_hours=int(ttl) if ttl is not None else None,
                    actor="console",
                )
            except (TypeError, ValueError) as exc:
                # `PolicyRefused` subclasses ValueError, and its message is written for
                # the person who is mid-decision — it is the reason for the rule, so it
                # goes to the panel verbatim rather than becoming a bare 400.
                code = 409 if isinstance(exc, PolicyRefused) else 400
                return self._send(code, {"error": str(exc)})
            return self._send(200, {"ok": True, "change": row,
                                    "harnesses": launch_policy_view()})

        if path == "/api/extractor-policy":
            module = extractor_policy_module()
            if module is None:
                return self._send(503, {"error": "the thalamus package is not importable"})
            try:
                row = module.select(
                    str(data.get("harness", "")),
                    str(data.get("model", "")),
                    pass_=str(data.get("pass", module.DEFAULT_PASS)),
                    actor="console",
                )
            except (TypeError, ValueError) as exc:
                # `ExtractorRefused` and `UnknownPass` both subclass ValueError, and
                # the first is written for the person mid-decision — the reason for the
                # rule is the rule's whole argument, so it goes to the panel verbatim.
                # An unknown pass is a client bug, not a decision, and is a 400.
                code = 409 if isinstance(exc, module.ExtractorRefused) else 400
                return self._send(code, {"error": str(exc)})
            return self._send(200, {"ok": True, "change": row,
                                    "passes": extractor_policy_view()})

        windows = list_windows(self.cfg)
        idx = data.get("index")
        if not isinstance(idx, int) or not any(w["index"] == idx for w in windows):
            return self._send(400, {"error": "unknown window"})
        target = f"{self.cfg.session}:{idx}"

        if path == "/api/recycle":
            with RECYCLING_LOCK:
                already = idx in RECYCLING
                # setdefault, not assignment: a second request for a restart already
                # in flight must not reset the clock the operator is reading.
                RECYCLING.setdefault(idx, time.time())
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
                CLOSING.setdefault(idx, time.time())
            if not already:
                threading.Thread(target=close_window, args=(self.cfg, idx),
                                 daemon=True).start()
            return self._send(200, {"ok": True, "already": already})

        if path == "/api/send":
            # No `waiting` pre-flight here, and that is not an oversight — it is the
            # line between the two send paths. `/api/dispatch` refuses a `waiting`
            # target because the sender cannot see it, so the Enter would actuate a
            # highlighted default nobody read. This endpoint types into the one window
            # the operator is watching live, where *answering* a permission prompt is a
            # primary use of the composer and the terminal keys beside it. Gating it on
            # `waiting` would break exactly the case the console exists for.
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
    try:
        httpd = ConsoleServer((host, port), Handler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        raise PortInUse(
            f"port {port} is already in use on {host} — most often a `thalamus console` "
            f"that is still running. Stop that one, or serve this one somewhere else "
            f"with `thalamus console --port <n>`."
        ) from exc
    httpd.config = cfg
    if cfg.fetch_interval_s > 0:
        threading.Thread(target=_fetch_loop, args=(cfg.fetch_interval_s,),
                         daemon=True).start()
    build = build_info()
    if build.get("vcs"):
        print(f"Serving {build.get('branch')}@{build.get('sha')} from {build.get('root')}")
    print(f"Control plane on http://{host}:{port}  (tmux session `{cfg.session}`)")
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("  ! bound off-loopback and this server has NO authentication — "
              "anything that can reach it can drive your sessions.")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()


def main(argv: list[str] | None = None) -> None:
    """`python3 -m thalamus.console.server`, and the file run directly.

    The bridge is documented to run under a bare `python3` with nothing installed,
    and that is only true if there is something to run: without an entry point the
    module imports, defines `serve`, and exits 0 without ever listening — which
    looks exactly like a server that started and said nothing.

    Deliberately not `thalamus console`. That command builds a `Config` from an
    installed package's notion of the project root and offers the expert layer's
    flags; this one takes the two arguments a bare bridge can honour and lets
    `Config.__post_init__` fall back to the checkout-less defaults.
    """
    ap = argparse.ArgumentParser(
        prog="python3 -m thalamus.console.server",
        description="The console's tmux bridge, without the expert layer.",
    )
    ap.add_argument("--host", default="127.0.0.1",
                    help="Bind address (default: localhost — there is no auth here)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help=f"Port (default: {DEFAULT_PORT})")
    args = ap.parse_args(argv)
    try:
        serve(Config(), host=args.host, port=args.port)
    except PortInUse as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
