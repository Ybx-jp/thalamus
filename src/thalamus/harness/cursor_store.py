"""Cursor's per-session blob store — the ingress floor's evidence, recognized whole.

The transcript Cursor writes carries tool call *inputs* and never their results
(`cursor_transcripts`). The results are not lost, only elsewhere: every session has a
`~/.cursor/chats/<hash>/<session-id>/store.db`, a content-addressed SQLite blob store
holding the same conversation with results attached. This module reads it, and reading
it is what lets a Cursor session earn tier 1 back instead of being floored whole.

**Shape, measured — Cursor publishes no schema for any of it.**

- `meta` holds one row whose value is **hex-encoded** JSON: `latestRootBlobId`,
  `agentId`, `createdAt`, and a `blobEncryptionKey` that encrypts nothing observed and
  sits in plaintext beside the data it names.
- `blobs(id, data)` is content-addressed under **the vendor's own digest**: `id ==
  sha256(data)`, measured 264/264. That is what lets a derived artifact name its source
  bytes in a way someone who distrusts us entirely can still check.
- `latestRootBlobId` addresses a **protobuf** blob whose repeated field 1 holds 32-byte
  blob ids — the conversation's messages, in order. Every other non-JSON blob is an
  earlier revision of that root, one per append.
- Message blobs are plain JSON. An assistant's `tool-call` and the `tool` role's
  `tool-result` both carry `toolCallId`, so calls and results join **by id**.

**Why this reader is two-pass.** LangSec's doctrine (Sassaman et al., Dartmouth
TR2011-709) is full recognition before processing: decide the whole input is valid
*before* acting on any of it. That is not stylistic here. A reader that emits as it
walks produces a partial corpus on a partial store and cannot tell that it did — with
two ingress calls and one result blob removed, an "is it non-empty" check still reports
success while a whole fetched page is missing from what the floor judges against.
Non-empty is not complete. So `read()` recognizes everything and only then
emits, and every surprise raises rather than being skipped.

**Why anything unknown is floored rather than tolerated.** A tool name this module does
not know might be an ingress tool, and we cannot see that it was not. Unknown names
therefore yield `UNRECOGNIZED`, which floors the session exactly as today's
unconditional behaviour does — so the unknown is never worse than the status quo, and
lift is claimed only where the store was recognized whole. The known-tool set below is
*measured, not enumerated from a vendor list*; Cursor has tools no session on the
measuring box invoked.

**Recognition is of the tool that ran, not of the name the store recorded.** Cursor
routes every MCP call through one wrapper, so the recorded name says only "an MCP tool
ran" — the same string for a first-party memory read and for a fetch through some
third-party server. Matching the wrapper name would therefore have been *worse* than
refusing it: it would vouch for a call whose reach nothing here had established. So the
wrapper is resolved through its arguments to `server/toolName` and that is what the
known-set is consulted for, which keeps the rule ("floor what we cannot identify")
while ending the case where every Thalamus-pinned session floored itself, scope priming
being an MCP call that every one of them makes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from thalamus.harness.transcripts import EXTERNAL_INGRESS_TOOLS

# Where Cursor keeps them. The `<hash>` segment is not the session and is not derivable
# from it, so session directories are globbed for rather than addressed.
CURSOR_CHATS = Path.home() / ".cursor" / "chats"

# Tool names this reader has actually seen in a store, beyond the ingress pair. Not a
# vendor list — see the module docstring. A name outside this set plus
# EXTERNAL_INGRESS_TOOLS makes the reading UNRECOGNIZED.
KNOWN_LOCAL_TOOLS = frozenset({
    "Glob", "Grep", "Read", "Shell", "LS", "Edit", "Write", "StrReplace",
})

# `Task` is measured, and is deliberately NOT above. It spawns a subagent with its own
# tools, so its result can carry a page the subagent fetched, summarized and handed
# back — external content arriving under a local-looking name, with no call of our own
# to bind it to. Adding it would lift the floor on exactly the sessions that most need
# it, so it stays unknown and floors. Named here because it looks like an oversight.

# Cursor routes every MCP call through one of these, so the recorded `toolName` names
# the *mechanism* and not the tool: a first-party memory read and a web fetch through
# some MCP server arrive as the same string. Left unresolved, the wrapper is an unknown
# name and floors the session — which is how a Thalamus-pinned Cursor session floored
# itself, since scope priming instructs a `memory_open_threads` call and every pinned
# session therefore makes one. Recognition looks through the wrapper instead, to the
# `server`/`toolName` in its arguments.
MCP_WRAPPER_TOOLS = frozenset({"CallMcpTool", "GetMcpTools"})

# MCP servers whose tools are first-party reads of this machine, named `server/tool`
# after the wrapper is resolved. Only servers *we* author qualify, and the reason is
# the one that puts `Read` and `Shell` in KNOWN_LOCAL_TOOLS rather than in the ingress
# set: their results are observations of the operator's own machine, not content
# fetched from an origin nobody curated. Thalamus's tools read the operator's own graph.
#
# Server-level rather than per-tool, because the unit we can actually vouch for is the
# server: we ship its whole tool surface, and a per-tool list would floor every session
# that used a tool added since this line was written — failing closed on our own
# release cadence rather than on anything about Cursor. A *third-party* server is a
# different matter and stays unknown: it can fetch whatever it likes, and we cannot see
# that it did not.
KNOWN_LOCAL_MCP_SERVERS = frozenset({"thalamus"})

# A successful ingress result is framed, and the frame binds to the call that produced
# it. Refusals ("Web fetch rejected: User Rejected") carry no frame.
#
# The discriminator is deliberately the frame and never the refusal prose. Matching the
# prose would hand an attacker a channel in the *lifting* direction: a fetched page
# whose body opens with that sentence would be discarded from the corpus, removing the
# evidence a claim should have been judged against. The frame contains `args.url` —
# our record of our own call — so forging it means predicting what we asked for.
_WEBSEARCH_FRAME = "Title: Web search results\nContent: "


class StoreVerdict(str, Enum):
    """Why `ingress_verifiable` came out the way it did.

    The floor has two behaviours, so `ingress_verifiable` stays a bool. This is the
    *verdict* rather than the action, and it is four-valued because three separate
    decisions need to tell these apart: which sessions to re-run after a reader fix,
    what a format-drift monitor can count, and what the trust model is entitled to
    claim. Under a bool alone, a Cursor version bump that breaks this reader arrives in
    the same channel as the wholly benign case of a session that has no store.
    """

    VERIFIED = "verified"
    NO_STORE = "no-store"
    INCOMPLETE = "incomplete"
    UNRECOGNIZED = "unrecognized"


class StoreUnrecognized(Exception):
    """The store did not match the shape this reader recognizes. Never caught to skip."""


@dataclass(frozen=True)
class IngressResult:
    """One external-ingress tool result, with what it takes to check we read it right."""

    tool: str
    call_id: str
    args: dict
    text: str
    framed: bool
    # Cursor's own name for the bytes we read it out of: sha256 of the blob.
    source_blob: str
    # Our hash of the text we extracted, so the transform is checkable and not merely
    # asserted. The pair (source_blob, payload_sha256) is the transform receipt.
    payload_sha256: str


@dataclass
class StoreReading:
    verdict: StoreVerdict
    path: Path | None = None
    reason: str = ""
    results: list[IngressResult] = field(default_factory=list)
    ingress_calls: int = 0
    tool_calls: int = 0
    tool_results: int = 0
    message_count: int = 0
    root_blob: str = ""
    root_revisions: int = 0
    prefix_chain_ok: bool = False

    @property
    def verifiable(self) -> bool:
        """Only a store recognized whole licenses lifting the floor."""
        return self.verdict is StoreVerdict.VERIFIED

    @property
    def external_texts(self) -> list[str]:
        """Third-party content only — vendor refusal prose is not corpus."""
        return [r.text for r in self.results if r.framed]


def find_store(session_id: str, chats_dir: Path | None = None) -> Path | None:
    base = chats_dir or CURSOR_CHATS
    for candidate in sorted(base.glob(f"*/{session_id}/store.db")):
        if candidate.is_file():
            return candidate
    return None


def read(session_id: str, chats_dir: Path | None = None) -> StoreReading:
    """Recognize a session's store completely, then emit what the floor needs."""
    path = find_store(session_id, chats_dir)
    if path is None:
        return StoreReading(
            verdict=StoreVerdict.NO_STORE,
            reason="no store.db for this session",
        )
    return read_path(path)


def _effective_tool(name: str, args: dict) -> str:
    """The tool that actually ran, looked up through Cursor's MCP wrapper.

    Returns `server/toolName` for a resolvable wrapper call and the name unchanged
    for everything else. A wrapper whose arguments do not carry both fields is left
    as the bare wrapper name, which `_recognized` refuses — an MCP call we cannot
    identify is exactly the case that must floor, since it could be a fetch.
    """
    if name not in MCP_WRAPPER_TOOLS:
        return name
    server, tool = args.get("server"), args.get("toolName")
    if not isinstance(server, str) or not server:
        return name
    if not isinstance(tool, str) or not tool:
        return name
    return f"{server}/{tool}"


def _recognized(name: str) -> bool:
    """Is this effective tool name one the reader can vouch for?

    Kept separate from the ingress question: `EXTERNAL_INGRESS_TOOLS` decides what
    gets *collected*, this decides whether the store may be read at all.
    """
    if name in EXTERNAL_INGRESS_TOOLS or name in KNOWN_LOCAL_TOOLS:
        return True
    server, sep, tool = name.partition("/")
    return bool(sep and tool) and server in KNOWN_LOCAL_MCP_SERVERS


def read_path(path: Path) -> StoreReading:
    try:
        blobs, meta = _load(path)
    except (OSError, sqlite3.Error) as exc:
        return StoreReading(
            verdict=StoreVerdict.UNRECOGNIZED, path=path, reason=f"unreadable: {exc}"
        )

    # --- pass 1: recognition. Nothing is emitted until all of this succeeds. ---
    try:
        root_id = _root_id(meta)
        if root_id not in blobs:
            return StoreReading(
                verdict=StoreVerdict.INCOMPLETE,
                path=path,
                reason="latestRootBlobId names no blob in the store",
            )
        refs = _field1_refs(blobs[root_id])
        missing = [r for r in refs if r not in blobs]
        if missing:
            return StoreReading(
                verdict=StoreVerdict.INCOMPLETE,
                path=path,
                root_blob=root_id,
                reason=f"{len(missing)} of {len(refs)} message blobs missing",
            )
        messages = [(r, _message(blobs[r])) for r in refs]
        revisions, prefix_ok = _root_revisions(blobs, refs)
    except StoreUnrecognized as exc:
        return StoreReading(
            verdict=StoreVerdict.UNRECOGNIZED, path=path, reason=str(exc)
        )

    calls: dict[str, tuple[str, dict]] = {}
    results: dict[str, tuple[str, str, str]] = {}
    unknown: set[str] = set()
    for blob_id, message in messages:
        for block in message:
            kind = block.get("type")
            name = block.get("toolName")
            if kind not in ("tool-call", "tool-result"):
                continue
            if not isinstance(name, str) or not name:
                return StoreReading(
                    verdict=StoreVerdict.UNRECOGNIZED,
                    path=path,
                    reason=f"{kind} with no toolName",
                )
            call_id = block.get("toolCallId")
            if not isinstance(call_id, str) or not call_id:
                return StoreReading(
                    verdict=StoreVerdict.UNRECOGNIZED,
                    path=path,
                    reason=f"{kind} for {name} carries no toolCallId",
                )
            if kind == "tool-call":
                args = block.get("args")
                args = args if isinstance(args, dict) else {}
                name = _effective_tool(name, args)
                calls[call_id] = (name, args)
            else:
                # A result carries the wrapper name and no arguments, so on its own it
                # cannot say which MCP tool produced it. Its identity is its call's,
                # joined by id; a result whose call is missing stays the bare wrapper
                # name, which is unrecognized and floors — the reconciliation check
                # below would fail on it anyway.
                held = calls.get(call_id)
                name = held[0] if held else _effective_tool(name, {})
                results[call_id] = (name, str(block.get("result", "")), blob_id)
            if not _recognized(name):
                unknown.add(name)

    if unknown:
        # Fail closed. An unrecognized tool may be an ingress tool, and its absence
        # from the corpus is indistinguishable from it never having run.
        return StoreReading(
            verdict=StoreVerdict.UNRECOGNIZED,
            path=path,
            reason=f"unrecognized tool name(s): {', '.join(sorted(unknown))}",
            message_count=len(messages),
        )

    partial = StoreReading(
        path=path,
        verdict=StoreVerdict.INCOMPLETE,
        tool_calls=len(calls),
        tool_results=len(results),
        message_count=len(messages),
        root_blob=root_id,
        root_revisions=revisions,
        prefix_chain_ok=prefix_ok,
        ingress_calls=sum(1 for name, _ in calls.values() if name in EXTERNAL_INGRESS_TOOLS),
    )
    if set(calls) != set(results):
        orphans = len(set(calls) ^ set(results))
        partial.reason = f"{orphans} tool call(s) and result(s) do not reconcile by id"
        return partial
    if not prefix_ok:
        partial.reason = "root revisions are not a prefix chain"
        return partial

    # --- pass 2: emission. Recognition is complete, so this cannot be partial. ---
    partial.results = [
        _ingress(call_id, calls[call_id], results[call_id])
        for call_id in results
        if results[call_id][0] in EXTERNAL_INGRESS_TOOLS
    ]
    partial.verdict = StoreVerdict.VERIFIED
    partial.reason = ""
    return partial


def receipt(reading: StoreReading, session_id: str) -> dict:
    """The derived artifact retained in place of the store — a transform receipt.

    The archive keeps the transcript because "evidence that can disappear is not
    evidence" (`transcripts.retain`). It does not keep `store.db`: the store holds every
    `Read`, `Grep` and `Shell` result too, a far larger and more sensitive surface than
    the transcript, and the archive's posture is scan-and-report-never-redact. So what
    is retained is the ingress texts and the record needed to check we extracted them
    faithfully.

    That record is stronger than a copy, and stronger than in-toto's own default. In
    link metadata the materials are hashed by the functionary — the party under audit —
    so a dishonest functionary can hash whatever it likes. Here the material's *name* is
    `sha256(blob)` under **Cursor's** digest, computed by the counterparty before we
    existed: `source_blob` is the vendor's id for the bytes, `payload_sha256` is ours
    for the text we took out of them. Anyone still holding the store can recompute both
    and check the transform without trusting us at all.

    Selective imaging's §3.4 (arXiv 2012.02573) asks that the *selection* be documented
    beside the acquisition, since a partial acquisition is only defensible if a reader
    can reconstruct what was left and why. `selection` states the rule, and `discarded`
    gives the denominator — what a reader needs to see that 20 of 26 results were
    deliberately not taken rather than missed.
    """
    return {
        "session_id": session_id,
        "verdict": reading.verdict.value,
        "selection": {
            "rule": "external-ingress tool results only",
            "tools": sorted(EXTERNAL_INGRESS_TOOLS),
            "acquired": len(reading.results),
            "discarded": max(0, reading.tool_results - len(reading.results)),
            "tool_results_total": reading.tool_results,
        },
        "store": {
            "root_blob": reading.root_blob,
            "root_revisions": reading.root_revisions,
            "prefix_chain_ok": reading.prefix_chain_ok,
            "message_count": reading.message_count,
            "blob_id_algorithm": "sha256",
        },
        "results": [
            {
                "tool": r.tool,
                "call_id": r.call_id,
                "args": r.args,
                "source_blob": r.source_blob,
                "payload_sha256": r.payload_sha256,
                "framed": r.framed,
                "bytes": len(r.text.encode()),
            }
            for r in reading.results
        ],
    }


def _ingress(call_id: str, call: tuple[str, dict], result: tuple[str, str, str]) -> IngressResult:
    name, args = call
    _, text, blob_id = result
    return IngressResult(
        tool=name,
        call_id=call_id,
        args=args,
        text=text,
        framed=_is_framed(name, args, text),
        source_blob=blob_id,
        payload_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


def _is_framed(tool: str, args: dict, text: str) -> bool:
    """True when the result carries the frame a *successful* fetch/search writes."""
    if tool == "WebFetch":
        url = args.get("url")
        return isinstance(url, str) and text.startswith(f"# Content from {url}\n\n")
    if tool == "WebSearch":
        return text.startswith(_WEBSEARCH_FRAME)
    return False


def _load(path: Path) -> tuple[dict[str, bytes], dict]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        blobs = {
            (bid if isinstance(bid, str) else bid.hex()): (
                data if isinstance(data, (bytes, bytearray)) else str(data).encode()
            )
            for bid, data in con.execute("SELECT id, data FROM blobs")
        }
        rows = list(con.execute("SELECT key, value FROM meta"))
    finally:
        con.close()
    return blobs, _meta(rows)


def _meta(rows: list) -> dict:
    """`meta.value` is hex-encoded JSON. Nothing documents that; it is measured."""
    for _key, value in rows:
        raw = value if isinstance(value, str) else str(value)
        try:
            decoded = json.loads(bytes.fromhex(raw))
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(decoded, dict):
            return decoded
    return {}


def _root_id(meta: dict) -> str:
    root = meta.get("latestRootBlobId")
    if not isinstance(root, str) or not root:
        raise StoreUnrecognized("meta carries no latestRootBlobId")
    return root


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if i >= len(buf):
            raise StoreUnrecognized("varint runs past end of blob")
        byte = buf[i]
        result |= (byte & 0x7F) << shift
        i += 1
        shift += 7
        if not byte & 0x80:
            return result, i


def _field1_refs(buf: bytes) -> list[str]:
    """The root's message ids, in order.

    Walks protobuf keys properly. It does not scan for the *byte shape* of a
    length-delimited field-1 entry: that reader exists, it was written for this store,
    and it reported a reference that was really a window straddling a field boundary —
    four bytes early, swallowing the key of a neighbouring hash. It found a dangling
    reference that was not there and said nothing was wrong.

    Every surprise raises. A field-1 entry of an unexpected length or an unhandled
    wiretype means the shape assumed here is wrong, and returning a short list that
    looks complete is precisely the failure this module exists to avoid.
    """
    refs: list[str] = []
    i = 0
    while i < len(buf):
        key, i = _varint(buf, i)
        field_no, wire = key >> 3, key & 7
        if wire == 0:
            _, i = _varint(buf, i)
        elif wire == 2:
            length, i = _varint(buf, i)
            if i + length > len(buf):
                raise StoreUnrecognized("length-delimited field runs past end of blob")
            if field_no == 1:
                if length != 32:
                    raise StoreUnrecognized(f"field 1 is {length} bytes, expected 32")
                refs.append(buf[i : i + length].hex())
            i += length
        elif wire == 5:
            i += 4
        elif wire == 1:
            i += 8
        else:
            raise StoreUnrecognized(f"unhandled protobuf wiretype {wire}")
    return refs


def _message(blob: bytes) -> list[dict]:
    """A message blob's content blocks. Anything that is not one raises."""
    try:
        decoded = json.loads(blob)
    except (ValueError, json.JSONDecodeError) as exc:
        raise StoreUnrecognized(f"message blob is not JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise StoreUnrecognized("message blob is not an object")
    content = decoded.get("content")
    if content is None:
        return []
    # Two forms occur, both legitimate: plain prose as a bare string (every `system`
    # message and some `user` ones), or a list of typed blocks. A string carries no
    # tool blocks, so it contributes nothing here — but it is recognized rather than
    # tolerated, and a third form still raises.
    if isinstance(content, str):
        return []
    if not isinstance(content, list):
        raise StoreUnrecognized(f"message content is {type(content).__name__}")
    return [block for block in content if isinstance(block, dict)]


def _root_revisions(blobs: dict[str, bytes], latest: list[str]) -> tuple[int, bool]:
    """Count earlier roots and check they form a prefix chain.

    The store keeps every root it has ever written, one per append, and each
    revision's message list is a strict prefix of the next — measured 10/10 stores over
    52 revisions. That is RFC 6962's consistency-proof shape sitting in the
    vendor's own data, so this reads it rather than building one.

    What it catches follows from the structure rather than from a measurement: an
    interior deletion or a reorder breaks the prefix relation against every later
    revision. Tail truncation does not — a shortened list is still a valid prefix,
    indistinguishable from an earlier honest state — which is why reconciling calls
    against results stays load-bearing beside this.
    """
    chains: list[list[str]] = []
    for blob in blobs.values():
        if blob[:1] in (b"{", b"["):
            continue
        try:
            refs = _field1_refs(blob)
        except StoreUnrecognized:
            # Not every non-JSON blob has to be a root; only ones that parse count.
            continue
        if refs and all(ref in blobs for ref in refs):
            chains.append(refs)
    chains.sort(key=len)
    consistent = all(
        chains[i] == chains[i + 1][: len(chains[i])] for i in range(len(chains) - 1)
    )
    if chains and chains[-1] != latest:
        consistent = False
    return max(0, len(chains) - 1), consistent
