"""A room dispatch reaches exactly the room's members, whole or not at all.

`POST /api/dispatch` is the console's fan-out verb: type one message into every live member
of a room, without approving anything. Its safety claim is spread across three layers that
each look correct alone — the room's `sessions/` descriptor roster (what the harness says
is alive in the room), the pin ledger (which tmux pane each session owns), and tmux itself
(which panes exist) — and the property that matters is the one across all three: the text
lands in the panes of the room's members and in no other pane, and when it cannot land in
all of them it lands in none.

Real `thalamus console` subprocess, private tmux socket, redirected HOME (`_console_rig`);
members are windows the console itself spawned into room `r1`, their pin-ledger rows are
written by the real SessionStart hook run in each pane's own environment, and delivery is
read back with `capture-pane`. The one thing supplied by hand is each member's
`sessions/<id>.json` descriptor — only Claude Code writes those and the rig's stub agent is
`cat` — with the `pid` of the pane's process and the status the case wants the harness to
have published.

**Properties asserted**

1. *Exactly the room.* With two idle members in `r1`, one roomless window, and the anchor:
   `delivered` is 2, the message text appears in both members' panes, and in neither the
   outsider's nor the anchor's. The audit rows under `~/.thalamus/guards/` are two, with
   the response's handle.
2. *Dry run delivers nothing.* `dryRun` returns the same two targets, `delivered` 0, writes
   no audit rows, and no pane shows the text.
3. *Text is data.* A message that is a tmux argument (`-t %0 ; kill-server`) and ends in
   the one character tmux consumes (`;`) arrives byte-for-byte in the members' panes, still
   reaches no other pane, and the tmux server is alive afterwards.
4. *All or nothing.* With a third member whose descriptor says `waiting`, the default
   dispatch is 409 naming it and *no* idle member received the text; `partial: true`
   delivers to the two idle ones, reports the third in `undelivered`, and the waiting
   member's pane stays empty.
5. *Refusals are refusals.* Invalid room name, empty message, non-list `to`, a room with no
   members, and a `to` naming a scope nobody in the room holds are 4xx and type nothing
   anywhere.

**Controls.** The delivered text is first shown visible: the case reads its own pane back
after a delivery that must land, so "nothing appeared in the outsider's pane" cannot be
"`capture-pane` cannot see typed text". The outsider and the anchor each have a
`cat` in the foreground, which echoes anything typed into them.

**Shown capable of going red.** In a copy of the console tree (`QE_CONSOLE_SRC`), change
`dispatch.dispatch`'s `error = send(target.pane, text, submit)` to send to
`"%0"` (the anchor's pane) instead of `target.pane`: property 1 reports the text in the
anchor's pane and absent from the members'. Change `if blocked and not partial:` to
`if False:` and property 4 reports the idle members receiving a message the dispatch
should have refused.
"""

from __future__ import annotations

import json
import time
import uuid

from ..model import Case, FailureClass, Finding, Substrate, Tier
from . import _console_integ as C

_SERVER = "packages/thalamus-console/src/thalamus_console/server.py::do_POST"
_DISPATCH = "packages/thalamus-console/src/thalamus_console/dispatch.py::dispatch"
_FIX = "tests/qe/cases/console_integ_dispatch_room.py"


def _f(summary, witness, site=_DISPATCH, cls=FailureClass.INVARIANT_FALSIFIED):
    return Finding(cls, summary, witness=witness, site=site)


def _descriptor(rig, room, win, sid, scope, status):
    d = rig.home / ".thalamus" / "rooms" / room / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.json").write_text(json.dumps({
        "pid": win["pane_pid"], "sessionId": sid, "cwd": win["cwd"],
        "agent": f"thalamus-{scope}" if scope != "main" else "",
        "name": f"{room}-{scope}", "status": status,
        "updatedAt": int(time.time() * 1000)}))


def _screen(rig, pane):
    return rig.tmux("capture-pane", "-p", "-J", "-t", pane, "-S", "-200").stdout


def _guard_rows(rig):
    out = []
    for p in sorted((rig.home / ".thalamus" / "guards").glob("*.jsonl")):
        for line in p.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"unparsable": line})
    return out


def _dispatch(rig, **body):
    return rig.post("/api/dispatch", {"room": "r1", **body}, timeout=30)


def run() -> Finding | None:
    with C.integ_rig() as rig:
        C.seed_credentials(rig)
        d = C.alpha(rig)
        members = {}
        for scope in ("main", "qe"):
            if C.spawn(rig, scope, room="r1").status != 200:
                return _f("fixture: spawn into the room failed", scope, _FIX,
                          FailureClass.COLLAPSED_SENTINEL)
        if C.spawn(rig, "main").status != 200:
            return _f("fixture: roomless spawn failed", "", _FIX,
                      FailureClass.COLLAPSED_SENTINEL)
        rows = C.windows(rig)
        for w in rows:
            if w["room"] == "r1":
                sid, p = C.run_session_start_hook(rig, pane_id=w["pane_id"], scope="",
                                                  cwd=d, from_pid=w["pane_pid"])
                if p.returncode != 0:
                    return _f("fixture: hook failed", p.stderr[-300:], _FIX,
                              FailureClass.COLLAPSED_SENTINEL)
                members[w["name"]] = (w, sid)
                _descriptor(rig, "r1", w, sid, w["name"], "idle")
        outsider = next(w for w in rows if not w["room"] and not w["anchor"])
        anchor = next(w for w in rows if w["anchor"])
        member_panes = {w["pane_id"] for w, _ in members.values()}
        if len(members) != 2 or len(member_panes | {outsider["pane_id"],
                                                    anchor["pane_id"]}) != 4:
            return _f("fixture: expected two room members, an outsider and an anchor",
                      f"members={sorted(members)} windows={[w['pane_id'] for w in rows]}",
                      _FIX, FailureClass.COLLAPSED_SENTINEL)

        def seen(token):
            return {w["pane_id"] for w in C.windows(rig)
                    if token in _screen(rig, w["pane_id"])}

        # ---- 2: dry run first, so it cannot be contaminated by a real send ----
        dry_token = "QE-DRY-" + uuid.uuid4().hex[:8]
        r = _dispatch(rig, message=dry_token, dryRun=True)
        if (r.status != 200 or len(r.json().get("targets", [])) != 2
                or r.json().get("delivered") != 0):
            return _f("a dry run did not report two targets and zero deliveries",
                      f"{r.status} {r.body[:300]!r}")
        time.sleep(0.4)
        if seen(dry_token) or _guard_rows(rig):
            return _f("a dry run typed into a pane or wrote an audit row",
                      f"panes showing it={sorted(seen(dry_token))} "
                      f"guard rows={_guard_rows(rig)}")

        # ---- 1: exactly the room ----
        token = "QE-LIVE-" + uuid.uuid4().hex[:8]
        r = _dispatch(rig, message=token)
        if r.status != 200 or r.json().get("delivered") != 2:
            return _f("a dispatch to two idle members did not deliver to both",
                      f"{r.status} {r.body[:400]!r}")
        got = rig.wait_for(lambda: seen(token) >= member_panes and seen(token), timeout=8)
        leaked = seen(token) - member_panes
        if leaked:
            return _f("a room dispatch typed into a pane outside the room",
                      f"token {token}: in {sorted(seen(token))}, members "
                      f"{sorted(member_panes)}, outsider={outsider['pane_id']}, "
                      f"anchor={anchor['pane_id']}")
        if not got:  # control: delivered text is visible at all
            return _f("the delivered text never appeared in a member's pane",
                      f"panes showing it={sorted(seen(token))}, members={sorted(member_panes)}",
                      _DISPATCH, FailureClass.COLLAPSED_SENTINEL)
        rows_ = [x for x in _guard_rows(rig) if isinstance(x, dict)]
        if len(rows_) != 2 or any(x.get("unparsable") for x in rows_):
            return _f("the dispatch audit rows are not one per delivery",
                      f"{rows_}", _DISPATCH + "::_append_rows")

        # ---- 3: text is data ----
        hostile = "-t %0 ; kill-server ;"
        r = _dispatch(rig, message=hostile)
        time.sleep(0.5)
        if r.status != 200 or r.json().get("delivered") != 2:
            return _f("a hostile-looking message was not delivered", f"{r.status} "
                      f"{r.body[:300]!r}")
        if rig.tmux("list-sessions").returncode != 0:
            return _f("a dispatched message executed as a tmux command — the server is "
                      "gone", hostile, _DISPATCH + "::_send")
        for w, _ in members.values():
            if hostile.rstrip() not in _screen(rig, w["pane_id"]):
                return _f("a dispatched message did not arrive byte-for-byte",
                          f"sent {hostile!r}; pane shows "
                          f"{_screen(rig, w['pane_id'])[-160:]!r}",
                          "packages/thalamus-console/src/thalamus_console/tmux.py"
                          "::literal_text_args")
        if seen("kill-server") - member_panes:
            return _f("a hostile dispatch reached a non-member pane",
                      f"{sorted(seen('kill-server') - member_panes)}")

        # ---- 4: all or nothing ----
        if C.spawn(rig, "literature", room="r1").status != 200:
            return _f("fixture: third member spawn failed", "", _FIX,
                      FailureClass.COLLAPSED_SENTINEL)
        third = next(w for w in C.windows(rig) if w["name"] == "literature")
        sid, p = C.run_session_start_hook(rig, pane_id=third["pane_id"], scope="", cwd=d,
                                          from_pid=third["pane_pid"])
        _descriptor(rig, "r1", third, sid, "literature", "waiting")
        token2 = "QE-ALL-" + uuid.uuid4().hex[:8]
        r = _dispatch(rig, message=token2)
        time.sleep(0.5)
        if r.status != 409 or "literature" not in r.body.decode():
            return _f("a fan-out with a `waiting` member was not refused naming it",
                      f"{r.status} {r.body[:300]!r}")
        if seen(token2):
            return _f("a refused fan-out still typed into a pane — the pre-flight is "
                      "not all-or-nothing", f"panes showing {token2}: {sorted(seen(token2))}")
        token3 = "QE-PART-" + uuid.uuid4().hex[:8]
        r = _dispatch(rig, message=token3, partial=True)
        got = rig.wait_for(lambda: seen(token3) >= member_panes, timeout=8)
        if (r.status != 200 or r.json().get("delivered") != 2
                or "literature" not in " ".join(r.json().get("undelivered", []))):
            return _f("a partial dispatch did not deliver to the two idle members and "
                      "name the waiting one", f"{r.status} {r.body[:400]!r}")
        if not got or seen(token3) != member_panes:
            return _f("a partial dispatch reached the wrong set of panes",
                      f"in {sorted(seen(token3))}, want {sorted(member_panes)} (waiting "
                      f"member {third['pane_id']} must stay empty)")

        # ---- 5: refusals ----
        probe = "QE-REFUSED-" + uuid.uuid4().hex[:8]
        for body, codes in (({"room": "../x", "message": probe}, (400,)),
                            ({"room": "", "message": probe}, (400,)),
                            ({"room": "r1", "message": "   "}, (400,)),
                            ({"room": "r1", "message": probe, "to": "qe"}, (400,)),
                            ({"room": "r1", "message": probe, "to": [1]}, (400,)),
                            ({"room": "r9", "message": probe}, (409,)),
                            ({"room": "r1", "message": probe, "to": ["architect"]}, (409,))):
            r = rig.post("/api/dispatch", body, timeout=30)
            if r.status not in codes:
                return _f("a malformed or empty dispatch got the wrong status",
                          f"{body}: {r.status} (want {codes}) {r.body[:200]!r}", _SERVER)
        time.sleep(0.4)
        if seen(probe):
            return _f("a refused dispatch typed into a pane",
                      f"{probe} in {sorted(seen(probe))}", _DISPATCH)
        return None


CASE = Case(
    name="console-dispatch-reaches-exactly-the-rooms-members-or-none",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_JQ),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a room dispatch types into the panes of the room's live members and no other "
            "pane, a dry run types nothing, and a fan-out one member cannot take is "
            "refused whole unless partial",
    run=run,
)
