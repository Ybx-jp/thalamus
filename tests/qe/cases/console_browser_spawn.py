"""The spawn sheet's round trip: ＋, choose an expert and a directory, spawn.

Board frames 49 (*Spawn session — default*) and 50 (*ready*). The sheet is the only way
to start a session from the phone, and its failure mode is the quiet one: the button
looks tapped, the log line says "spawning", and nothing joins the roster. The case
drives the sheet in Chromium against the rig (stub `claude` on its PATH, a private tmux
server) and asserts the three places a spawn must show up:

1. **the gate** (frame 49): with nothing chosen the spawn button is disabled; with an
   expert and a directory chosen it is enabled (measured both ways, so "enabled" means
   something);
2. **tmux**: a new window exists on the rig's server whose pane runs the stub agent
   (`STUB-AGENT claude` on screen) — the window is real, not a row painted from a
   response;
3. **the roster**: after the sheet closes, the roster has one more row than before, and
   its name is the new window's name.

Locating: `#spawn-btn`, the `.chip` buttons by their text (the expert and directory
names the server offers through `/api/spawn-options`), `#spawn-go`.

**Driven red** by mutating a copy of `app.js` so `doSpawn` posts `scope: ""`: the
server refuses, no window appears, and the case names the sheet's log text.
"""

from __future__ import annotations

import time

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_browser import add_windows, browser, collapsed, finding, wait_count
from ._console_rig import console_rig


def run() -> Finding | None:
    with console_rig() as rig:
        add_windows(rig, ("w-one",))
        before = rig.window_names()
        with browser(rig.base) as (page, watch):
            page.goto(rig.base + "/")
            if wait_count(page, ".srow", len(before)) < len(before):
                return collapsed("the roster did not render before the sheet was opened",
                                 f"windows={before}")
            rows_before = page.locator(".srow").count()
            page.click("#spawn-btn")
            page.wait_for_selector("#spawn", state="visible", timeout=5000)
            if wait_count(page, "#spawn-scopes .chip", 1) < 1 \
                    or wait_count(page, "#spawn-dirs .chip", 1) < 1:
                return collapsed("the spawn sheet offered no expert or directory chips, "
                                 "so nothing could be chosen",
                                 f"sheet text={page.inner_text('#spawn')[:300]!r}")

            if not page.is_disabled("#spawn-go"):
                return finding(FailureClass.FAILED_OPEN,
                               "the spawn button is enabled before an expert and a "
                               "directory are chosen (board frame 49: default state)",
                               f"#spawn-go disabled=False, sheet={page.inner_text('#spawn')[:200]!r}")
            page.locator("#spawn-scopes .chip", has_text="literature").first.click()
            page.locator("#spawn-dirs .chip", has_text="beta").first.click()
            if page.is_disabled("#spawn-go"):
                return collapsed("choosing an expert and a directory did not enable the "
                                 "spawn button (board frame 50: ready), so the spawn "
                                 "cannot be driven",
                                 f"sheet={page.inner_text('#spawn')[:300]!r}")
            page.click("#spawn-go")

            new = rig.wait_for(lambda: [w for w in rig.window_names()
                                        if w not in before] or None, timeout=25)
            log = page.inner_text("#spawn-log") if page.locator("#spawn-log").is_visible() else ""
            if not new:
                return finding(FailureClass.INVARIANT_FALSIFIED,
                               "tapping spawn with an expert and a directory chosen "
                               "created no tmux window",
                               f"windows before={before} after={rig.window_names()}; "
                               f"sheet log={log[:300]!r}; console log tail="
                               f"{rig.log_tail(400)!r}")
            idx, name = new[0]
            shown = rig.wait_for(lambda: "STUB-AGENT" in rig.capture(idx), timeout=10)
            if not shown:
                return finding(FailureClass.INVARIANT_FALSIFIED,
                               "the spawned window exists but is not running the agent "
                               "the sheet asked for",
                               f"window {idx} ({name}) pane={rig.capture(idx)[:200]!r}")
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if page.locator(".srow").count() >= rows_before + 1:
                    break
                time.sleep(0.2)
            rows = [t.strip() for t in page.locator(".srow-name").all_inner_texts()]
            if page.locator(".srow").count() != rows_before + 1 or name not in rows:
                return finding(FailureClass.INVARIANT_FALSIFIED,
                               "the spawned window never appeared as a roster row",
                               f"new window {idx}:{name}; rows before={rows_before}; "
                               f"rows after={rows}")
    return None


CASE = Case(
    name="browser-spawn-sheet-round-trip-creates-window-and-row",
    tier=Tier.BROWSER,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_PLAYWRIGHT),
    classes=(FailureClass.FAILED_OPEN, FailureClass.INVARIANT_FALSIFIED,
             FailureClass.COLLAPSED_SENTINEL),
    summary="the spawn sheet is gated until an expert and directory are chosen, and a "
            "spawn creates a real tmux window and a roster row",
    run=run,
)

CASES = (CASE,)
