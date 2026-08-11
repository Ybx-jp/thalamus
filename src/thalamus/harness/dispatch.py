"""Dispatch — delivering a message to live room members without approving anything.

[docs/12](../../../docs/12-room-lifecycle.md) §Delivery mechanics. Delivery to a live
pinned session is `tmux send-keys`, which is the only substrate available: the console
is a stdlib HTTP server with no messaging socket, and a room member has no inbox. The
measured behaviour against a real interactive session is what the whole module is built
around:

| target status | text | the following Enter |
|---|---|---|
| `idle` | lands in the composer | submits it |
| `busy` | lands in the composer | **queues** — order preserved, next turn |
| `waiting` | **discarded** | **actuates the highlighted default** |

The third row is the reason dispatch exists as its own verb rather than as a loop over
`tmux send-keys`. A `waiting` window is sitting on a permission prompt or a trust
dialog, so a blind send **throws away the message and approves a tool call the sender
knows nothing about** — and the first message to a freshly spawned member is the most
likely to hit one. The console's `/api/send` is exactly that blind path; nothing here
routes through it.

> **Dispatch reads `$CLAUDE_CONFIG_DIR/sessions/<pid>.json` per target, delivers on
> `idle` and `busy`, and refuses on `waiting`, naming the target.** Never a bare Enter
> into a `waiting` window.

## Pre-flight is over the whole fan-out, not per target

Delivering to the reachable members and skipping the rest looks like the tolerant
choice and quietly corrupts the protocol. A Contract Net announcement admits three
replies — a bid, a **decline**, and silence past expiration, which is a *timeout* and a
third state distinct from both (docs/12 §1). A member that never received the
announcement is silent, so a partial fan-out makes silence ambiguous: it can no longer
separate *this expert judged itself ineligible* from *this expert was never asked*.

So the default is all-or-nothing — every target is pre-flighted before any of them is
written to, and one undeliverable target refuses the dispatch naming it. `--partial`
proceeds anyway and records the undelivered targets on the row, which is what keeps the
later reading of a silence honest rather than merely permitted.

## What is trusted, and what is cross-checked

Two rosters have to agree. The **descriptor roster** is `sessions/*.json` in the room's
own config dir, which is what makes enumerating it *be* enumerating live membership
(lab/045); liveness is `pid` + `procStart` against `/proc`, already implemented in
`quick.live_sessions`. The **pin ledger** supplies the tmux pane a session owns, which
is the one handle unique per window and stable across the respawn a console recycle
performs. Where the descriptor roster and the live pane list disagree, dispatch refuses
rather than guesses.

Confirmation is `updatedAt` advancing on the descriptor. Never `capture-pane`, which
truncates to the visible height and would report a long reply as no reply.

## The rows are not collaboration

Dispatch rows land in `~/.thalamus/guards/` in the guard row shape but under
`guard: "dispatch"`, so `eval/rooms.py` — which filters on `guard == "room-boundary"`
— excludes them from `RoomTopology.edges` by construction rather than by remembering
to. A broadcast is the **stimulus**, not the collaboration, and folding operator
sends into the edge set would let a room pass its own manipulation check on operator
action alone.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from thalamus.harness import pin, quick

GUARDS_DIR = Path.home() / ".thalamus" / "guards"
PINS_FILE = Path.home() / ".thalamus" / "pins" / "pins.jsonl"

# Distinct from `room-boundary` so eval/rooms.py's own filter keeps these out of the
# realized edge set. The name is the mechanism, not a label on one.
DISPATCH_GUARD = "dispatch"
GUARD_VERSION = 1

# The delivery substrate, recorded per row so a later channel is distinguishable from
# this one rather than silently pooled with it.
VIA_TMUX = "tmux-send-keys"

# Statuses the measurement covers. `waiting` is absent deliberately: it is not a status
# dispatch handles cautiously, it is one it refuses.
DELIVERABLE_STATUSES = ("idle", "busy")
WAITING_STATUS = "waiting"


class DispatchRefused(RuntimeError):
    """The dispatch declined before sending anything. The message is the reason."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=5)


def live_panes() -> set[str]:
    """Every pane id tmux currently has, across all sessions."""
    result = _tmux("list-panes", "-a", "-F", "#{pane_id}")
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.split() if line.strip()}


def ledger_panes(pins_file: Path | None = None) -> dict[str, str]:
    """session_id → the tmux pane it claimed, newest row winning.

    `event` rows are skipped. They share this ledger and carry none of the launch
    facts, and a reader that let one overwrite the row that does is the defect that
    once reported a correctly-launched fork as having met no obligation.
    """
    path = pins_file or PINS_FILE
    if not path.is_file():
        return {}
    panes: dict[str, str] = {}
    with path.open(errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or row.get("event"):
                continue
            session_id = str(row.get("session_id") or "")
            pane = str(row.get("tmux_pane") or "")
            if session_id and pane:
                panes[session_id] = pane
    return panes


@dataclass(frozen=True)
class Target:
    """One room member, pre-flighted. `refusal` empty means deliverable."""

    scope: str
    session_id: str
    name: str
    pane: str
    status: str
    updated_at: int
    refusal: str = ""

    @property
    def deliverable(self) -> bool:
        return not self.refusal

    def note(self) -> str:
        if self.deliverable:
            return f"{self.name or self.scope:24} {self.status:8} pane {self.pane}"
        return f"{self.name or self.scope:24} {self.status or '?':8} REFUSED — {self.refusal}"


def preflight(
    room: str,
    scopes: list[str] | None = None,
    *,
    config_dir: Path | None = None,
    pins_file: Path | None = None,
    panes: set[str] | None = None,
) -> list[Target]:
    """Every addressable member of `room`, each with its verdict already decided.

    Reads before it writes anything, which is the property the whole verb rests on:
    the status that must not be written to is knowable without writing to it.
    """
    root = config_dir or pin.room_config_dir(room)
    sessions = quick.live_sessions(root)
    if scopes:
        wanted = set(scopes)
        sessions = [s for s in sessions if s.scope in wanted]

    known_panes = ledger_panes(pins_file)
    live = live_panes() if panes is None else panes

    targets = []
    for session in sorted(sessions, key=lambda s: s.scope or s.session_id):
        pane = known_panes.get(session.session_id, "")
        refusal = ""
        if not pane:
            # The descriptor roster has a member the pin ledger cannot place. Guessing
            # a pane here would send a stranger's window the room's message.
            refusal = (
                "live in the room but absent from the pin ledger, so no pane can be "
                "resolved for it — relaunch it through `thalamus spawn --room`"
            )
        elif pane not in live:
            refusal = (
                f"pin ledger claims pane {pane}, which tmux does not have — the "
                "rosters disagree, so the target is ambiguous"
            )
        elif session.status == WAITING_STATUS:
            refusal = (
                "is `waiting` — a send would be discarded and the Enter would actuate "
                "the highlighted default, approving a prompt this dispatch cannot see"
            )
        elif session.status not in DELIVERABLE_STATUSES:
            refusal = (
                f"reports status `{session.status or 'unknown'}`, which is outside the "
                "measured set; refusing rather than assuming it behaves like `idle`"
            )
        targets.append(
            Target(
                scope=session.scope,
                session_id=session.session_id,
                name=session.name,
                pane=pane,
                status=session.status,
                updated_at=session.updated_at,
                refusal=refusal,
            )
        )
    return targets


def announcement(
    task: str, eligibility: str, bid: str, expires: str, *, sender: str = ""
) -> str:
    """A Contract Net task announcement — the four mandatory slots, all required.

    Task abstraction, eligibility specification, bid specification and expiration are
    Smith's four (1980), and the extra three are what turn a broadcast into *focused
    addressing*: a member reads the eligibility slot and discards the rest without
    paying to process it. A slot left blank is refused rather than defaulted, because
    the format's whole economy is that a member can stop reading early.

    The decline line is part of the format, not politeness. An expert with no
    protocol-legal way to say *this is not mine* is an expert under exactly the
    pressure Instruction Decay Rate scores.
    """
    missing = [
        label
        for label, value in (
            ("task", task), ("eligibility", eligibility),
            ("bid", bid), ("expires", expires),
        )
        if not value.strip()
    ]
    if missing:
        raise DispatchRefused(
            f"announcement is missing {', '.join(missing)} — Contract Net's four slots "
            "are mandatory, and a member that cannot read eligibility must process the "
            "whole message to discover it does not apply"
        )
    lines = [
        "<task-announcement>",
        f"from: {sender or 'unknown'}",
        f"task: {task}",
        f"eligibility: {eligibility}",
        f"bid: {bid}",
        f"expires: {expires}",
        "",
        "Reply with a bid or a decline. A decline is a protocol-legal reply and "
        "carries information — it records that this expert judged itself ineligible. "
        "Silence past expiration is a timeout, which is a different state from both.",
        "</task-announcement>",
    ]
    return "\n".join(lines)


def dispatch_id(room: str, sender: str, text: str, targets: list[Target]) -> str:
    """A stable handle for one fan-out, derived from what it was."""
    material = "|".join(
        [room, sender, text, _now(), *(target.session_id for target in targets)]
    )
    return hashlib.sha256(material.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Delivery:
    """What happened to one target, after the send."""

    target: Target
    performed: bool
    updated_delta: int = 0
    """`updatedAt` movement after the send. Zero is not proof of failure — a queued
    message on a busy session may not touch the descriptor until the turn lands — so
    it is recorded rather than asserted on."""

    error: str = ""


def _send(pane: str, text: str, submit: bool = True) -> str:
    """Literal text, then Enter as a separate call. Returns "" or an error."""
    # `-l` sends the text literally: without it tmux interprets the payload as key
    # names, so a message containing the word `Enter` would submit itself early.
    typed = _tmux("send-keys", "-t", pane, "-l", text)
    if typed.returncode != 0:
        return typed.stderr.strip() or "send-keys refused the text"
    if submit:
        entered = _tmux("send-keys", "-t", pane, "Enter")
        if entered.returncode != 0:
            return entered.stderr.strip() or "send-keys refused the Enter"
    return ""


def _row(
    room: str,
    sender: str,
    handle: str,
    fanout: int,
    delivery: Delivery,
    undelivered: list[str],
) -> dict:
    return {
        "ts": _now(),
        "session_id": delivery.target.session_id,
        "scope": sender,
        "room": room,
        "cwd": "",
        "guard": DISPATCH_GUARD,
        "guard_version": GUARD_VERSION,
        "verdict": "pass" if delivery.performed else "refused",
        "branch": "dispatch",
        "target": delivery.target.name or delivery.target.scope,
        "dispatch_id": handle,
        "fanout": fanout,
        "via": VIA_TMUX,
        "sender": sender,
        "preflight_status": delivery.target.status,
        "performed": delivery.performed,
        "refusal": delivery.target.refusal or delivery.error,
        "updated_delta": delivery.updated_delta,
        # Carried on every row of a partial fan-out so a later reader can tell an
        # expert's silence from an expert that was never asked. Without it a partial
        # broadcast's timeouts are uninterpretable.
        "undelivered": sorted(undelivered),
    }


def _append_rows(rows: list[dict], guards_dir: Path | None = None) -> Path:
    directory = guards_dir or GUARDS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{datetime.now(timezone.utc).strftime('%Y-%m')}.jsonl"
    with path.open("a") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return path


@dataclass(frozen=True)
class DispatchResult:
    room: str
    sender: str
    handle: str
    deliveries: tuple[Delivery, ...]
    undelivered: tuple[str, ...]
    dry_run: bool = False

    @property
    def performed(self) -> int:
        return sum(1 for delivery in self.deliveries if delivery.performed)

    def note(self) -> str:
        lines = [
            f"dispatch {self.handle} — room `{self.room}`, sender `{self.sender}`, "
            f"{self.performed}/{len(self.deliveries)} delivered"
            + (" (dry run, nothing sent)" if self.dry_run else "")
        ]
        for delivery in self.deliveries:
            if delivery.performed:
                lines.append(
                    f"  → {delivery.target.name or delivery.target.scope:24} "
                    f"{delivery.target.status:8} pane {delivery.target.pane}"
                    + (f"  updatedAt +{delivery.updated_delta}ms"
                       if delivery.updated_delta else "  updatedAt unmoved (queued)")
                )
            else:
                reason = delivery.target.refusal or delivery.error
                lines.append(
                    f"  ✗ {delivery.target.name or delivery.target.scope:24} {reason}"
                )
        if self.undelivered:
            lines.append(
                f"  {len(self.undelivered)} target(s) never received this: "
                f"{', '.join(self.undelivered)} — their silence is not a decline and "
                "must not be read as a timeout"
            )
        return "\n".join(lines)


def dispatch(
    room: str,
    text: str,
    *,
    sender: str = "",
    scopes: list[str] | None = None,
    partial: bool = False,
    dry_run: bool = False,
    submit: bool = True,
    config_dir: Path | None = None,
    pins_file: Path | None = None,
    guards_dir: Path | None = None,
    panes: set[str] | None = None,
    sender_fn=None,
) -> DispatchResult:
    """Pre-flight every member, then deliver — or refuse the whole fan-out.

    `dry_run` runs the pre-flight and writes no rows, which is the mode to answer
    *would this land?* without the send that answers it destructively.
    """
    if not text.strip():
        raise DispatchRefused("nothing to dispatch — an empty message still costs "
                              "every recipient a turn")
    targets = preflight(
        room, scopes, config_dir=config_dir, pins_file=pins_file, panes=panes
    )
    if not targets:
        raise DispatchRefused(
            f"room `{room}` has no live members to dispatch to — a room whose members "
            "have exited is not a room that can be announced to"
        )

    blocked = [target for target in targets if not target.deliverable]
    if blocked and not partial:
        detail = "; ".join(
            f"`{target.name or target.scope}` {target.refusal}" for target in blocked
        )
        raise DispatchRefused(
            f"refusing the whole fan-out: {len(blocked)} of {len(targets)} target(s) "
            f"cannot be delivered to — {detail}. A partial announcement makes a "
            "member's silence ambiguous between a decline and never having been "
            "asked; re-run with --partial to accept that and record who missed it."
        )

    undelivered = [target.name or target.scope for target in blocked]
    send = sender_fn or _send

    deliveries: list[Delivery] = []
    for target in targets:
        if not target.deliverable:
            deliveries.append(Delivery(target=target, performed=False))
            continue
        if dry_run:
            deliveries.append(Delivery(target=target, performed=False,
                                       error="dry run"))
            continue
        error = send(target.pane, text, submit)
        delta = 0
        if not error:
            # Re-read the descriptor rather than the pane: `capture-pane` truncates to
            # the visible height, so a long reply would read as no reply at all.
            for session in quick.live_sessions(config_dir or pin.room_config_dir(room)):
                if session.session_id == target.session_id:
                    delta = max(0, session.updated_at - target.updated_at)
                    break
        deliveries.append(
            Delivery(target=target, performed=not error, updated_delta=delta,
                     error=error)
        )

    handle = dispatch_id(room, sender, text, targets)
    result = DispatchResult(
        room=room, sender=sender, handle=handle,
        deliveries=tuple(deliveries), undelivered=tuple(undelivered),
        dry_run=dry_run,
    )
    if not dry_run:
        _append_rows(
            [
                _row(room, sender, handle, len(targets), delivery, undelivered)
                for delivery in deliveries
            ],
            guards_dir,
        )
    return result
