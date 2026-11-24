"""The roster paints exactly the windows tmux has, and opening one reveals the composer.

The roster is the console's landing view and the only way into a session
(`index.html`: "the only way into a session"). A row that is missing is a session the
operator cannot reach from the phone; a row for a window that is gone is a send into
nothing. Both are invisible to every server-side case, because `/api/panes` is right and
the paint is wrong.

The case stands up the rig (a real console, a private tmux server), adds three windows
to the one the console seeds, opens the page in Chromium and asserts, on the rendered
DOM and not the JSON:

1. every tmux window name appears as a row name, once (`.srow-name`), and the row count
   equals the window count;
2. the **denominator**: at least one row rendered. "Every window has a row" over an
   empty roster is vacuously true, so an unrendered page is reported as the instrument
   failing (collapsed sentinel), never as a pass;
3. metamorphic — a window added after the page loaded appears on the next poll, and a
   window killed disappears from it;
4. the composer (`#composer`) is not visible on the roster and is visible after a row
   is opened (the control for "visible" meaning anything: it is measured both ways).

**Driven red** by mutating a copy of `app.js` so `renderRoster` skips its last row (point
`QE_CONSOLE_SRC` at the copy): property 1 fails naming the missing window.
"""

from __future__ import annotations

import time

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_browser import (add_windows, browser, collapsed, finding, wait_count)
from ._console_rig import console_rig


def _names(page) -> list[str]:
    return [t.strip() for t in page.locator(".srow-name").all_inner_texts()]


def run() -> Finding | None:
    with console_rig() as rig:
        add_windows(rig, ("w-one", "w-two", "w-three"))
        want = [n for _, n in rig.window_names()]
        with browser(rig.base) as (page, watch):
            page.goto(rig.base + "/")
            n = wait_count(page, ".srow", len(want))
            if n < 1:
                return collapsed(
                    "the roster rendered no rows for a rig with four "
                    "windows, so 'every window has a row' is not being tested",
                    f"tmux windows={want}, .srow count={n}, body="
                    f"{page.inner_text('body')[:200]!r}")
            got = _names(page)
            missing = [w for w in want if got.count(w) != 1]
            if missing or len(got) != len(want):
                return finding(
                    FailureClass.INVARIANT_FALSIFIED,
                    "the rendered roster does not hold exactly one row per tmux window",
                    f"tmux windows={want}; rendered row names={got}; "
                    f"not exactly once: {missing}")

            if page.locator("#composer").is_visible():
                return finding(FailureClass.INVARIANT_FALSIFIED,
                               "the composer is visible on the roster, before any row is "
                               "opened — a send could be typed with no target",
                               f"#composer visible at data-view="
                               f"{page.locator('body').get_attribute('data-view')!r}")
            page.locator(".srow", has_text="w-two").first.click()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not page.locator("#composer").is_visible():
                time.sleep(0.1)
            if not page.locator("#composer").is_visible():
                return finding(FailureClass.INVARIANT_FALSIFIED,
                               "opening a roster row did not reveal the composer",
                               f"clicked the w-two row; data-view="
                               f"{page.locator('body').get_attribute('data-view')!r}; "
                               f"#msg visible={page.locator('#msg').is_visible()}")
            page.click("#roster-btn")  # back to the roster

            # Metamorphic: the live poll follows tmux in both directions.
            add_windows(rig, ("w-late",))
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline and "w-late" not in _names(page):
                time.sleep(0.2)
            if "w-late" not in _names(page):
                return finding(FailureClass.INVARIANT_FALSIFIED,
                               "a window created after the page loaded never got a row",
                               f"added w-late; rows after 12s={_names(page)}")
            rig.tmux("kill-window", "-t", f"{rig.session}:w-late")
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline and "w-late" in _names(page):
                time.sleep(0.2)
            if "w-late" in _names(page):
                return finding(FailureClass.INVARIANT_FALSIFIED,
                               "a killed window kept its row: a send from it would land "
                               "in whatever tmux reuses the index for",
                               f"killed w-late; rows after 12s={_names(page)}")
    return None


CASE = Case(
    name="browser-roster-renders-every-tmux-window-and-opens-the-composer",
    tier=Tier.BROWSER,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_PLAYWRIGHT),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="the rendered roster has one row per tmux window (with a denominator), "
            "follows windows added and killed, and a row opens the composer",
    run=run,
)

CASES = (CASE,)
