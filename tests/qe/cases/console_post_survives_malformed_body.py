"""No console write route may drop the connection on a body it does not like.

Issue #175, open — `do_POST` guards the JSON parse and nothing after it. The
corpus this case drives is the one issue #74 specified when it filed the coverage
gap; the defect it found is #175.

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
reason. `/api/dispatch` fans out to another room's members but is driven: its own first
statement reads `data`, so the crash-inducing shapes below still fail before any member
is reached — the request that would actually reach `dispatch.dispatch(...)` needs a
well-formed room and message, which is a different probe, covered structurally below.

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

**Beyond the non-object shapes**, four more items from #74's stated corpus:

- *Empty body and oversized body* fold into the same driven-route sweep as one more
  literal each: `""` (no bytes at all — `_body()`'s own `if n else {}` means this reaches
  every route as `{}`, never a crash, but it is in the issue's list and costs nothing to
  carry) and a ~200KB JSON array (still a list, so still a crash on every driven route —
  "oversized" and "wrong shape" are not independent axes here, and a body that large is
  what tells apart a `_body()` that reads `Content-Length` bytes cleanly from one that
  chokes or truncates on a large read).
- *Wrong content-type* is one extra probe, not one per route: `_body()` does not
  consult `Content-Type` at all, so a well-formed `/api/key` body posted as `text/plain`
  must land exactly like `application/json` does. `console_write_origin.py` already
  leans on this fact for the CORS vector; this pins it from the parser's side.
- *A spoofed or missing `caller_room`* is asserted structurally, not over the wire.
  `/api/dispatch` is the one route that fans into a room other than the caller's, and
  `do_POST` passes `caller_room=""` as a literal — never `data.get("caller_room", ...)`.
  A live probe carrying a forged `caller_room` would have to be well-formed enough to
  reach `dispatch.dispatch(...)` for real, which is exactly the actuation this file
  otherwise refuses to risk. The AST walk instead confirms the body is never read for
  that key and that the hardcoded empty string is still the literal passed, so a probe
  that spoofs it is provably indistinguishable from one that omits it.
- *Path traversal on `/frame/<name>`* is a GET, not one of the 13 POST routes, but #74
  names it and this is where the console's request-driven file surface is covered.
  `frame_bytes` (:769) matches the requested name for *equality* against a list parsed
  from the frames file, and never builds a path from the request — traversal is not
  expressible by construction. Driven live against a real frames file with one legitimate
  entry, so the equality-only claim is pinned rather than read off the source.

**Concurrent writes to the same window** is its own probe: `N` simultaneous
`POST /api/close` on one non-anchor window must dedupe to exactly one background
`close_window` under `CLOSING_LOCK` — the rest answer `{"already": true}` — never two
starters and never a dropped connection. `RECYCLE_GRACE_S` is shrunk and
`_record_forced_kill` is stubbed for this probe alone, the same reasoning as
`console_close_reads_pane_death.py`: the window never actually resolves under this
handler's tmux stub, so the background workers would otherwise burn the real grace
budget and (if a real distill watcher happened to be configured on the box) append to
its kill ledger.

**Three controls, all running** (for the core dropped-connection property; the four new
items above carry their own inline discrimination, noted where they are checked).

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
guardian of that choice rather than of the crash. To see the new pieces go red on their
own: (a) make `do_POST` read `data.get("caller_room")` anywhere and pass it through —
the structural check below fails on that alone, before any wire probe is needed; (b)
change `frame_bytes` to build a path from the request instead of matching a parsed list
— the traversal probe answers something other than 404; (c) move the `CLOSING_LOCK`
acquisition to after the `idx in CLOSING` read — the concurrent-close probe then sees
more than one `already: false`.
"""

from __future__ import annotations

import ast
import contextlib
import json
import subprocess
import tempfile
import threading
import time
from http.client import HTTPConnection, RemoteDisconnected
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]
_SERVER = _REPO / "src" / "thalamus" / "console" / "server.py"

# Two windows: 0 is the anchor (lowest index, per `parse_windows`) and must never be
# targeted by the concurrent-close probe; 1 is an ordinary window the probe can close.
_WINDOWS = ("0\tmain\t1\tclaude\t80\t24\t0\t/tmp\tclaude\t%0\t991\n"
            "1\tclaude\t0\tclaude\t80\t24\t0\t/tmp\tclaude\t%1\t992")

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
#: `.get` on one of these. `""` (no bytes) and the oversized array are #74's own list;
#: `_body()` treats an empty body as `{}` rather than a crash, so it never contributes to
#: `dropped`, but it costs nothing to carry through the same sweep.
_OVERSIZED_ARRAY = json.dumps([0] * 50_000)
_NON_OBJECT = ("[]", '"hello"', "3", "null", "", _OVERSIZED_ARRAY)

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

#: Names that must never resolve to a real file through `/frame/<name>`. `frame_bytes`
#: matches by equality against a parsed list, so every one of these should 404 exactly
#: like any other unknown name — none is special-cased as "worse".
_TRAVERSAL_NAMES = (
    "../../../../../../etc/passwd",
    "..%2f..%2f..%2fetc%2fpasswd",
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "/etc/passwd",
    "sign/../../../../etc/passwd",
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


def _post(port: int, path: str, raw: str, headers: dict[str, str] | None = None) -> str:
    """The status as a string, or `dropped` if the handler died mid-request."""
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("POST", path, raw, headers or {"Content-Type": "application/json"})
        response = conn.getresponse()
        response.read()
        return str(response.status)
    except (RemoteDisconnected, ConnectionResetError):
        return "dropped"
    except Exception as exc:  # noqa: BLE001
        return f"dropped ({type(exc).__name__})"
    finally:
        conn.close()


def _post_json(port: int, path: str, raw: str) -> tuple[str, dict | None]:
    """(status, parsed JSON body) — for probes that need to read the answer, not just
    whether one arrived."""
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("POST", path, raw, {"Content-Type": "application/json"})
        response = conn.getresponse()
        body = response.read()
        try:
            parsed = json.loads(body) if body else None
        except ValueError:
            parsed = None
        return str(response.status), parsed
    except (RemoteDisconnected, ConnectionResetError):
        return "dropped", None
    except Exception as exc:  # noqa: BLE001
        return f"dropped ({type(exc).__name__})", None
    finally:
        conn.close()


def _get(port: int, path: str) -> str:
    """The status of a GET, as a string, or `dropped` on a mid-request death."""
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
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


def _do_post_stmts() -> list[ast.stmt]:
    """`Handler.do_POST`'s statement list, from the shipped source."""
    tree = ast.parse(_SERVER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "do_POST":
            return node.body
    return []


def _routes_and_drivability(body: list[ast.stmt]) -> list[tuple[str, bool]]:
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


def _reads_caller_room_from_body(body: list[ast.stmt]) -> bool:
    """True if any statement in `do_POST` reads `"caller_room"` off the request body."""
    for stmt in body:
        for node in ast.walk(stmt):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "caller_room"):
                return True
            if (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant)
                    and node.slice.value == "caller_room"):
                return True
    return False


def _hardcodes_empty_caller_room(body: list[ast.stmt]) -> bool:
    """True if some call in `do_POST` passes `caller_room=""` as a literal keyword."""
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if (kw.arg == "caller_room" and isinstance(kw.value, ast.Constant)
                            and kw.value.value == ""):
                        return True
    return False


def _concurrent_close(console, cfg) -> tuple[list[str], list[dict | None]]:
    """Fire six concurrent `POST /api/close` for the same non-anchor window.

    `RECYCLE_GRACE_S` is shrunk and the ledger/session lookups are stubbed so the
    background `close_window` threads this spawns finish in a fraction of a second and
    touch nothing real — the window never actually resolves under this handler's tmux
    stub, so left at their real size they would burn the whole grace budget and, on a
    box with a real distillation watcher configured, record a forced kill that never
    happened.
    """
    saved = (console.RECYCLE_GRACE_S, console._record_forced_kill,
             console._pinned_session)
    console.RECYCLE_GRACE_S = 0.15
    console._record_forced_kill = lambda who, op: None
    console._pinned_session = lambda cfg, idx: {"session": "qe000000", "scope": "qe",
                                                "cwd": "/tmp", "project": "thalamus",
                                                "repo_root": "/tmp"}
    console.CLOSING.pop(1, None)
    try:
        with _serving(console, console.Handler, cfg) as port:
            results: list[tuple[str, dict | None]] = [("", None)] * 6

            def _fire(i: int) -> None:
                results[i] = _post_json(port, "/api/close", '{"index":1}')

            threads = [threading.Thread(target=_fire, args=(i,)) for i in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)
            # Give the (shrunk-budget) background closers time to finish before the
            # stub they depend on gets restored underneath them.
            time.sleep(console.RECYCLE_GRACE_S + 0.3)
        return [s for s, _ in results], [b for _, b in results]
    finally:
        (console.RECYCLE_GRACE_S, console._record_forced_kill,
         console._pinned_session) = saved
        console.CLOSING.pop(1, None)


def run() -> Finding | None:
    from thalamus.console import server as console  # noqa: PLC0415

    class _AlwaysRaises(console.Handler):
        """A handler that dies the way an unguarded `do_POST` dies."""

        def do_POST(self):  # noqa: N802
            raise RuntimeError("qe detector control")

    post_body = _do_post_stmts()

    # CONTROL 3, first and cheapest: the enumeration must find the surface.
    catalogue = _routes_and_drivability(post_body)
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

    # STRUCTURAL: caller_room can be neither read from the body nor spoofed through it.
    if _reads_caller_room_from_body(post_body):
        return Finding(
            failure_class=FailureClass.BOUNDARY_LEAK,
            summary="do_POST reads `caller_room` off the request body, so a request to "
                    "/api/dispatch can name the room it is asking on behalf of — the "
                    "thing a long-lived server must never take from the caller, because "
                    "it would authenticate the fan-out as whatever room the request "
                    "claims rather than as the roomless server process",
            witness="ast walk of do_POST found a `.get(\"caller_room\", ...)` or "
                    "`[\"caller_room\"]` read",
            site="src/thalamus/console/server.py::Handler.do_POST",
        )
    if not _hardcodes_empty_caller_room(post_body):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="do_POST no longer passes a literal caller_room=\"\" anywhere, so "
                    "'the body is never read for it' would hold vacuously if the "
                    "mechanism that closes this moved somewhere the AST walk cannot see",
            witness="no call in do_POST passes the keyword caller_room=\"\"",
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

        dropped: list[str] = []
        total = 0

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

            # Wrong content-type: `_body()` never consults the header, so a well-formed
            # body posted as text/plain must land exactly like application/json does.
            total += 1
            wrong_ct = _post(port, "/api/key", '{"index":0,"key":"enter"}',
                             headers={"Content-Type": "text/plain"})
            if wrong_ct != "200":
                return Finding(
                    failure_class=FailureClass.INVARIANT_FALSIFIED,
                    summary="a well-formed /api/key body posted with Content-Type: "
                            "text/plain did not answer 200 the way the same body does "
                            "under application/json, so parsing has started depending "
                            "on a header _body() is not supposed to read",
                    witness=f"/api/key, Content-Type: text/plain: answered {wrong_ct!r}, "
                            f"want 200",
                    site="src/thalamus/console/server.py::Handler._body",
                )

            driven = [name for name, drivable in catalogue if drivable]
            for route in driven:
                for raw in _NON_OBJECT:
                    total += 1
                    status = _post(port, route, raw)
                    if status.startswith("dropped"):
                        shown = raw if len(raw) <= 40 else f"{raw[:40]}…(len={len(raw)})"
                        dropped.append(f"POST {route} {shown} -> {status}")

            for route, raw, why in _TYPE_CONFUSION:
                total += 1
                status = _post(port, route, raw)
                if status.startswith("dropped"):
                    dropped.append(f"POST {route} {raw} -> {status} [{why}]")

            # Path traversal on /frame/<name>. A separate frames file, so this probe
            # does not disturb `cfg` for anything above it.
            frame_dir = Path(tmp) / "frames"
            frame_dir.mkdir()
            image = frame_dir / "sign.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
            conf = frame_dir / "frames.conf"
            conf.write_text(
                '{ name = "sign", path = "%s", '
                'panel = { left = 0, right = 1, top = 0, bottom = 1 } }' % image
            )
        # A fresh server bound to a cfg carrying the frames file — the one above never
        # had one, and Config resolves frames_file once at construction.
        frame_cfg = console.Config(session="qe-malformed-probe", project_root=root,
                                   frames_file=conf)
        with _serving(console, console.Handler, frame_cfg) as port:
            # Discrimination: the legitimately configured name must still resolve —
            # otherwise "every traversal 404s" and "everything 404s" are the same
            # observation.
            legit = _get(port, "/frame/sign")
            if legit != "200":
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="a frame name that IS in the configured list did not "
                            "resolve, so this probe cannot tell a working equality "
                            "match from a route that 404s everything",
                    witness=f"GET /frame/sign answered {legit!r}, want 200",
                    site="tests/qe/cases/console_post_survives_malformed_body.py",
                )
            for name in _TRAVERSAL_NAMES:
                status = _get(port, "/frame/" + quote(name, safe=""))
                if status != "404":
                    return Finding(
                        failure_class=FailureClass.BOUNDARY_LEAK,
                        summary="a path-traversal-shaped /frame/<name> did not answer "
                                "404, so the request is reaching a file the frames "
                                "list never named",
                        witness=f"GET /frame/{name} answered {status!r}, want 404",
                        site="src/thalamus/console/server.py::frame_bytes",
                    )

        # Concurrent writes to the same window: N simultaneous closes on one non-anchor
        # window must dedupe to exactly one starter.
        statuses, bodies = _concurrent_close(console, cfg)
        if any(not s.isdigit() for s in statuses):
            return Finding(
                failure_class=FailureClass.FAILED_OPEN,
                summary="a concurrent POST /api/close on a window already being closed "
                        "dropped the connection instead of answering",
                witness=f"statuses: {statuses}",
                site="src/thalamus/console/server.py::Handler.do_POST",
            )
        starters = [b for b in bodies if b and b.get("already") is False]
        if len(starters) != 1:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary="six concurrent POST /api/close on the same window did not "
                        "dedupe to exactly one background close — CLOSING_LOCK is "
                        "supposed to make the check-and-set atomic, and a second "
                        "starter means two close_window threads can race the same "
                        "window",
                witness=f"already=False count={len(starters)} of {len(bodies)}: "
                        f"{bodies}",
                site="src/thalamus/console/server.py::Handler.do_POST (/api/close)",
            )

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
                witness=f"{len(dropped)} of {total} probes "
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
             FailureClass.COLLAPSED_SENTINEL, FailureClass.BOUNDARY_LEAK),
    summary="every console POST route must answer a malformed body instead of letting "
            "an unhandled exception kill the handler thread",
    run=run,
    issue=175,
)
