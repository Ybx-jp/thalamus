"""The origin recorded for fetched bytes must be where the bytes actually came from.

`fetch()` (`src/thalamus/harness/ingest.py:114-122`) returns `response.read(), location`
— the *requested* URL — while `urlopen` follows redirects and `response.url` (which
names the host that actually answered) is discarded.

That origin is what `ExpertManifest.allows()` (`contract/manifest.py:90`) later checks,
and what is stamped onto the `Source` node as provenance. So an allowlisted URL that
302s anywhere yields attacker-controlled bytes carrying an allowlisted origin. The
allowlist is never *wrong* — it is answering a question about a URL nobody fetched.

This is the sharper half of the gate-ordering defect its sibling case covers, and it
survives the obvious fix to that one: moving the allowlist check ahead of `fetch()`
would still consult it against the pre-redirect URL, so closing the ordering without
closing this leaves the hole open while looking shut.

Hermetic — two loopback servers, no egress, no model. Loopback is on no scope's
allowlist, which is exactly the property being exercised.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from ..model import Case, FailureClass, Finding, Substrate, Tier

_PAYLOAD = b"REDIRECT TARGET CONTENT. " + b"Body served by the host that actually answered. " * 8


def _make_server(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


class _Target(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(_PAYLOAD)))
        self.end_headers()
        self.wfile.write(_PAYLOAD)

    def log_message(self, *_args):
        return


def run() -> Finding | None:
    from thalamus.harness import ingest as ingest_mod  # noqa: PLC0415

    target_server, target_port = _make_server(_Target)
    target_url = f"http://127.0.0.1:{target_port}/actually-served-here"

    class _Redirector(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(302)
            self.send_header("Location", target_url)
            self.end_headers()

        def log_message(self, *_args):
            return

    redirect_server, redirect_port = _make_server(_Redirector)
    entry_url = f"http://127.0.0.1:{redirect_port}/looks-allowlisted"

    try:
        fetched = ingest_mod.fetch(entry_url)
    except Exception as exc:  # noqa: BLE001
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="fetch() raised, so the redirect path was never exercised and this "
                    "case cannot distinguish a correct origin from an untested one",
            witness=f"{type(exc).__name__}: {exc}",
            site="src/thalamus/harness/ingest.py:114",
        )
    finally:
        for server in (redirect_server, target_server):
            server.shutdown()
            server.server_close()

    # POSITIVE CONTROL: the redirect must actually have been followed. If it were not,
    # origin would equal the entry URL for the correct reason, and this case would
    # report a leak that is not there.
    payload, origin = fetched.payload, fetched.origin
    if payload != _PAYLOAD:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="control failed: the redirect was not followed, so origin==entry is "
                    "correct here and proves nothing about redirect handling",
            witness=f"got {len(payload)} bytes, expected the target's {len(_PAYLOAD)}",
            site="src/thalamus/harness/ingest.py:119",
        )

    if origin == target_url:
        return None

    return Finding(
        failure_class=FailureClass.BOUNDARY_LEAK,
        summary=(
            "fetch() records the requested URL as the origin while urlopen follows "
            "redirects, so bytes from one host are attributed to another — and that "
            "attribution is what the allowlist checks and what the Source node carries"
        ),
        witness=(
            f"requested={entry_url} served-by={target_url} recorded-origin={origin} "
            f"(body came from the target, proving the redirect was followed)"
        ),
        site="src/thalamus/harness/ingest.py:120",
    )


CASE = Case(
    name="ingest-origin-survives-redirect",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="the recorded origin must name the host that actually served the bytes",
    run=run,
)
