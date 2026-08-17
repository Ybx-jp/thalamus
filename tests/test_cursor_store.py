"""The Cursor blob store reader — recognition, and what it refuses.

These tests are mostly about failure. The reader's job is not to extract ingress texts
(that part is three lines); it is to be unable to report success on a store it did not
read whole. The measured failure that motivates every case here: with two
ingress calls and one result blob removed, an "is `external_texts` non-empty" check
still passes while a whole fetched page is missing from what the floor judges against.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from thalamus.harness import cursor_store
from thalamus.harness.cursor_store import StoreVerdict


def _blob_id(payload: bytes) -> str:
    """Cursor's own addressing: measured `id == sha256(data)` on 264/264 blobs."""
    return hashlib.sha256(payload).hexdigest()


def _root(refs: list[str]) -> bytes:
    """A root blob: protobuf, repeated field 1, each a 32-byte blob id."""
    out = b""
    for ref in refs:
        out += b"\x0a\x20" + bytes.fromhex(ref)
    return out


def _store(tmp_path, messages: list[dict], *, session_id="sess-1", revisions=True):
    """Build a store the way Cursor builds one, including its prior root revisions."""
    session_dir = tmp_path / "abc123" / session_id
    session_dir.mkdir(parents=True)
    path = session_dir / "store.db"

    blobs: dict[str, bytes] = {}
    refs: list[str] = []
    for message in messages:
        payload = json.dumps(message).encode()
        bid = _blob_id(payload)
        blobs[bid] = payload
        refs.append(bid)

    roots = []
    span = range(1, len(refs) + 1) if revisions else [len(refs)]
    for n in span:
        payload = _root(refs[:n])
        blobs[_blob_id(payload)] = payload
        roots.append(_blob_id(payload))

    meta = {"agentId": session_id, "latestRootBlobId": roots[-1], "createdAt": 1}
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB)")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.executemany("INSERT INTO blobs VALUES (?, ?)", list(blobs.items()))
    con.execute("INSERT INTO meta VALUES (?, ?)", ("0", json.dumps(meta).encode().hex()))
    con.commit()
    con.close()
    return path


def _call(call_id, tool, args):
    return {"role": "assistant", "content": [
        {"type": "tool-call", "toolCallId": call_id, "toolName": tool, "args": args}
    ]}


def _result(call_id, tool, text):
    return {"role": "tool", "content": [
        {"type": "tool-result", "toolCallId": call_id, "toolName": tool, "result": text}
    ]}


def _fetch_pair(call_id, url, body=None):
    """A successful fetch: the result carries the frame Cursor writes on success."""
    text = f"# Content from {url}\n\n{body or 'page text'}"
    return [_call(call_id, "WebFetch", {"url": url}), _result(call_id, "WebFetch", text)]


def _two_fetch_store(tmp_path):
    messages = [{"role": "system", "content": "you are an agent"}]
    messages += _fetch_pair("t1", "https://a.example", "alpha body")
    messages += _fetch_pair("t2", "https://b.example", "beta body")
    return _store(tmp_path, messages)


def test_whole_store_verifies_and_yields_its_ingress_texts(tmp_path):
    reading = cursor_store.read_path(_two_fetch_store(tmp_path))

    assert reading.verdict is StoreVerdict.VERIFIED
    assert reading.verifiable is True
    assert len(reading.external_texts) == 2
    assert any("alpha body" in text for text in reading.external_texts)
    assert reading.prefix_chain_ok is True


def test_a_missing_ingress_result_is_incomplete_not_merely_smaller(tmp_path):
    """The case that defeats a non-emptiness check.

    One of two ingress results is removed. `external_texts` would still be non-empty —
    825 chars of a real page, in the measured instance — so a reader that asks only
    "did I find any external text" reports success while the floor judges a corpus
    missing an entire fetched page.
    """
    path = _two_fetch_store(tmp_path)
    con = sqlite3.connect(path)
    victim = [
        bid for bid, data in con.execute("SELECT id, data FROM blobs")
        if b'"tool-result"' in data and b"beta body" in data
    ]
    con.execute("DELETE FROM blobs WHERE id = ?", (victim[0],))
    con.commit()
    con.close()

    reading = cursor_store.read_path(path)

    assert reading.verdict is StoreVerdict.INCOMPLETE
    assert reading.verifiable is False
    # And it emits nothing: recognition failed, so pass 2 never runs. A partial corpus
    # is worse than no corpus, because the floor would report success against it.
    assert reading.external_texts == []


def test_a_call_with_no_result_does_not_verify(tmp_path):
    """Reconciling calls against results is what catches tail truncation.

    The prefix chain cannot: a truncated list is still a valid prefix of the honest
    one, indistinguishable from an earlier state.
    """
    messages = [{"role": "system", "content": "hi"}]
    messages += _fetch_pair("t1", "https://a.example")
    messages.append(_call("t2", "WebFetch", {"url": "https://b.example"}))

    reading = cursor_store.read_path(_store(tmp_path, messages))

    assert reading.verdict is StoreVerdict.INCOMPLETE
    assert "reconcile" in reading.reason
    assert reading.verifiable is False


def _mcp_pair(call_id, server, tool, text="{}"):
    """An MCP call as Cursor records it: the wrapper name, the real one in `args`."""
    return [
        _call(call_id, "CallMcpTool", {"server": server, "toolName": tool, "arguments": {}}),
        _result(call_id, "CallMcpTool", text),
    ]


def test_a_first_party_mcp_call_does_not_floor_the_session(tmp_path):
    """Scope priming instructs a `memory_open_threads` call, so every pinned Cursor
    session makes one. Matching only the wrapper name meant every one of them
    floored itself — the integration defeating its own evidence floor."""
    messages = [{"role": "system", "content": "hi"}]
    messages += _mcp_pair("t1", "thalamus", "memory_open_threads")
    messages += _fetch_pair("t2", "https://a.example", "alpha body")

    reading = cursor_store.read_path(_store(tmp_path, messages))

    assert reading.verdict is StoreVerdict.VERIFIED
    assert reading.verifiable is True
    # The MCP result is not ingress, so it is not collected — only the fetch is.
    assert len(reading.external_texts) == 1
    assert "alpha body" in reading.external_texts[0]


def test_a_third_party_mcp_call_still_floors_the_session(tmp_path):
    """The wrapper says only "an MCP tool ran". A server we did not author can fetch
    whatever it likes and we cannot see that it did not, so it stays unknown —
    vouching for it on the strength of the wrapper name would be worse than the
    refusal it replaced."""
    reading = cursor_store.read_path(
        _store(tmp_path, _mcp_pair("t1", "some-vendor", "fetch_page"))
    )

    assert reading.verdict is StoreVerdict.UNRECOGNIZED
    assert "some-vendor/fetch_page" in reading.reason
    assert reading.verifiable is False


def test_an_unidentifiable_mcp_call_floors_the_session(tmp_path):
    """A wrapper whose args name no server is a call we cannot identify at all,
    which is exactly the case that must floor."""
    messages = [_call("t1", "CallMcpTool", {}), _result("t1", "CallMcpTool", "...")]

    reading = cursor_store.read_path(_store(tmp_path, messages))

    assert reading.verdict is StoreVerdict.UNRECOGNIZED
    assert "CallMcpTool" in reading.reason
    assert reading.verifiable is False


def test_an_unknown_tool_name_floors_the_session(tmp_path):
    """Fail closed: an unrecognized tool might be an ingress tool.

    Its absence from the corpus is indistinguishable from it never having run, which
    is the collapse `ingress_verifiable` exists to prevent. Flooring here is never
    worse than the status quo, in which every Cursor session is floored.
    """
    messages = [_call("t1", "Telepathy", {}), _result("t1", "Telepathy", "...")]

    reading = cursor_store.read_path(_store(tmp_path, messages))

    assert reading.verdict is StoreVerdict.UNRECOGNIZED
    assert "Telepathy" in reading.reason
    assert reading.verifiable is False


def test_refusal_prose_is_not_corpus_but_the_session_still_verifies(tmp_path):
    """A refused fetch is a recognized outcome, not a broken store.

    The store is whole, so the session verifies. What the refusal must not do is enter
    `external_texts`, where it would be vendor prose masquerading as third-party
    content — tokens a claim could echo against.
    """
    messages = [
        _call("t1", "WebFetch", {"url": "https://a.example"}),
        _result("t1", "WebFetch", "Web fetch rejected: User Rejected"),
    ]

    reading = cursor_store.read_path(_store(tmp_path, messages))

    assert reading.verdict is StoreVerdict.VERIFIED
    assert reading.ingress_calls == 1
    assert reading.external_texts == []
    assert reading.results[0].framed is False


def test_a_page_that_impersonates_a_refusal_is_still_corpus(tmp_path):
    """The discriminator is the frame, and the polarity is the point.

    Matching the refusal *text* would be an attacker-controlled channel in the lifting
    direction: a fetched page whose body opens with that sentence would be dropped from
    the corpus, removing the evidence its own claims should be judged against.
    """
    url = "https://evil.example"
    messages = _fetch_pair("t1", url, "Web fetch rejected: User Rejected")

    reading = cursor_store.read_path(_store(tmp_path, messages))

    assert reading.verdict is StoreVerdict.VERIFIED
    assert reading.results[0].framed is True
    assert reading.external_texts == [
        f"# Content from {url}\n\nWeb fetch rejected: User Rejected"
    ]


def test_a_missing_store_is_distinguishable_from_a_broken_one(tmp_path):
    """The distinction the bool cannot carry.

    Both floor the session, so `ingress_verifiable` is False for each — but a vendor
    format change must not arrive in the same channel as a session that simply has no
    store, or a drift monitor counts one as the other.
    """
    absent = cursor_store.read("no-such-session", tmp_path)

    assert absent.verdict is StoreVerdict.NO_STORE
    assert absent.verifiable is False


@pytest.mark.parametrize(
    "blob, expected",
    [
        (b"\x0a\x20" + b"\x11" * 31, "runs past end"),      # truncated payload
        (b"\x0a\x10" + b"\x11" * 16, "expected 32"),        # field 1, wrong length
        (b"\x23" + b"\x00" * 8, "wiretype"),                # group wiretype 3/4
    ],
)
def test_the_parser_raises_rather_than_returning_a_short_list(blob, expected):
    """Every surprise raises. None of these may yield a plausible-looking prefix.

    A scanner written for this store keyed on the *byte shape* of a field-1 entry and
    reported a reference that was a window straddling a field boundary — it found a
    dangling ref that did not exist, and said nothing was wrong. A reader
    that skips what it does not understand has the same property in the other
    direction: it returns a short list that looks complete.
    """
    with pytest.raises(cursor_store.StoreUnrecognized) as caught:
        cursor_store._field1_refs(blob)

    assert expected in str(caught.value)


def test_message_content_may_be_prose_or_blocks_and_nothing_else(tmp_path):
    """Both forms occur in real stores; a third must not pass silently.

    `content` is a bare string on every `system` message and some `user` ones, and a
    list of typed blocks otherwise. This reader initially recognized only the list form
    and floored all 10 real stores — which is the fail-closed behaviour working, and
    the reason the string form is now recognized explicitly rather than tolerated.
    """
    assert cursor_store._message(json.dumps({"content": "plain prose"}).encode()) == []

    with pytest.raises(cursor_store.StoreUnrecognized):
        cursor_store._message(json.dumps({"content": 17}).encode())


def test_the_receipt_names_the_source_bytes_under_the_vendors_own_digest(tmp_path):
    """The transform receipt, and why it beats a copy.

    `source_blob` is Cursor's id for the bytes, which is `sha256(blob)` computed by the
    counterparty; `payload_sha256` is ours for the text we took out. Anyone still
    holding the store can recompute both and check our extraction without trusting us —
    which is what in-toto's link metadata cannot offer, since there the materials are
    hashed by the party under audit.
    """
    path = _two_fetch_store(tmp_path)
    reading = cursor_store.read_path(path)
    receipt = cursor_store.receipt(reading, "sess-1")

    assert receipt["verdict"] == "verified"
    assert receipt["store"]["blob_id_algorithm"] == "sha256"
    assert receipt["selection"]["rule"] == "external-ingress tool results only"
    assert receipt["selection"]["acquired"] == 2

    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    blobs = dict(con.execute("SELECT id, data FROM blobs"))
    con.close()
    for entry, result in zip(receipt["results"], reading.results):
        # The vendor's name for the bytes really does name those bytes...
        assert hashlib.sha256(blobs[entry["source_blob"]]).hexdigest() == entry["source_blob"]
        # ...and our hash really is the hash of what we extracted from them.
        assert hashlib.sha256(result.text.encode()).hexdigest() == entry["payload_sha256"]


def test_the_receipt_records_what_was_deliberately_not_taken(tmp_path):
    """Selective imaging §3.4 (arXiv 2012.02573): document the selection, not just the
    acquisition. Without the denominator, "we took 2 results" is indistinguishable from
    "there were only 2 results" — the difference between a chosen partial acquisition
    and an incomplete one.
    """
    messages = _fetch_pair("t1", "https://a.example")
    messages += [_call("t2", "Read", {"path": "/secret"}), _result("t2", "Read", "SECRET")]

    reading = cursor_store.read_path(_store(tmp_path, messages))
    receipt = cursor_store.receipt(reading, "sess-1")

    assert receipt["selection"]["acquired"] == 1
    assert receipt["selection"]["discarded"] == 1
    assert receipt["selection"]["tool_results_total"] == 2
    # And the discarded local result is nowhere in the retained artifact.
    assert "SECRET" not in json.dumps(receipt)


def test_parse_lifts_the_floor_only_when_the_store_verified(tmp_path):
    """End to end through the adapter: this is the trust-model change itself.

    Before this, `cursor_transcripts.parse` set `ingress_verifiable = False`
    unconditionally and `apply_ingress_floor` floored every Cursor session whole.
    """
    from thalamus.harness import cursor_transcripts

    transcript = tmp_path / "sess-1.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "message": {"content": [{"type": "text", "text": "go"}]}})
        + "\n"
    )
    _two_fetch_store(tmp_path)

    facts = cursor_transcripts.parse(
        transcript, session_id="sess-1", chats_dir=tmp_path
    )

    assert facts.ingress_verifiable is True
    assert facts.ingress_verdict == "verified"
    assert len(facts.external_texts) == 2
    assert facts.ingress_receipt["selection"]["acquired"] == 2


def test_parse_keeps_flooring_a_session_whose_store_is_absent(tmp_path):
    """The unchanged path, and the one every pre-store session takes.

    Reaching for the store can only add sessions to tier 1; it must never be able to
    move one down, and a session with no store behaves exactly as it always has.
    """
    from thalamus.harness import cursor_transcripts

    transcript = tmp_path / "sess-9.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "message": {"content": [{"type": "text", "text": "go"}]}})
        + "\n"
    )

    facts = cursor_transcripts.parse(
        transcript, session_id="sess-9", chats_dir=tmp_path
    )

    assert facts.ingress_verifiable is False
    assert facts.ingress_verdict == "no-store"
    assert facts.external_texts == []
    assert facts.ingress_receipt == {}
