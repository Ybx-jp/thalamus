"""A real Chromium on a real console — the shared instrument of the browser arm.

Not a case. `console_browser_*` cases drive the console's own pages through Playwright
(sync API, headless Chromium) against the rig in `_console_rig`, and every one of them
needs the same four things this module keeps in one place:

- a 430x932 page, the viewport the design board is drawn at;
- a record of everything the page did that it should not have: `pageerror`s, console
  errors, failed same-origin requests and **every request to an origin other than the
  console's** (the console is a private-network tool; a foreign request is a leak
  whether or not the server meant it);
- a way to wait on the DOM that returns what it saw rather than raising, so a case can
  state a denominator ("0 rows rendered") instead of dying on a timeout;
- `finding()` to build a `Finding` whose `site` defaults to the console's static tree.

**Locating things.** Shipped surfaces are located by the ids and classes the existing
DOM walker (`.github/workflows/contrast-dom-driver.mjs`) already depends on (`.srow`,
`#msg`, `#send`, `#spawn-btn`). Surfaces still on the board are located by accessible
role and the board's own words, never by a guessed class.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..model import FailureClass, Finding

VIEWPORT = {"width": 430, "height": 932}
SITE = "packages/thalamus-console/src/thalamus_console/static/"


@dataclass
class Watch:
    """What a page did, collected while a case drives it."""

    origin: str
    page_errors: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    foreign: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    requests: list[str] = field(default_factory=list)

    def clean(self) -> bool:
        return not (self.page_errors or self.console_errors or self.foreign)

    def describe(self) -> str:
        bits = []
        if self.page_errors:
            bits.append("pageerror: " + " | ".join(self.page_errors[:3]))
        if self.console_errors:
            bits.append("console.error: " + " | ".join(self.console_errors[:3]))
        if self.foreign:
            bits.append("foreign request: " + " | ".join(self.foreign[:3]))
        return "; ".join(bits)


def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


@contextlib.contextmanager
def browser(base: str, *, init_script: str | None = None,
            extra_origins: tuple[str, ...] = (), viewport: dict | None = None
            ) -> Iterator[tuple[object, Watch]]:
    """Yield `(page, watch)` for a fresh Chromium context. Closed on exit.

    `extra_origins` are origins a case itself serves (a stub source the page may reach
    through the console's proxy never needs listing — the browser only ever talks to the
    console; this is for a page that is *meant* to be handed another origin).
    """
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    watch = Watch(origin=_origin(base))
    allowed = {watch.origin, *extra_origins}
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            ctx = b.new_context(viewport=viewport or VIEWPORT, service_workers="block")
            if init_script:
                ctx.add_init_script(init_script)
            page = ctx.new_page()
            page.on("pageerror", lambda e: watch.page_errors.append(str(e)[:300]))
            page.on("console", lambda m: m.type == "error"
                    and watch.console_errors.append(m.text[:300]))

            def on_request(r) -> None:
                u = r.url
                if u.startswith(("data:", "blob:", "about:")):
                    return
                watch.requests.append(u)
                if _origin(u) not in allowed:
                    watch.foreign.append(u)

            page.on("request", on_request)
            page.on("requestfailed", lambda r: watch.failed.append(
                f"{r.url} {r.failure}"))
            yield page, watch
        finally:
            b.close()


def wait_count(page, selector: str, at_least: int, timeout: float = 10.0) -> int:
    """Poll until `selector` matches at least `at_least` nodes; return the count seen."""
    deadline = time.monotonic() + timeout
    n = 0
    while time.monotonic() < deadline:
        n = page.locator(selector).count()
        if n >= at_least:
            return n
        time.sleep(0.1)
    return n


def wait_text(page, needle: str, timeout: float = 8.0) -> bool:
    """Is `needle` in the page's visible text within the timeout?"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if needle in page.inner_text("body"):
            return True
        time.sleep(0.1)
    return False


def finding(cls: FailureClass, summary: str, witness: str, site: str = SITE) -> Finding:
    return Finding(failure_class=cls, summary=summary, witness=witness, site=site)


def collapsed(summary: str, witness: str, site: str = "tests/qe/cases/_console_browser.py"
              ) -> Finding:
    """The case could not conclude. Never a pass, and named as the instrument's fault."""
    return Finding(failure_class=FailureClass.COLLAPSED_SENTINEL, summary=summary,
                   witness=witness, site=site)


def add_windows(rig, names: tuple[str, ...]) -> None:
    """Extra tmux windows on the rig's private server, each a live `cat` that says hello.

    `-c` pins the cwd to the rig's root: a window created without it starts in the
    caller's directory, which is the operator's checkout.
    """
    for n in names:
        r = rig.tmux("new-window", "-d", "-t", rig.session + ":", "-n", n, "-c", str(rig.root),
                     f"sh -c 'echo HELLO-{n}; exec cat'")
        if r.returncode != 0:
            raise RuntimeError(f"could not add window {n}: {r.stderr}")


# ---------------------------------------------------------------------------
# A stub jobs source that answers the shapes the jobs and board pages read.
#
# The shapes are fixtures read off `static/jobs.js` and `static/board.js` of the tree
# that builds those pages; what they are *judged* against is the board's own rules
# (every status arrives as a word and a tone and the client prints the word; moves and
# every other source string render as text, never as HTML). Every display string is
# supplied by a callable `S(n)` so a case chooses what the source says: an XSS payload
# for the markup property, a plain word for the emptiness property.
# ---------------------------------------------------------------------------

PREFIX = "/v1/console/"


def payload(n: int) -> str:
    """The n-th hostile string. Each names `QX<n>` so a witness says which field ran."""
    tag = f"QX{n}"
    push = f"window.__qe_xss.push('{tag}')"
    return (
        f"<img src=x onerror=\"{push}\">{tag}",
        f"<script>{push}</script>{tag}",
        f"\"><svg onload=\"{push}\">{tag}",
        f"javascript:{push};{tag}",
        f"<a href=\"javascript:{push}\">{tag}</a>",
        f"<iframe srcdoc=\"<script>parent.{push}</script>\"></iframe>{tag}",
        f"</div><style>body{{display:none}}</style>{tag}",
    )[n % 7]


def jobs_world(S) -> dict:
    """Responses for every screen of the jobs page, each display string from `S(n)`."""
    c = iter(range(10_000))

    def s() -> str:
        return S(next(c))

    def st(tone: str = "ok") -> dict:
        return {"word": s(), "tone": tone}

    def diff() -> dict:
        return {"path": s(), "added": 1, "removed": 1,
                "lines": [{"op": "+", "text": s()}, {"op": "-", "text": s()},
                          {"op": " ", "text": s()}]}

    run = {"id": "r1", "label": s(), "version": s(), "status": st()}
    return {
        "jobs": {"banner": {"change": "abc123", "title": s(), "line": s()}, "summary": s(),
                 "groups": [{"name": s(), "note": s(), "jobs": [
                     {"id": "j1", "name": s(), "line": s(), "status": st(), "runnable": True}]}]},
        "jobs/j1": {"id": "j1", "name": s(), "scope": s(),
                    "header": {"line": s(), "sub": s()}, "run": run, "runs": [run],
                    "drift": {"title": s(), "line": s()}, "replay_note": s(),
                    "actions": {"run_now": True, "replay": True}, "auto_apply": True,
                    "stages": [{"name": s(), "status": st(), "reached": True, "changed": True,
                                "lines": [s()], "mono": [s()], "out": s(),
                                "progress": {"used": 3, "cap": 10, "segments": [{"n": 3}]}}]},
        "jobs/j1/history": {"columns": [s()], "more": True, "items": [
            {"type": "commit", "sha": s(), "subject": s(), "line": s(), "head": True,
             "change": "abc123"},
            {"type": "empty", "text": s()},
            {"type": "replays", "title": s(), "line": s(), "rows": [s()], "note": s(),
             "grid": [[{"word": s(), "tone": "ok"}]]},
            {"id": "r1", "title": s(), "line": s(), "cells": [{"tone": "ok", "text": s()}]}]},
        "changes/abc123": {"sha": s(), "title": s(), "line": s(), "job": "j1",
                           "auto_apply": True, "revert": {"available": False, "reason": s()},
                           "gate": {"status": st(), "line": s(), "note": s(),
                                    "rows": [{"label": s(), "before": s(), "after": s()}],
                                    "checks": [{"label": s(), "passed": True}]},
                           "diff": [diff()]},
        "runs/r1": {"id": "r1", "title": s(), "job": s(), "status": st(), "line": s(),
                    "tiles": [{"label": s(), "value": s(), "sub": s()}], "events": 3,
                    "findings": {"heading": s(), "more": 2, "items": [
                        {"id": "f1", "title": s(), "kind": s(), "label": None},
                        {"id": "f2", "title": s(),
                         "rejected": {"word": s(), "line": s()}}]}},
        "runs/r1/events": {"more": False, "events": [
            {"seq": 1, "type": s(), "subtype": s(), "text": s()}]},
        "repo": {"name": s(), "status": st(), "line": s(), "summary": s(), "jobs": 2,
                 "commits": [{"sha": s(), "subject": s(), "line": s(), "tag": s()}]},
        "commits/abc123": {"sha": s(), "subject": s(), "line": s(), "tag": s(), "body": s(),
                           "change": "abc123", "files": [diff()],
                           "runs": [{"id": "r1", "label": s(), "status": st()}]},
        "graph": {"columns": [s()], "edges": [], "note": [{"col": 0, "row": 0, "text": s()}],
                  "nodes": [{"id": "n1", "col": 0, "row": 0, "title": s(), "line": s(),
                             "status": st(), "job": "j1", "scope": s(),
                             "stages": [{"name": s(), "text": s()}]}],
                  "lane": {"repo": s(), "commits": [{"sha": "c1x", "time": s(), "tag": s()}],
                           "jobs": [{"name": s(), "marks": [
                               {"sha": "c1x", "tone": "ok", "text": s()}]}]}},
    }


BOARD_KINDS = ("number", "series", "table", "tail", "inbox", "control", "note", "app")

SANDBOX_CSP = ("sandbox allow-scripts; default-src 'none'; script-src 'self' "
               "'wasm-unsafe-eval' blob:; worker-src blob:; connect-src 'self'; "
               "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'")


def board_world(S) -> dict:
    """Board screen responses: the widgets, and the eval answer by widget kind."""
    c = iter(range(20_000, 30_000))

    def s() -> str:
        return S(next(c))

    widgets = [{"id": f"w-{k}", "kind": k, "title": s(), "binding": {}, "show_when": "always",
                "x": i % 4, "y": (i // 4) * 3, "w": 1, "h": 3}
               for i, k in enumerate(BOARD_KINDS)]
    evals = {
        "number": {"title": s(), "value": s(), "compare": s(), "foot": s(), "run": "r1",
                   "bars": [{"label": s(), "value": 3, "text": s()}]},
        "series": {"title": s(), "foot": s(), "ticks": [{"value": 1, "text": s()}],
                   "line": [{"label": s(), "value": 1, "text": s()},
                            {"label": s(), "value": 2, "text": s()}]},
        "table": {"title": s(), "columns": [s(), s()], "rows": [[s(), s()]],
                  "total": [s(), s()], "runs": ["r1"], "foot": s()},
        "tail": {"title": s(), "rows": [{"time": s(), "source": s(), "kind": s()}]},
        "inbox": {"title": s(), "items": [{"id": "f1", "title": s(), "kind": s(),
                                           "label": None}]},
        "control": {"title": s(), "items": [
            {"type": "mute", "scope": "main", "label": s(), "line": s(), "on": True},
            {"type": "run", "job": "j1", "label": s()}]},
        "note": {"title": s(), "text": s(), "line": s(), "tone": s()},
        "app": {"title": s(), "app": "qe-app"},
    }
    return {"widgets": widgets, "evals": evals}


def source_responder(world: dict, *, board: dict | None = None, app_html: str = "",
                     app_headers: dict | None = None, app_js: str = ""):
    """A `JobsSource` responder serving `world` (jobs screens) and optionally a board.

    An app's files are `apps/<app>/files/<path>`: `*.js` answers `app_js`, anything else
    `app_html`, both with `app_headers` (an app's script must be a file, not inline,
    under the documented `script-src 'self'` policy).
    """
    import json as _json
    from urllib.parse import urlsplit as _split

    def respond(req):
        path = _split(req.path).path
        rest = path[len(PREFIX):] if path.startswith(PREFIX) else path
        jh = {"Content-Type": "application/json"}

        def ok(obj):
            return 200, jh, _json.dumps(obj).encode()

        if rest.startswith("apps/") and "/files/" in rest and rest.endswith(".js"):
            return 200, {"Content-Type": "application/javascript", **(app_headers or {})}, \
                app_js.encode()
        if rest.startswith("apps/") and "/files/" in rest:
            return 200, {"Content-Type": "text/html; charset=utf-8", **(app_headers or {})}, \
                app_html.encode()
        if board is not None:
            if rest == "board" and req.method == "GET":
                return ok({"widgets": board["widgets"], "version": "v1"})
            if rest == "board/eval":
                kind = (_json.loads(req.body or b"{}").get("widget") or {}).get("kind")
                return ok(board["evals"].get(kind, {}))
            if rest == "board/sources":
                return ok({"sources": [], "suggestions": []})
            if rest == "apps":
                return ok({"apps": []})
        if rest in world:
            return ok(world[rest])
        return 404, jh, _json.dumps({"error": "no such thing: " + rest}).encode()

    return respond


# Installed before any page script. Records what a string must never cause: running a
# payload (`__qe_xss`), and inserting an inline script, an image, a stray frame, an
# embed, or any element carrying an `on*` attribute or a `javascript:` URL
# (`__qe_ins`). An element a later repaint removes is still recorded.
XSS_WATCH = r"""
window.__qe_xss = [];
window.__qe_ins = [];
(function () {
  function sus(el) {
    if (!el || el.nodeType !== 1) return null;
    var t = el.tagName;
    if (t === 'SCRIPT' && !el.getAttribute('src')) return 'inline <script>';
    if (t === 'IMG' || t === 'OBJECT' || t === 'EMBED') return '<' + t.toLowerCase() + '>';
    if (t === 'IFRAME' && !(el.classList && el.classList.contains('b-app-frame')))
      return '<iframe>';
    for (var i = 0; i < el.attributes.length; i++) {
      var n = el.attributes[i].name.toLowerCase(), v = el.attributes[i].value;
      if (n.indexOf('on') === 0) return 'attribute ' + n;
      if ((n === 'href' || n === 'src') && /^\s*javascript:/i.test(v)) return n + '=javascript:';
    }
    return null;
  }
  function visit(el) {
    var why = sus(el);
    if (why) window.__qe_ins.push(why + ' in ' + el.outerHTML.slice(0, 120));
    if (el.children) for (var k = 0; k < el.children.length; k++) visit(el.children[k]);
  }
  new MutationObserver(function (muts) {
    muts.forEach(function (m) {
      m.addedNodes.forEach(visit);
      if (m.type === 'attributes') {
        var why = sus(m.target);
        if (why) window.__qe_ins.push(why + ' in ' + m.target.outerHTML.slice(0, 120));
      }
    });
  }).observe(document, {childList: true, subtree: true, attributes: true});
})();
"""


def xss_state(page) -> tuple[list, list]:
    """(payloads that executed, markup the observer saw inserted)."""
    return (page.evaluate("window.__qe_xss || []"), page.evaluate("window.__qe_ins || []"))
