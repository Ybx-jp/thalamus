"""An app widget's page cannot drive the console, framed or navigated to.

Board: an App is *"a page a person or a job built, in a sandboxed frame; reads only what
its binding grants"*. A page a **job** built is code nobody on this machine reviewed, and
the console is the thing that can type into every agent session on it
(`/api/send` is `tmux send-keys`). The documented defence (`docs/console-jobs-source.md`)
is that the source serves app files with `Content-Security-Policy: sandbox allow-scripts
...`, the board frames them with `sandbox="allow-scripts"` and no `allow-same-origin`,
and so any request the page sends carries `Origin: null` and the console's Origin gate
refuses it.

Two cases, two different places that defence can fail:

1. **`navigated`** (needs the jobs proxy only). The console serves the source's reply on
   its *own* origin at `/api/jobs/apps/<app>/files/index.html`. Anyone can navigate a tab
   there: a link, a redirect, an `<a target=_top>`. If the source's reply carries no
   `sandbox` CSP (a source that forgot, an older one, a job-built file served by a
   source that does not set it) the page runs **same-origin with the console**, and
   `fetch('/api/send', {method: 'POST'})` carries the console's own Origin and passes
   its gate. The case serves such a page, navigates the browser to it top-level, and the
   page types a unique string at the rig's window. Arrival in the pane is a boundary
   leak, with the pane capture as the witness. Controls: (a) the instrument — a fetch
   from the console's own origin must arrive; (b) the same page served **with** the
   documented sandbox CSP must not arrive, which shows the leak (if any) is the missing
   header and not the harness. Three replies are driven, because the guarantee belongs
   to the console and not to whichever path a source chose to answer with HTML: an app
   file with no policy, a non-app path (`runs/qe-run/report`) with no policy, and an app
   file whose source sends a permissive policy with no `sandbox` — a source's policy may
   tighten the console's sandbox and must never stand in for it.
2. **`framed`** (needs the board page). The App widget's iframe carries `sandbox` with
   `allow-scripts` and with none of `allow-same-origin`, `allow-top-navigation*`,
   `allow-popups*`, `allow-forms`, `allow-modals`; the frame's own `self.origin` is
   `"null"`; and the same hostile page, running inside it, cannot get text into the pane.
   Controls: the page demonstrably ran (`window.__ran`), and it demonstrably sent the
   request (Playwright saw a POST to `/api/send` leave the frame).

**Driven red** by mutating a copy of `board.js` so the frame gets `allow-same-origin`
(`framed`). `navigated` went red on the jobs tree before the console forced its own
policy (the no-CSP app page reached the pane); against that fix it is green, and each of
the other two replies goes red on its own mutant of the fix — the policy forced only on
`apps/*/files/*` paths (the non-app reply arrives), and the source's policy replacing the
console's instead of joining it (the permissive reply arrives).
"""

from __future__ import annotations

import json
import time
import uuid

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_browser import (SANDBOX_CSP, add_windows, board_world, browser, collapsed,
                               finding, jobs_world, source_responder)
from ._console_rig import console_rig, jobs_source

SITE = "packages/thalamus-console/src/thalamus_console/jobs_source.py"


_HTML = '<!doctype html><title>qe app</title><script src="a.js"></script><p>qe app</p>'


def _attack(text: str, index: int) -> str:
    """The app's script. A file, not inline: the documented policy's `script-src 'self'`
    would block an inline one and the 'with the policy' control would then be vacuous."""
    body = json.dumps({"index": index, "text": text})
    return ("window.__ran = true;\n"
            "fetch('/api/send', {method: 'POST', headers: {'Content-Type': 'text/plain'},\n"
            f"  body: {json.dumps(body)}}})\n"
            "  .then(function (r) { window.__res = r.status; },\n"
            "        function (e) { window.__res = 'err: ' + e; });")


def _arrived(rig, index: int, text: str, timeout: float = 5.0) -> bool:
    return bool(rig.wait_for(lambda: text in rig.capture(index), timeout=timeout))


def run_navigated() -> Finding | None:
    world = {"jobs": {"groups": [], "summary": ""}}
    text_open = "QE-APP-NOCSP-" + uuid.uuid4().hex[:8]
    text_csp = "QE-APP-CSP-" + uuid.uuid4().hex[:8]
    state = {"js": _attack(text_open, 0), "headers": {}}

    def responder(req):
        # A source answering HTML on a path that is not an app file: the console's
        # guarantee has to hold there too, since nothing stops a source doing it.
        if req.path.split("?", 1)[0] == "/v1/console/runs/qe-run/report":
            return 200, {"Content-Type": "text/html; charset=utf-8", **state["headers"]}, \
                _HTML.encode()
        if req.path.split("?", 1)[0] == "/v1/console/runs/qe-run/a.js":
            return 200, {"Content-Type": "application/javascript", **state["headers"]}, \
                state["js"].encode()
        return source_responder(world, app_html=_HTML, app_js=state["js"],
                                app_headers=state["headers"])(req)

    with jobs_source(responder=responder) as src:
        with console_rig(extra_args=("--jobs-source", src.url,
                                     "--jobs-token-file", str(src.token_file))) as rig:
            add_windows(rig, ("w-one",))
            target = 0
            url = rig.base + "/api/jobs/apps/qe-app/files/index.html"
            with browser(rig.base) as (page, _w):
                # Control (a): a request from the console's own origin must arrive.
                ctl = "QE-CTL-" + uuid.uuid4().hex[:8]
                page.goto(rig.base + "/")
                page.evaluate("t => fetch('/api/send', {method: 'POST', headers: "
                              "{'Content-Type': 'application/json'}, body: JSON.stringify("
                              f"{{index: {target}, text: t}})}})", ctl)
                if not _arrived(rig, target, ctl):
                    return collapsed("a send from the console's own origin did not reach "
                                     "the pane, so an app page's send could not be seen "
                                     "arriving either", f"pane={rig.capture(target)[:200]!r}")

                # Control (b): the documented policy. Same page, sandbox CSP.
                state["js"] = _attack(text_csp, target)
                state["headers"] = {"Content-Security-Policy": SANDBOX_CSP}
                page.goto(url)
                time.sleep(0.5)
                ran_csp = page.evaluate("window.__ran === true")
                if not ran_csp:
                    return collapsed("the app's script did not run under the documented "
                                     "sandbox CSP, so 'did not arrive' under it proves "
                                     "nothing", f"url={url}")
                if _arrived(rig, target, text_csp, timeout=3):
                    return finding(
                        FailureClass.BOUNDARY_LEAK,
                        "an app page served WITH the documented sandbox CSP still typed "
                        "into a console window",
                        f"navigated to {url} with CSP; pane {target}: "
                        f"{rig.capture(target)[:300]!r}", SITE)

                # The case: replies whose policy the source got wrong. The guarantee is
                # the console's, so it holds on every /api/jobs/ path a source can answer
                # with HTML — not only app files — and a policy the source does send can
                # tighten the sandbox but never remove it.
                variants = (
                    ("app file, no policy", url, {}),
                    ("non-app path, no policy", rig.base + "/api/jobs/runs/qe-run/report",
                     {}),
                    ("app file, source policy without sandbox", url,
                     {"Content-Security-Policy": "default-src * 'unsafe-inline'"}),
                )
                for label, target_url, headers in variants:
                    text = "QE-APP-" + uuid.uuid4().hex[:8]
                    state["js"] = _attack(text, target)
                    state["headers"] = headers
                    page.goto(target_url)
                    time.sleep(0.5)
                    if not page.evaluate("window.__ran === true"):
                        return collapsed("the page's script did not run when navigated to, "
                                         "so a send that never arrives proves nothing",
                                         f"{label}: url={target_url} ran_with_csp={ran_csp}")
                    if _arrived(rig, target, text):
                        sent = headers.get("Content-Security-Policy", "none")
                        return finding(
                            FailureClass.BOUNDARY_LEAK,
                            "a page the jobs source served without a sandbox CSP, opened "
                            "top-level on the console's origin, ran same-origin and typed "
                            "into a live agent window through /api/send",
                            f"{label}: GET {target_url} (stub reply: text/html, "
                            f"source Content-Security-Policy: {sent}) -> page script POSTed "
                            f"/api/send {{index: {target}, text: {text!r}}}; pane {target} "
                            f"now shows "
                            f"{[ln for ln in rig.capture(target).splitlines() if text in ln]!r}"
                            f"; the same page served with the documented sandbox CSP did "
                            f"not arrive; window.__res={page.evaluate('window.__res')!r}",
                            SITE)
    return None


_FORBIDDEN = {"allow-same-origin", "allow-top-navigation",
              "allow-top-navigation-by-user-activation", "allow-popups",
              "allow-popups-to-escape-sandbox", "allow-forms", "allow-modals"}


def run_framed() -> Finding | None:
    text = "QE-APP-FRAMED-" + uuid.uuid4().hex[:8]
    board = board_world(lambda n: f"w{n}")
    resp = source_responder(jobs_world(lambda n: f"w{n}"), board=board,
                            app_html=_HTML, app_js=_attack(text, 0),
                            app_headers={"Content-Security-Policy": SANDBOX_CSP})
    with jobs_source(responder=resp) as src:
        with console_rig(extra_args=("--jobs-source", src.url,
                                     "--jobs-token-file", str(src.token_file))) as rig:
            with browser(rig.base) as (page, watch):
                sent: list[dict] = []
                page.on("request", lambda r: r.method == "POST"
                        and r.url.endswith("/api/send") and sent.append(r.headers))
                ctl = "QE-CTL-" + uuid.uuid4().hex[:8]
                page.goto(rig.base + "/")
                page.evaluate("t => fetch('/api/send', {method: 'POST', headers: "
                              "{'Content-Type': 'application/json'}, body: JSON.stringify("
                              "{index: 0, text: t})})", ctl)
                if not _arrived(rig, 0, ctl):
                    return collapsed("a send from the console's own origin did not reach "
                                     "the pane", f"pane={rig.capture(0)[:200]!r}")
                sent.clear()
                page.goto(rig.base + "/board.html")
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not page.locator(
                        "#main iframe").count():
                    time.sleep(0.2)
                frames = page.locator("#main iframe")
                if frames.count() == 0:
                    return collapsed("the board rendered no iframe for its app widget, so "
                                     "there is no sandbox to read",
                                     f"main={page.inner_text('#main')[:200]!r}")
                for i in range(frames.count()):
                    tokens = set((frames.nth(i).get_attribute("sandbox") or "").split())
                    bad = sorted(tokens & _FORBIDDEN)
                    if bad or "allow-scripts" not in tokens or \
                            frames.nth(i).get_attribute("sandbox") is None:
                        return finding(
                            FailureClass.BOUNDARY_LEAK,
                            "the board's app frame is not sandboxed as the board says "
                            "(allow-scripts only, no allow-same-origin)",
                            f"iframe[{i}] sandbox={frames.nth(i).get_attribute('sandbox')!r}; "
                            f"forbidden present={bad}", "board.js appFrame")
                time.sleep(2.0)
                app = next((f for f in page.frames if "/apps/qe-app/files/" in f.url), None)
                if app is None:
                    return collapsed("no frame ever loaded the app's page",
                                     f"frames={[f.url for f in page.frames]}")
                if not app.evaluate("window.__ran === true"):
                    return collapsed("the app page's script did not run in its frame, so "
                                     "its send never being attempted proves nothing",
                                     f"frame={app.url}")
                origin = app.evaluate("self.origin")
                if origin != "null":
                    return finding(
                        FailureClass.BOUNDARY_LEAK,
                        "the app frame runs with a real origin, not an opaque one",
                        f"self.origin inside the frame = {origin!r}", "board.js appFrame")
                if not sent:
                    return collapsed("the sandboxed page's send did not leave the frame, "
                                     "so its not arriving proves nothing",
                                     f"requests={watch.requests[-6:]}")
                if _arrived(rig, 0, text, timeout=3):
                    return finding(
                        FailureClass.BOUNDARY_LEAK,
                        "a page running in the board's app frame typed into a console "
                        "window through /api/send",
                        f"sent headers={sent[0]}; pane 0: {rig.capture(0)[:300]!r}",
                        "board.js appFrame")
    return None


CASE = Case(
    name="browser-app-file-opened-top-level-cannot-drive-the-console",
    tier=Tier.BROWSER,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_PLAYWRIGHT,
               Substrate.CONSOLE_UNBUILT_JOBS_API),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="an app page served by the jobs source with no sandbox CSP, navigated to on "
            "the console's origin, must not be able to POST /api/send at a live window",
    run=run_navigated,
)

CASE_FRAMED = Case(
    name="browser-board-app-frame-is-sandboxed-and-cannot-drive-the-console",
    tier=Tier.BROWSER,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_PLAYWRIGHT,
               Substrate.CONSOLE_UNBUILT_JOBS_API, Substrate.CONSOLE_UNBUILT_BOARD_PAGE),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="the board's App widget frame has sandbox=allow-scripts only, an opaque "
            "origin, and a page inside it cannot type into a console window",
    run=run_framed,
)

CASES = (CASE, CASE_FRAMED)
