"""The jobs source — the console's one window onto a system that runs scheduled jobs.

The jobs, board and app-widget screens render data that belongs to another program:
whatever runs the operator's scheduled jobs, keeps their run records, and holds the
tables a board reads. The console knows nothing about that program's schema. It is
configured with one source URL and a bearer token, and forwards

    GET  /api/jobs/<rest>  ->  GET  <source>/v1/console/<rest>
    POST /api/jobs/<rest>  ->  POST <source>/v1/console/<rest>

with the token attached server-side, so the token never reaches the browser and the
page stays same-origin. A POST is forwarded only after the console's own Origin gate
has passed it (`Handler.do_POST`), which is the same gate every other write here goes
through; whatever preflight the source applies to the job it starts is the source's.

The source reduces and the console renders: every status arrives as a word and a tone,
composed on the far side, and the client prints the word. The wire shapes are
documented in docs/console-jobs-source.md.

Stdlib only, like the bridge: urllib, not requests.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# The path below /api/jobs/ that may be forwarded. Letters, digits and the few
# punctuation marks a job id, a commit sha or an app file name carries; never `..`,
# never a scheme, never a percent-escape that could decode into either.
_REST = re.compile(r"^[A-Za-z0-9._:/-]+$")
# The query string, by the same rule plus `=` and `&`.
_QUERY = re.compile(r"^[A-Za-z0-9._:=&-]*$")

# Headers carried back from the source. An app widget's files arrive with their own
# Content-Security-Policy and Access-Control-Allow-Origin, which is what lets the
# console serve them into a sandboxed frame without knowing what they are.
PASSED_HEADERS = ("Content-Type", "Content-Security-Policy", "Access-Control-Allow-Origin",
                  "Cache-Control", "X-Content-Type-Options")

# What the console sends on every /api/jobs/ reply, whatever the source sent. A reply
# here is served from the console's own origin, and that origin can drive every tmux
# window (/api/send passes the Origin check for it). So a source that answered some
# path with HTML and no policy of its own would hand a page opened at that URL the
# whole console. The sandbox policy gives any such document an opaque origin, and it
# is sent beside the source's policy, never instead of it: a browser enforces every
# policy it receives, so a source can tighten (connect-src, wasm-unsafe-eval for an
# engine) and cannot loosen. A sandbox policy does nothing to a JSON reply, so it is
# sent on all of them rather than on the paths that look like files.
FORCED_HEADERS = (("Content-Security-Policy", "sandbox allow-scripts"),
                  ("X-Content-Type-Options", "nosniff"))


def relay_headers(source_headers: dict[str, str]) -> list[tuple[str, str]]:
    """The header lines the console sends with a source's reply.

    FORCED_HEADERS first, then the source's own Content-Security-Policy and CORS header
    as further lines. Content-Type and Cache-Control are the caller's; the source's
    nosniff is dropped as a duplicate of the forced one.
    """
    lines = list(FORCED_HEADERS)
    for key in ("Content-Security-Policy", "Access-Control-Allow-Origin"):
        if source_headers.get(key):
            lines.append((key, source_headers[key]))
    return lines

TIMEOUT_S = 15.0
# A JSON reply is small; an app's engine bytes are not (a Stockfish WebAssembly build
# with its network runs to tens of megabytes).
MAX_BODY = 64_000_000


@dataclass
class Reply:
    status: int
    body: bytes
    headers: dict[str, str]


def _error(status: int, message: str) -> Reply:
    import json

    return Reply(status, json.dumps({"error": message}).encode(),
                 {"Content-Type": "application/json"})


def forward(source: str, token_file: Path | None, method: str, rest: str, query: str = "",
            body: bytes | None = None) -> Reply:
    """Forward one request to the source and return its reply verbatim.

    Answers 404 when no source is configured — a console without one has no jobs
    screens, which the client renders as their absence — and 502 when the source does
    not answer, redirects, or sends less or more than a whole reply, so a failing
    source reads as failing and never as a short or empty answer.
    """
    if not source:
        return _error(404, "no jobs source")
    if (not _REST.match(rest) or ".." in rest or "//" in rest or rest.startswith("/")
            or not _QUERY.match(query)):
        return _error(400, "bad path")
    url = f"{source.rstrip('/')}/v1/console/{rest}" + (f"?{query}" if query else "")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    token = ""
    if token_file:
        try:
            token = Path(token_file).expanduser().read_text().strip()
        except OSError as exc:
            return _error(502, f"jobs source token unreadable: {exc.strerror}")
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    if token:
        # Unredirected: even if a later change let a redirect through, the token would
        # not travel to wherever the Location header points.
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with _OPENER.open(req, timeout=TIMEOUT_S) as resp:
            return _relay(resp.status, resp, resp.headers)
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            # _NoRedirects refused to follow it, so the token went nowhere.
            return _error(502, "jobs source redirected; a source must answer, not redirect")
        return _relay(exc.code, exc, exc.headers)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        reason = getattr(exc, "reason", exc)
        return _error(502, f"jobs source unreachable: {reason}")


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect. urllib's own handler copies every header but the
    body's two onto the new request, Authorization included, so following one would
    hand the source's token to whatever host Location names."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirects)


def _relay(status: int, stream, headers) -> Reply:
    """The source's reply, or a 502 when its body is not the whole of what it declared.

    `read(n)` does not raise when the connection closes short of Content-Length, so a
    truncated body would otherwise go out as the source's 200; and a body past the cap
    would be cut and go out the same way. Both are the source failing, and say so.
    """
    data = stream.read(MAX_BODY + 1)
    if len(data) > MAX_BODY:
        return _error(502, "jobs source reply too large")
    declared = headers.get("Content-Length")
    if declared is not None and declared.isdigit() and int(declared) != len(data):
        return _error(502, f"jobs source reply truncated: {len(data)} of {declared} bytes")
    return Reply(status, data, {k: v for k in PASSED_HEADERS if (v := headers.get(k))})
