"""A toolCallId that occurs twice is a surprise and must not verify a store missing its fetched page.

Reproduces a defect in `harness/cursor_store.py` found by QE (F2). Builds a store the
way `tests/test_cursor_store.py` does and drives the real reader; the arm marked
control shows the probe can see a correct reading.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from thalamus.harness import cursor_store
from thalamus.harness.cursor_store import StoreVerdict

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SITE = "src/thalamus/harness/cursor_store.py"

import hashlib, json, sqlite3


def _bid(payload):
    return hashlib.sha256(payload).hexdigest()


def _store(base, messages, session_id="sess-1"):
    d = base / "abc123" / session_id
    d.mkdir(parents=True)
    path = d / "store.db"
    blobs, refs = {}, []
    for m in messages:
        p = json.dumps(m).encode()
        blobs[_bid(p)] = p
        refs.append(_bid(p))
    roots = []
    for n in range(1, len(refs) + 1):
        p = b"".join(b"\x0a\x20" + bytes.fromhex(r) for r in refs[:n])
        blobs[_bid(p)] = p
        roots.append(_bid(p))
    meta = {"agentId": session_id, "latestRootBlobId": roots[-1], "createdAt": 1}
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB)")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.executemany("INSERT INTO blobs VALUES (?, ?)", list(blobs.items()))
    con.execute("INSERT INTO meta VALUES (?, ?)", ("0", json.dumps(meta).encode().hex()))
    con.commit()
    con.close()
    return path


def _call(cid, tool, args):
    return {"role": "assistant", "content": [
        {"type": "tool-call", "toolCallId": cid, "toolName": tool, "args": args}]}


def _result(cid, tool, text):
    return {"role": "tool", "content": [
        {"type": "tool-result", "toolCallId": cid, "toolName": tool, "result": text}]}


def _fetch(cid, url, body):
    return [_call(cid, "WebFetch", {"url": url}),
            _result(cid, "WebFetch", f"# Content from {url}\n\n{body}")]



def run() -> Finding | None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        msgs = [{"role": "system", "content": "x"}]
        msgs += _fetch("t1", "https://a.example", "fetched page body")
        msgs += [_call("t1", "Read", {"path": "/x"}), _result("t1", "Read", "local")]
        r = cursor_store.read_path(_store(base / "a", msgs))
        ctl = cursor_store.read_path(_store(base / "b", _fetch("t1", "https://a.example", "fetched page body")))
    if not (ctl.verifiable and len(ctl.external_texts) == 1):
        return Finding(FailureClass.FAILED_OPEN, "control: a lone fetch did not verify", witness="control failed", site=_SITE)
    if any("fetched page body" in t for t in r.external_texts) or not r.verifiable:
        return None
    return Finding(
        FailureClass.FAILED_OPEN,
        "a reused toolCallId overwrites the WebFetch call and result, and the store still verifies with the page gone",
        witness=f"verdict={r.verdict.value} external_texts={r.external_texts} ingress_calls={r.ingress_calls} tool_calls={r.tool_calls}",
        site=_SITE)


CASE = Case(
    name="cursor-store-reused-tool-call-id-drops-ingress",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.FAILED_OPEN,),
    summary="a toolCallId that occurs twice is a surprise and must not verify a store missing its fetched page",
    run=run,
    issue=433,
)
