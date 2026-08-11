"""The ingest allowlist must gate the fetch, not just the graph write.

`cli.py:184` advertises the argument as "URL (allowlist-gated)". The allowlist is real —
`ExpertManifest.allows()` at `contract/manifest.py:90`, per-scope, populated in every
`config/experts/*.yaml` — but it is reached from exactly one caller, `check_batch()` at
`manifest.py:110`, which the CLI invokes only after `ingest()` has returned.

Inside `ingest()` (`harness/ingest.py:522-531`) the order is:

    fetch(location) -> archive_bytes(payload) -> to_text() -> run_extraction(build_prompt(...))

So an arbitrary URL is fetched, its bytes are written to the operator's archive, and its
text is handed to a tool-enabled model, all before any host check runs. The control is
positioned behind the three things a reader would expect it to guard. The rejection
message at `cli.py:1660` even says so out loud: *"The fetch is archived; fix and re-run
without refetching cost."*

This case asserts the ordering directly, and it is deliberately built to cost nothing:
`run_extraction` is replaced with a recorder that raises, so no model is ever invoked
even while proving the model WOULD have been. Serving from 127.0.0.1 keeps it hermetic —
no egress, and loopback is not on any scope's allowlist, which is the property under
test.

The negative half ("no model call") has no floor on its own — a case asserting only that
something did NOT happen passes trivially if the code path never ran. Hence the positive
control: the fetch must actually reach the server first.
"""

from __future__ import annotations

import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_BODY = (
    "SETUP GUIDE. " + ("This document is long enough to clear the 200-character floor "
                       "that ingest applies before it will assert anything at all. ") * 4
).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    hits = 0

    def do_GET(self):  # noqa: N802
        type(self).hits += 1
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(_BODY)))
        self.end_headers()
        self.wfile.write(_BODY)

    def log_message(self, *_args):
        return


def run() -> Finding | None:
    from thalamus.harness import extraction, ingest as ingest_mod  # noqa: PLC0415

    _Handler.hits = 0
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/not-on-any-allowlist"

    called: list[str] = []

    class _ModelWasReached(RuntimeError):
        pass

    def _recording_extraction(*_a, **_k):
        called.append("run_extraction")
        raise _ModelWasReached("qe probe: refusing to spend a real model call")

    original = extraction.run_extraction
    with tempfile.TemporaryDirectory() as archive_dir:
        prior = os.environ.get("THALAMUS_ARCHIVE_DIR")
        os.environ["THALAMUS_ARCHIVE_DIR"] = archive_dir
        extraction.run_extraction = _recording_extraction
        try:
            ingest_mod.ingest(url, scope="qe", feed="qe")
        except _ModelWasReached:
            pass
        except Exception:  # noqa: BLE001 - any other failure is reported via the probes below
            pass
        finally:
            extraction.run_extraction = original
            if prior is None:
                os.environ.pop("THALAMUS_ARCHIVE_DIR", None)
            else:
                os.environ["THALAMUS_ARCHIVE_DIR"] = prior
            server.shutdown()
            server.server_close()

        archived = [p for p in Path(archive_dir).rglob("*") if p.is_file()]

    # POSITIVE CONTROL: the fetch must have happened. Without this, both assertions
    # below would pass on any error that prevented ingest from running at all, and the
    # case would report the gate as correct precisely when it was never exercised.
    if _Handler.hits == 0:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "positive control failed: the server was never contacted, so 'nothing "
                "archived' and 'nothing attempted' are indistinguishable here"
            ),
            witness=f"server hits=0 for {url}",
            site="tests/qe/cases/ingest_gate.py",
        )

    leaks = []
    if archived:
        leaks.append(f"archived {len(archived)} file(s) from a non-allowlisted origin")
    if called:
        leaks.append("run_extraction was reached — the document would have gone to a "
                     "tool-enabled model")

    if not leaks:
        return None

    return Finding(
        failure_class=FailureClass.GATE_ORDERING,
        summary=(
            "the ingest allowlist gates only the graph write: bytes from a "
            "non-allowlisted origin are fetched, archived, and passed to the extraction "
            "model before any host check runs"
        ),
        witness=f"origin={url}; " + "; ".join(leaks),
        site="src/thalamus/harness/ingest.py:522-531 vs src/thalamus/contract/manifest.py:110",
    )


CASE = Case(
    name="ingest-allowlist-gates-fetch",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.GATE_ORDERING, FailureClass.COLLAPSED_SENTINEL),
    summary="a non-allowlisted origin must not be fetched, archived, or sent to a model",
    run=run,
)
