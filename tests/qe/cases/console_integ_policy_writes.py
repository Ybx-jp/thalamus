"""The console's operator-state writes must agree with the core that reads them, and survive
the console being a threaded server.

The gear panel and the star in the spawn picker write three files under the operator's
HOME through the console: `~/.thalamus/launch/policy.json` (what posture a launched
window gets), `~/.thalamus/extractor/policy.json` (which CLI and model distil and ingest)
and `~/.thalamus/console/favorites.json`. The console does not read them back for its own
use — the core does, at launch and at extraction — so a write that the console
acknowledges and the core never sees is a setting the operator thinks they changed. The
HTTP server is `ThreadingHTTPServer`, so two requests can be in those write paths at once;
two taps on a phone, or the panel's own retry, are enough.

Real `thalamus console` subprocess on a redirected HOME (`_console_rig`); the second
channel is the core's own reader run as a subprocess with the same HOME
(`_console_integ.py`), the real launch path (a spawned window's argv), and the files.

**Cases**

1. `console-policy-posts-agree-with-the-core-that-reads-them` — a POST to
   `/api/launch-policy` and `/api/extractor-policy` is what `GET`, the core's own
   `effective()` readers, and the next spawn's argv all report; repeating the same POST
   leaves the store's bytes unchanged and the view equal (idempotent in effect — the
   ledger does gain a `same` row, which is the audit trail and not asserted away); a
   refused POST (unknown harness, unknown model, unknown pass, a lifetime on a narrowing)
   leaves both store and ledger untouched; every ledger line is a JSON object.
2. `console-policy-staleness-flags-a-window-launched-looser-than-the-posture` — a window
   launched under `--permission-mode acceptEdits` while the posture is changed to `manual`
   ("ask every time", which has no argv) is flagged `policy_stale`, exactly as it is when
   the posture changes to `auto`.
3. `console-launch-policy-concurrent-posts-lose-nothing`,
   `console-extractor-policy-concurrent-posts-lose-nothing`,
   `console-favorites-concurrent-writes-lose-nothing` — each round fires one POST per
   key from a barrier (three harnesses; the two extraction passes; two directories'
   stars) and then asserts that the store parses and holds every selection the console
   answered 200 to. A store that cannot be parsed, or that has dropped an acknowledged
   selection, is the finding. The launch and extractor stores are written with
   `Path.write_text` after an unlocked read-modify-write; `set_favorite` replaces the file
   atomically but reads, edits and writes the whole list unlocked, and shares one `.tmp`
   name between writers.

**Controls.** Every state reader is first shown to see a sequential write (otherwise "no
loss" is "the reader sees nothing"), and each concurrent case begins from rounds in which
the posts are serialised and must come out lossless — so a red is the concurrency, not a
fixture that cannot hold two keys.

**Shown capable of going red AND of going green.** Red is the current tree. For green,
copy the console tree (`QE_CONSOLE_SRC`), rename `Handler.do_POST` to `_do_post_inner`
and add a `do_POST` that calls it under one module-level `threading.Lock()` (run
2026-11-24): the three concurrent cases then pass over all their rounds, and the
agreement case still passes. The staleness case goes green when
`_contains_run(start.split(), want)` is replaced by a comparison that treats an empty
`want` as "no `--permission-mode` flag expected".
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier
from . import _console_integ as C

_SERVER = "packages/thalamus-console/src/thalamus_console/server.py"
_LAUNCH = "src/thalamus/harness/launch_policy.py::select"
_EXTRACT = "src/thalamus/harness/extractor_policy.py::select"


def _f(summary, witness, site, cls=FailureClass.INVARIANT_FALSIFIED):
    return Finding(cls, summary, witness=witness, site=site)


def _launch_store(rig) -> Path:
    return rig.home / ".thalamus" / "launch" / "policy.json"


def _launch_ledger(rig) -> Path:
    return rig.home / ".thalamus" / "launch" / "policy.jsonl"


def _ext_store(rig) -> Path:
    return rig.home / ".thalamus" / "extractor" / "policy.json"


def _ext_ledger(rig) -> Path:
    return rig.home / ".thalamus" / "extractor" / "policy.jsonl"


def _lines(path: Path) -> list[str]:
    try:
        return path.read_text().splitlines()
    except OSError:
        return []


def _ledger_malformed(path: Path) -> str:
    for n, line in enumerate(_lines(path), 1):
        try:
            if not isinstance(json.loads(line), dict):
                return f"{path.name} line {n} is not an object: {line[:80]!r}"
        except ValueError:
            return f"{path.name} line {n} does not parse: {line[:80]!r}"
    return ""


def _bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def _launch_view(rig, harness="claude"):
    for h in rig.get("/api/launch-policy").json()["harnesses"]:
        if h["harness"] == harness:
            return {c["key"]: c["value"] for c in h["capabilities"]}
    return {}


def _launch_post(rig, harness, value, **extra):
    return rig.post("/api/launch-policy", {"harness": harness,
                                           "capability": "permission_posture",
                                           "value": value, **extra})


def _ext_view(rig):
    out = {}
    for p in rig.get("/api/extractor-policy").json()["passes"]:
        out[p["pass"]] = (p["value"]["harness"], p["value"]["model"])
    return out


# ---------------------------------------------------------------- agreement


def run_agree() -> Finding | None:
    with C.integ_rig() as rig:
        # ---- launch policy ----
        r = _launch_post(rig, "claude", "acceptEdits")
        if r.status != 200:
            return _f("a legal launch-policy POST was refused", f"{r.status} {r.body[:200]!r}",
                      _SERVER)
        if _launch_view(rig) != {"permission_posture": "acceptEdits"}:
            return _f("GET /api/launch-policy does not report the posture just POSTed",
                      repr(_launch_view(rig)), _SERVER + "::launch_policy_view")
        core = C.py(rig, "import json; from thalamus.harness import launch_policy as p; "
                         "print(json.dumps(p.effective('claude')))")
        if core.returncode != 0 or json.loads(core.stdout) != {
                "permission_posture": "acceptEdits"}:
            return _f("the core's own reader does not see the posture the console wrote "
                      "(or the reader could not run)",
                      f"rc={core.returncode} out={core.stdout!r} err={core.stderr[-200:]!r}",
                      _LAUNCH)
        if C.spawn(rig, "main").status != 200:
            return _f("fixture: spawn failed", "", "tests/qe/cases/_console_integ.py",
                      FailureClass.COLLAPSED_SENTINEL)
        win = [w for w in C.windows(rig) if not w["anchor"]][0]
        start = rig.tmux("display-message", "-p", "-t", win["pane_id"],
                         "#{pane_start_command}").stdout
        if "--permission-mode acceptEdits" not in start:
            return _f("a window spawned after the POST was not launched under the posture "
                      "the POST selected", f"start command={start.strip()!r}",
                      "src/thalamus/harness/launcher.py")
        # idempotent in effect
        before = _bytes(_launch_store(rig))
        view = rig.get("/api/launch-policy").body
        again = _launch_post(rig, "claude", "acceptEdits")
        if (again.status != 200 or _bytes(_launch_store(rig)) != before
                or rig.get("/api/launch-policy").body != view):
            return _f("repeating the same launch-policy POST changed the store or the view",
                      f"status={again.status}; store before={before!r} "
                      f"after={_bytes(_launch_store(rig))!r}", _LAUNCH)
        # refusals leave no trace
        snap = (_bytes(_launch_store(rig)), _lines(_launch_ledger(rig)))
        for body in ({"harness": "emacs", "capability": "permission_posture", "value": "auto"},
                     {"harness": "claude", "capability": "nope", "value": "auto"},
                     {"harness": "claude", "capability": "permission_posture",
                      "value": "yolo"},
                     {"harness": "claude", "capability": "permission_posture",
                      "value": "manual", "ttl_hours": 24},
                     {"harness": "cursor", "capability": "permission_posture",
                      "value": "force", "ttl_hours": 7},
                     {"harness": "claude", "capability": "permission_posture",
                      "value": "auto", "ttl_hours": "x"}):
            r = rig.post("/api/launch-policy", body)
            if r.status not in (400, 409):
                return _f("an illegal launch-policy request was accepted",
                          f"{body}: {r.status} {r.body[:160]!r}", _SERVER)
        if (_bytes(_launch_store(rig)), _lines(_launch_ledger(rig))) != snap:
            return _f("a refused launch-policy POST changed the store or wrote a ledger row",
                      f"ledger rows {len(snap[1])} -> {len(_lines(_launch_ledger(rig)))}",
                      _LAUNCH)
        if _ledger_malformed(_launch_ledger(rig)):
            return _f("the launch-policy ledger holds a line that is not a JSON object",
                      _ledger_malformed(_launch_ledger(rig)), _LAUNCH)

        # ---- extractor policy ----
        r = rig.post("/api/extractor-policy", {"harness": "claude", "model": "sonnet",
                                               "pass": "distill"})
        r2 = rig.post("/api/extractor-policy", {"harness": "codex", "model": "",
                                                "pass": "ingest"})
        if r.status != 200 or r2.status != 200:
            return _f("a legal extractor-policy POST was refused",
                      f"{r.status} {r.body[:160]!r}; {r2.status} {r2.body[:160]!r}", _SERVER)
        want = {"distill": ("claude", "sonnet"), "ingest": ("codex", "")}
        if _ext_view(rig) != want:
            return _f("GET /api/extractor-policy does not report the selections POSTed",
                      f"view={_ext_view(rig)} want={want}", _SERVER + "::extractor_policy_view")
        core = C.py(rig, "import json; from thalamus.harness import extractor_policy as p; "
                         "print(json.dumps({k: p.effective(k) for k in p.PASS_KEYS}))")
        got = json.loads(core.stdout) if core.returncode == 0 else {}
        if {k: (v.get("harness"), v.get("model", "")) for k, v in got.items()} != want:
            return _f("the core's own extractor reader does not see what the console wrote",
                      f"rc={core.returncode} out={core.stdout!r} err={core.stderr[-200:]!r}",
                      _EXTRACT)
        before = _bytes(_ext_store(rig))
        if (rig.post("/api/extractor-policy", {"harness": "claude", "model": "sonnet",
                                               "pass": "distill"}).status != 200
                or _bytes(_ext_store(rig)) != before):
            return _f("repeating the same extractor-policy POST changed the store",
                      f"before={before!r} after={_bytes(_ext_store(rig))!r}", _EXTRACT)
        snap = (_bytes(_ext_store(rig)), _lines(_ext_ledger(rig)))
        for body, codes in (({"harness": "emacs"}, (409,)),
                            ({"harness": "claude", "model": "gpt-9"}, (409,)),
                            ({"harness": "claude", "pass": "zzz"}, (400,)),
                            ({"harness": "", "model": "sonnet"}, (409,))):
            r = rig.post("/api/extractor-policy", body)
            if r.status not in codes:
                return _f("an illegal extractor-policy request got the wrong status",
                          f"{body}: {r.status} (want {codes}) {r.body[:160]!r}", _SERVER)
        if (_bytes(_ext_store(rig)), _lines(_ext_ledger(rig))) != snap:
            return _f("a refused extractor-policy POST changed the store or wrote a ledger "
                      "row", f"ledger rows {len(snap[1])} -> {len(_lines(_ext_ledger(rig)))}",
                      _EXTRACT)
        if _ledger_malformed(_ext_ledger(rig)):
            return _f("the extractor-policy ledger holds a line that is not a JSON object",
                      _ledger_malformed(_ext_ledger(rig)), _EXTRACT)
        return None


def run_stale() -> Finding | None:
    with C.integ_rig() as rig:
        _launch_post(rig, "claude", "acceptEdits")
        if C.spawn(rig, "main").status != 200:
            return _f("fixture: spawn failed", "", "tests/qe/cases/_console_integ.py",
                      FailureClass.COLLAPSED_SENTINEL)
        pane = [w for w in C.windows(rig) if not w["anchor"]][0]["pane_id"]

        def stale():
            return next(w for w in C.windows(rig) if w["pane_id"] == pane)["policy_stale"]

        if stale():
            return _f("a window launched under the current posture reads stale",
                      "posture acceptEdits, window launched under acceptEdits",
                      _SERVER, FailureClass.COLLAPSED_SENTINEL)
        _launch_post(rig, "claude", "auto")
        if not stale():  # control: the flag can fire for this window at all
            return _f("the staleness flag never fires, so it cannot be judged for `manual`",
                      "posture auto vs a window launched under acceptEdits: policy_stale "
                      "False", _SERVER, FailureClass.COLLAPSED_SENTINEL)
        _launch_post(rig, "claude", "acceptEdits")
        _launch_post(rig, "claude", "manual")
        start = rig.tmux("display-message", "-p", "-t", pane,
                         "#{pane_start_command}").stdout.strip()
        if not stale():
            return _f("a window still running `--permission-mode acceptEdits` is not "
                      "flagged stale after the posture is set to `manual` (ask every "
                      "time) — the direction in which the operator tightens the posture "
                      "is the one where a running window silently stays looser",
                      f"posture manual, window start command {start!r}, "
                      f"policy_stale={stale()}",
                      _SERVER + "::list_windows (policy_stale / _contains_run)")
        return None


# ------------------------------------------------------------- concurrency


def _race(rig, rounds, jobs_for, read, store: Path, ledger: Path | None):
    """Fire `jobs_for(rnd)` = [(key, want, post_fn)] from a barrier, `rounds` times.

    Returns a witness string at the first violation, else "". Serialised rounds come
    first (control); the concurrent ones follow.
    """
    for mode in ("serial", "concurrent"):
        for rnd in range(rounds if mode == "concurrent" else 3):
            jobs = jobs_for(rnd)
            results: dict[str, int] = {}
            gate = threading.Barrier(len(jobs) if mode == "concurrent" else 1)

            def go(key, post):
                gate.wait()
                results[key] = post().status
            if mode == "serial":
                for key, _want, post in jobs:
                    go(key, post)
            else:
                ts = [threading.Thread(target=go, args=(k, p)) for k, _w, p in jobs]
                [t.start() for t in ts]
                [t.join() for t in ts]
            try:
                state = read()
            except Exception as exc:  # noqa: BLE001 — an unparsable store is the finding
                return (f"{mode} round {rnd}: the store cannot be read after the posts "
                        f"({type(exc).__name__}: {exc}); file now {_bytes(store)[-120:]!r}")
            for key, want, _post in jobs:
                if results.get(key) == 200 and state.get(key) != want:
                    return (f"{mode} round {rnd}: POST for {key!r} answered 200 with "
                            f"{want!r} but the store holds {state.get(key)!r} "
                            f"(statuses {results}, state {state})")
            if mode == "serial" and ledger is not None and _ledger_malformed(ledger):
                return _ledger_malformed(ledger)
    return _ledger_malformed(ledger) if ledger else ""


def run_launch_race() -> Finding | None:
    with C.integ_rig() as rig:
        values = {"claude": ["acceptEdits", "auto", "manual"],
                  "cursor": ["force", "manual", "auto-review"],
                  "codex": ["auto", "manual", "workspace-write"]}

        def jobs_for(rnd):
            return [(h, v[rnd % 3], (lambda h=h, val=v[rnd % 3]: _launch_post(rig, h, val)))
                    for h, v in values.items()]

        def read():
            raw = json.loads(_launch_store(rig).read_text())["harnesses"]
            return {h: raw.get(h, {}).get("permission_posture", {}).get("value")
                    for h in values}

        witness = _race(rig, 40, jobs_for, read, _launch_store(rig), _launch_ledger(rig))
        if not witness:
            return None
        if witness.startswith("serial"):
            return _f("fixture: the serialised control rounds failed", witness,
                      "tests/qe/cases/console_integ_policy_writes.py",
                      FailureClass.COLLAPSED_SENTINEL)
        return _f("concurrent launch-policy POSTs corrupted or dropped an acknowledged "
                  "selection — select() reads the store, edits it and rewrites it with "
                  "write_text, unlocked and non-atomically, inside a threaded server",
                  witness, _LAUNCH)


def run_extractor_race() -> Finding | None:
    with C.integ_rig() as rig:
        vals = ["claude", "codex", ""]

        def jobs_for(rnd):
            out = []
            for i, p in enumerate(("distill", "ingest")):
                v = vals[(rnd + i) % 3]
                out.append((p, (v, ""), (lambda p=p, v=v: rig.post(
                    "/api/extractor-policy", {"harness": v, "model": "", "pass": p}))))
            return out

        def read():
            raw = json.loads(_ext_store(rig).read_text())["passes"]
            return {p: (raw.get(p, {}).get("harness"), raw.get(p, {}).get("model"))
                    for p in ("distill", "ingest")}

        witness = _race(rig, 60, jobs_for, read, _ext_store(rig), _ext_ledger(rig))
        if not witness:
            return None
        if witness.startswith("serial"):
            return _f("fixture: the serialised control rounds failed", witness,
                      "tests/qe/cases/console_integ_policy_writes.py",
                      FailureClass.COLLAPSED_SENTINEL)
        return _f("concurrent extractor-policy POSTs corrupted or dropped an acknowledged "
                  "selection — select() reads, edits and rewrites the store with "
                  "write_text, unlocked and non-atomically", witness, _EXTRACT)


def run_favorites_race() -> Finding | None:
    with C.integ_rig() as rig:
        dirs = [str(p.resolve()) for p in rig.repos]

        def post(d, fav):
            return rig.post("/api/favorite", {"path": d, "favorite": fav})

        def jobs_for(rnd):
            return [(dirs[0], rnd % 2 == 0, (lambda: post(dirs[0], rnd % 2 == 0))),
                    (dirs[1], rnd % 2 == 1, (lambda: post(dirs[1], rnd % 2 == 1)))]

        def read():
            return {d["path"]: d["favorite"]
                    for d in rig.get("/api/spawn-options").json()["dirs"]}

        witness = _race(rig, 40, jobs_for, read,
                        rig.home / ".thalamus" / "console" / "favorites.json", None)
        if not witness:
            return None
        if witness.startswith("serial"):
            return _f("fixture: the serialised control rounds failed", witness,
                      "tests/qe/cases/console_integ_policy_writes.py",
                      FailureClass.COLLAPSED_SENTINEL)
        return _f("concurrent star toggles on different directories lost one — "
                  "set_favorite reads the whole list, edits it and replaces the file with "
                  "no lock, and writers share one `.tmp` name", witness,
                  _SERVER + "::set_favorite")


_SUB = (Substrate.NEEDS_TMUX,)
_CLS = (FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL)

AGREE = Case(
    name="console-policy-posts-agree-with-the-core-that-reads-them",
    tier=Tier.FAST, substrate=_SUB, classes=_CLS,
    summary="a launch- or extractor-policy POST is what GET, the core's own reader and the "
            "next spawn's argv report; a repeat is idempotent and a refusal leaves no trace",
    run=run_agree,
)
STALE = Case(
    name="console-policy-staleness-flags-a-window-launched-looser-than-the-posture",
    issue=416,
    tier=Tier.FAST, substrate=_SUB, classes=_CLS,
    summary="a window launched under a permissive posture is flagged stale when the "
            "posture is tightened to `manual`, as it is when it changes to another flag",
    run=run_stale,
)
LAUNCH_RACE = Case(
    name="console-launch-policy-concurrent-posts-lose-nothing",
    issue=417,
    tier=Tier.FAST, substrate=_SUB, classes=_CLS,
    summary="simultaneous launch-policy POSTs for different harnesses leave a parseable "
            "store holding every selection answered 200",
    run=run_launch_race,
)
EXTRACTOR_RACE = Case(
    name="console-extractor-policy-concurrent-posts-lose-nothing",
    issue=417,
    tier=Tier.FAST, substrate=_SUB, classes=_CLS,
    summary="simultaneous extractor-policy POSTs for the two passes leave a parseable "
            "store holding both selections",
    run=run_extractor_race,
)
FAVORITES_RACE = Case(
    name="console-favorites-concurrent-writes-lose-nothing",
    issue=417,
    tier=Tier.FAST, substrate=_SUB, classes=_CLS,
    summary="simultaneous star toggles on two directories both persist",
    run=run_favorites_race,
)

CASES = (AGREE, STALE, LAUNCH_RACE, EXTRACTOR_RACE, FAVORITES_RACE)
