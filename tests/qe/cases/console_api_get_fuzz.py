"""Generated GET paths and query strings never crash the console, leak a file, or 200 a stranger.

The property over `_route_get`, generated. `console_post_survives_malformed_body` pins
five hand-written `/frame/<name>` traversal strings; this case drives the *real* server in
`_console_rig` with request targets Hypothesis builds.

**Two input families.**

- *Query fuzz* on the three routes that parse a query — `/api/read`, `/api/read/body`,
  `/api/commands` — against a rig that holds one live window: `index`, `since` and `item`
  take digit-shaped hostile values (negatives and `--5`, 5000-digit integers, Unicode
  digits that `str.isdigit()` accepts and `int()` does not — `²`, `①` — Arabic-Indic digits
  that both accept, `%`, `%zz`, `%00`, repeated and unknown parameters).
- *Path fuzz*: request targets built from `..`, `%2e%2e`, `%2E%2E`, `%2f`, `%5c`, `//`,
  `/./`, `;`, `%00`, `/frame/…`, `/static/…`, `/api/…` and the names of the files this
  case plants, each percent-encoded into a valid request line.

**Invariants**, on every reply:

1. a response arrives, and an error status carries a JSON object with a string `error`;
2. no 500 whose `error` begins with a Python exception type name (`_answered` catching a
   crash);
3. *nothing outside `STATIC` is ever served from disk*: sentinel files with unique
   contents are planted in the rig's HOME and in its root (the server's cwd), the root and
   HOME copies are also named `index.html`/`app.js`/`style.css`, and no reply body may
   contain a sentinel;
4. a target whose path (before `?`, undecoded) is not a known route, a `STATIC` entry, or
   under a prefix route (`/frame/`, `/api/jobs/`) answers `404` with a JSON `error`.
   `/frame/<anything>` also answers 404, since the rig has no frames file.

The known-route set is derived from the shipped `_route_get` and `STATIC` by AST walk,
not listed here.

**Controls.** (a) `/style.css` answers 200 with exactly the bytes in `STATIC_DIR` — the
server is up and serving, so "no sentinel in any reply" is not "no reply". (b) The test
reads each planted sentinel itself, so the files exist where the server could reach them.
(c) The leak detector and the crash classifier are run on synthetic replies and must flag
them. (d) The AST walk must find `/api/read` and `/api/commands`.

**Not driven:** `/api/admin` and `/api/cursor-sweep` (they call out to a service manager
and to the sweep worker); every other known GET route is exercised by the path-only
arm only when generated verbatim, and by query when named above.

**Shown capable of going red.** On the unmodified tree this case is red:
`GET /api/commands?index=²` and `?index=--5` answer `500 ValueError` (`isdigit()` / the
`lstrip("-")` guard pass a string `int()` rejects), and a 5000-digit `index` trips
CPython's 4300-digit `int()` limit. Repairing those three sites in a copy of the console
tree (`QE_CONSOLE_SRC=<copy>/packages/thalamus-console/src`) turns the crash signatures
green; making `STATIC` resolve against the rig cwd instead of `STATIC_DIR`, or
serving `frame_bytes` from a request-built path, turns the leak/404 arm red.
"""

from __future__ import annotations

import ast
import time
from urllib.parse import quote_from_bytes

from hypothesis import strategies as st

from ..model import Case, FailureClass, Finding, Substrate, Tier
from . import _console_rig as rig_mod
from ._console_hypothesis import (
    Resp,
    crash_type,
    http_call,
    hunt,
    reply_shape_problem,
    short,
)
from ._console_rig import console_rig

SITE = "packages/thalamus-console/src/thalamus_console/server.py::Handler._route_get"
_ME = "tests/qe/cases/console_api_get_fuzz.py"
_NOT_FUZZED = {"/api/admin", "/api/cursor-sweep"}

_DIGITS = ["", "-", "--5", "-5", "+1", " 1", "1 ", "1e3", "0x10", "1_0", "²", "①", "٣", "１",
           "9" * 5000, "-" + "9" * 5000, "9" * 4300, "0" * 5000, "%", "%zz", "%00", "%ff",
           "0", "1", "2", "999999999999999999999", "-0", "\x00"]
_PARAMS = ["index", "since", "item", "junk"]


def _enc(raw: str) -> str:
    """Percent-encode a text into a valid request-target fragment (surrogates kept)."""
    return quote_from_bytes(raw.encode("utf-8", "surrogatepass"), safe="")


def _digitish():
    return st.one_of(
        st.sampled_from(_DIGITS).map(lambda s: s if s.startswith("%") else _enc(s)),
        st.sampled_from(_DIGITS).filter(lambda s: s.startswith("%")),
        st.text(alphabet=st.characters(categories=("Nd", "No", "Pd", "Zs", "Cc")),
                max_size=8).map(_enc),
    )


_QUERY_ROUTES = ["/api/read", "/api/read/body", "/api/commands"]


def _query_target():
    pair = st.tuples(st.sampled_from(_PARAMS), _digitish()).map(lambda kv: f"{kv[0]}={kv[1]}")
    qs = st.lists(pair, min_size=1, max_size=4).map("&".join)
    return st.builds(lambda r, q: f"{r}?{q}", st.sampled_from(_QUERY_ROUTES), qs)


_SEGS = ["..", ".", "%2e%2e", "%2E%2E", "%2e", "..%2f", "%2f", "%5c", "..%5c", "", "frame",
         "static", "api", "read", "app.js", "index.html", "style.css", "etc", "passwd", "%00",
         ";", "%252e%252e", "qe-sentinel-home.txt", "qe-sentinel-root.txt", "home",
         "jobs", "sw.js", "manifest.webmanifest", "%c0%ae%c0%ae", "~", "%7e", "x.png"]


def _path_target():
    seg = st.one_of(st.sampled_from(_SEGS),
                    st.text(alphabet=st.characters(blacklist_categories=("Cs",)),
                            max_size=6).map(_enc))
    head = st.sampled_from(["/", "//", "/frame/", "/static/", "/api/", "/api/read/", "///",
                            "/frame/..%2f", "/frame/%2e%2e/", "/./", "/%2e/"])
    tail = st.sampled_from(["", "", "?", "?index=1", "#frag", "/", ";a=b"])
    return st.builds(lambda h, segs, t: h + "/".join(segs) + t, head,
                     st.lists(seg, max_size=7), tail)


def _known_routes(server_py) -> tuple[set[str], set[str], set[str]]:
    """(exact GET routes, STATIC keys, prefix routes) from the shipped server source."""
    tree = ast.parse(server_py.read_text(encoding="utf-8"))
    exact: set[str] = set()
    prefixes: set[str] = set()
    static: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_route_get":
            for n in ast.walk(node):
                if (isinstance(n, ast.Compare) and isinstance(n.left, ast.Name)
                        and n.left.id == "path"):
                    for c in n.comparators:
                        if isinstance(c, ast.Constant) and isinstance(c.value, str):
                            exact.add(c.value)
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr == "startswith"
                        and isinstance(n.func.value, ast.Name) and n.func.value.id == "path"
                        and n.args and isinstance(n.args[0], ast.Constant)):
                    prefixes.add(n.args[0].value)
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "STATIC" for t in node.targets):
            if isinstance(node.value, ast.Dict):
                static = {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    return exact, static, prefixes


def _classify(target: str, resp: Resp, known: set[str], prefixes: set[str],
              sentinels: list[bytes]) -> tuple[tuple, str] | None:
    path = target.split("?", 1)[0]
    if path.startswith("//"):
        # http.server collapses leading slashes before the handler sees the path
        # (gh-87389, an open-redirect guard); `//` is `/`, which is a STATIC entry.
        path = "/" + path.lstrip("/")
    cls = path if path in known else "unknown-path"
    if resp.status is None:
        return (cls, "no-response"), f"GET {target}: no response ({resp.error})"
    for s in sentinels:
        if s in resp.body:
            return ("leak", cls), f"GET {target} -> {resp.status} served planted file bytes"
    exc = crash_type(resp)
    if exc:
        return (cls, 500, exc), f"GET {short(target, 90)} -> 500 {resp.body.decode('utf-8', 'replace')[:130]}"
    problem = reply_shape_problem(resp)
    if problem:
        return (cls, "shape", resp.status), f"GET {short(target, 90)}: {problem}"
    if path not in known and not any(path.startswith(p) for p in prefixes - {"/api/jobs/"}):
        obj = resp.obj()
        if resp.status != 404 or not (isinstance(obj, dict) and isinstance(obj.get("error"), str)):
            return ("unknown-not-404", resp.status), (
                f"GET {short(target, 90)} -> {resp.status} {resp.body[:80]!r}, want 404 JSON")
    if path.startswith("/frame/") and resp.status != 404:
        return ("frame-not-404", resp.status), f"GET {short(target, 90)} -> {resp.status}, want 404"
    return None


def run() -> Finding | None:
    exact, static, prefixes = _known_routes(rig_mod.SERVER_PY)
    known = exact | static
    if not {"/api/read", "/api/commands"} <= exact or "/app.js" not in static:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the AST walk of _route_get/STATIC did not find the named routes, so "
                    "the 404 arm would run against an empty known-set",
            witness=f"exact={sorted(exact)} static={sorted(static)} prefixes={sorted(prefixes)}",
            site=_ME)

    tok = "QE-SENTINEL-%s" % time.monotonic_ns()
    sentinels = [f"{tok}-HOME".encode(), f"{tok}-ROOT".encode()]
    synth = [_classify("/x", Resp(200, sentinels[0] + b"..", {}), known, prefixes, sentinels),
             _classify("/api/read?index=1", Resp(500, b'{"error": "ValueError: x"}'), known,
                       prefixes, sentinels),
             _classify("/nope", Resp(200, b'{"ok": true}'), known, prefixes, sentinels)]
    if any(s is None for s in synth) or _classify(
            "/nope", Resp(404, b'{"error": "not found"}'), known, prefixes, sentinels):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the reply classifier does not flag a planted-file leak, a crash or a "
                    "200 on an unknown path, or flags a clean 404",
            witness=f"classifier on synthetic replies: {synth}", site=_ME)

    with console_rig() as rig:
        plants = {rig.home / "qe-sentinel-home.txt": sentinels[0],
                  rig.root / "qe-sentinel-root.txt": sentinels[1]}
        for name in ("index.html", "app.js", "style.css"):
            plants[rig.home / name] = sentinels[0]
            plants[rig.root / name] = sentinels[1]
        for path, content in plants.items():
            path.write_bytes(content)
        for path, content in plants.items():
            if path.read_bytes() != content:
                return Finding(failure_class=FailureClass.COLLAPSED_SENTINEL,
                               summary="a planted sentinel is not readable by the test itself",
                               witness=str(path), site=_ME)
        rig.tmux("new-window", "-t", f"{rig.session}:1", "-n", "qe-victim", "cat")

        css = http_call(rig.port, "GET", "/style.css")
        want = (rig_mod.STATIC_DIR / "style.css").read_bytes()
        if css.status != 200 or css.body != want:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="GET /style.css did not answer 200 with the bytes in STATIC_DIR, so "
                        "'no reply carries a sentinel' would hold of a server serving nothing",
                witness=f"status={css.status} len={len(css.body)} want_len={len(want)}",
                site=_ME)

        def check(target: str):
            resp = http_call(rig.port, "GET", target)
            if resp.status is None:
                time.sleep(1.0)  # one slow reply is the box; two are the route
                resp = http_call(rig.port, "GET", target)
            verdict = _classify(target, resp, known, prefixes, sentinels)
            if verdict is None and not rig.alive():
                return ("server-died",), f"GET {target}: the console process exited"
            return verdict

        hits, truncated = hunt(st.one_of(_query_target(), _query_target(), _path_target()),
                               check, max_examples=300, rounds=7, budget_s=30.0)
        if not hits:
            return None
        parts = [f"{short(h.example, 100)} :: {h.detail}" for h in hits]
        leak = any(h.signature[0] == "leak" for h in hits)
        return Finding(
            failure_class=FailureClass.BOUNDARY_LEAK if leak else FailureClass.FAILED_OPEN,
            summary="a generated GET target made the console crash (500 naming a Python "
                    "exception), drop the connection, serve a file outside STATIC, or "
                    "answer an unknown path with something other than a 404 JSON; one "
                    "shrunk target per distinct signature below",
            witness=f"{len(hits)} distinct signature(s)"
                    + (" (time budget reached; more may remain)" if truncated else "")
                    + ": " + " || ".join(parts),
            site=SITE)


CASE = Case(
    name="a-generated-get-target-never-crashes-leaks-or-200s-a-stranger",
    issue=419,
    fixed=True,
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX,),
    classes=(FailureClass.FAILED_OPEN, FailureClass.BOUNDARY_LEAK,
             FailureClass.COLLAPSED_SENTINEL),
    summary="generated GET paths and queries never crash a console route, never serve a "
            "file outside STATIC, and answer every unknown path with a 404 JSON",
    run=run,
)
