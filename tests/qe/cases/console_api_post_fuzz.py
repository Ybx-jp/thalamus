"""Every drivable console POST route answers any generated body, and never by crashing.

The property over `do_POST`, generated rather than listed. `console_post_survives_malformed_body`
pins a literal corpus (non-objects, five hand-picked type confusions) against a stubbed
tmux; this case drives the *real* server in `_console_rig` with bodies Hypothesis builds,
so it is the arm that finds the crash shape nobody thought to write down.

**Inputs.** The route list is derived from `do_POST` (an AST walk of the shipped
`server.py`, honouring `QE_CONSOLE_SRC`) minus `_console_rig.UNDRIVABLE_POSTS`; prefix
routes (`/api/jobs/`) belong to `console_api_jobs_proxy_fuzz`. For each route the body is
one of: a *route-shaped* object whose keys are the `data.get("<key>")` names that route's
own AST reads (plus `index` for routes below the window gate), each taking a hostile
value — wrong types, 63/64-bit and 10^300 integers, NaN/Infinity (json.dumps emits them
bare, which `json.loads` accepts), lone surrogates, NUL, `-t 0`, path traversal, `;`,
escape sequences, 1000..300000-character strings, nested containers; an arbitrary
recursive JSON value; or a raw byte body (truncated JSON, binary, 100000-deep nesting, a
5000-digit integer).

**Invariants**, on every reply:

1. a response arrives (a dropped connection, reset or 10s timeout is a failure);
2. an error status carries a JSON object with a string `error` (or the `{"ok": false,
   "output": ...}` shape spawn/shell/roster use);
3. no 500 whose `error` begins with a Python exception type name — that is `_answered`
   catching an unhandled crash (`TypeError: unhashable type: 'list'`), which turns "the
   route refused the input" into "the route died on it".

**Not driven with live values.** `/api/close` and `/api/recycle` are generated with an
`index` that cannot name a live window (a bool or an int 0..8 is filtered out of those two
routes only — `True == 1` would close the victim window); the gate still runs on every
other hostile value. `/api/spawn` and `/api/shell` take `dir` from the hostile pool, never
a path the picker offered, so no body can reach `do_spawn`/`open_shell`. Everything else is
driven with whatever Hypothesis builds; the rig's HOME and tmux server contain the effects.

**Counterexamples.** `hunt()` reports one shrunk body per distinct signature
(route, status, exception type), so a run lists each way the surface breaks at its minimal
input rather than only the first.

**Controls.** (a) A well-formed `/api/key` for a live window answers 200 — a fixture that
refuses everything would satisfy every invariant above. (b) The reply classifier is run on
synthetic crash and no-response replies and must flag them — the detector must be able to
see what it is looking for. (c) The route enumeration must find the named core routes.

**Shown capable of going red.** On the unmodified tree this case is red: `POST /api/key
{"key": []}` answers `500 TypeError: unhashable type: 'list'`, `{"count": Infinity}` an
`OverflowError`, `/api/send` with a NUL byte a `ValueError` (see
`console_post_survives_malformed_body`'s docstring, which lists these as known crash
shapes). To see it go green, copy the console tree, wrap those three sites in the
`isinstance`/range checks they lack, and run with `QE_CONSOLE_SRC=<copy>/packages/
thalamus-console/src`; the remaining signatures (if any) are new findings.
"""

from __future__ import annotations

import ast
import json
import time

from hypothesis import strategies as st

from ..model import Case, FailureClass, Finding, Substrate, Tier
from . import _console_rig as rig_mod
from ._console_hypothesis import (
    Resp,
    crash_type,
    hunt,
    post_raw,
    reply_shape_problem,
    short,
)
from ._console_rig import console_rig
from .console_post_survives_malformed_body import _reads_data, _routes_and_drivability

SITE = "packages/thalamus-console/src/thalamus_console/server.py::Handler.do_POST"

_BIG = [2**31, 2**63 - 1, 2**63, -(2**63), 10**300, -(10**300), 0, -1, 1, 9, 10**18]
_SPECIAL_TEXT = ["", "\x00", "a\x00b", "\ud800", "\udfff", "-t 0", "-", "--",
                 "../../../../etc/passwd", "/etc/passwd", ";", "\\;", "a;", "%s", "%",
                 "\n", "\r\n", "\x1b[31m", "\x1b", "\x03", "🙂", "‮", "﻿",
                 "~", "$(id)", "`id`", "'", '"', "{", "enter", "escape", "up", "space", "ctrl-c", "main", "claude",
                 "codex", "qe", "hello"]
_LONG = [1000, 20_000]
_RAW = [
    b"", b"{", b"}", b"{}", b"[]", b"null", b"{\"index\": 1,", b"\xff\xfe\x00\x01",
    b'{"index": NaN}', b'{"index": Infinity}', b'{"index": -Infinity}',
    b'{"count": NaN, "key": "enter", "index": 1}',
    b'{"count": Infinity, "key": "enter", "index": 1}',
    b'{"index": 1, "key": "enter", "count": 1' + b"0" * 5000 + b"}",
    b'{"a":' * 100_000 + b"1" + b"}" * 100_000,
    b"[" * 100_000 + b"]" * 100_000,
    b'{"index": 1, "text": ' + b"[" * 5000 + b"]" * 5000 + b"}",
]


def _hostile_text():
    special = st.sampled_from(_SPECIAL_TEXT)
    return st.one_of(
        special, special, special,
        st.text(alphabet=st.characters(blacklist_categories=()), max_size=40),
        st.text(alphabet=st.sampled_from(["a", "\x00", "\ud800", "-", ";"]), max_size=6),
        st.builds(lambda n, c: c * n, st.sampled_from(_LONG), st.sampled_from(["A", "\x00", "é"])),
    )


def _leaf():
    return st.one_of(
        st.none(), st.booleans(), st.sampled_from(_BIG), st.integers(),
        st.floats(allow_nan=True, allow_infinity=True), _hostile_text(),
    )


def _value():
    return st.recursive(
        _leaf(),
        lambda kids: st.one_of(st.lists(kids, max_size=3),
                               st.dictionaries(st.text(max_size=6), kids, max_size=3)),
        max_leaves=6)


def _encode(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


def _stmt_keys(stmt: ast.stmt) -> set[str]:
    keys: set[str] = set()
    for n in ast.walk(stmt):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get"
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "data"
                and n.args and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)):
            keys.add(n.args[0].value)
        if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
                and n.value.id == "data" and isinstance(n.slice, ast.Constant)
                and isinstance(n.slice.value, str)):
            keys.add(n.slice.value)
    return keys


def derive_routes(server_py) -> dict[str, set[str]]:
    """{route: the body keys its own code reads}, from the shipped `do_POST`."""
    tree = ast.parse(server_py.read_text(encoding="utf-8"))
    body = next((n.body for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "do_POST"), [])
    gate = next((i for i, s in enumerate(body)
                 if isinstance(s, ast.Assign) and _reads_data(s)
                 and any(isinstance(t, ast.Name) and t.id == "idx" for t in s.targets)),
                len(body))
    names_of = dict()
    for name, _ in _routes_and_drivability(body):
        names_of[name] = set()
    for i, stmt in enumerate(body):
        if not isinstance(stmt, ast.If):
            continue
        names = [o.value for o in ast.walk(stmt.test)
                 if isinstance(o, ast.Constant) and isinstance(o.value, str)
                 and o.value.startswith("/api/")]
        for name in names:
            names_of.setdefault(name, set()).update(_stmt_keys(stmt))
            if i > gate:
                names_of[name].add("index")
    return {k: v for k, v in names_of.items()
            if k not in rig_mod.UNDRIVABLE_POSTS and not k.endswith("/")}


_PROTECTED_INDEX_ROUTES = {"/api/close", "/api/recycle"}


def _body_strategy(routes: dict[str, set[str]]):
    names = sorted(routes)

    def shaped(route: str):
        keys = sorted(routes[route])
        values = st.one_of(_hostile_text(), _hostile_text(), _leaf(), _value())
        if route in _PROTECTED_INDEX_ROUTES:
            values = values.filter(
                lambda v: not (isinstance(v, (bool, int)) and 0 <= int(v) <= 8))
        live = st.sampled_from([None, 1, 1, 1, 0]) if (
            "index" in keys and route not in _PROTECTED_INDEX_ROUTES) else st.none()

        def build(d, pick, r=route):
            if pick is not None:  # a live window, so the route's own code is reached
                d = {**d, "index": pick}
            return r, _encode(d)

        # Every known key is independently optional, so several land in one body — a
        # crash that needs a valid `key` AND a hostile `count` is reachable.
        return st.builds(build, st.fixed_dictionaries({}, optional={k: values for k in keys}),
                         live)

    def raw(route: str):
        if route in _PROTECTED_INDEX_ROUTES:
            return st.sampled_from([b for b in _RAW if b"index" not in b or b"[" in b])
        return st.sampled_from(_RAW)

    per_route = st.sampled_from(names).flatmap(lambda r: st.one_of(
        shaped(r), shaped(r), shaped(r),
        st.builds(lambda b, r=r: (r, b), raw(r)),
        st.builds(lambda v, r=r: (r, _encode(v)),
                  _value().filter(lambda v: not isinstance(v, dict)))))
    return per_route


def _ensure_victim(rig) -> int:
    """A `cat` window that is not the anchor, for the window-gated routes to land on."""
    if any(i == 1 for i, _ in rig.window_names()):
        return 1
    rig.tmux("new-window", "-t", f"{rig.session}:1", "-n", "qe-victim", "cat")
    return 1


def _classify(route: str, resp: Resp) -> tuple[tuple, str] | None:
    if resp.status is None:
        return (route, "no-response"), f"POST {route}: no response ({resp.error})"
    exc = crash_type(resp)
    if exc:
        return (route, 500, exc), f"POST {route} -> 500 {short(resp.body.decode('utf-8', 'replace'), 200)}"
    problem = reply_shape_problem(resp)
    if problem:
        return (route, "shape", resp.status), f"POST {route}: {problem}"
    return None


def run() -> Finding | None:
    # Detector control: the classifier must see a crash and a missing reply.
    synthetic = [
        _classify("/api/x", Resp(500, b'{"error": "TypeError: unhashable type: \'list\'"}')),
        _classify("/api/x", Resp(None, error="RemoteDisconnected")),
        _classify("/api/x", Resp(400, b"not json")),
    ]
    if any(s is None for s in synthetic) or _classify("/api/x", Resp(400, b'{"error": "no"}')):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the reply classifier does not flag a crash, a missing reply and a "
                    "non-JSON error, or flags a clean refusal, so a green run says nothing",
            witness=f"classifier on synthetic replies: {synthetic}",
            site="tests/qe/cases/console_api_post_fuzz.py")

    routes = derive_routes(rig_mod.SERVER_PY)
    if not {"/api/send", "/api/key", "/api/favorite"} <= set(routes) or len(routes) < 6:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the AST walk of do_POST found too few drivable routes, so the sweep "
                    "would stay green over a surface it no longer reads",
            witness=f"routes: {sorted(routes)}",
            site="tests/qe/cases/console_api_post_fuzz.py")

    with console_rig() as rig:
        idx = _ensure_victim(rig)
        ok = post_raw(rig.port, "/api/key", json.dumps({"index": idx, "key": "enter"}).encode())
        if ok.status != 200:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="a well-formed POST /api/key for a live window did not answer 200, "
                        "so the rig refuses everything and the invariants below are vacuous",
                witness=f"status={ok.status} body={ok.body[:120]!r}",
                site="tests/qe/cases/console_api_post_fuzz.py")

        def check(example):
            route, raw = example
            _ensure_victim(rig)
            resp = post_raw(rig.port, route, raw)
            if resp.status is None:
                # A reply that never arrives is only a finding if it never arrives
                # twice: one slow reply on a loaded box is the box, not the route.
                time.sleep(1.0)
                resp = post_raw(rig.port, route, raw)
            verdict = _classify(route, resp)
            if verdict is None and not rig.alive():
                return (route, "server-died"), f"POST {route}: the console process exited"
            return verdict

        hits, truncated = hunt(_body_strategy(routes), check, max_examples=400, rounds=8,
                               budget_s=36.0)
        if not hits:
            return None
        parts = [f"{short(h.example[1].decode('utf-8', 'replace'), 110)} :: {h.detail}"
                 for h in hits]
        return Finding(
            failure_class=FailureClass.FAILED_OPEN,
            summary="a generated POST body made a console route crash (500 naming a Python "
                    "exception), drop the connection, or answer an error that is not a "
                    "JSON {error}; one shrunk body per distinct (route, exception) below",
            witness=f"{len(hits)} distinct signature(s)"
                    + (" (time budget reached; more may remain)" if truncated else "")
                    + ": " + " || ".join(parts),
            site=SITE)


CASE = Case(
    name="a-generated-post-body-never-crashes-a-console-route",
    issue=419,
    fixed=True,
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX,),
    classes=(FailureClass.FAILED_OPEN, FailureClass.COLLAPSED_SENTINEL),
    summary="every drivable console POST route answers hypothesis-generated bodies with "
            "a JSON reply, never a dropped connection or a 500 naming an unhandled exception",
    run=run,
)
