"""Every member the pin ledger places in a room must be addressable by dispatch.

Corpus record: `dispatch-cannot-address-main` (lab/056). `--to main` can never reach a
room's `main`: `preflight` filters on `LiveSession.scope`, which is derived from the
session's `--agent`, and `main` has no manifest to be launched with. So the one member
present in every room is a legitimate member with no address.

The asymmetry is what makes it worth pinning. With no `--to` filter the main member is
returned — it is in the room, it is on a pane, dispatch can see it — and naming it makes
it vanish. A caller cannot distinguish "that member is not here" from "that member
cannot be named", so the failure reads as an empty room rather than as a broken address.

The membership list drives the check rather than a hand-written roster, which is the
form the record asks for: every row the ledger places on a pane in this room is asserted
addressable under its own recorded scope. A case listing the scopes it expects would
keep passing when a new unaddressable member class arrives.

The fixture borrows `_descriptor` from dev's dispatch tests rather than restating the
session-descriptor shape. A second constructor here could drift from the one the rest of
the suite builds, and this case would then be asserting against a room shape nothing
else produces. `preflight` takes `config_dir`, `pins_file` and `panes` as parameters, so
none of this needs a live room, a real tmux server or the operator's config dir.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_ROOM = "qe-probe-room"


def _descriptor_helper():
    tests_dir = str(Path(__file__).resolve().parents[2])
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_dispatch import _descriptor  # noqa: PLC0415

    return _descriptor


def run() -> Finding | None:
    from thalamus.harness import dispatch  # noqa: PLC0415

    descriptor = _descriptor_helper()
    root = Path(tempfile.mkdtemp(prefix="qe-dispatch-"))
    try:
        config, pins = root / "room", root / "pins.jsonl"
        sessions = config / "sessions"

        # An ordinary expert member, launched with its manifest.
        descriptor(sessions, "qe", "sid-qe", 101, "idle")
        # The room's `main`: launched with no `--agent`, because no manifest exists for
        # it. Written directly rather than through the helper, which names an agent by
        # construction — the absent key IS the condition under test.
        sessions.mkdir(parents=True, exist_ok=True)
        (sessions / "102.json").write_text(json.dumps({
            "sessionId": "sid-main",
            "pid": 102,
            "cwd": "/home/op/code/thalamus",
            "name": f"{_ROOM}-main",
            "status": "idle",
            "updatedAt": 1000,
        }))

        membership = [
            {"session_id": "sid-qe", "scope": "qe", "room": _ROOM, "tmux_pane": "%11"},
            {"session_id": "sid-main", "scope": "main", "room": _ROOM, "tmux_pane": "%12"},
        ]
        pins.write_text("\n".join(json.dumps(row) for row in membership))
        panes = {row["tmux_pane"] for row in membership}

        everyone = dispatch.preflight(
            _ROOM, None, config_dir=config, pins_file=pins, panes=panes
        )
        seen = {target.session_id for target in everyone}

        # CONTROL: the unfiltered call must see the whole membership. If it does not,
        # the fixture is wrong — a descriptor the reader skipped, a ledger row it could
        # not place — and every "unaddressable" verdict below would be an artifact.
        missing = [row["session_id"] for row in membership if row["session_id"] not in seen]
        if missing:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the fixture's own members are not visible to an unfiltered "
                        "preflight, so this case cannot tell unaddressable from absent",
                witness=f"ledger places {[r['session_id'] for r in membership]}; "
                        f"preflight saw {sorted(seen)}",
                site="tests/qe/cases/dispatch_addressability.py",
            )

        unaddressable: list[str] = []
        for row in membership:
            named = dispatch.preflight(
                _ROOM, [row["scope"]], config_dir=config, pins_file=pins, panes=panes
            )
            if row["session_id"] not in {target.session_id for target in named}:
                unaddressable.append(
                    f"--to {row['scope']} returns {len(named)} target(s) and not "
                    f"{row['session_id']}, which the ledger places on {row['tmux_pane']}"
                )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # CONTROL: at least one member must be addressable. All of them failing means the
    # scope filter is broken outright rather than blind to one member class, which is a
    # different defect and would be mis-triaged under this entry.
    if len(unaddressable) == len(membership):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no member of the room is addressable by name, so the filter is "
                    "failing wholesale rather than for one member class",
            witness="; ".join(unaddressable),
            site="src/thalamus/harness/dispatch.py::preflight",
        )

    if not unaddressable:
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "a room member the pin ledger places on a pane cannot be addressed by name: "
            "dispatch filters on a scope derived from the launch agent, and a member "
            "launched without one is visible when unnamed and invisible when named"
        ),
        witness="; ".join(unaddressable),
        site="src/thalamus/harness/dispatch.py::preflight (scope filter)",
    )


CASE = Case(
    name="every-room-member-is-addressable",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="dispatch must be able to name every member the pin ledger places in a room",
    run=run,
)
