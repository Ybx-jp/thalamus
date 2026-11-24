"""The console's roster is a join of tmux and the pin ledger, and the join must be exact.

`/api/panes` is the one thing the phone renders the whole control plane from, and it is
assembled from two sources that do not know about each other: tmux says which windows
exist, the pin ledger (written by a session's SessionStart hook) says which session is
in which pane. Each half has its own unit tests. What nothing asserts is that the *join*
stays exact when the two move independently — a window created, renamed or killed by
someone who is not the console (a desktop `tmux attach`, an operator's own
`new-window`), and a ledger that keeps rows for panes that are long gone.

Everything here runs against a real `thalamus console` subprocess (`_console_rig`) on a
private tmux socket and a redirected HOME. The second channel — what is *true* — is
tmux's own `list-windows`, read without going through the console, and the real
SessionStart hook for the ledger side (`_console_integ.run_session_start_hook`),
so neither half of the join is a fixture invented to agree with the reader.

**Properties asserted**

1. *Mirror.* The roster's `(index, name, pane_id)` set equals tmux's, after windows are
   created out of band, renamed, and killed; indices do not renumber when one closes;
   exactly the lowest index is the anchor.
2. *Harness is read off the start command, not the foreground process.* A window started
   as `claude` reads `claude`, `codex` reads `codex` (its foreground process is `node`),
   anything else reads empty — so a roster that keyed on `pane_current_command` would
   misfile the codex window.
3. *Pane identity, not name.* Two windows with the same name in the same checkout, each
   with its own ledger row, get their own `session_id`. A window with no row gets `""`
   and no guess. A ledger row for a pane that no longer exists produces no phantom
   window.
4. *Order independence (metamorphic).* Creating the same windows in a different order
   yields the same multiset of `(name, harness, cwd_label)` rows.

**Controls.** The probe must be able to see change: the roster is polled until it
reflects each out-of-band edit, and the case reports a collapsed sentinel if it never
does (a console serving a frozen list would otherwise fail every later assertion with a
misleading witness). The ledger half has its own control: a row written by the hook for a
pane must *appear* on that window before the absences are asserted.

**Shown capable of going red.** In a copy of the console tree
(`QE_CONSOLE_SRC=<copy>/packages/thalamus-console/src`), change
`attach_ledger_facts` so the pane lookup yields nothing (`row = None` in place of
`row = _LEDGER.by_pane(...)`): property 3 reports `invariant-falsified`, witness `pane
%4: roster session_id='', ledger session_id='f535…'` (run 2026-11-24).
"""

from __future__ import annotations

from ..model import Case, FailureClass, Finding, Substrate, Tier
from . import _console_integ as C

_SITE = "packages/thalamus-console/src/thalamus_console/server.py::list_windows"
_LEDGER_SITE = _SITE.replace("list_windows", "attach_ledger_facts")


def _view(rows):
    return sorted((w["index"], w["name"], w["pane_id"]) for w in rows)


def _tview(rows):
    return sorted((r["index"], r["name"], r["pane_id"]) for r in rows)


def _fail(summary, witness, cls=FailureClass.INVARIANT_FALSIFIED, site=_SITE):
    return Finding(cls, summary, witness=witness, site=site)


def _new(rig, name, command, cwd):
    return rig.tmux("new-window", "-d", "-t", rig.session + ":", "-n", name, "-c", cwd,
                    command)


def _settled(rig, want_names):
    """Poll until the roster shows exactly `want_names` (as a multiset)."""
    def check():
        got = sorted(w["name"] for w in C.windows(rig))
        return got == sorted(want_names) and got
    return rig.wait_for(check, timeout=10)


def run() -> Finding | None:
    with C.integ_rig() as rig:
        beta = str(rig.repos[1].resolve())

        base = C.windows(rig)
        truth = C.tmux_rows(rig)
        if _view(base) != _tview(truth) or len(base) != 1:
            return _fail("the freshly started console's roster is not tmux's window list",
                         f"roster={_view(base)} tmux={_tview(truth)}")

        # ---- 1 + 2: out-of-band create, harness, rename, kill ----
        made = {"w-claude": "claude", "w-codex": "codex", "w-plain": "cat"}
        for name, cmd in made.items():
            r = _new(rig, name, cmd, beta)
            if r.returncode != 0:
                return _fail("tmux refused to create a fixture window — the rig is unusable",
                             r.stderr, FailureClass.COLLAPSED_SENTINEL,
                             "tests/qe/cases/console_integ_roster.py")
        if not _settled(rig, ["main", *made]):
            return _fail("a window created outside the console never appeared on "
                         "/api/panes, so every later assertion would be about a frozen list",
                         f"roster names={[w['name'] for w in C.windows(rig)]} "
                         f"tmux={[r['name'] for r in C.tmux_rows(rig)]}",
                         FailureClass.COLLAPSED_SENTINEL)
        rows, truth = C.windows(rig), C.tmux_rows(rig)
        if _view(rows) != _tview(truth):
            return _fail("the roster's (index, name, pane) set differs from tmux's after "
                         "windows were created out of band",
                         f"roster={_view(rows)} tmux={_tview(truth)}")
        harness = {w["name"]: w["harness"] for w in rows}
        want = {"main": "claude", "w-claude": "claude", "w-codex": "codex", "w-plain": ""}
        # `main` is the rig's anchor, started as the stub `claude`.
        if harness != want:
            return _fail("a window's harness is not read off the command it was started "
                         "with", f"harness by window={harness}, want={want}")
        anchors = [w["index"] for w in rows if w["anchor"]]
        if anchors != [min(w["index"] for w in rows)]:
            return _fail("the anchor is not exactly the lowest-index window",
                         f"anchors={anchors} indices={[w['index'] for w in rows]}")

        victim = next(r for r in truth if r["name"] == "w-codex")
        rig.tmux("rename-window", "-t", victim["window_id"], "w-renamed")
        rig.tmux("kill-window", "-t", next(r for r in truth
                                           if r["name"] == "w-plain")["window_id"])
        if not _settled(rig, ["main", "w-claude", "w-renamed"]):
            return _fail("a rename and a kill made outside the console did not reach the "
                         "roster",
                         f"roster={[(w['index'], w['name']) for w in C.windows(rig)]} "
                         f"tmux={[(r['index'], r['name']) for r in C.tmux_rows(rig)]}")
        rows, truth = C.windows(rig), C.tmux_rows(rig)
        if _view(rows) != _tview(truth):
            return _fail("after a rename and a kill the roster's (index, name, pane) set "
                         "differs from tmux's — an index was renumbered or a pane reused",
                         f"roster={_view(rows)} tmux={_tview(truth)}")
        if next(w for w in rows if w["name"] == "w-renamed")["harness"] != "codex":
            return _fail("renaming a window changed the harness the roster reads for it",
                         f"rows={[(w['name'], w['harness']) for w in rows]}")

        # ---- 3: pane identity, not name ----
        for _ in range(2):
            _new(rig, "dup", "claude", beta)
        _settled(rig, ["main", "w-claude", "w-renamed", "dup", "dup"])
        dups = [r for r in C.tmux_rows(rig) if r["name"] == "dup"]
        ids = []
        for r in dups:
            sid, p = C.run_session_start_hook(rig, pane_id=r["pane_id"], scope="main",
                                              cwd=beta)
            if p.returncode != 0:
                return _fail("the real SessionStart hook failed under the rig HOME — the "
                             "ledger half of the join cannot be built", p.stderr[-300:],
                             FailureClass.COLLAPSED_SENTINEL,
                             "tests/qe/cases/_console_integ.py::run_session_start_hook")
            ids.append((r["pane_id"], sid))
        rows = C.windows(rig)
        by_pane = {w["pane_id"]: w for w in rows}
        # control: the ledger facts must show up where a row exists
        for pane, sid in ids:
            if by_pane[pane]["session_id"] != sid:
                return _fail("two windows sharing a name and a checkout were not told "
                             "apart by the pin ledger — each must carry the session "
                             "launched into its own pane",
                             f"pane {pane}: roster session_id="
                             f"{by_pane[pane]['session_id']!r}, ledger session_id={sid!r}; "
                             f"all rows={[(w['pane_id'], w['session_id']) for w in rows]}",
                             site=_LEDGER_SITE)
            if by_pane[pane]["project"] != "beta" or by_pane[pane]["repo_root"] != beta:
                return _fail("the ledger's project/repo_root did not reach the roster row",
                             f"pane {pane}: project={by_pane[pane]['project']!r} "
                             f"repo_root={by_pane[pane]['repo_root']!r} want beta/{beta}",
                             site=_LEDGER_SITE)
        if len({sid for _, sid in ids}) != 2:
            return _fail("fixture: the two hook runs minted one session id", repr(ids),
                         FailureClass.COLLAPSED_SENTINEL,
                         "tests/qe/cases/_console_integ.py")
        unrowed = by_pane[next(r for r in C.tmux_rows(rig)
                               if r["name"] == "w-claude")["pane_id"]]
        if unrowed["session_id"] or unrowed["project"] or unrowed["started"] is not None:
            return _fail("a window with no ledger row was given session facts — absence "
                         "must be served as absence, not inferred from the cwd",
                         f"w-claude row: session_id={unrowed['session_id']!r} "
                         f"project={unrowed['project']!r} started={unrowed['started']!r}",
                         site=_LEDGER_SITE)

        # a ledger row outlives its window; it must not resurrect it
        gone_pane, _gone_sid = ids[0]
        rig.tmux("kill-window", "-t", next(r for r in C.tmux_rows(rig)
                                            if r["pane_id"] == gone_pane)["window_id"])
        _settled(rig, ["main", "w-claude", "w-renamed", "dup"])
        rows, truth = C.windows(rig), C.tmux_rows(rig)
        if gone_pane in {w["pane_id"] for w in rows} or _view(rows) != _tview(truth):
            return _fail("a pin-ledger row for a pane tmux no longer has produced a "
                         "roster entry (or the roster diverged from tmux)",
                         f"killed pane={gone_pane}; roster={_view(rows)} tmux={_tview(truth)}")
        survivor = next(w for w in rows if w["pane_id"] == ids[1][0])
        if survivor["session_id"] != ids[1][1]:
            return _fail("killing one same-name window changed the sibling's session",
                         f"sibling pane {ids[1][0]} now session_id="
                         f"{survivor['session_id']!r}, want {ids[1][1]!r}",
                         site=_LEDGER_SITE)

        # ---- 4: creation order does not matter ----
        names = [("o-claude", "claude"), ("o-codex", "codex"), ("o-plain", "cat")]
        seen = []
        for order in (names, list(reversed(names)), [names[1], names[2], names[0]]):
            for r in C.tmux_rows(rig):
                if r["index"] != min(x["index"] for x in C.tmux_rows(rig)):
                    rig.tmux("kill-window", "-t", r["window_id"])
            for name, cmd in order:
                _new(rig, name, cmd, beta)
            _settled(rig, ["main", *[n for n, _ in names]])
            rows = C.windows(rig)
            seen.append(sorted((w["name"], w["harness"], w["cwd_label"]) for w in rows))
        if any(s != seen[0] for s in seen[1:]) or len(seen[0]) != 4:
            return _fail("the set of roster rows depends on the order windows were created "
                         "in", "; ".join(f"order {i}: {s}" for i, s in enumerate(seen)))
        return None


CASE = Case(
    name="console-roster-agrees-with-tmux-and-the-pin-ledger",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_JQ),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="windows created, renamed and killed outside the console appear on "
            "/api/panes exactly as tmux has them, and the pin ledger attaches to a pane, "
            "never to a name",
    run=run,
)
