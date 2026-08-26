"""Readiness a harness never published — a descriptor bracketed by our own hooks.

Dispatch must refuse a member that is holding an approval modal, because a send into
one is discarded and the Enter that follows it actuates the highlighted default —
measured on Cursor, where a dispatched message never reached the model and the Enter
approved a shell command the sender could not see.

Claude Code answers "is it safe to send" from `$CLAUDE_CONFIG_DIR/sessions/<pid>.json`,
whose `status` the harness writes from inside its own event loop. Cursor publishes no
equivalent, and the substitute `harness/panes.py` reads — the visible screen — is a
**one-directional falsifier**: seeing a modal proves `waiting`, not seeing one proves
nothing, because `capture-pane` truncates to the visible height and a dialog can be
drawn below the fold. A check whose negative result is uninformative is not a
mitigation; it is a permission to send.

So the readiness signal is one we author. Two of our own hooks bracket the interval:
`beforeShellExecution` writes `pending` and `afterShellExecution` writes `ready`, with
the MCP pair doing the same for tool calls. The interval between them is the interval
in which a modal may be up, and it is delimited by two events we emit rather than by a
vendor's rendering of a dialog.

**The bracket is only a bracket because the opening event precedes the modal**, and
that is measured, not inferred: a probe hook logged at 11:01:15 with Cursor's approval
modal still unanswered at 11:01:20. Had it fired after, `pending` would be
written only once the operator had already been asked, and this module would be a
slower screen read.

## Absence refuses

A missing descriptor is not an idle member. Nothing here treats the absence of a record
as evidence about the state it would have recorded — the hooks' only effect is to write
the record, and the consumer acts off the record, never off its own guess about why one
is missing. A member whose hooks are unarmed is therefore unaddressable, which is the
correct outcome: it is exactly the member whose modals nothing would report.

## What the bracket covers, and what it does not

`pending` is written for **shell commands and MCP tool calls**. It is not written for a
workspace-trust dialog, a model picker, a file-write approval, or any other modal Cursor
draws outside those two events — a partial safety gate, which is the shape that hid an
earlier failure, and so the coverage is enumerated here rather than left to a reader to
discover.

The screen read covers part of that remainder, and it is retained for exactly the half
it is good for: `panes.classify` can only *add* `waiting`, never clear one. A descriptor
saying `ready` is confirmed against the screen before a send is allowed, so an
unbracketed modal that happens to be visible still refuses; an unbracketed modal below
the fold is the residual, and it is the reason `room.peer_readiness` is not a claim that
every modal is caught.
"""

from __future__ import annotations

import json
from pathlib import Path

from thalamus.harness import panes as panes_mod

READINESS_DIR = Path.home() / ".thalamus" / "readiness"

# The two phases a bracket has. `ready` is the resting state — written when a session
# starts and again when each bracketed call completes — and `pending` holds only for
# the interval in which a modal may be up.
PENDING = "pending"
READY = "ready"


def descriptor_path(room: str, scope: str, *, root: Path | None = None) -> Path:
    """Where the member of `room` pinned to `scope` writes its readiness.

    Keyed by (room, scope) rather than by pane, because the writer cannot name its own
    pane: the Cursor `sessionStart` hook deliberately declines to write `tmux_pane`,
    since a headless `agent -p` spawned from a member's shell inherits `TMUX_PANE` and
    an unconditional claim hands the console's read view to a probe. (room, scope) is
    what the writer has from its own environment and what `panes.room_panes` recovers
    from the window's start command, so the two halves meet without either guessing.
    """
    base = root or READINESS_DIR
    return base / room / f"{scope}.json"


def read_descriptor(room: str, scope: str, *, root: Path | None = None) -> dict | None:
    """The member's descriptor, or None when there is nothing to read.

    None covers every way a record can fail to arrive — never written, unreadable,
    truncated mid-write, holding something that is not an object. They are one outcome
    here on purpose: each is equally uninformative about whether a modal is up, and a
    reader that distinguished them would be tempted to treat the recoverable ones as
    "probably idle".
    """
    if not room or not scope:
        return None
    try:
        loaded = json.loads(descriptor_path(room, scope, root=root).read_text())
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def descriptor_status(room: str, scope: str, *, root: Path | None = None) -> str:
    """The readiness verdict the descriptor alone supports.

    Anything that is not an explicit `ready` refuses: a `pending` bracket that never
    closed (the session was killed while the modal was up) reads as `waiting` for as
    long as it stands, which is the fail-closed direction — the pane is either still
    holding that modal or gone, and `panes.room_panes` drops the gone ones by liveness.
    """
    descriptor = read_descriptor(room, scope, root=root)
    if descriptor is None:
        return panes_mod.UNREADABLE
    phase = descriptor.get("phase")
    if phase == READY:
        return panes_mod.DELIVERABLE
    if phase == PENDING:
        return panes_mod.WAITING
    return panes_mod.UNREADABLE


def pane_status(pane, *, root: Path | None = None, screen_fn=None) -> str:
    """A pane's readiness: the descriptor, confirmed against the screen.

    The two signals are composed in the one direction each is sound in. The descriptor
    is the signal — it is first-party, it brackets the modal, and it refuses on absence.
    The screen is kept as a **positive-only falsifier** over the events the bracket does
    not cover: it may turn a `ready` descriptor into a refusal, and it may never turn a
    refusal into a send. That asymmetry is the whole reason a screen read is admissible
    here at all, and inverting it would reintroduce exactly the "did not see a modal, so
    send" inference the descriptor exists to replace.
    """
    from_descriptor = descriptor_status(pane.room, pane.scope, root=root)
    if from_descriptor != panes_mod.DELIVERABLE:
        return from_descriptor
    # Whatever the screen says stands: it agrees (`deliverable`) or it refuses. There is
    # no branch here in which the screen upgrades a verdict, which is what keeps its
    # uninformative negative out of the decision.
    return (screen_fn or panes_mod.pane_status)(pane.pane_id)
