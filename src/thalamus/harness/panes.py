"""The roster a harness never wrote — room membership and readiness, read from tmux.

On Claude Code a room's membership is enumerable because the harness registers each
session in `$CLAUDE_CONFIG_DIR/sessions/<pid>.json`, and `harness/quick.py` reads
liveness and a `status` straight off that descriptor. Cursor writes no such
directory, which is the absence that made a Cursor member unaddressable and stalled
the room decision.

The substitute is the control plane itself. Every pinned window is created by
`pin._open_window` with the room and the scope in its **own start command**, and
`#{pane_start_command}` renders that command back for as long as the pane exists —
including across the `respawn-window` the console's restart button runs, which is
exactly why `pin._with_room` puts them there rather than trusting tmux's `-e`
environment. So membership, scope, harness and address are all recoverable from the
window list, for a harness that registers nothing anywhere.

## What this roster is, and what it is not

It is **weaker in one specific way** than the descriptor roster, and the difference is
worth naming rather than smoothing over: a descriptor is written by the session and
proves a session exists; a start command is written by the *launcher* and proves only
that a window was created to hold one. A pane whose process died leaves a start command
behind, so liveness is asked of the pane (`#{pane_dead}`) rather than inferred from the
command being readable.

It is **stronger in one way**: it needs no cooperation from the harness at all, so it
answers for `main` — which has no manifest, carries no `--agent`, and is therefore
invisible to the descriptor roster's scope derivation.

## Readiness, when there is no `status` field

The descriptor's `status` is what lets dispatch refuse a `waiting` target. Cursor
publishes no equivalent, so readiness is read from the one surface that always tells
the truth about a TUI: the visible screen.

Measured 2026-08-13 against cursor/2026.08.11-e8db854, driving a real
interactive session in tmux:

| state | what the pane shows | send-keys behaviour |
|---|---|---|
| idle | the composer, a placeholder line, the model footer | text composes, Enter submits |
| busy | the same footer, output streaming above it | text composes, Enter queues it |
| waiting | `Waiting for approval...`, a rule, a question, and an option list | **text discarded, Enter actuates the highlighted default** |

The third row was measured by doing it: a message sent into a pane holding
`Run this command?` never reached the model, and the Enter selected `→ Run (once)`,
running the command. That is the same hazard Claude Code's `waiting` row records, so
it is refused the same way — and it is why `capture-pane` is read here at all, in a
module whose sibling forbids it. The rule is not "never capture a pane", it is **never
confirm a reply from one**: `capture-pane` truncates to the visible height, so a long
answer reads as no answer. A modal is drawn *in* the visible height, so the same call
that cannot see a reply is the right instrument for seeing a dialog.

## Fail closed

An unrecognized screen is refused rather than delivered to, matching the rule dispatch
already applies to a status outside its measured set. The discriminator is deliberately
the *modal* rather than the composer: Cursor's footer carries the selected model's name
(`Composer 2.5`, `gpt-5`, …), so a check for the ready state would silently change
meaning when an operator switches models, while an approval dialog is structural — a
highlighted `→` option carrying a keyboard hotkey, which no ready screen draws.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass

# Which harness a window is running, read from the command it was created with. The
# binary is the only honest signal: `pane_current_command` shows whatever is in the
# foreground, so a window shelling out reads as `bash` for as long as that lasts.
HARNESS_BINARIES = {"claude": "claude", "agent": "cursor", "codex": "codex"}

# The three readiness verdicts. `DELIVERABLE` deliberately does not distinguish idle
# from busy: both accept a send (one submits, one queues), and a distinction nothing
# acts on is a field that goes stale.
DELIVERABLE = "deliverable"
WAITING = "waiting"
UNREADABLE = "unreadable"

# A modal's option line: an arrow-marked choice carrying the key that picks it. The
# hotkey is what makes this precise — a ready pane draws `→ Plan, search, build
# anything` and a finished turn draws `→ Add a follow-up`, both arrow-marked and
# neither one selectable, so the arrow alone would refuse every idle member.
_HOTKEY_OPTION = re.compile(r"^\s*[→>]\s.*\((?:y|n|tab|shift\+tab|enter|esc[^)]*)\)\s*$",
                            re.IGNORECASE | re.MULTILINE)

# Phrases a pane shows while it is holding a turn open for an answer. Kept alongside
# the structural check rather than instead of it: this list is a vendor's wording and
# will drift, while the option shape is the dialog's grammar.
_WAITING_MARKERS = (
    "waiting for approval",
    "run this command?",
    "do you want to proceed?",
    "not in allowlist:",
)


def harness_of(start_command: str) -> str:
    """The harness a start command launches, or "" if it names none we know.

    Reads the first token that is not part of an `env` prefix. The prefix nests in
    practice — `pin` wraps a room launch in `env -u …` and the Cursor pin carrier adds
    its own `env THALAMUS_SCOPE=…` inside that — so this loops rather than stripping one
    `env`. Anything unrecognized is "" rather than a guess: a wrong harness here would
    mark a window stale against some other harness's flags.
    """
    tokens = start_command.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "env":
            index += 1
        elif token == "-u":
            # `-u NAME` unsets, so the name after it is a bare token, not a NAME=VALUE.
            index += 2
        elif "=" in token:
            index += 1
        else:
            return HARNESS_BINARIES.get(os.path.basename(token), "")
    return ""


def _assignment(start_command: str, name: str) -> str:
    """The value of a `NAME=VALUE` in an `env` prefix, or "".

    Anchored to a word boundary so `THALAMUS_ROOM` cannot be matched inside a longer
    variable name that happens to end with it.
    """
    match = re.search(rf"(?:^|\s){re.escape(name)}=(\S+)", start_command)
    return match.group(1) if match else ""


@dataclass(frozen=True)
class Pane:
    """One window of the control plane, as a room addresses it."""

    pane_id: str
    window_name: str
    room: str
    scope: str
    harness: str
    cwd: str
    dead: bool

    @property
    def alive(self) -> bool:
        return not self.dead


def _tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=5)


# A tab, and not one of the non-printable record separators that would be safer in
# any other pipeline: tmux's format renderer escapes non-printable characters into
# octal (`\037`), so a `\x1f` separator arrives as four literal characters and every
# line fails to split. The start command is parsed last and with a bounded split, so
# a tab inside it cannot shift the fields before it.
_FIELD = "\t"
_PANE_FORMAT = _FIELD.join(
    ("#{pane_id}", "#{window_name}", "#{pane_current_path}", "#{pane_dead}",
     "#{pane_start_command}")
)


def panes(target: str | None = None) -> list[Pane]:
    """Every pane the control plane holds, with its room and scope already resolved.

    `list-panes -a` rather than `list-windows`: the address a send is delivered to is
    a pane, and a window that has been split holds more than one. Resolving to the
    window would silently pick the first.
    """
    args = ["list-panes", "-a", "-F", _PANE_FORMAT]
    if target:
        args[1:1] = ["-t", target]
    result = _tmux(*args)
    if result.returncode != 0:
        return []
    found = []
    for line in result.stdout.splitlines():
        fields = line.split(_FIELD, 4)
        if len(fields) != 5:
            continue
        pane_id, window_name, cwd, dead, start = fields
        found.append(
            Pane(
                pane_id=pane_id.strip(),
                window_name=window_name.strip(),
                room=_assignment(start, "THALAMUS_ROOM"),
                # The window name is the scope by convention, but the start command is
                # the scope by construction — `_open_window` puts it there and a rename
                # cannot move it. Falling back to the name keeps a hand-made window
                # addressable rather than invisible.
                scope=_assignment(start, "THALAMUS_SCOPE") or window_name.strip(),
                harness=harness_of(start),
                cwd=cwd.strip(),
                dead=dead.strip() == "1",
            )
        )
    return found


def room_panes(room: str, target: str | None = None) -> list[Pane]:
    """The live panes belonging to `room`, sorted by scope.

    A dead pane is dropped rather than reported unreachable: its start command still
    names the room, so keeping it would grow a room's membership every time a member
    exited, and `--partial`'s undelivered list would fill with sessions that ended
    hours ago.
    """
    if not room:
        return []
    return sorted(
        (pane for pane in panes(target) if pane.room == room and pane.alive),
        key=lambda pane: (pane.scope, pane.pane_id),
    )


def classify(screen: str) -> str:
    """Read a captured screen as a readiness verdict.

    Pure so the measured frames can be replayed as fixtures — the alternative is a
    test that has to launch a real session to check the one branch that decides
    whether dispatch approves somebody else's tool call.
    """
    if not screen.strip():
        # A pane with nothing on it is a window that has not drawn yet, or one whose
        # process is gone. Neither is a target.
        return UNREADABLE
    lowered = screen.lower()
    if any(marker in lowered for marker in _WAITING_MARKERS):
        return WAITING
    if _HOTKEY_OPTION.search(screen):
        return WAITING
    return DELIVERABLE


def pane_status(pane_id: str) -> str:
    """Capture a pane's visible screen and classify it.

    Deliberately without `-S -`: the scrollback holds every dialog the session has
    ever answered, so a history read would report a member as `waiting` on the
    strength of a prompt it resolved an hour ago.
    """
    result = _tmux("capture-pane", "-p", "-t", pane_id)
    if result.returncode != 0:
        return UNREADABLE
    return classify(result.stdout)
