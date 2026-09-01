"""No console write route may drop the connection on a body it does not like.

Issue #74, open — the console's 13 mutating POST routes had no adversarial coverage.

`do_POST` guards the *parse* and nothing after it (`console/server.py:1932`):

    try:
        data = self._body()
    except Exception:
        return self._send(400, {"error": "bad json"})

`_body()` (:1743) is `json.loads(...)`, which succeeds on any JSON value. `[]`, `"x"`,
`3` and `null` all parse, so the `except` never fires, and the first `data.get(...)`
below raises `AttributeError` on a list. Nothing catches it: the exception leaves
`do_POST`, the handler thread dies, and the client gets a closed connection with no
response at all.

`do_GET` does not have this hole, and says why (:1765):

    # Unwrapped, the exception kills the handler thread and the browser sees a
    # connection that closed, which is the least diagnosable failure the surface has.

The same sentence describes `do_POST`, which never got the wrapper. Measured against the
real handler, tmux stubbed, 2026-08-31 — every one of these closed the connection without
a response:

    POST /api/key      []                          AttributeError: 'list' object …
    POST /api/key      "hello" / 3 / null          same, on str / int / NoneType
    POST /api/send     []                          same
    POST /api/service  []                          same
    POST /api/close    []                          same
    POST /api/key      {"key": []}                 TypeError: unhashable type: 'list'
    POST /api/key      {"count": Infinity}         OverflowError — `int()` raises it and
                                                   the `except (TypeError, ValueError)`
                                                   at :2184 does not catch it
    POST /api/send     {"text": "a\\u0000b"}        ValueError: embedded null byte, from
                                                   subprocess, past the isinstance check
    POST /api/send     {"text": "\\ud800"}          UnicodeEncodeError on the argv encode

`{"count": NaN}` is caught (ValueError) and `{"index": true}` is not a crash but is not
right either: `bool` passes `isinstance(idx, int)` and `True == 1` matches window 1, then
the f-string at :2128 renders the target as `<session>:True`, a pane name that cannot
exist. tmux errors, the return code is unread, and the route answers `200 {"ok": true}`.
That one is recorded here as a witness rather than asserted on — it is a distinct defect
from the dropped connection and belongs to its own issue if it is to be fixed.

**Five routes are not driven live**, because they begin acting before they read `data`,
so a malformed body does not stop them in time: `/api/roster`, `/api/deploy`,
`/api/cursor-sweep`, `/api/launch-policy` and `/api/extractor-policy`. A probe would sync
the operator's real roster, `git pull` and restart the unit serving the request, launch a
real extraction over real transcripts, or reach a policy writer. They are covered by the
structural half instead — the same division `console_write_origin` makes, for the same
reason.

**The route list and the exemptions are both generated.** #74 left open whether to
enumerate the routes from `do_POST`'s dispatch or hand-list them. Generated is the
stronger oracle and costs one AST walk, but the enumeration alone is not enough: if the
set of routes to drive is simply "every route found", then a newly added route is driven
automatically, and a new route that acts before reading `data` would be actuated against
the operator's box by the case meant to protect it. So *drivability* is derived too — a
route is driven only when the `AttributeError` is certain to fire first, either because
it sits below the shared window gate or because its own first statement reads `data` —
and the resulting undrivable set is compared against the one named above. A route added
on either side of that line is a finding rather than a silent change in what this case
covers, in the direction of coverage and in the direction of safety.

**Three controls, all running.**

1. *The detector control.* A subclass whose `do_POST` raises unconditionally must be
   observed as a dropped connection. Without it, "every probe got a response" and "this
   case cannot tell a drop from a reply" are the same output, and the case would pass
   forever the moment the probe stopped working.
2. *Discrimination.* A well-formed POST must get 200. A fixture whose window never
   resolves would 400 everything, and a server that had fallen over would drop
   everything; either would make the result meaningless.
3. *Route enumeration.* The AST walk must find routes. Zero routes found and full
   coverage are the same clean result otherwise, and a refactor moving the dispatch out
   of `do_POST` would empty this half in silence.

**Shown capable of going red** — it is red now, against the defect as it ships. The green
direction is control 1 inverted: wrap `do_POST`'s body in the same `try/except` `do_GET`
carries, and every probe below answers 500 instead of closing the socket, which is a
response and passes. Note that the case asserts *a response*, not a status: which code a
malformed body deserves is a design question, and pinning one here would make this the
guardian of that choice rather than of the crash.
"""

from __future__ import annotations

import ast
import contextlib
import subprocess
import tempfile
import threading
from http.client import HTTPConnection, RemoteDisconnected
from http.server import ThreadingHTTPServer
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]
_SERVER = _REPO / "src" / "thalamus" / "console" / "server.py"

_WINDOWS = "0\tmain\t1\tclaude\t80\t24\t0\t/tmp\tclaude\t%0\t991"

#: Routes that begin acting before they read `data`, so a malformed body does not stop
#: them in time and a live probe would actuate the operator's box: sync the real roster,
#: `git pull` and restart the unit answering the request, start a real extraction, or
#: reach a policy writer. Structural half only.
#:
#: This is the *expected* value of a set computed from the shipped dispatch on every run
#: — see `_routes_and_drivability`. It is not the input to the decision about what to
#: drive, which is why a new route cannot quietly land on either side of it.
_NOT_DRIVEN = {"/api/roster", "/api/deploy", "/api/cursor-sweep",
               "/api/launch-policy", "/api/extractor-policy"}

#: Bodies that are valid JSON and not objects. Every route that reads `data` reaches a
#: `.get` on one of these.
_NON_OBJECT = ("[]", '"hello"', "3", "null")

#: Type confusion inside a well-formed object, on the two routes the direct-typing path
#: uses. These reach past the route's own validation.
_TYPE_CONFUSION = (
    ("/api/key", '{"index":0,"key":[]}', "unhashable key: TypeError in KEYMAP.get"),
    ("/api/key", '{"index":0,"key":{}}', "unhashable key: dict"),
    ("/api/key", '{"index":0,"key":"enter","count":Infinity}',
     "OverflowError: int(inf), uncaught by `except (TypeError, ValueError)`"),
    ("/api/send", '{"index":0,"text":"a\\u0000b","submit":false}',
     "ValueError: embedded null byte, past the isinstance(text, str) check"),
    ("/api/send", '{"index":0,"text":"\\ud800","submit":false}',
     "UnicodeEncodeError: lone surrogate on the argv encode"),
)


class _StubTmux:
    """Answers `list-windows`, and emulates the argv encode that real sends die on."""

    def __call__(self, *args: str) -> subprocess.CompletedProcess:
        for a in args:
            # subprocess raises on both of these before tmux is ever exec'd. Emulated
            # rather than executed: the case must reach the failure without running a
            # real send-keys at the operator's control plane.
            if "\x00" in a:
                raise ValueError("embedded null byte")
            a.encode("utf-8", "strict")
        out = _WINDOWS if args and args[0] == "list-windows" else ""
        return subprocess.CompletedProcess(args=list(args), returncode=0,
                                           stdout=out, stderr="")


class _QuietServer(ThreadingHTTPServer):
    """The same server, without socketserver's traceback-per-dead-thread.

    Every probe here is *expected* to kill a handler thread while the defect stands, and
    the default `handle_error` prints a full traceback for each — 37 of them, into the
    suite's output, which buries every other case's verdict. The drop is observed on the
    client side (`_post` returns `dropped`), so nothing is being hidden from the case;
    only the duplicate report to stderr is dropped.
    """

    def handle_error(self, request, client_address):
        return


@contextlib.contextmanager
def _serving(console, handler_cls, cfg):
    real = console.tmux
    console.tmux = _StubTmux()
    httpd = _QuietServer(("127.0.0.1", 0), handler_cls)
    httpd.config = cfg
    thread = threading.Thread(target=httpd.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        console.tmux = real


def _post(port: int, path: str, raw: str) -> str:
    """The status as a string, or `dropped` if the handler died mid-request."""
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("POST", path, raw, {"Content-Type": "application/json"})
        response = conn.getresponse()
        response.read()
        return str(response.status)
    except (RemoteDisconnected, ConnectionResetError):
        return "dropped"
    except Exception as exc:  # noqa: BLE001
        return f"dropped ({type(exc).__name__})"
    finally:
        conn.close()


def _reads_data(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Name) and n.id == "data" for n in ast.walk(node))


def _routes_and_drivability() -> list[tuple[str, bool]]:
    """Every POST route in `do_POST`, and whether a non-object body stops it in time.

    Derived, not declared. Driving a route whose body runs before `data` is touched
    would sync the operator's real roster or restart the unit answering the request, so
    which routes this case may drive is a fact about the shipped dispatch and has to be
    read back out of it on every run.

    A route is drivable when the `AttributeError` is certain to fire before its body:

    * the shared window gate (`idx = data.get("index")`, :2126) sits at `do_POST`'s top
      level and every route below it is behind it — those are drivable by position; or
    * the route is above the gate and its own first statement reads `data`.

    Conservative in the safe direction: a route above the gate that reads `data` on its
    second statement is called undrivable, which costs coverage and never costs the
    operator a spawn.
    """
    tree = ast.parse(_SERVER.read_text(encoding="utf-8"))
    body: list[ast.stmt] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "do_POST":
            body = node.body
            break

    gate = next((i for i, stmt in enumerate(body)
                 if isinstance(stmt, ast.Assign) and _reads_data(stmt)
                 and any(isinstance(t, ast.Name) and t.id == "idx" for t in stmt.targets)),
                len(body))

    routes: list[tuple[str, bool]] = []
    for index, stmt in enumerate(body):
        if not isinstance(stmt, ast.If):
            continue
        names = [o.value for o in ast.walk(stmt.test)
                 if isinstance(o, ast.Constant) and isinstance(o.value, str)
                 and o.value.startswith("/api/")]
        if not names:
            continue
        drivable = index > gate or (bool(stmt.body) and _reads_data(stmt.body[0]))
        for name in names:
            routes.append((name, drivable))
    return routes


def run() -> Finding | None:
    from thalamus.console import server as console  # noqa: PLC0415

    class _AlwaysRaises(console.Handler):
        """A handler that dies the way an unguarded `do_POST` dies."""

        def do_POST(self):  # noqa: N802
            raise RuntimeError("qe detector control")

    # CONTROL 3, first and cheapest: the enumeration must find the surface.
    catalogue = _routes_and_drivability()
    routes = [name for name, _ in catalogue]
    if len(routes) < 5:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the AST walk found almost no POST routes in do_POST, so the "
                    "coverage half of this case is empty and would stay green over a "
                    "surface it is no longer reading",
            witness=f"routes found: {routes}",
            site="tests/qe/cases/console_post_survives_malformed_body.py",
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "checkout"
        (root / ".git").mkdir(parents=True)
        cfg = console.Config(session="qe-malformed-probe", project_root=root)

        # CONTROL 1: the detector must be able to see a dropped connection.
        with _serving(console, _AlwaysRaises, cfg) as port:
            seen = _post(port, "/api/key", '{"index":0,"key":"enter"}')
        if not seen.startswith("dropped"):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="a handler that raises unconditionally was not observed as a "
                        "dropped connection, so this case cannot tell a crash from a "
                        "reply and every green below is worthless",
                witness=f"_AlwaysRaises answered {seen!r}, want 'dropped'",
                site="tests/qe/cases/console_post_survives_malformed_body.py",
            )

        with _serving(console, console.Handler, cfg) as port:
            # CONTROL 2: a well-formed request must land.
            ok = _post(port, "/api/key", '{"index":0,"key":"enter"}')
            if ok != "200":
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="a well-formed POST did not answer 200, so this fixture "
                            "refuses everything and 'no response' below would say "
                            "nothing about malformed input",
                    witness=f"/api/key with a valid body answered {ok!r}",
                    site="tests/qe/cases/console_post_survives_malformed_body.py",
                )

            dropped: list[str] = []

            driven = [name for name, drivable in catalogue if drivable]
            for route in driven:
                for raw in _NON_OBJECT:
                    status = _post(port, route, raw)
                    if status.startswith("dropped"):
                        dropped.append(f"POST {route} {raw} -> {status}")

            for route, raw, why in _TYPE_CONFUSION:
                status = _post(port, route, raw)
                if status.startswith("dropped"):
                    dropped.append(f"POST {route} {raw} -> {status} [{why}]")

        # COVERAGE: the undriven set is read out of the dispatch and must be exactly the
        # set this case declares. A route added above the window gate that acts before
        # reading `data` appears here and is a finding rather than something quietly
        # driven live; a declared route that has since become drivable is a stale
        # exemption, and drift in either direction costs coverage the case still claims.
        undrivable = {name for name, drivable in catalogue if not drivable}
        if undrivable != _NOT_DRIVEN:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary="the set of console POST routes this case cannot safely drive "
                        "has changed, so its adversarial coverage no longer matches the "
                        "surface it claims to cover",
                witness=f"undrivable in the shipped dispatch: {sorted(undrivable)}; "
                        f"declared here: {sorted(_NOT_DRIVEN)}; "
                        f"newly undrivable: {sorted(undrivable - _NOT_DRIVEN)}; "
                        f"stale exemptions: {sorted(_NOT_DRIVEN - undrivable)}",
                site="src/thalamus/console/server.py:1927",
            )

        if dropped:
            return Finding(
                failure_class=FailureClass.FAILED_OPEN,
                summary="a POST body that is valid JSON but not an object, or that "
                        "carries a wrong-typed field, escapes do_POST as an unhandled "
                        "exception and kills the handler thread — the client gets a "
                        "closed connection and no response, which do_GET's own wrapper "
                        "exists to prevent",
                witness=f"{len(dropped)} of "
                        f"{len(driven) * len(_NON_OBJECT) + len(_TYPE_CONFUSION)} probes "
                        f"dropped the connection: " + "; ".join(dropped[:6])
                        + (f"; …and {len(dropped) - 6} more" if len(dropped) > 6 else ""),
                site="src/thalamus/console/server.py:1932",
            )
    return None


CASE = Case(
    name="a-malformed-post-body-gets-a-response-not-a-dropped-connection",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.FAILED_OPEN, FailureClass.INVARIANT_FALSIFIED,
             FailureClass.COLLAPSED_SENTINEL),
    summary="every console POST route must answer a malformed body instead of letting "
            "an unhandled exception kill the handler thread",
    run=run,
    issue=74,
)
