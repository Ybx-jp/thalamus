# 066 — The readiness we author

**Date:** 2026-08-13 · **Scope:** main · **Build:** `cursor/2026.08.11-e8db854` ·
**Verdict:** Option C built to the spec that was already settled; not yet run against a
live Cursor room, and that is the standing limitation

lab/065 shipped Cursor rooms and closed with one named residual: the readiness read was
`capture-pane`, which the `architect` had refused as a readiness *signal* on an argument
the shipped code did not answer. This entry is the build. It contains no new design —
the design is consultation `d4c5982f12cf41ab`, and the one measurement it was blocking
on was made in lab/065 §5.

## What the refusal actually said, and why it was not "never capture a pane"

> **A screen-scrape readiness check is a falsifier in one direction only.** Seeing a
> modal proves `waiting`; *not* seeing one proves nothing — scrollback position, a
> redraw race, a modal rendered below the fold. A check whose negative result is
> uninformative is not a mitigation, it is a permission to send.

That is an argument about the *direction* a signal is sound in, not about the tool. It
rules out `capture-pane` as the thing that decides a send and says nothing against it as
a thing that can veto one. The build takes it at exactly that width: the descriptor
decides, and the screen may only refuse.

## The bracket

`beforeShellExecution` writes `pending`; `afterShellExecution` writes `ready`; the MCP
pair does the same. The interval between them is the interval in which a modal can be
up, and it is delimited by two events we emit rather than by a vendor's rendering of a
dialog. It is a bracket only because the opening event precedes the modal — measured in
lab/065 §5, hook logged 11:01:15 against a modal still unanswered at 11:01:20. Had it
fired after, `pending` would arrive only once the operator had already been asked, and
`readiness.py` would be a slower screen read.

Three conditions came with the design and all three are in the code:

**1. The default is inverted.** No descriptor means refuse. That is the member whose
hooks are unarmed — precisely the member whose modals nothing would report — so reading
absence as idle would invert the only guarantee the mechanism offers. Every way a record
can fail to arrive collapses to one outcome (absent, unreadable, truncated mid-write,
not an object), because distinguishing them invites treating the recoverable ones as
"probably idle".

**2. The coverage gap is written into the row, not left to be discovered.** The bracket
covers shell and MCP calls. A workspace-trust dialog, a model picker and a file-write
approval are outside it. `room.peer_readiness` on cursor states that in its own note,
because partial coverage on a safety gate is the shape that hid lab/033's failure.

**3. The screen is kept as a positive-only falsifier.** A `ready` descriptor is
confirmed against the pane before a send, so an unbracketed modal that happens to be
visible still refuses. A clean screen can never clear a `pending`, and never supplies a
missing descriptor. Two tests exist for the inversion specifically, because it is the
one edit that would make the descriptor decorative while leaving every other test green.

## The key is `(room, scope)`, and that is forced

The writer cannot name its own pane: Cursor's `sessionStart` hook deliberately declines
to write `tmux_pane`, because a headless `agent -p` spawned from a member's shell
inherits `TMUX_PANE` and an unconditional claim hands the console's read view to a probe
(measured 2026-08-10, five hours of a window's read view lost to a two-message probe).
`(room, scope)` is what the writer has from its own environment and what the pane roster
recovers from the window's start command, so the two halves meet without either guessing.

That same inherited environment is a hazard in the other direction, and it is the
subtlest thing in the build. A nested `agent -p` inherits `THALAMUS_ROOM` and
`THALAMUS_SCOPE`, fires its own `sessionStart`, and would write `ready` over its parent's
`pending` — clearing the bracket at the exact moment it is describing, by its own side
effect. **A `ready` never clears a `pending` left by a different session**, enforced in
both the shell and the Python halves, with a test driving the real hook scripts.

## The row the refusal names

`dispatch` refused an unreadable member with "shows a screen this pre-flight cannot read
as ready". It now refuses naming `room.peer_readiness`, and the row exists:
`contract/rooms.py`, four components × two harnesses, split because Claude Code ships
identity, liveness and readiness fused in one artifact and the fusion is what let a gate
pass vacuously — delivery was permitted when a *roster* existed, tmux supplies a roster,
and the hazard the gate was protecting against was untouched. `room.peer_delivery` may
be PROVIDED only where `room.peer_readiness` is, and `check_rooms` enforces that rather
than trusting a reviewer, because a row promoted without its precondition reads exactly
like one that earned it.

## What is not established

**No live Cursor room has run under this.** Every test drives the hook scripts as
subprocesses with a synthetic payload and a temp `HOME`; none drives Cursor. The design's
one blocking measurement was made in lab/065, but the build on top of it is verified only
against our own fixtures, and the `room.peer_readiness` row on cursor reports
`unprobeable` on every run for that reason. What would settle it: a room member driven
into a real approval modal, with a dispatch refused while the modal stands and delivered
after it is answered.

**The unbracketed modal below the fold remains open by construction.** It is the residual
the coverage note names: outside the bracket, and out of the screen read's sight.
Closing it needs a Cursor event that fires on the dialogs the shell and MCP pairs do not
cover, and no such event has been probed.
