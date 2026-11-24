"""A page a job built must not be able to run in the console's origin.

The board's App widget is "a page a person or a job built, in a sandboxed frame; reads only
what its binding grants" (board notes N2/N3), and the same note says plainly that it "needs
a sandbox and a grant model before any job may publish one". The console is where that
page's bytes arrive: the jobs source serves `apps/<name>/files/<file>` and the console
relays them under `GET /api/jobs/apps/<name>/files/<file>`. That URL is on the console's own
origin, and the console's origin can type into every tmux session
(`/api/send`, `/api/key`) with the Origin gate passing it, because the request *is*
same-origin.

So the only thing between a job-authored `index.html` and a script with the operator's whole
control plane is the browser being told not to give that document the console's origin. A
sandboxed `<iframe>` is the board page's half of that and is unavailable to anyone who
simply *navigates* to the URL — a link, a redirect, an `<a>` an app renders into another app.
The half that holds for every route to the bytes is a response header: `Content-Security-Policy:
sandbox ...` without `allow-same-origin`, which applies to the document however it was
reached. `jobs_source.PASSED_HEADERS` relays the *source's* CSP and adds none of the
console's own, so what the console does depends entirely on what the source remembered to
send — and the source's author is the job.

**Property.** For every response the relay serves whose content type a browser will execute
(`text/html`, `application/xhtml+xml`, `image/svg+xml`), at least one `Content-Security-Policy`
header on the reply carries a `sandbox` directive that does not grant `allow-same-origin`,
whatever the source sent: nothing, a policy that omits `sandbox`, or a `sandbox
allow-same-origin allow-scripts` of its own.

Asserted over real HTTP, reading every response header (repeats kept), against a recording
stub source that serves a script-carrying page. The browser arm proves the consequence in
Chromium; this case proves the header.

**Control.** A source that sends a distinctive policy of its own
(`img-src data: 'self'; qe-control`) must come through with exactly that value, so the probe
reads the CSP lines the console relays and a pass is not "this reader sees no CSP"; each
page must also arrive byte-identical with the content type the source set, so the property
is judged on the document a browser would run.

**Shown capable of going red and green** (2026-11-24, `QE_CONSOLE_SRC`). Green: the jobs
tree with `FORCED_HEADERS` (a `sandbox allow-scripts` line on every `/api/jobs/` reply,
sent beside the source's own) passes all nine combinations. Red: a copy of that tree whose
`relay_headers` starts from `[]` instead of `list(FORCED_HEADERS)` — the relay of the
source's headers only — reports `boundary-leak`, witness `source served index.html as
text/html; charset=utf-8 with no CSP; ... Content-Security-Policy on the reply: none`.
"""

from __future__ import annotations

import http.client

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_rig import console_rig, jobs_source

_SITE = ("packages/thalamus-console/src/thalamus_console/server.py::Handler._jobs "
         "(jobs_source.PASSED_HEADERS)")
_SELF = "tests/qe/cases/console_integ_jobs_app_sandbox.py"

_PAGE = (b"<!doctype html><title>app</title><script>"
         b"fetch('/api/key',{method:'POST',body:JSON.stringify({index:0,key:'enter'})})"
         b"</script>")
_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg"><script>'
        b"fetch('/api/key',{method:'POST'})</script></svg>")
_XHTML = (b'<html xmlns="http://www.w3.org/1999/xhtml"><body>'
          b"<script>fetch('/api/key',{method:'POST'})</script></body></html>")

_CONTROL_POLICY = "img-src data: 'self'; qe-control"

_TYPES = (("text/html; charset=utf-8", _PAGE, "index.html"),
          ("application/xhtml+xml", _XHTML, "page.xhtml"),
          ("image/svg+xml", _SVG, "logo.svg"))


def _get(rig, path):
    conn = http.client.HTTPConnection("127.0.0.1", rig.port, timeout=20)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.getheaders(), resp.read()
    finally:
        conn.close()


def _sandboxed(headers) -> tuple[bool, list[str]]:
    csps = [v for k, v in headers if k.lower() == "content-security-policy"]
    for policy in csps:
        for directive in policy.split(";"):
            tokens = directive.split()
            if tokens and tokens[0].lower() == "sandbox" and "allow-same-origin" not in (
                    t.lower() for t in tokens[1:]):
                return True, csps
    return False, csps


def run() -> Finding | None:
    # what the source sends alongside the page: nothing, a policy without `sandbox`, a
    # policy that hands the document the console's origin back
    variants = {
        "no CSP": {},
        "a CSP with no sandbox": {"Content-Security-Policy": "default-src 'self'"},
        "a permissive sandbox": {"Content-Security-Policy":
                                 "sandbox allow-same-origin allow-scripts"},
    }
    state = {"extra": {}, "ctype": _TYPES[0][0], "body": _PAGE}

    def responder(req):
        if req.path.endswith("/control-csp"):
            return 200, {"Content-Type": "text/html",
                         "Content-Security-Policy": _CONTROL_POLICY}, _PAGE
        return 200, {"Content-Type": state["ctype"], **state["extra"]}, state["body"]

    with jobs_source(responder=responder) as src, console_rig(
            extra_args=("--jobs-source", src.url, "--jobs-token-file",
                        str(src.token_file))) as rig:
        # control: a policy the source sends comes through the relay and is readable
        # here — a distinctive one, so it cannot be mistaken for anything the console
        # adds itself. Without this, "no sandbox seen" could be "this reader sees no CSP".
        status, headers, _b = _get(rig, "/api/jobs/apps/x/files/control-csp")
        _ok, csps = _sandboxed(headers)
        if status != 200 or _CONTROL_POLICY not in csps:
            return Finding(
                FailureClass.COLLAPSED_SENTINEL,
                "a source-supplied policy did not come through the relay, so this case "
                "cannot read what the console serves",
                witness=f"status={status} CSP headers={csps}", site=_SITE)

        for label, extra in variants.items():
            for ctype, body, name in _TYPES:
                state.update(extra=extra, ctype=ctype, body=body)
                status, headers, got = _get(rig, f"/api/jobs/apps/x/files/{name}")
                served_type = next((v for k, v in headers if k.lower() == "content-type"),
                                   "")
                if status != 200 or got != body or ctype.split(";")[0] not in served_type:
                    return Finding(
                        FailureClass.COLLAPSED_SENTINEL,
                        "fixture: the app file did not arrive as the source served it",
                        witness=f"{name}: status={status} type={served_type!r} "
                                f"body-equal={got == body}", site=_SITE)
                ok, csps = _sandboxed(headers)
                if not ok:
                    return Finding(
                        FailureClass.BOUNDARY_LEAK,
                        "the console serves a job-authored page from its own origin with "
                        "no sandbox of its own: a browser that navigates to the URL runs "
                        "the page's script as the console, which can type into every tmux "
                        "session through /api/send and /api/key and passes the Origin "
                        "gate as same-origin",
                        witness=f"source served {name} as {ctype} with {label}; "
                                f"GET /api/jobs/apps/x/files/{name} -> {status}, "
                                f"Content-Security-Policy on the reply: "
                                f"{csps or 'none'}; body runs fetch('/api/key') "
                                f"same-origin",
                        site=_SITE)
    return None


CASE = Case(
    name="console-jobs-app-files-cannot-run-in-the-consoles-origin",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX, Substrate.CONSOLE_UNBUILT_JOBS_API),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="an HTML, XHTML or SVG file relayed from the jobs source carries a console-"
            "enforced CSP sandbox without allow-same-origin, whatever the source sent",
    run=run,
)
