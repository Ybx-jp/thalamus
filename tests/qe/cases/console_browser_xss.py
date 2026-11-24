"""Strings the jobs source sends are text on the console's pages, never markup.

The jobs and board pages draw data that belongs to another program (`jobs_source.py`:
"the console knows nothing about that program's schema"). Some of that data is written
by models reading the web (a run's raw event stream is "web pages a research stage
fetched", `jobs.js`), so any string on these pages can be attacker-chosen. The board's
rule, and the pages' own comment on their DOM builder: *"Moves render as text, never
as HTML"*, *"Strings become text nodes, always; there is no path from data to markup"*.

The case runs the real console with `--jobs-source` pointed at a recording stub, and has
the stub answer **every screen's every display string with a hostile one** (seven shapes
cycled: `<img onerror>`, `<script>`, an attribute break-out into `<svg onload>`, a
`javascript:` URL, an `<a href=javascript:>`, an `<iframe srcdoc>`, a `<style>`). Then it
opens each screen in Chromium and asserts, per screen:

1. nothing ran: `window.__qe_xss` (pushed to by every payload) is empty;
2. nothing was inserted: a MutationObserver installed before any page script saw no
   inline `<script>`, `<img>`, `<object>`, `<embed>`, stray `<iframe>`, element with an
   `on*` attribute or `javascript:` URL, and a DOM scan of `#main` agrees;
3. **the control**: the payload text is *visible* on the screen as literal text
   (`<img src=x` and a `QX<n>` tag in the screen's text). If a screen shows no payload
   the case cannot conclude, and says so (collapsed sentinel) instead of passing.

The pages ship a CSP (`script-src 'self'`) that blocks inline handlers, so (1) alone
would pass even over an `innerHTML` sink; (2) is what catches the sink. Screens: J1,
J2, J3, J4, J5 (and its raw event stream), J6, a commit, and D1 at desktop width (the
graph and version lane). The board case does the same for all eight widget kinds.

**Driven red** by mutating a copy of `jobs.js` so `jobRow` builds its name with
`innerHTML`: the observer reports the inserted `<img>` / attribute on J1, naming the
payload tag. Arms with `CONSOLE_UNBUILT_JOBS_PAGE`; the board case with `_BOARD_PAGE`.
"""

from __future__ import annotations

import re
import time

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_browser import (XSS_WATCH, board_world, browser, collapsed, finding,
                               jobs_world, payload, source_responder, xss_state)
from ._console_rig import console_rig, jobs_source

_JOBS_ROUTES = (
    ("J1 list", "#/"),
    ("J2 job", "#/job/j1"),
    ("J3 history", "#/job/j1/history"),
    ("J4 change", "#/change/abc123"),
    ("J5 run", "#/run/r1"),
    ("J5 raw stream", "#/run/r1?view=events"),
    ("J6 repo", "#/repo"),
    ("commit", "#/commit/abc123"),
)

_DOM_SCAN = """() => {
  const bad = [];
  document.querySelectorAll('#main *').forEach((e) => {
    const t = e.tagName;
    if (['IMG', 'SCRIPT', 'OBJECT', 'EMBED', 'STYLE', 'LINK'].includes(t)) bad.push(e.outerHTML.slice(0, 140));
    else if (t === 'IFRAME' && !e.classList.contains('b-app-frame')) bad.push(e.outerHTML.slice(0, 140));
    else for (const a of e.attributes) {
      if (/^on/i.test(a.name) ||
          (/^(href|src|action|formaction|data|xlink:href)$/i.test(a.name)
           && /^\\s*javascript:/i.test(a.value))) { bad.push(e.outerHTML.slice(0, 140)); break; }
    }
  });
  return bad;
}"""


def _screen(page, base: str, where: str, label: str, *, page_path: str, ready: str
            ) -> Finding | None:
    """Open one screen, wait for it, and judge it. None = clean and the control held."""
    page.goto(base + page_path + where)
    deadline = time.monotonic() + 8
    text = ""
    while time.monotonic() < deadline:
        text = page.inner_text("#main")
        if ready in text:
            break
        time.sleep(0.15)
    time.sleep(0.4)
    text = page.inner_text("#main")
    executed, inserted = xss_state(page)
    scan = page.evaluate(_DOM_SCAN)
    if executed or inserted or scan:
        return finding(
            FailureClass.BOUNDARY_LEAK,
            f"a string from the jobs source was parsed as markup on the {label} screen",
            f"{label} {page_path}{where}: executed={executed[:4]}; inserted="
            f"{[i[:140] for i in inserted[:3]]}; DOM scan={scan[:3]}",
            site="packages/thalamus-console/src/thalamus_console/static/"
                 + page_path.lstrip("/").replace(".html", ".js"))
    tags = set(re.findall(r"QX\d+", text))
    if ("<img src=x" not in text and "<script>" not in text) or len(tags) < 2:
        return collapsed(
            f"the {label} screen did not show the hostile strings as visible text, so "
            "'nothing ran' says nothing about it",
            f"{page_path}{where}: visible tags={sorted(tags)[:6]}; text={text[:240]!r}")
    return None


def run_jobs() -> Finding | None:
    world = jobs_world(payload)
    with jobs_source(responder=source_responder(world)) as src:
        with console_rig(extra_args=("--jobs-source", src.url,
                                     "--jobs-token-file", str(src.token_file))) as rig:
            with browser(rig.base, init_script=XSS_WATCH) as (page, _w):
                for label, where in _JOBS_ROUTES:
                    r = _screen(page, rig.base, where, label,
                                page_path="/jobs.html", ready="QX")
                    if r:
                        return r
            # D1: the desktop canvas draws the graph and the version lane.
            with browser(rig.base, init_script=XSS_WATCH,
                         viewport={"width": 1440, "height": 900}) as (page, _w):
                r = _screen(page, rig.base, "#/", "D1 canvas", page_path="/jobs.html",
                            ready="QX")
                if r:
                    return r
            if not any(rq.path.startswith("/v1/console/") for rq in src.requests):
                return collapsed("the source received no request, so the pages were not "
                                 "reading it", "src.requests is empty")
    return None


def run_board() -> Finding | None:
    board = board_world(payload)
    world = jobs_world(payload)
    resp = source_responder(world, board=board,
                            app_html="<!doctype html><p>benign</p>",
                            app_headers={})
    with jobs_source(responder=resp) as src:
        with console_rig(extra_args=("--jobs-source", src.url,
                                     "--jobs-token-file", str(src.token_file))) as rig:
            for label, vp in (("board phone", None),
                              ("board desktop", {"width": 1440, "height": 900})):
                with browser(rig.base, init_script=XSS_WATCH, viewport=vp) as (page, _w):
                    r = _screen(page, rig.base, "", label, page_path="/board.html",
                                ready="QX")
                    if r:
                        return r
    return None


CASE = Case(
    name="browser-jobs-source-strings-render-as-text-not-markup",
    tier=Tier.BROWSER,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_PLAYWRIGHT,
               Substrate.CONSOLE_UNBUILT_JOBS_API, Substrate.CONSOLE_UNBUILT_JOBS_PAGE),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="every display string a jobs source sends is shown as literal text on every "
            "jobs screen; none runs, none is inserted as markup",
    run=run_jobs,
)

CASE_BOARD = Case(
    name="browser-board-widget-strings-render-as-text-not-markup",
    tier=Tier.BROWSER,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_PLAYWRIGHT,
               Substrate.CONSOLE_UNBUILT_JOBS_API, Substrate.CONSOLE_UNBUILT_BOARD_PAGE),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="every string in every board widget kind's answer is shown as literal text; "
            "none runs, none is inserted as markup",
    run=run_board,
)

CASES = (CASE, CASE_BOARD)
