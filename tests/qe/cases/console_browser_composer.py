"""What is typed into the composer and sent arrives in that window's pane, verbatim.

Issue #152 (fixed) was the server half of this property: `/api/send` handed text to
`tmux send-keys -l` without `--`, so a chunk starting `-t 0` retargeted the keystrokes
and one ending `;` lost its last character. `console_send_text_is_data_not_argv`
guards the argv. This case guards the whole path a person actually uses — the
composer's textarea, the SEND button, `sendMessage()` in `app.js`, the proxy, the
handler and tmux — in a real browser, and reads the result off the **pane** of a real
(private) tmux server, so a regression in any layer (the client rewriting the text,
posting to a different window than the one opened, dropping a trailing character)
shows up here and nowhere else.

Opens the `w-two` row, then sends each payload through `#msg` + `#send`:
a leading `-t 0`, a trailing `;`, `$(id)` and backticks, unicode, a leading `--`, and a
1,500-character single line. The pane is `sh -c 'exec cat'`, so the tty echoes the line
and `cat` repeats it; the property is that a (wrap-joined, `capture-pane -J`) line equal
to the payload exists in the target window, and that **no other window** shows the
payload's token.

**Controls.** The first payload is plain text and its absence from the pane is reported
as a collapsed sentinel (the instrument cannot see an arrival), not as a defect. The
decoy windows are checked for a token that *did* arrive in the target, which shows the
decoy check could see a leak if there were one.

**Driven red** by mutating a copy of `app.js` so `sendMessage` posts `index: 0`: the
payloads land in window 0, the target window stays empty, and the case names both.
"""

from __future__ import annotations

import time

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_browser import add_windows, browser, collapsed, finding, wait_count
from ._console_rig import console_rig

_LONG = "QEC6 " + "abcdefghij" * 150 + " END"

# (token, text). The token is inside the text, so a line holding the text proves
# arrival and a line holding the token anywhere else is a leak.
_PAYLOADS = (
    ("QEC0", "QEC0 an ordinary line"),
    ("QEC1", "-t 0 QEC1"),
    ("QEC2", "--help QEC2"),
    ("QEC3", "QEC3 ends in a semicolon;"),
    ("QEC4", "QEC4 $(id) `id` ${HOME} %1 #{pane_id}"),
    ("QEC5", "QEC5 héllo ✓ 日本語"),
    ("QEC6", _LONG),
)


def _lines(capture: str) -> list[str]:
    return [ln.rstrip() for ln in capture.splitlines()]


def run() -> Finding | None:
    with console_rig() as rig:
        add_windows(rig, ("w-one", "w-two", "w-three"))
        names = dict((n, i) for i, n in rig.window_names())
        target = names["w-two"]
        others = [i for i in names.values() if i != target]
        with browser(rig.base) as (page, watch):
            page.goto(rig.base + "/")
            if wait_count(page, ".srow", len(names)) < len(names):
                return collapsed("the roster did not render its rows, so no row could be "
                                 "opened to type into", f"windows={names}")
            page.locator(".srow", has_text="w-two").first.click()
            page.wait_for_selector("#msg", state="visible", timeout=5000)

            for token, text in _PAYLOADS:
                page.fill("#msg", text)
                if page.input_value("#msg") != text:
                    return collapsed("the textarea did not hold the payload it was "
                                     "given, so what was sent is not what was typed",
                                     f"payload={text!r} value={page.input_value('#msg')!r}")
                page.click("#send")
                got = rig.wait_for(lambda: text in _lines(rig.capture(target)), timeout=6)
                if not got:
                    leaked = {i: rig.capture(i)[:200] for i in others
                              if token in rig.capture(i)}
                    if token == "QEC0" and not leaked:
                        return collapsed(
                            "an ordinary line sent through the composer reached no pane "
                            "at all, so a missing payload below could not be told from "
                            "an instrument that sees nothing",
                            f"pane {target} after 6s: {rig.capture(target)[:300]!r}")
                    return finding(
                        FailureClass.BOUNDARY_LEAK if leaked else
                        FailureClass.INVARIANT_FALSIFIED,
                        "text sent from the composer did not arrive verbatim in the "
                        "window that was open",
                        f"sent {text[:120]!r} ({len(text)} chars) to window {target}; "
                        f"pane lines={[ln[:120] for ln in _lines(rig.capture(target))][:8]}"
                        + (f"; token found in OTHER windows {leaked}" if leaked else ""))
                time.sleep(0.15)

            # The decoy check, with its control: QEC0..QEC6 all arrived in `target`
            # (above), so a leak of any of them into another window is visible here.
            for token, text in _PAYLOADS:
                for i in others:
                    if token in rig.capture(i):
                        return finding(
                            FailureClass.BOUNDARY_LEAK,
                            "text sent from the composer also reached a window that was "
                            "not open",
                            f"token {token} (sent to window {target}) found in window "
                            f"{i}: {rig.capture(i)[:200]!r}")
            if watch.page_errors:
                return finding(FailureClass.INVARIANT_FALSIFIED,
                               "the page raised an uncaught error while sending",
                               watch.describe())
    return None


CASE = Case(
    name="browser-composer-text-arrives-verbatim-in-the-open-window-only",
    tier=Tier.BROWSER,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_PLAYWRIGHT),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.INVARIANT_FALSIFIED,
             FailureClass.COLLAPSED_SENTINEL),
    summary="text typed in the composer and sent via SEND lands byte-for-byte in the "
            "open window's pane and in no other window",
    run=run,
)

CASES = (CASE,)
