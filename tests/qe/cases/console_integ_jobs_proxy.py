"""The console's window onto the jobs source must keep its token, its origin gate and its
failure modes honest.

The jobs surfaces (design board page *Jobs*, handoff note N1) read a program that is not
the console. The console is configured with one source URL and a bearer token
(`--jobs-source`, `--jobs-token-file`), forwards `GET|POST /api/jobs/<rest>` to
`<source>/v1/console/<rest>` with the token attached server-side, and relays the reply.
Four things have to hold of that relay and none of them is a property of any one function:

1. *The token never reaches the browser, and never reaches anything but the source.* Not in
   a body, not in a header, not in an error reply — and not forwarded onward when the
   source answers with a redirect to somewhere else, which `urllib` follows by default and
   carries every header of the original request across. The browser's own `Authorization`
   and `Cookie` do not replace or join the token on the way to the source.
2. *A write is refused before anything reaches the source unless it comes from the
   console's own page* — the same `Origin` gate every other write has, including the
   `Origin: null` that a sandboxed app frame sends (an app widget, board note N3, runs in
   exactly that frame; whatever it can POST, it must not be able to POST *here*).
3. *Failures are failures.* No source configured is 404, on read and write alike; a source
   that does not answer is 502, a source that hangs up mid-reply is not a 200; neither reads
   as an empty list.
4. *The relay is not a header tap.* Only the headers the console names are passed on;
   `Set-Cookie`, `WWW-Authenticate`, `Location` and `Server` from the source are dropped.
   A path that would climb out of `/v1/console/` — `..`, a scheme, `//`, an escape — never
   reaches the source.

Real `thalamus console` subprocess (`_console_rig`) against a recording stub source
(`_console_rig.jobs_source`). The case is armed by `Substrate.CONSOLE_UNBUILT_JOBS_API` and
skips on a tree without the route.

**Controls.** A same-origin request must reach the stub with the token before any absence
is asserted (the probe can see what arrives at the source); a request with a legal path must
arrive as `/v1/console/<path>` before the hostile paths are judged by the stub's silence; a
`Content-Type` and `Cache-Control` from the source must be relayed before `Set-Cookie`'s
absence means anything; the console's own 404/502 bodies are scanned for the token the same
way the relayed ones are.

**Shown capable of going red and green** (2026-11-24, against the in-flight jobs tree
via `QE_CONSOLE_SRC`). Red as it stands: the redirect check reports the token arriving at a
second origin, and the failure case reports a truncated reply relayed as `200`. Green: a copy
whose `forward` opens the URL through `build_opener(<handler whose redirect_request returns
None>)` passes the proxy case in full — token, headers, hostile paths, origin gate. Red again
for the gate: replacing `if not self._origin_ok():` with `if False:` in `do_POST` makes the
cross-site POST reach the stub (`source received [('POST', '/v1/console/jobs/j1/run')]`).
"""

from __future__ import annotations

import http.client
import json
import socketserver
import threading
import urllib.parse

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_rig import console_rig, dead_port, jobs_source

_SITE = "packages/thalamus-console/src/thalamus_console/jobs_source.py::forward"
_SERVER = "packages/thalamus-console/src/thalamus_console/server.py::Handler._jobs"
_SELF = "tests/qe/cases/console_integ_jobs_proxy.py"
_EVIL = "https://evil.example"


def _f(summary, witness, site=_SITE, cls=FailureClass.BOUNDARY_LEAK):
    return Finding(cls, summary, witness=witness, site=site)


def _raw(rig, method, path, headers=None, body=None):
    """One request with *every* response header kept (a dict would collapse repeats)."""
    conn = http.client.HTTPConnection("127.0.0.1", rig.port, timeout=30)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, resp.getheaders(), data
    finally:
        conn.close()


def _hdr(headers, name):
    return [v for k, v in headers if k.lower() == name.lower()]


def _scan(token, status, headers, body):
    """Where in a reply the token appears, or ''."""
    hay = [f"header {k}: {v}" for k, v in headers] + [body.decode("latin-1")]
    return next((h[:120] for h in hay if token in h), "")


class _Truncating(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _Cut(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.recv(65536)
        self.request.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                             b"Content-Length: 500\r\n\r\n[{\"id\":")
        self.request.close()


def _reply(status=200, headers=None, body=b"{}"):
    return status, {"Content-Type": "application/json", **(headers or {})}, body


def run() -> Finding | None:
    with jobs_source() as src, console_rig(
            extra_args=("--jobs-source", src.url, "--jobs-token-file", str(src.token_file))
    ) as rig:
        own = {"Origin": rig.base, "Content-Type": "application/json"}

        # ---- control: the probe sees what arrives at the source ----
        status, headers, body = _raw(rig, "GET", "/api/jobs/runs?limit=3",
                                     {"Authorization": "Bearer attacker",
                                      "Cookie": "session=victim"})
        got = [r for r in src.requests if r.path.startswith("/v1/console/")]
        if (status != 200 or len(got) != 1 or got[0].path != "/v1/console/runs?limit=3"
                or got[0].headers.get("Authorization") != f"Bearer {src.token}"):
            return _f("fixture: a legal GET did not reach the source as "
                      "/v1/console/<path> with the console's token",
                      f"status={status} source saw={[(r.path, r.headers.get('Authorization')) for r in src.requests]}",
                      _SITE, FailureClass.COLLAPSED_SENTINEL)
        sent = {k.lower(): v for k, v in got[0].headers.items()}
        if "cookie" in sent or "attacker" in json.dumps(sent):
            return _f("the browser's own Cookie or Authorization was forwarded to the "
                      "source", f"source saw headers={sent}", _SITE)
        leak = _scan(src.token, status, headers, body)
        if leak:
            return _f("the bearer token is in a reply to the browser", leak, _SERVER)

        # ---- 1b: token in replies of every shape ----
        shapes = {
            "source 500": _reply(500, body=b'{"error":"boom"}'),
            "source 404": _reply(404, body=b'{"error":"nope"}'),
            "source 401": _reply(401, {"WWW-Authenticate": "Bearer realm=x"},
                                 b'{"error":"unauthorized"}'),
        }
        for name, resp in shapes.items():
            src.responder = lambda req, resp=resp: resp
            status, headers, body = _raw(rig, "GET", "/api/jobs/jobs")
            leak = _scan(src.token, status, headers, body)
            if leak or status != resp[0]:
                return _f("the token is in a reply to the browser, or an upstream status "
                          "was rewritten", f"{name}: relayed {status} (want {resp[0]}); "
                          f"{leak}", _SERVER)
        # the token must not follow a redirect to another origin
        with jobs_source() as elsewhere:
            target = f"{elsewhere.url}/collect"
            src.responder = lambda req: (302, {"Location": target}, b"")
            _raw(rig, "GET", "/api/jobs/jobs")
            _raw(rig, "POST", "/api/jobs/jobs/j1/run", own, b"{}")
            stolen = [r for r in elsewhere.requests
                      if src.token in json.dumps(dict(r.headers))]
            reached = bool(elsewhere.requests)
            if stolen:
                return _f("the console follows a redirect from the source to another "
                          "origin and carries the bearer token with it (urllib keeps "
                          "every request header across a redirect)",
                          f"source answered 302 Location: {target}; the second origin "
                          f"received {len(stolen)} request(s) with Authorization="
                          f"{stolen[0].headers.get('Authorization')!r}", _SITE)
            _ = reached
        src.responder = lambda req: _reply()

        # ---- 4: header allowlist, path confinement ----
        src.responder = lambda req: _reply(200, {
            "Set-Cookie": "sid=1; Path=/", "Set-Cookie2": "x=1", "WWW-Authenticate": "Basic",
            "Location": "https://evil.example", "Server": "stub-source/9",
            "X-Powered-By": "stub", "Cache-Control": "max-age=60"}, b'{"ok":1}')
        status, headers, body = _raw(rig, "GET", "/api/jobs/jobs")
        if "max-age=60" not in " ".join(_hdr(headers, "Cache-Control")) or status != 200:
            return _f("fixture: allowlisted headers were not relayed, so the absence of "
                      "others means nothing", f"{status} {headers}", _SERVER,
                      FailureClass.COLLAPSED_SENTINEL)
        for name in ("Set-Cookie", "Set-Cookie2", "WWW-Authenticate", "Location",
                     "X-Powered-By"):
            if _hdr(headers, name):
                return _f("a source header outside the relay allowlist reached the browser",
                          f"{name}: {_hdr(headers, name)}", _SERVER)
        if any("stub-source" in v for v in _hdr(headers, "Server")):
            return _f("the source's Server header was relayed", f"{_hdr(headers, 'Server')}",
                      _SERVER)
        src.responder = lambda req: _reply()
        src.requests.clear()
        hostile = ("../../etc/passwd", "a/../../x", "%2e%2e/x", "x%2f..%2fy", "//evil.example/x",
                   "http://evil.example/x", "x?y=1&z=http://e", "x\\y", "x%20y", "a;b",
                   "x%00y", "x/./../../v2/other")
        for rest in hostile:
            _raw(rig, "GET", "/api/jobs/" + rest)
        status, _h, _b = _raw(rig, "GET", "/api/jobs/jobs/j1/runs/r1:log")  # legal
        outside = [r.path for r in src.requests
                   if not r.path.startswith("/v1/console/") or ".." in
                   urllib.parse.unquote(r.path)]
        legal = [r.path for r in src.requests if r.path == "/v1/console/jobs/j1/runs/r1:log"]
        if not legal:
            return _f("fixture: a legal path with a colon did not arrive as sent",
                      f"{[r.path for r in src.requests]}", _SITE,
                      FailureClass.COLLAPSED_SENTINEL)
        if outside:
            return _f("a hostile path reached the source outside /v1/console/ or with a "
                      "`..`", f"source saw {outside}", _SITE)

        # ---- 2: the origin gate on writes ----
        src.requests.clear()
        status, _h, _b = _raw(rig, "POST", "/api/jobs/jobs/j1/run", own, b'{"a":1}')
        landed = [r for r in src.requests if r.method == "POST"]
        if (status != 200 or len(landed) != 1 or json.loads(landed[0].body or b'null') != {"a": 1}
                or landed[0].headers.get("Authorization") != f"Bearer {src.token}"):
            return _f("fixture: a same-origin POST did not reach the source with its body "
                      "and the token", f"status={status} source saw="
                      f"{[(r.method, r.path, r.body) for r in src.requests]}", _SITE,
                      FailureClass.COLLAPSED_SENTINEL)
        for label, headers in (
                ("a cross-site page", {"Origin": _EVIL, "Content-Type": "text/plain"}),
                ("a sandboxed app frame (Origin: null)",
                 {"Origin": "null", "Content-Type": "text/plain"}),
                ("a cross-site Referer", {"Referer": _EVIL + "/page",
                                          "Content-Type": "text/plain"}),
                ("a lookalike origin", {"Origin": rig.base.replace("127.0.0.1", "127.0.0.1.evil.example"),
                                        "Content-Type": "text/plain"})):
            src.requests.clear()
            status, _h, body = _raw(rig, "POST", "/api/jobs/jobs/j1/run", headers, b"{}")
            if status != 403 or [r for r in src.requests if r.method == "POST"]:
                return _f("a write the console's own page did not make reached the jobs "
                          "source, carrying the console's token",
                          f"{label}: POST /api/jobs/jobs/j1/run -> {status} "
                          f"{body[:80]!r}; source received "
                          f"{[(r.method, r.path) for r in src.requests]}", _SERVER)

        # a sandboxed frame must not drive the pane-typing endpoints either
        status, _h, body = _raw(rig, "POST", "/api/send",
                                {"Origin": "null", "Content-Type": "text/plain"},
                                json.dumps({"index": 0, "text": "QE-NULL-ORIGIN",
                                            "submit": False}).encode())
        typed = "QE-NULL-ORIGIN" in rig.capture(0)
        if status != 403 or typed:
            return _f("a request from a sandboxed frame (Origin: null) typed into a pane",
                      f"POST /api/send Origin: null -> {status}; text in pane 0: {typed}",
                      "packages/thalamus-console/src/thalamus_console/server.py"
                      "::Handler._origin_ok")

    return None


def run_failures() -> Finding | None:
    """No source is 404, a dead source 502, a source that cuts its reply short is no 200."""
    def inv(summary, witness):
        return _f(summary, witness, _SITE, FailureClass.INVARIANT_FALSIFIED)

    with console_rig() as rig:
        for method, path in (("GET", "/api/jobs/runs"), ("POST", "/api/jobs/jobs/j1/run"),
                             ("GET", "/api/jobs/")):
            status, _h, body = _raw(rig, method, path, {"Content-Type": "application/json"},
                                    b"{}" if method == "POST" else None)
            if status != 404:
                return inv("a console with no jobs source did not answer 404 for the jobs "
                           "API", f"{method} {path}: {status} {body[:120]!r}")
    with jobs_source() as live, console_rig(extra_args=(
            "--jobs-source", live.url, "--jobs-token-file", str(live.token_file))) as rig:
        # control: this console, with a source that answers, is not what 502s below
        if _raw(rig, "GET", "/api/jobs/runs")[0] != 200:
            return _f("fixture: a live source did not read as 200", "", _SELF,
                      FailureClass.COLLAPSED_SENTINEL)
    with console_rig(extra_args=("--jobs-source", f"http://127.0.0.1:{dead_port()}")) as rig:
        for method, path in (("GET", "/api/jobs/runs"), ("POST", "/api/jobs/jobs/j1/run")):
            status, _h, body = _raw(rig, method, path,
                                    {"Origin": rig.base, "Content-Type": "application/json"},
                                    b"{}" if method == "POST" else None)
            if status != 502 or b"error" not in body:
                return inv("a dead jobs source did not read as one", f"{method} {path}: "
                           f"{status} {body[:120]!r} (want 502 with an error body)")
    srv = _Truncating(("127.0.0.1", 0), _Cut)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with console_rig(extra_args=("--jobs-source",
                                     f"http://127.0.0.1:{srv.server_address[1]}")) as rig:
            status, _h, body = _raw(rig, "GET", "/api/jobs/runs")
            if status < 500:
                return inv("a source that declared 500 bytes and hung up after 7 was "
                           "relayed as a success — `resp.read(MAX_BODY)` returns what "
                           "arrived instead of raising IncompleteRead, so the browser "
                           "gets a truncated list under a 200",
                           f"source: HTTP/1.1 200, Content-Length: 500, body "
                           f"'[{{\"id\":' then close; console: GET /api/jobs/runs -> "
                           f"{status} {body[:120]!r}")
    finally:
        srv.shutdown()
        srv.server_close()
    return None


CASE = Case(
    name="console-jobs-proxy-keeps-the-token-and-the-origin-gate",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX, Substrate.CONSOLE_UNBUILT_JOBS_API),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="the jobs relay forwards the token to the source only (not to a redirect "
            "target, not into any reply), refuses cross-origin and null-origin writes "
            "before the source sees them, and drops non-allowlisted headers and "
            "escaping paths",
    run=run,
)

FAILURES = Case(
    name="console-jobs-proxy-reports-a-missing-dead-or-truncating-source-as-failure",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX, Substrate.CONSOLE_UNBUILT_JOBS_API),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="no source is a 404, a source that does not answer is a 502, and a source "
            "that cuts its reply short is never relayed as a 200",
    run=run_failures,
)

CASES = (CASE, FAILURES)
