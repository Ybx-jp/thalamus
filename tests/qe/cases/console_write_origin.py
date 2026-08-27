"""A console write must not be reachable from a page the console did not serve.

Issue #132, closed by `8b460c4`. Every `/api/` POST on the console types into the
operator's tmux session, and until that commit nothing on the request was checked. The
console authenticates nothing and says so in its own module docstring — the posture is
that it sits behind something that already authenticates — but that reasoning covers a
request *addressed* to the console, not one the operator's own browser is tricked into
sending. Loopback binding is no defence and neither is an authenticating proxy: the
request starts inside the boundary, carrying whatever the proxy already granted.

The delivery shape is what makes this reachable rather than theoretical. `_body()`
parses JSON whatever content type is declared, so a cross-site `text/plain` POST is a
CORS *simple* request: no preflight, delivered, and the write lands on the pane even
though the reply is unreadable to the page that sent it. So the probe below sends
`Content-Type: text/plain` with a JSON body — a header set a browser will actually
deliver from another origin. A probe sending `application/json` would be preflighted out
of existence in a real browser and would prove nothing about the vector.

`/api/send` is the sharpest target: it types text into the pane the operator is
watching and then presses Enter, which is also how a permission prompt gets answered.

Two halves, because they fail differently.

**Behavioural**, over real HTTP against the real `Handler`: a cross-site POST to
`/api/send` and to `/api/key` must answer 403 and reach tmux with nothing. Response code
alone is not the property — a refusal that still ran `send-keys` would be no refusal —
so the recorded argv is what is asserted.

**Structural**, over `do_POST`'s own statement order, because the behavioural half can
only drive routes that are inert under a stubbed tmux. The gate is one call at the top
of one method, and every one of the thirteen POST routes is behind it *by position*.
Assert that position: the origin check must be evaluated before the body is read and
before the first route comparison. A gate that moved below a route would leave that
route open while every probe above it still passed.

**Nothing here executes tmux.** The stub records argv and answers `list-windows` from a
fixed line. A case that let the calls through would drive the operator's real roster,
which is the thing this case says must not happen — and it would do it hardest at the
moment the defect had regressed. The same reasoning bounds which routes are driven:
`/api/roster`, `/api/deploy`, `/api/service` and `/api/spawn` are not probed live,
because a regression would actuate them for real on the box running the suite. They are
covered by the ordering half instead.

**Three controls, all running.**

1. *The red control.* The same probe runs first against a subclass whose `_origin_ok`
   returns True — the handler as it behaved before `8b460c4`. That request must reach
   tmux. If it does not, the probe cannot show the check doing anything, and its green
   is worthless; that is reported instead of a pass. This is the mutation the suite
   README asks for, run rather than described.
2. *Discrimination.* A same-origin POST must land. A console that refused everything —
   or a fixture whose window never resolves, so every request 400s before the route —
   produces the same "no tmux write" as a working refusal.
3. *Route enumeration.* The ordering half must find POST routes to be behind the gate.
   Zero routes found and a correctly ordered gate are the same clean result otherwise,
   and a refactor that moved the dispatch out of `do_POST` would empty this silently.

**Shown capable of going red, against the defect as it shipped.** The behavioural
mutation cannot live in the case — it needs the real handler to be the broken one — so
repeat it:

    from qe.cases import console_write_origin as case
    from thalamus.console import server
    server.Handler._origin_ok = lambda self: True   # do_POST before 8b460c4
    case.run()

Run on 2026-08-27 it reported `boundary-leak`, witness `status=200 (want 403)` with both
`send-keys` calls recorded — the text and the Enter that actuates it. Move the gate below
`self._body()` in a copy of `server.py` and point `_SERVER` at it, and the ordering half
reports `gate-ordering` naming the 13 routes then sitting in front of it.

Deliberately **not** asserted: that a request carrying neither `Origin` nor `Referer` is
refused. It is allowed through on purpose so curl, scripts and health probes keep
working, and a browser sends `Origin` on every cross-site POST, so the allowance does
not reopen the vector. Pinning it here would make this case the guardian of a design
decision rather than of the defect. Two residual holes are named in `docs/console.md`
and are outside what any header comparison can close: DNS rebinding reaches the console
same-origin, and `Host` carries no scheme, so `http://` and `https://` on one authority
are indistinguishable.
"""

from __future__ import annotations

import ast
import contextlib
import json
import subprocess
import tempfile
import threading
from collections.abc import Callable
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]
_SERVER = _REPO / "src" / "thalamus" / "console" / "server.py"

# One window, in the eleven tab-separated fields `list-windows -F` prints and
# `parse_windows` splits. The routes under test all resolve their target through it.
_WINDOWS = "0\tmain\t1\tclaude\t80\t24\t0\t/tmp\tclaude\t%0\t991"

# A page on some other site. The payload is what a real attack would carry: text plus
# the Enter that actuates it.
_ELSEWHERE = "https://evil.example"
_PROBES = (
    ("/api/send", {"index": 0, "text": "qe cross-site probe", "submit": True}),
    ("/api/key", {"index": 0, "key": "enter"}),
)


def _cross_site(_port: int) -> dict[str, str]:
    """A CORS simple request: no preflight, so the browser delivers it."""
    return {"Content-Type": "text/plain", "Origin": _ELSEWHERE}


def _own_page(port: int) -> dict[str, str]:
    return {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"}


class _RecordingTmux:
    """Records argv and answers `list-windows`. Executes nothing, ever."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> subprocess.CompletedProcess:
        self.calls.append(args)
        out = _WINDOWS if args and args[0] == "list-windows" else ""
        return subprocess.CompletedProcess(args=list(args), returncode=0,
                                           stdout=out, stderr="")

    @property
    def writes(self) -> list[tuple[str, ...]]:
        """The calls that would have typed into a pane."""
        return [c for c in self.calls if c and c[0] == "send-keys"]


@contextlib.contextmanager
def _serving(console, handler_cls, cfg):
    """A live console on an ephemeral port, with tmux replaced by a recorder.

    The refusal lives in the request handler, not in a pure function, so it is
    exercised over real HTTP — the same path a browser would take.
    """
    recorder = _RecordingTmux()
    real_tmux = console.tmux
    console.tmux = recorder
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    httpd.config = cfg
    thread = threading.Thread(target=httpd.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1], recorder
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        console.tmux = real_tmux


def _drive(console, handler_cls, cfg, path: str, payload: dict,
           headers: Callable[[int], dict[str, str]]) -> tuple[int, list[tuple[str, ...]]]:
    """(status, tmux writes) for one POST."""
    with _serving(console, handler_cls, cfg) as (port, recorder):
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("POST", path, json.dumps(payload), headers(port))
            response = conn.getresponse()
            # Drained rather than ignored: the response body is not the property here
            # — the recorded argv is — but a half-read keep-alive response leaves the
            # handler thread mid-request when the server is asked to shut down.
            response.read()
            status = response.status
        finally:
            conn.close()
        return status, list(recorder.writes)


def _do_post() -> ast.FunctionDef | None:
    """`Handler.do_POST`, from the shipped source."""
    tree = ast.parse(_SERVER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Handler":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "do_POST":
                    return item
    return None


def _first(statements: list[ast.stmt], predicate: Callable[[ast.AST], bool]) -> int | None:
    """The index of the first top-level statement whose subtree satisfies `predicate`."""
    for index, statement in enumerate(statements):
        if any(predicate(node) for node in ast.walk(statement)):
            return index
    return None


def _calls(name: str) -> Callable[[ast.AST], bool]:
    return lambda node: isinstance(node, ast.Attribute) and node.attr == name


def _is_route_test(node: ast.AST) -> bool:
    """`path == "/api/…"` in either operand order."""
    if not isinstance(node, ast.Compare):
        return False
    operands = [node.left, *node.comparators]
    return any(isinstance(o, ast.Constant) and isinstance(o.value, str)
               and o.value.startswith("/api/") for o in operands)


def run() -> Finding | None:
    from thalamus.console import server as console  # noqa: PLC0415

    class _WithoutTheCheck(console.Handler):
        """`Handler` as it behaved before `8b460c4`: every POST accepted."""

        def _origin_ok(self) -> bool:
            return True

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "checkout"
        (root / ".git").mkdir(parents=True)
        cfg = console.Config(session="qe-origin-probe", project_root=root)

        for path, payload in _PROBES:
            # CONTROL, and it runs first: with the check removed, this exact request
            # must reach tmux. A probe that cannot reproduce the defect cannot report
            # its absence, and a green from one would mean nothing.
            status, writes = _drive(console, _WithoutTheCheck, cfg, path, payload,
                                    _cross_site)
            if not writes:
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="with the origin check removed, the cross-site probe still "
                            "reached no tmux call — so this case cannot show the check "
                            "doing anything and its green is not evidence",
                    witness=f"{path} against a handler whose _origin_ok returns True: "
                            f"status={status}, send-keys calls=0",
                    site="tests/qe/cases/console_write_origin.py::_WithoutTheCheck",
                )

            # CONTROL: the console's own page must get through. "Refuses everything"
            # and "refuses another origin" produce the same evidence otherwise.
            status, writes = _drive(console, console.Handler, cfg, path, payload,
                                    _own_page)
            if status != 200 or not writes:
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="a same-origin write did not land, so this case cannot tell "
                            "a working refusal from a route that never works at all",
                    witness=f"{path} from the console's own origin: status={status}, "
                            f"send-keys calls={len(writes)}",
                    site="tests/qe/cases/console_write_origin.py",
                )

            # The property.
            status, writes = _drive(console, console.Handler, cfg, path, payload,
                                    _cross_site)
            if status != 403 or writes:
                return Finding(
                    failure_class=FailureClass.BOUNDARY_LEAK,
                    summary="a cross-site POST carrying a foreign Origin was not refused "
                            "— any page open in the operator's browser can drive the "
                            "tmux control plane, and the reply being unreadable to it "
                            "does not take the write back",
                    witness=f"POST {path} Origin={_ELSEWHERE} Content-Type=text/plain: "
                            f"status={status} (want 403), send-keys={writes or 'none'}",
                    site="src/thalamus/console/server.py::Handler.do_POST",
                )

    # The structural half: every POST route is behind the gate by position.
    body = _do_post()
    if body is None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="Handler.do_POST was not found in the console source, so the "
                    "ordering property was asserted over nothing",
            witness=f"parsed {_SERVER.relative_to(_REPO)}, found no Handler.do_POST",
            site="tests/qe/cases/console_write_origin.py::_do_post",
        )

    routes = sum(1 for statement in body.body
                 for node in ast.walk(statement) if _is_route_test(node))
    # CONTROL: there must be routes behind the gate for its position to mean anything.
    if routes < 2:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no POST route dispatch was found inside do_POST, so 'the gate "
                    "precedes every route' holds vacuously and would keep holding if "
                    "the routes moved somewhere the gate does not cover",
            witness=f"do_POST contains {routes} `path == \"/api/…\"` comparison(s)",
            site="tests/qe/cases/console_write_origin.py::_is_route_test",
        )

    gate = _first(body.body, _calls("_origin_ok"))
    reads_body = _first(body.body, _calls("_body"))
    first_route = _first(body.body, _is_route_test)
    after = [name for name, index in (("the body read", reads_body),
                                      ("the first route", first_route))
             if index is not None and (gate is None or gate > index)]
    if after:
        return Finding(
            failure_class=FailureClass.GATE_ORDERING,
            summary="the origin check does not precede everything do_POST does with a "
                    "request, so a route reached before it is open to any page in the "
                    "operator's browser",
            witness=f"statement index of _origin_ok={gate}, of _body={reads_body}, "
                    f"of the first /api/ route={first_route}; behind it: "
                    f"{', '.join(after)}; {routes} route(s) dispatched in do_POST",
            site="src/thalamus/console/server.py::Handler.do_POST",
        )

    return None


CASE = Case(
    name="a-cross-site-write-reaches-no-pane",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.GATE_ORDERING,
             FailureClass.COLLAPSED_SENTINEL),
    summary="a POST carrying an Origin the console does not serve is refused before the "
            "body is read, and every POST route sits behind that check",
    issue=132,
    fixed=True,
    run=run,
)
