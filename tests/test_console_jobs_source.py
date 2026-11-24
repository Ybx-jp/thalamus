"""
The console's jobs source: the proxy the jobs, board and app-widget pages read through.

Interfaces: thalamus_console.jobs_source.forward and the console Handler's /api/jobs/
routes, over real HTTP against a fake source.
Infrastructure: two real sockets on ephemeral ports; no tmux, no graph, no browser.
Scope: what the console promises about a source it knows nothing about — the token is
attached server-side and never leaves, a write is forwarded only past the console's own
Origin gate, the reply (status, body, an app file's CSP and CORS headers) comes back
verbatim, nothing outside the source's /v1/console/ tree is reachable, and a console
with no source says so. Also pins the jobs pages' identity hue to the roster's.
"""

import json
import re
import threading
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from thalamus_console import jobs_source
from thalamus_console.server import STATIC_DIR, Config, Handler

TOKEN = "s3cret-token"


class _Source(BaseHTTPRequestHandler):
    """Records what arrived, answers per path."""

    seen: list[dict] = []
    elsewhere = ""

    def log_message(self, *args):
        pass

    def _reply(self, code: int, body: bytes, ctype: str = "application/json", extra=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        _Source.seen.append({"method": "GET", "path": self.path,
                             "auth": self.headers.get("Authorization")})
        if self.path.startswith("/v1/console/apps/x/files/"):
            return self._reply(200, b"<!doctype html>", "text/html", [
                ("Content-Security-Policy", "sandbox allow-scripts; default-src 'none'"),
                ("Access-Control-Allow-Origin", "*")])
        if self.path == "/v1/console/missing":
            return self._reply(404, b'{"error": "no such job"}')
        if self.path == "/v1/console/redirect":
            return self._reply(302, b"", extra=[("Location", _Source.elsewhere + "/stolen")])
        if self.path == "/v1/console/short":
            # Declares 500 bytes, sends 7, and closes.
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "500")
            self.end_headers()
            self.wfile.write(b'[{"id":')
            self.close_connection = True
            return
        self._reply(200, json.dumps({"path": self.path}).encode())

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        _Source.seen.append({"method": "POST", "path": self.path, "body": json.loads(self.rfile.read(n)),
                             "auth": self.headers.get("Authorization")})
        self._reply(200, b'{"ok": true}')


class _Elsewhere(BaseHTTPRequestHandler):
    """Where a redirecting source points. Records every request that arrives."""

    seen: list[dict] = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        _Elsewhere.seen.append({"path": self.path, "auth": self.headers.get("Authorization")})
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")


@pytest.fixture
def source():
    _Source.seen = []
    _Elsewhere.seen = []
    other = ThreadingHTTPServer(("127.0.0.1", 0), _Elsewhere)
    threading.Thread(target=other.serve_forever, args=(0.01,), daemon=True).start()
    _Source.elsewhere = f"http://127.0.0.1:{other.server_address[1]}"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Source)
    threading.Thread(target=httpd.serve_forever, args=(0.01,), daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    other.shutdown()


@pytest.fixture
def console(tmp_path, source):
    token = tmp_path / "token"
    token.write_text(TOKEN + "\n")
    cfg = Config(session="t", project_root=tmp_path, jobs_source=source, jobs_token_file=token)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.config = cfg
    threading.Thread(target=httpd.serve_forever, args=(0.01,), daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def _request(port, method, path, body=None, headers=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, json.dumps(body) if body is not None else None, headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), data


def test_a_read_reaches_the_source_with_the_token_attached_server_side(console):
    status, headers, data = _request(console, "GET", "/api/jobs/jobs/weekly-digest?run=abc")
    assert status == 200
    assert json.loads(data) == {"path": "/v1/console/jobs/weekly-digest?run=abc"}
    assert _Source.seen[-1]["auth"] == f"Bearer {TOKEN}"
    # The token is the source's second lock; the browser never holds it.
    assert TOKEN.encode() not in data and all(TOKEN not in v for v in headers.values())


def test_a_write_from_another_page_never_reaches_the_source(console):
    status, _, data = _request(console, "POST", "/api/jobs/jobs/x/run", {},
                               {"Content-Type": "text/plain", "Origin": "https://evil.example"})
    assert status == 403
    assert not [s for s in _Source.seen if s["method"] == "POST"]


def test_a_write_from_a_sandboxed_frame_is_refused(console):
    """An app widget's frame has an opaque origin, which the browser sends as `null`."""
    status, _, _ = _request(console, "POST", "/api/jobs/apps/x/write", {"row": {}},
                            {"Content-Type": "text/plain", "Origin": "null"})
    assert status == 403
    assert not [s for s in _Source.seen if s["method"] == "POST"]


def test_a_write_from_the_consoles_own_page_is_forwarded_with_its_body(console):
    status, _, data = _request(console, "POST", "/api/jobs/findings/f1/label", {"label": "useful"},
                               {"Content-Type": "application/json",
                                "Origin": f"http://127.0.0.1:{console}"})
    assert status == 200 and json.loads(data) == {"ok": True}
    assert _Source.seen[-1] == {"method": "POST", "path": "/v1/console/findings/f1/label",
                                "body": {"label": "useful"}, "auth": f"Bearer {TOKEN}"}


def test_an_app_file_keeps_its_sandbox_policy_and_cors_header(console):
    status, headers, _ = _request(console, "GET", "/api/jobs/apps/x/files/index.html")
    assert status == 200
    assert headers["Content-Type"] == "text/html"
    assert headers["Content-Security-Policy"].startswith("sandbox allow-scripts")
    assert headers["Access-Control-Allow-Origin"] == "*"


def _header_lines(port, path):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    resp.read()
    conn.close()
    return resp.getheaders()


@pytest.mark.parametrize("path", ["/api/jobs/apps/x/files/index.html", "/api/jobs/jobs", "/api/jobs/missing",
                                  "/api/jobs/../x"])
def test_every_jobs_reply_carries_the_consoles_own_sandbox_policy(console, path):
    """A reply here is served from the console's origin, which can drive every pane.

    A source that answered with HTML and no policy would hand a top-level tab at that
    URL the whole console, so the console sends its own sandbox policy on every reply,
    as a separate line beside the source's: the browser enforces both, so a source can
    tighten and never loosen.
    """
    lines = _header_lines(console, path)
    policies = [v for k, v in lines if k.lower() == "content-security-policy"]
    assert "sandbox allow-scripts" in policies
    assert all("allow-same-origin" not in p for p in policies)
    assert ("X-Content-Type-Options", "nosniff") in lines
    if path.endswith("index.html"):
        # The source's own policy still arrives, as a second line.
        assert "sandbox allow-scripts; default-src 'none'" in policies


def test_a_source_that_sends_no_policy_still_gets_one(tmp_path):
    from thalamus_console.jobs_source import relay_headers

    lines = relay_headers({"Content-Type": "text/html"})
    assert ("Content-Security-Policy", "sandbox allow-scripts") in lines
    assert ("X-Content-Type-Options", "nosniff") in lines


def test_a_redirect_is_refused_and_the_token_goes_nowhere(console):
    """urllib's redirect handler copies Authorization onto the new request."""
    status, _, data = _request(console, "GET", "/api/jobs/redirect")
    assert status == 502 and "redirected" in json.loads(data)["error"]
    assert _Elsewhere.seen == []


def test_a_truncated_reply_is_a_failure_not_a_short_answer(console):
    status, _, data = _request(console, "GET", "/api/jobs/short")
    assert status == 502 and "truncated" in json.loads(data)["error"]


def test_a_reply_past_the_cap_is_a_failure_not_a_cut_answer(source, monkeypatch):
    monkeypatch.setattr(jobs_source, "MAX_BODY", 5)
    reply = jobs_source.forward(source, None, "GET", "jobs")
    assert reply.status == 502 and b"too large" in reply.body


def test_the_sources_refusal_comes_back_as_it_was_sent(console):
    status, _, data = _request(console, "GET", "/api/jobs/missing")
    assert status == 404 and json.loads(data) == {"error": "no such job"}


@pytest.mark.parametrize("rest", ["../etc/passwd", "a/../../b", "a%2f..%2fb", "http://x/"])
def test_nothing_outside_the_sources_console_tree_is_reachable(rest):
    reply = jobs_source.forward("http://127.0.0.1:9", None, "GET", rest)
    assert reply.status == 400


def test_a_console_with_no_source_has_no_jobs():
    reply = jobs_source.forward("", None, "GET", "jobs")
    assert reply.status == 404 and json.loads(reply.body) == {"error": "no jobs source"}


def test_a_source_that_does_not_answer_reads_as_unreachable():
    reply = jobs_source.forward("http://127.0.0.1:9", None, "GET", "jobs")
    assert reply.status == 502 and "unreachable" in json.loads(reply.body)["error"]


def test_the_jobs_pages_draw_a_scope_in_the_rosters_hue():
    """A scope is one colour on every console page, so the hash is the roster's code."""
    app = (STATIC_DIR / "app.js").read_text()
    surface = (STATIC_DIR / "surface.js").read_text()
    for pattern in (r'const MAIN_HUE = "[^"]+"', r"const PALETTE = \[[^\]]+\]",
                    r"function hashHue\(name\) \{.*?\n\}"):
        match = re.search(pattern, app, re.S)
        assert match and match.group(0) in surface, pattern


def test_every_jobs_page_asset_is_served(tmp_path):
    from thalamus_console.server import STATIC

    for name in ("jobs.html", "jobs.js", "jobs.css", "surface.css", "surface.js"):
        assert f"/{name}" in STATIC and (Path(STATIC_DIR) / name).exists(), name
