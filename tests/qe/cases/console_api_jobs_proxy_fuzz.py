"""`/api/jobs/<rest>?<query>` forwards only to `<source>/v1/console/...`, with the configured token.

Armed by `CONSOLE_UNBUILT_JOBS_API`: the console's jobs proxy (board note N1) forwards

    GET|POST /api/jobs/<rest>  ->  GET|POST <source>/v1/console/<rest>

attaching a bearer token server-side. That makes `<rest>` and the query string the only
parts of the request the browser controls on a hop that carries a secret to a program the
operator did not write the console for. The property is about what *reaches the source*,
so the source here is a recording stand-in (`_console_rig.jobs_source`) and the invariants
are read off what it received.

**Generated.** `rest` is a join of segments from `..`, `%2e%2e`, `%2E%2E`, `.`, `%2f`,
`%5c`, `%00`, `%0d%0a`, `..;`, `@evil`, `:`, `//`, `?`, `#`, `\\`, a scheme (`http:`), the
names of real endpoints and random printable/percent-encoded text; the query is generated
the same way; the method is GET or POST (POST with an object, a non-object, or no body);
POST carries a same-origin, absent, or foreign `Origin`; every request also carries a
client-supplied `Authorization: Bearer attacker-token`.

**Invariants.**

1. *Whatever reaches the source stays under `/v1/console/`.* The request path the source
   saw starts with `/v1/console/`; percent-decoded to a fixed point and normalised it still
   does, contains no `..` segment, no backslash, no control character; and the request was
   made to the configured source (it is the only listener, so a request that left for
   another host would be a request the source never saw — covered by the next point).
2. *Whatever is refused does not reach the source.* A request whose own text is unsafe
   (`..` segment, scheme, authority, control character, percent-escape that decodes into any
   of them) answers 4xx and the source's request log does not grow.
3. *The token is the configured one.* The `Authorization` the source saw is
   `Bearer <the token file's token>` — never the client's.
4. *A foreign-origin POST is refused (403) and never reaches the source.*
5. *No 5xx naming a Python exception.* `_answered` catching a crash is a failure.

**Controls.** A well-formed `GET /api/jobs/jobs` reaches the source with path
`/v1/console/jobs` and the right token; a same-origin `POST` does too. The safety predicate
used for (1)/(2) is run on synthetic paths (`/v1/console/../admin`, `/v2/x`, `/v1/console/%2e%2e/x`)
and must call them unsafe, and call `/v1/console/jobs/1` safe.

**Shown capable of going red.** In a copy of the console tree (`QE_CONSOLE_SRC`), drop the
`".." in rest` clause from `jobs_source.forward` — `/api/jobs/a/../../../admin` then
reaches the source as `/v1/console/a/../../../admin`, which normalises out of the prefix.
Or build the URL with `urllib.parse.urljoin` instead of concatenation: a scheme or
`//host` in `rest` then replaces the source.
"""

from __future__ import annotations

import posixpath
import re
import time
from urllib.parse import unquote

from hypothesis import strategies as st

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_hypothesis import crash_type, http_call, hunt, short
from ._console_rig import console_rig, jobs_source

SITE = "packages/thalamus-console/src/thalamus_console/jobs_source.py::forward"
_ME = "tests/qe/cases/console_api_jobs_proxy_fuzz.py"

_SEGS = ["..", ".", "%2e%2e", "%2E%2E", "%2e", ".%2e", "%2f", "%5c", "%00", "%0d%0a", "%0a",
         "..;", "@evil", ":", "", "http:", "http:", "//evil", "?x", "#x", "\\", "a:b",
         "jobs", "runs", "apps", "app", "index.html", "x" * 300, "~", "%", "%zz", "%25",
         "%252e%252e", "..%2f..", "a b", "‮"]
_PRINTABLE = st.characters(min_codepoint=0x21, max_codepoint=0x7E)


def _enc(raw: str) -> str:
    from urllib.parse import quote_from_bytes  # noqa: PLC0415
    return quote_from_bytes(raw.encode("utf-8", "surrogatepass"), safe="")


def _piece():
    return st.one_of(st.sampled_from(_SEGS),
                     st.text(alphabet=_PRINTABLE, max_size=8),
                     st.text(alphabet=st.characters(blacklist_categories=()),
                             max_size=4).map(_enc))


_REST = st.lists(_piece(), min_size=1, max_size=6).map("/".join)
_QUERY = st.one_of(st.just(""), st.lists(_piece(), max_size=4).map("&".join),
                   st.sampled_from(["a=b", "x=../../etc", "a=%2e%2e", "a=b&c", "=", "&&",
                                    "a=b\r\nHost:evil"]))
_ORIGINS = st.sampled_from(["same", "same", "none", "foreign", "foreign-referer"])
_BODIES = st.sampled_from(["object", "object", "list", "none"])
_EXAMPLE = st.tuples(st.sampled_from(["GET", "GET", "POST"]), _REST, _QUERY, _ORIGINS, _BODIES)


def target_is_safe(path: str) -> bool:
    """Is the request target the *source* saw confined to `/v1/console/`?"""
    if not path.startswith("/v1/console/"):
        return False
    base = path.split("?", 1)[0]
    if any(ord(c) < 0x21 or ord(c) == 0x7F for c in path) or "\\" in base:
        return False
    decoded = base
    for _ in range(4):
        nxt = unquote(decoded)
        if nxt == decoded:
            break
        decoded = nxt
    if any(ord(c) < 0x20 or c == "\\" for c in decoded) or ".." in decoded.split("/"):
        return False
    return posixpath.normpath(decoded).startswith("/v1/console")


def _unsafe_input(rest: str, query: str) -> bool:
    """Did the request text itself ask for something outside the prefix?"""
    text = rest
    for _ in range(4):
        nxt = unquote(text)
        if nxt == text:
            break
        text = nxt
    segs = text.split("/")
    return (".." in segs or "\\" in text or any(ord(c) < 0x20 for c in text)
            or text.startswith("/") or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", text) is not None
            and "//" in text or "//" in rest)


def run() -> Finding | None:
    synth_bad = ["/v1/console/../admin", "/v2/x", "/v1/console/%2e%2e/x",
                 "/v1/console/a/%252e%252e/%252e%252e/x", "/v1/consolex", "/v1/console/a\\b"]
    if any(target_is_safe(p) for p in synth_bad) or not target_is_safe("/v1/console/jobs/1"):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the path-safety predicate accepts an escaping path or rejects a "
                    "legitimate one, so a green here says nothing",
            witness=f"accepted bad: {[p for p in synth_bad if target_is_safe(p)]}", site=_ME)

    with jobs_source() as src:
        args = ("--jobs-source", src.url, "--jobs-token-file", str(src.token_file))
        with console_rig(extra_args=args) as rig:
            want_auth = f"Bearer {src.token}"
            # Controls: a well-formed GET and a same-origin POST reach the source.
            r = http_call(rig.port, "GET", "/api/jobs/jobs",
                          headers={"Authorization": "Bearer attacker-token"})
            seen = [(q.method, q.path, q.headers.get("Authorization")) for q in src.requests]
            if r.status != 200 or seen != [("GET", "/v1/console/jobs", want_auth)]:
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="a well-formed GET /api/jobs/jobs did not reach the stub source "
                            "as /v1/console/jobs with the configured token, so the "
                            "'refused requests do not reach it' arm is vacuous",
                    witness=f"status={r.status} source saw {seen}", site=_ME)
            r = http_call(rig.port, "POST", "/api/jobs/jobs/1/run", b"{}",
                          {"Content-Type": "application/json",
                           "Origin": f"http://127.0.0.1:{rig.port}"})
            if r.status != 200 or src.requests[-1].path != "/v1/console/jobs/1/run":
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="a same-origin POST /api/jobs/... did not reach the stub source",
                    witness=f"status={r.status} last source request={src.requests[-1:]}",
                    site=_ME)

            def check(example):
                method, rest, query, origin, body = example
                target = f"/api/jobs/{rest}" + (f"?{query}" if query else "")
                headers = {"Authorization": "Bearer attacker-token"}
                data = None
                if method == "POST":
                    headers["Content-Type"] = "application/json"
                    data = {"object": b'{"a": 1}', "list": b"[1]", "none": None}[body]
                    if origin == "same":
                        headers["Origin"] = f"http://127.0.0.1:{rig.port}"
                    elif origin == "foreign":
                        headers["Origin"] = "http://evil.example"
                    elif origin == "foreign-referer":
                        headers["Referer"] = "http://evil.example/page"
                if not all(0x21 <= ord(c) <= 0x7E for c in target):
                    return None  # not a request line a client can send; encoded variants are
                before = len(src.requests)
                resp = http_call(rig.port, method, target, data, headers)
                if resp.status is None:
                    time.sleep(1.0)
                    return ("no-response", method), f"{method} {short(target, 90)}: {resp.error}"
                exc = crash_type(resp)
                if exc:
                    return ("crash", exc), f"{method} {short(target, 90)} -> 500 {resp.body[:120]!r}"
                reached = src.requests[before:]
                for q in reached:
                    if not target_is_safe(q.path):
                        return ("escaped", method), (
                            f"{method} {short(target, 90)} reached the source as "
                            f"{short(q.path, 100)!r}")
                    if q.headers.get("Authorization") != want_auth:
                        return ("token", method), (
                            f"{method} {short(target, 90)}: source saw Authorization "
                            f"{q.headers.get('Authorization')!r}")
                if method == "POST" and origin.startswith("foreign"):
                    if resp.status != 403 or reached:
                        return ("origin", method), (
                            f"POST {short(target, 70)} Origin/Referer evil -> {resp.status}, "
                            f"reached source: {[q.path for q in reached]}")
                    return None
                if method == "POST" and body == "list" and (reached or resp.status != 400):
                    return ("non-object-body",), (
                        f"POST {short(target, 70)} body [1] -> {resp.status}, reached "
                        f"{[q.path for q in reached]}")
                if _unsafe_input(rest, query) and (reached or resp.status < 400):
                    return ("refusal", method), (
                        f"{method} {short(target, 90)} should be refused: status "
                        f"{resp.status}, reached {[q.path for q in reached]}")
                return None

            hits, truncated = hunt(_EXAMPLE, check, max_examples=400, rounds=6, budget_s=30.0)
            if not hits:
                return None
            parts = [f"{short(h.example, 120)} :: {h.detail}" for h in hits]
            escaped = any(h.signature[0] in ("escaped", "token", "origin") for h in hits)
            return Finding(
                failure_class=(FailureClass.BOUNDARY_LEAK if escaped
                               else FailureClass.INVARIANT_FALSIFIED),
                summary="a generated /api/jobs request reached the source outside "
                        "/v1/console/, carried a token that is not the configured one, "
                        "got through a foreign Origin, or crashed the proxy; one shrunk "
                        "request per distinct signature below",
                witness=f"{len(hits)} distinct signature(s)"
                        + (" (time budget reached; more may remain)" if truncated else "")
                        + ": " + " || ".join(parts),
                site=SITE)


CASE = Case(
    name="jobs-proxy-only-forwards-under-v1-console-with-the-configured-token",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX, Substrate.CONSOLE_UNBUILT_JOBS_API),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.INVARIANT_FALSIFIED,
             FailureClass.COLLAPSED_SENTINEL),
    summary="generated /api/jobs/<rest>?<query> requests only reach the jobs source under "
            "/v1/console/, with the configured token, and refused ones never reach it",
    run=run,
)
