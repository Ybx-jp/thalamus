"""A control byte in `/api/send` text is data to the pane, not a signal to its process.

`POST /api/send` is the composer: the text field the operator types a prompt into. Its
contract, stated in `literal_text_args` and in `console_send_text_is_data_not_argv`, is
that the text is *data* — typed into the pane byte for byte. Terminal control keys already
have their own route (`/api/key`, a closed `KEYMAP` of named keys), which is where a
signal is meant to be requested. This case asks whether the composer is a second, unnamed
way to send one.

**What is generated.** Short strings of letters, spaces and *control characters* — C0
bytes `\\x01..\\x1f` except `\\x0a`, `\\x0d` and `\\x00`, DEL, and escape sequences
(`\\x1b[A`, `\\x1b[200~`, an OSC) — each containing at least one control. Each example is
sent to a freshly created `cat` window (one process, one tty, nothing to restart it) with
`submit: false`.

**Invariant.** After the send and a 0.3s settle, the pane's process is the same `cat`,
alive, not stopped (`/proc/<pid>/stat` state is not `T`), and the window still exists.
`cat` under a default tty is the canonical victim: SIGINT, SIGQUIT and SIGTSTP are
delivered by the line discipline on `^C`, `^\\` and `^Z`, and `^D` at an empty line is EOF.

**After the first counterexample**, every single control byte is sent alone and the full
list of those that kill, stop or end the process is reported — the witness names the bytes,
not just the first one Hypothesis found.

**Excluded, and why.** `\\n` and `\\r` are the submit key (a different property: whether a
newline in the composer submits); `\\x00` crashes the route before it reaches tmux
(`console_api_post_fuzz` reports it); `^S` freezes output without ending the process and
has no process-visible signature here.

**Controls.** (a) The detector sees a kill: `POST /api/key {"key": "ctrl-c"}` — the named
key, the sanctioned path — makes the same check fail, so a green is not "the check cannot
see a dead cat". (b) Benign text (`hello`) leaves the window alive and appears in the
pane. (c) The window is `cat` before every send.

**A note on severity.** `ctrl-c` and every other `ctrl-<letter>` are in `KEYMAP` and are
requestable by any client that can POST here, so a control byte in `text` is not a new
capability. What it breaks is the contract that the composer's text is inert: a pasted
prompt, a transcript fragment or an agent's output that contains `\\x03` ends the session it
was typed into.

**Shown capable of going red.** On the unmodified tree this case is red on `\\x03`. To see
it green, make `literal_text_args` reject (or visibly escape) every character below
`0x20` except tab in a copy of the console tree (`QE_CONSOLE_SRC`).
"""

from __future__ import annotations

import json
import time

from hypothesis import strategies as st

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_hypothesis import hunt, post_raw
from ._console_rig import Rig, console_rig

SITE = "packages/thalamus-console/src/thalamus_console/tmux.py::literal_text_args"
_ME = "tests/qe/cases/console_api_send_control_bytes.py"
_CONTROLS = [chr(c) for c in range(1, 0x20) if c not in (0x0A, 0x0D)] + ["\x7f"]
_SEQUENCES = ["\x1b[A", "\x1b[200~", "\x1b[31m", "\x1b]0;qe\x07", "\x1bOP", "\x1b"]
_CTRL = st.one_of(st.sampled_from(_CONTROLS), st.sampled_from(_SEQUENCES))
TEXT = st.lists(st.one_of(_CTRL, st.sampled_from(list("ab ")), st.sampled_from(list("ab "))),
                min_size=1, max_size=4).map("".join).filter(
    lambda t: any(c in t for c in _CONTROLS) or any(s in t for s in _SEQUENCES))


def _fresh_victim(rig: Rig) -> int | None:
    rig.tmux("kill-window", "-t", f"{rig.session}:1")
    rig.tmux("new-window", "-d", "-t", f"{rig.session}:1", "-n", "qe-victim", "cat")
    r = rig.tmux("list-panes", "-t", f"{rig.session}:1", "-F", "#{pane_pid}")
    return int(r.stdout.split()[0]) if r.returncode == 0 and r.stdout.split() else None


def _state(rig: Rig, pid: int) -> str:
    """'alive', or what happened to the `cat` that was there."""
    r = rig.tmux("list-panes", "-t", f"{rig.session}:1", "-F",
                 "#{pane_pid} #{pane_dead} #{pane_current_command}")
    if r.returncode != 0 or not r.stdout.split():
        return "window-gone (process ended)"
    fields = r.stdout.split()
    if fields[0] != str(pid):
        return f"pane replaced (pid {pid} -> {fields[0]})"
    try:
        stat = open(f"/proc/{pid}/stat").read()
    except OSError:
        return "process-gone"
    st_char = stat[stat.rindex(")") + 2]
    if st_char in "TtZX":
        return {"T": "stopped (SIGTSTP)", "t": "stopped (trace)", "Z": "zombie",
                "X": "dead"}[st_char]
    if len(fields) > 2 and fields[2] != "cat":
        return f"command changed to {fields[2]!r}"
    if fields[1] != "0":
        return "pane-dead"
    return "alive"


def _send_and_observe(rig: Rig, text: str) -> tuple[str, str]:
    pid = _fresh_victim(rig)
    if pid is None:
        return "fixture", "could not create the victim window"
    resp = post_raw(rig.port, "/api/send",
                    json.dumps({"index": 1, "text": text, "submit": False}).encode())
    if resp.status != 200:
        return "refused", f"{resp.status} {resp.body[:100]!r}"
    time.sleep(0.3)
    state = _state(rig, pid)
    return ("ok" if state == "alive" else "signalled"), state


def run() -> Finding | None:
    with console_rig() as rig:
        # (b) benign text lands and leaves the window alive.
        outcome, state = _send_and_observe(rig, "hello")
        if outcome != "ok" or "hello" not in rig.capture(1):
            return Finding(failure_class=FailureClass.COLLAPSED_SENTINEL,
                           summary="a benign send did not land in a live cat window, so the "
                                   "liveness check below measures the fixture",
                           witness=f"outcome={outcome} state={state} "
                                   f"pane={rig.capture(1)[-60:]!r}", site=_ME)
        # (a) the detector sees a kill: the sanctioned path, the named key.
        pid = _fresh_victim(rig)
        post_raw(rig.port, "/api/key", json.dumps({"index": 1, "key": "ctrl-c"}).encode())
        time.sleep(0.3)
        if pid is None or _state(rig, pid) == "alive":
            return Finding(failure_class=FailureClass.COLLAPSED_SENTINEL,
                           summary="/api/key ctrl-c did not end the cat window, so this case "
                                   "cannot see a process dying and every green is vacuous",
                           witness=f"state after ctrl-c: {_state(rig, pid) if pid else None}",
                           site=_ME)

        def check(text: str):
            outcome, state = _send_and_observe(rig, text)
            if outcome == "signalled":
                return ("signalled", state.split(" ")[0]), (
                    f"text={text!r} -> {state}")
            if outcome in ("fixture", "refused"):
                return (outcome,), f"text={text!r}: {state}"
            return None

        hits, truncated = hunt(TEXT, check, max_examples=45, rounds=3, budget_s=24.0,
                               shrink_budget_s=4.0)
        if not hits:
            return None

        # One byte at a time, so the witness lists every byte that signals.
        per_byte: list[str] = []
        for ch in _CONTROLS:
            outcome, state = _send_and_observe(rig, ch)
            if outcome == "signalled":
                per_byte.append(f"{ch!r} -> {state}")
        parts = [h.detail for h in hits]
        return Finding(
            failure_class=FailureClass.UNENFORCED_SIGNAL,
            summary="a control character in the composer text reaches the pane's tty as "
                    "a signal or EOF — it kills, stops or ends the process the text was "
                    "typed into — where the route's contract is that text is data",
            witness=f"{len(hits)} distinct effect(s) via Hypothesis"
                    + (" (time budget reached)" if truncated else "") + ": "
                    + " || ".join(parts)
                    + f" ;; single bytes that signal a fresh `cat` ({len(per_byte)}): "
                    + ", ".join(per_byte),
            site=SITE)


CASE = Case(
    name="a-control-byte-in-send-text-is-data-not-a-signal-to-the-pane",
    issue=420,
    fixed=True,
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX,),
    classes=(FailureClass.UNENFORCED_SIGNAL, FailureClass.COLLAPSED_SENTINEL),
    summary="a control byte in /api/send text (^C, ^D, ^Z, ^\\) must not kill, stop or end "
            "the process in the pane — text is data, /api/key is the signal route",
    run=run,
)
