"""A window the console spawns must be the session the core says it is, and closing it must
touch that window and no other.

`POST /api/spawn` is the one place the console reaches into the core: it validates the
scope against the expert manifests, writes the derived agent file, resolves the harness's
launch argv from the launch policy, provisions a room's config root, and only then asks
tmux for a window. Every one of those is tested where it lives. This case follows one
spawn all the way through and reads the result back through a channel the console did not
write: tmux's own `pane_start_command`, the process environment tmux gave the pane
(`/proc/<pid>/environ`), the real SessionStart hook that records the pin ledger from that
environment, and `/api/panes` joining the ledger back onto the window.

**Properties asserted** (real console subprocess, private tmux socket, redirected HOME)

1. *Spawn is faithful.* For `main`, an expert scope and `codex`: 200, exactly one new
   tmux window named for the scope, whose start command names the requested harness's
   binary and `THALAMUS_SCOPE=<scope>`; an expert's carries `--agent thalamus-<scope>` and
   the derived agent file exists under the rig's HOME (not the operator's); the default
   launch posture (`--permission-mode auto`) is on the argv.
2. *The ledger sees what the console launched.* Firing the real hook inside the pane's own
   environment records `scope` equal to the spawned scope and `room` equal to the spawned
   room, and `/api/panes` then attaches that session to that window and no other.
3. *Rooms are provisioned, once.* A spawn into room `r1` creates the room's config root
   under the rig's HOME with its credentials, settings and `sessions/` in place, puts
   `CLAUDE_CONFIG_DIR` and `THALAMUS_ROOM` on the window, and lists `r1` in
   `/api/spawn-options`. A second spawn into the same room leaves the directory tree and
   file contents byte-identical. Names that are not rooms (`../x`, `A`, `a/b`) are 400,
   create no window and no directory.
4. *Bad spawns spawn nothing.* An unknown scope, an unknown harness and a directory
   outside the picker's list (including a symlink to one) are 400 and the roster is
   unchanged.
5. *Concurrent spawns serialise.* Three simultaneous spawns yield three windows with
   distinct indices and three 200s — not a `create window failed: index N in use`.
6. *Close is single, dedupes, and is local.* N concurrent `/api/close` for one window
   return exactly one `already: false`; the pane was typed `/exit` into (the control that
   close did anything); once the stand-in agent exits the window leaves tmux and the
   roster, every sibling keeps its pane id, and a repeat close on the vanished index is a
   400, not a close of whichever window inherited it. The anchor cannot be closed.

The stub agent is `cat`, which does not honour `/exit`; the case ends it with `C-d`
after observing the typed text — the harness's part of the protocol, supplied by hand.

Two more cases in this module are defect reproductions, each red on the tree as it stands:

- `console-spawn-survives-a-scope-named-like-its-session` — `windows._open_window` creates
  with `new-window -t <session>`, and tmux resolves a target that names both a session and
  a window to the *window*, so once any window is named like the session (the rig's
  session is `qe`, and `qe` is an expert scope; `--session architect` is the same hazard
  on a real box) every later spawn dies with `create window failed: index N in use`, which
  the phone receives as a 500 carrying a `CalledProcessError` repr.
- `console-ledger-fallback-never-claims-another-panes-session` — `LedgerIndex.legacy_match`
  exists for windows that predate pane ids in the ledger, but does not exclude a row that
  already names a pane. A second window of the same scope and cwd started within
  `LEGACY_SKEW_SECONDS` of the first (a codex `main` next to a claude `main`) is handed the
  first's session, and the roster then shows the wrong transcript — the failure that
  function's own docstring says is worse than showing none.

**Shown capable of going red** (copies of the console tree via `QE_CONSOLE_SRC`, run
2026-11-24): in `windows._open_window` drop the `"-e", f"THALAMUS_SCOPE={scope}"` pair and
property 1 reports `process env THALAMUS_SCOPE='main'` for the `qe` window; in
`server.py::do_POST` change `already = idx in CLOSING` to `already = False` and property 6
reports `already=[False, False, False, False, False, False]`; in `attach_ledger_facts`
(see `console_integ_roster`) replace the pane lookup with `None` and the ledger join
properties report it.
"""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier
from . import _console_integ as C
from ._console_rig import console_rig

_SERVER = "packages/thalamus-console/src/thalamus_console/server.py"
_WINDOWS = "packages/thalamus-console/src/thalamus_console/windows.py"


def _f(summary, witness, site=_SERVER, cls=FailureClass.INVARIANT_FALSIFIED):
    return Finding(cls, summary, witness=witness, site=site)


def _start(rig, pane):
    r = rig.tmux("display-message", "-p", "-t", pane, "#{pane_start_command}")
    return r.stdout.strip()


def _env(rig, pane) -> dict[str, str]:
    """The environment tmux gave the pane's process — what the session itself sees."""
    pid = next(w["pane_pid"] for w in C.windows(rig) if w["pane_id"] == pane)
    raw = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    return dict(e.decode(errors="replace").split("=", 1) for e in raw if b"=" in e)


def _tree_digest(root: Path) -> list[tuple[str, str]]:
    out = []
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        if p.is_symlink():
            out.append((rel, "->" + os.readlink(p)))
        elif p.is_file():
            out.append((rel, hashlib.sha256(p.read_bytes()).hexdigest()))
        else:
            out.append((rel, "dir"))
    return out


def _new_panes(rig, before):
    return [r for r in C.tmux_rows(rig) if r["pane_id"] not in before]


def run() -> Finding | None:
    with C.integ_rig() as rig:
        C.seed_credentials(rig)
        d = C.alpha(rig)
        before = C.tmux_rows(rig)
        if len(before) != 1:
            return _f("fixture: the rig did not start with exactly the anchor window",
                      repr(before), "tests/qe/cases/_console_rig.py",
                      FailureClass.COLLAPSED_SENTINEL)

        # ---- 1: spawn is faithful ----
        spawned = {}
        for scope, harness in (("main", ""), ("qe", ""), ("main", "codex")):
            seen = {r["pane_id"] for r in C.tmux_rows(rig)}
            r = C.spawn(rig, scope, harness=harness)
            if r.status != 200:
                return _f("a valid spawn was refused or failed",
                          f"scope={scope} harness={harness or 'claude'}: {r.status} "
                          f"{r.body[:300]!r}")
            fresh = _new_panes(rig, seen)
            if len(fresh) != 1 or fresh[0]["name"] != scope:
                return _f("a spawn did not create exactly one window named for its scope",
                          f"scope={scope}: new windows={fresh}")
            pane = fresh[0]["pane_id"]
            start = _start(rig, pane)
            binary = harness or "claude"
            got = _env(rig, pane).get("THALAMUS_SCOPE")
            if got != scope or binary not in start:
                return _f("the window does not carry the requested scope and harness",
                          f"scope={scope} harness={binary}: process env "
                          f"THALAMUS_SCOPE={got!r}, start command {start!r}", _WINDOWS)
            if binary == "claude":
                if "--permission-mode auto" not in start:
                    return _f("the launch policy's default posture is not on a spawned "
                              "claude window's argv", f"{start!r}", _WINDOWS)
                if scope == "qe" and "--agent thalamus-qe" not in start:
                    return _f("an expert spawn does not run under its derived agent",
                              f"{start!r}", _WINDOWS)
            spawned[(scope, binary)] = pane
        agent_file = rig.home / ".claude" / "agents" / "thalamus-qe.md"
        if not agent_file.is_file():
            return _f("spawning an expert did not write its derived agent file under the "
                      "rig's HOME", f"{agent_file} missing; HOME holds "
                      f"{[str(p.relative_to(rig.home)) for p in rig.home.rglob('*.md')]}",
                      _WINDOWS)

        # ---- 2: the ledger sees what the console launched ----
        rows = {w["pane_id"]: w for w in C.windows(rig)}
        sids = {}
        for key in (("main", "claude"), ("qe", "claude")):
            pane = spawned[key]
            sid, p = C.run_session_start_hook(rig, pane_id=pane, scope="", cwd=d,
                                              from_pid=rows[pane]["pane_pid"])
            if p.returncode != 0:
                return _f("fixture: the SessionStart hook failed in a spawned pane's "
                          "environment", p.stderr[-300:],
                          "tests/qe/cases/_console_integ.py",
                          FailureClass.COLLAPSED_SENTINEL)
            sids[key] = sid
        ledger = {r["session_id"]: r for r in C.pin_rows(rig)}
        for (scope, _), sid in sids.items():
            row = ledger.get(sid)
            if not row or row["scope"] != scope or row["room"] != "":
                return _f("the pin ledger row a spawned window's session wrote disagrees "
                          "with what the console launched",
                          f"spawned scope={scope}, ledger row={row}", _WINDOWS)
        rows = {w["pane_id"]: w for w in C.windows(rig)}
        for key, sid in sids.items():
            if rows[spawned[key]]["session_id"] != sid:
                return _f("/api/panes did not attach the ledger session to the window it "
                          "was launched in",
                          f"{key}: window session_id={rows[spawned[key]]['session_id']!r}, "
                          f"ledger={sid!r}", _SERVER + "::attach_ledger_facts")

        # ---- 3: rooms ----
        rooms_dir = rig.home / ".thalamus" / "rooms"
        seen = {r["pane_id"] for r in C.tmux_rows(rig)}
        r = C.spawn(rig, "qe", room="r1")
        if r.status != 200:
            return _f("a spawn into a new room failed", f"{r.status} {r.body[:300]!r}",
                      _WINDOWS)
        fresh = _new_panes(rig, seen)
        root = rooms_dir / "r1"
        env = _env(rig, fresh[0]["pane_id"]) if fresh else {}
        if (not fresh or env.get("CLAUDE_CONFIG_DIR") != str(root)
                or env.get("THALAMUS_ROOM") != "r1"):
            return _f("a room spawn's window does not carry the room's config root and "
                      "name", f"new={fresh} env CLAUDE_CONFIG_DIR="
                      f"{env.get('CLAUDE_CONFIG_DIR')!r} THALAMUS_ROOM="
                      f"{env.get('THALAMUS_ROOM')!r}, want {root} / r1", _WINDOWS)
        missing = [n for n in ("sessions", "settings.local.json", ".credentials.json")
                   if not (root / n).exists()]
        if missing:
            return _f("a room was spawned into without being provisioned",
                      f"{root} lacks {missing}; has {sorted(p.name for p in root.iterdir())}",
                      "packages/thalamus-console/src/thalamus_console/rooms.py::ensure_room")
        if "r1" not in rig.get("/api/spawn-options").json()["rooms"]:
            return _f("/api/spawn-options does not list a room that now exists on disk",
                      repr(rig.get("/api/spawn-options").json()["rooms"]), _SERVER)
        room_w = next(w for w in C.windows(rig) if w["pane_id"] == fresh[0]["pane_id"])
        if room_w["room"] != "r1":
            return _f("the roster does not report the room the window was spawned into",
                      f"room={room_w['room']!r}", _SERVER)
        sid, p = C.run_session_start_hook(rig, pane_id=room_w["pane_id"], scope="", cwd=d,
                                          from_pid=room_w["pane_pid"])
        row = {r["session_id"]: r for r in C.pin_rows(rig)}.get(sid, {})
        if row.get("room") != "r1" or row.get("scope") != "qe":
            return _f("a room member's pin-ledger row does not record its room and scope",
                      f"row={row}", _WINDOWS)
        digest = _tree_digest(rooms_dir)
        if C.spawn(rig, "qe", room="r1").status != 200 or _tree_digest(rooms_dir) != digest:
            return _f("spawning into an already-provisioned room changed its files — "
                      "provisioning is not idempotent",
                      f"before={digest[:6]}... after={_tree_digest(rooms_dir)[:6]}...",
                      "packages/thalamus-console/src/thalamus_console/rooms.py::ensure_room")
        n_before = len(C.tmux_rows(rig))
        for bad in ("../x", "A", "a/b", "x y", "-x", "r1/../r2"):
            r = C.spawn(rig, "main", room=bad)
            if r.status != 400:
                return _f("an invalid room name was not refused with 400",
                          f"room={bad!r}: {r.status} {r.body[:200]!r}", _SERVER)
        if (len(C.tmux_rows(rig)) != n_before
                or sorted(p.name for p in rooms_dir.iterdir()) != ["r1"]):
            return _f("a refused room name still created a window or a directory",
                      f"windows {n_before}->{len(C.tmux_rows(rig))}; "
                      f"rooms={[p.name for p in rooms_dir.iterdir()]}", _SERVER)

        # ---- 4: bad spawns spawn nothing ----
        link = rig.projects / "escape"
        link.symlink_to("/tmp")
        n_before = len(C.tmux_rows(rig))
        for body in ({"scope": "no-such-scope", "dir": d},
                     {"scope": "main", "dir": d, "harness": "emacs"},
                     {"scope": "main", "dir": "/etc"},
                     {"scope": "main", "dir": str(link)},
                     {"scope": "main", "dir": ["x"]}, {"scope": ["main"], "dir": d}):
            r = rig.post("/api/spawn", body)
            if r.status not in (400,):
                return _f("a malformed or out-of-list spawn was not a 400",
                          f"{body}: {r.status} {r.body[:200]!r}", _SERVER)
        if len(C.tmux_rows(rig)) != n_before:
            return _f("a refused spawn created a window", f"{n_before}->"
                      f"{len(C.tmux_rows(rig))}", _SERVER)

        # ---- 5: concurrent spawns ----
        seen = {r["pane_id"] for r in C.tmux_rows(rig)}
        out = []
        gate = threading.Barrier(3)

        def go():
            gate.wait()
            out.append(C.spawn(rig, "main"))
        ts = [threading.Thread(target=go) for _ in range(3)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        fresh = _new_panes(rig, seen)
        if [r.status for r in out] != [200] * 3 or len(fresh) != 3 or len(
                {r["index"] for r in fresh}) != 3:
            return _f("three simultaneous spawns did not yield three windows and three "
                      "successes", f"statuses={[(r.status, r.body[:160]) for r in out]} "
                      f"new windows={fresh}", _SERVER + "::do_spawn")

        # ---- 6: close ----
        rows = C.windows(rig)
        target = next(w for w in rows if w["pane_id"] == spawned[("main", "codex")])
        siblings = {w["pane_id"] for w in rows if w["pane_id"] != target["pane_id"]}
        anchor = next(w for w in rows if w["anchor"])
        if rig.post("/api/close", {"index": anchor["index"]}).status != 400:
            return _f("the anchor window can be closed",
                      f"close index {anchor['index']}", _SERVER)
        replies = []
        gate = threading.Barrier(6)

        def close():
            gate.wait()
            replies.append(rig.post("/api/close", {"index": target["index"]}))
        ts = [threading.Thread(target=close) for _ in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        already = sorted(bool(r.json().get("already")) for r in replies
                         if r.status == 200)
        if len(already) != 6 or already != [False] + [True] * 5:
            return _f("six concurrent closes of one window did not dedupe to a single "
                      "close", f"statuses={[r.status for r in replies]} "
                      f"already={already}", _SERVER + "::do_POST")
        typed = rig.wait_for(lambda: "/exit" in rig.capture(target["index"]), timeout=10)
        if not typed:
            return _f("close never typed /exit into the window — nothing shows that close "
                      "did anything, so its dedupe proves nothing",
                      f"pane capture={rig.capture(target['index'])[-200:]!r}", _SERVER
                      + "::close_window", FailureClass.COLLAPSED_SENTINEL)
        rig.tmux("send-keys", "-t", target["pane_id"], "C-d")  # the agent honours /exit
        gone = rig.wait_for(lambda: target["pane_id"] not in {
            w["pane_id"] for w in C.windows(rig)}, timeout=15)
        if not gone:
            return _f("a closed window whose agent exited is still on the roster",
                      f"windows={[(w['index'], w['name'], w['closing']) for w in C.windows(rig)]}",
                      _SERVER + "::close_window")
        after = C.windows(rig)
        if {w["pane_id"] for w in after} != siblings or any(w["closing"] for w in after):
            return _f("closing one window disturbed another, or left a closing flag set",
                      f"want panes {sorted(siblings)}, got "
                      f"{[(w['pane_id'], w['closing']) for w in after]}", _SERVER)
        r = rig.post("/api/close", {"index": target["index"]})
        if r.status != 400:
            return _f("a close addressed to a vanished index was accepted",
                      f"{r.status} {r.body[:200]!r}", _SERVER)
        return None


def run_collision() -> Finding | None:
    """A roster session named `qe`, which is also an expert scope's name."""
    with console_rig(session="qe") as rig:
        C.seed_credentials(rig)
        first = C.spawn(rig, "qe")  # window `qe` in session `qe`
        if first.status != 200:
            return _f("fixture: the first spawn failed", f"{first.status} {first.body!r}",
                      "tests/qe/cases/console_integ_spawn_roundtrip.py",
                      FailureClass.COLLAPSED_SENTINEL)
        windows_before = len(C.tmux_rows(rig))
        second = C.spawn(rig, "main")
        log = rig.log_tail(600).strip().splitlines()[-1:]
        if second.status != 200 or len(C.tmux_rows(rig)) != windows_before + 1:
            return _f("with a window named like the roster session, every later spawn "
                      "fails: `new-window -t <session>` resolves the target to the "
                      "window of that name",
                      f"session={rig.session!r}, window named {rig.session!r} exists; "
                      f"POST /api/spawn main -> {second.status} "
                      f"{second.json().get('output', '')[-60:]!r}; "
                      f"windows {windows_before}->{len(C.tmux_rows(rig))}; "
                      f"console stderr tail={log}", _WINDOWS + "::_open_window")
        return None


def run_misattribution() -> Finding | None:
    """A window with no ledger row must not be handed another window's session."""
    with C.integ_rig() as rig:
        d = C.alpha(rig)
        if C.spawn(rig, "main").status != 200:
            return _f("fixture: spawn failed", "", "tests/qe/cases/_console_integ.py",
                      FailureClass.COLLAPSED_SENTINEL)
        owner = [r for r in C.tmux_rows(rig) if r["index"] != 0][0]
        sid, p = C.run_session_start_hook(rig, pane_id=owner["pane_id"], scope="main",
                                          cwd=d)
        if p.returncode != 0:
            return _f("fixture: hook failed", p.stderr[-300:],
                      "tests/qe/cases/_console_integ.py",
                      FailureClass.COLLAPSED_SENTINEL)
        # A second window of the same scope in the same checkout, started moments later
        # on the other harness, whose session has not written a ledger row.
        if C.spawn(rig, "main", harness="codex").status != 200:
            return _f("fixture: codex spawn failed", "",
                      "tests/qe/cases/_console_integ.py",
                      FailureClass.COLLAPSED_SENTINEL)
        rows = {w["pane_id"]: w for w in C.windows(rig)}
        stranger = next(w for w in rows.values()
                        if w["harness"] == "codex" and w["pane_id"] != owner["pane_id"])
        if rows[owner["pane_id"]]["session_id"] != sid:  # control: the join sees the row
            return _f("the window that owns the ledger row does not carry its session",
                      f"window {owner['pane_id']} session_id="
                      f"{rows[owner['pane_id']]['session_id']!r}, ledger {sid!r}",
                      _SERVER + "::attach_ledger_facts")
        if stranger["session_id"]:
            return _f("a window with no ledger row of its own was attributed the session "
                      "that another pane's row names, by the same-scope-and-cwd fallback "
                      "meant for rows that predate pane ids — the roster would show the "
                      "wrong session's transcript, which `attach_ledger_facts` promises "
                      "never to guess",
                      f"ledger: one row, session {sid} in pane {owner['pane_id']} "
                      f"(claude, scope main, cwd {d}); roster: codex window "
                      f"{stranger['pane_id']} (no row) session_id="
                      f"{stranger['session_id']!r}",
                      "packages/thalamus-console/src/thalamus_console/transcript.py"
                      "::LedgerIndex.legacy_match")
        return None


CASE = Case(
    name="console-spawn-roundtrip-agrees-across-tmux-ledger-and-rooms",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_JQ),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a spawned window carries the scope, harness, posture and room it was asked "
            "for, the pin ledger and roster agree about it, a room is provisioned once, "
            "and N concurrent closes dedupe to one without touching a sibling",
    run=run,
)

COLLISION = Case(
    name="console-spawn-survives-a-scope-named-like-its-session",
    issue=414,
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="after one window is named like the roster's tmux session, a later spawn "
            "still creates its window",
    run=run_collision,
)

MISATTRIBUTION = Case(
    name="console-ledger-fallback-never-claims-another-panes-session",
    issue=415,
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_JQ),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a window with no pin-ledger row is served as having none, even when another "
            "window of the same scope and checkout started moments before it and owns a "
            "row",
    run=run_misattribution,
)

CASES = (CASE, COLLISION, MISATTRIBUTION)
