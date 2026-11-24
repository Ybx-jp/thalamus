"""The console's own pages raise no errors and reach no origin but their own.

A private-network tool that fetches a font from a CDN, posts telemetry, or throws on
load is wrong in ways no server-side case can see: the server is fine and the page is
not. The case walks the views a person reaches without any optional configuration —
roster, an opened row, the read view (`#view-toggle`), the infra sheet (`#admin-btn`),
the spawn sheet (`#spawn-btn`) — in Chromium at 430x932, and asserts across all of them:

1. zero `pageerror` (uncaught exceptions) and zero `console.error`;
2. zero requests to any origin other than the console's own (`data:`/`blob:` aside);
3. the **denominator**: each view rendered its landmark (rows; `#composer`; `#read`
   visible; `#admin`; `#spawn`) and the page made at least one request to the console's
   `/api/` — a walk where nothing rendered cannot report "no errors" as a result.

Service workers are blocked in the browser context, so a cached shell cannot hide a
request. The page's own failed requests are reported when they are same-origin (a 404
for an icon is a defect too) but only the three classes above fail the case.

**Driven red** by mutating a copy of `app.js` to append
`fetch("https://example.invalid/t")` at load (foreign request) or to throw in
`renderRoster` (page error); either is named by the witness.
"""

from __future__ import annotations

import time

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_browser import add_windows, browser, collapsed, finding, wait_count
from ._console_rig import console_rig


def run() -> Finding | None:
    with console_rig() as rig:
        add_windows(rig, ("w-one", "w-two"))
        with browser(rig.base) as (page, watch):
            page.goto(rig.base + "/", wait_until="load")
            seen: list[str] = []

            def step(view: str, landmark_ok: bool) -> Finding | None:
                if not watch.clean():
                    return finding(
                        FailureClass.INVARIANT_FALSIFIED,
                        f"the console's {view} view raised a page error, a console "
                        "error, or a request to a foreign origin",
                        f"at {view}: {watch.describe()}")
                if not landmark_ok:
                    return collapsed(
                        f"the {view} view did not render its landmark, so an error-free "
                        "run over it says nothing",
                        f"body={page.inner_text('body')[:200]!r}")
                seen.append(view)
                return None

            r = step("roster", wait_count(page, ".srow", 3) >= 3)
            if r:
                return r
            page.locator(".srow", has_text="w-one").first.click()
            page.wait_for_selector("#composer", state="visible", timeout=5000)
            time.sleep(0.8)
            r = step("opened-row", page.locator("#composer").is_visible())
            if r:
                return r
            page.click("#view-toggle")
            time.sleep(0.8)
            r = step("read-view", page.locator("#read").is_visible())
            if r:
                return r
            page.click("#roster-btn")
            page.click("#admin-btn")
            time.sleep(0.8)
            r = step("admin-sheet", page.locator("#admin").is_visible())
            if r:
                return r
            page.click("#admin-x")
            page.click("#spawn-btn")
            time.sleep(0.8)
            r = step("spawn-sheet", page.locator("#spawn").is_visible()
                     and wait_count(page, "#spawn-scopes .chip", 1) >= 1)
            if r:
                return r
            api = [u for u in watch.requests if "/api/" in u]
            if not api:
                return collapsed("the walk made no /api/ request, so the page never "
                                 "talked to the console and 'no foreign request' is "
                                 "vacuous", f"requests={watch.requests[:10]}")
    return None


CASE = Case(
    name="browser-console-pages-raise-no-errors-and-no-foreign-requests",
    tier=Tier.BROWSER,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_PLAYWRIGHT),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="across roster, opened row, read view, admin and spawn sheets: zero page "
            "errors, zero console errors, zero requests to another origin",
    run=run,
)

CASES = (CASE,)
