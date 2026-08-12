# 060 — The caveats were artifacts of the other file

**Date:** 2026-08-11 · **Harness:** Cursor CLI `2026.08.04-aaa8809`, 11 session dirs on
one box (10 with a store), 4 of them probes run tonight · **Verdict:** measurements,
three withdrawals from lab/059, and one from this entry's own first pass

lab/059 opened `store.db` and found the tool results. It then described them from the
outside — reasoning about the store's shape from the JSONL transcript it already knew,
because that is the file the adapter parses. Three of its four caveats are artifacts of
that vantage point and do not survive reading the store on its own terms. The fourth is
real and is the whole remaining problem.

## What the store actually is

`~/.cursor/chats/<hash>/<session-id>/store.db`, SQLite, two tables: `blobs(id, data)`
and `meta(key, value)`.

`meta` has a single row under key `'0'` whose value is **hex-encoded JSON**:

```json
{"agentId":"010556c9-…","latestRootBlobId":"2e9d3be0…","name":"New Agent",
 "mode":"default","isRunEverything":false,"createdAt":1786398926686,
 "blobEncryptionKey":"9aa7fd0c…"}
```

`latestRootBlobId` addresses a blob that is **protobuf**, not JSON — repeated field 1
(`0a20`), each entry a 32-byte blob id. Those ids are the session's messages **in
order**. The remaining blobs are earlier revisions of that same root, one per append,
which is why a 19-message session holds 62 blobs.

So the store is a content-addressed log with an explicit index. Message blobs are
plaintext JSON; the non-JSON blobs are structure.

## The three withdrawals

**1. "Joining results to calls is possible but not by id."** Withdrawn. The store holds
*both* sides — the assistant's `tool-call` record and the `tool` role's `tool-result` —
and both carry the same `toolCallId`:

```json
{"type":"tool-call","toolCallId":"tool_d9a92139-…","toolName":"WebFetch",
 "args":{"url":"https://example.com"}}
{"type":"tool-result","toolCallId":"tool_d9a92139-…","toolName":"WebFetch",
 "result":"# Content from https://example.com\n\nExample Domain\n…"}
```

Across all 10 stores: **26 tool-calls, 26 tool-results, 26 paired by id — 100%.** The
JSONL is not needed for the join at all. lab/059's "no shared id" was true of the
JSONL's `tool_use` blocks, which is where it was looking.

**2. "The store's blobs appear in the same order as the calls."** Withdrawn as an
assumption; the ordering is explicit, not positional. The root index gives the message
sequence directly, so nothing needs to rely on SQLite row order.

**3. "Every blob read here was plaintext; the conditions under which it is not are
unknown."** Narrowed. Only about a third of blobs are JSON. The rest are not encrypted
content — they are root-index revisions, structurally protobuf. `blobEncryptionKey` is
present in **10/10** stores and nothing in any of them is encrypted; the key also sits in
plaintext in `meta`, beside the data it would encrypt. The inference that its presence
implied possible ciphertext is unsupported on this box.

## The measurement lab/059 could not have made

**No Cursor session on this box had ever run a web tool.** Observed tool names across
the six pre-existing sessions: `Glob`, `Grep`, `Read`, `Shell`. The ingress floor cares
about exactly one class of tool, and that class had zero observations — so "the evidence
exists" was still a claim about the wrong tools.

Four live probes closed it. Cursor's ingress tools carry **the same names as Claude
Code's**:

| tool | args | result retained |
|---|---|---|
| `WebFetch` | `{url}` | full fetched page text, verbatim, plaintext |
| `WebSearch` | `{search_term, explanation}` | result list with titles and links |

so `EXTERNAL_INGRESS_TOOLS = frozenset({"WebFetch", "WebSearch"})` transfers to Cursor
as written, measured rather than assumed.

A rejected fetch is also recorded, as `"result":"Web fetch rejected: User Rejected"` —
the refusal is evidence too, and distinguishable from a fetch that returned nothing.

**Non-interactive runs reject by default.** `cursor-agent -p` denies tool approvals
unless `--force` is passed; the first probe's `WebFetch` was rejected twice and the
model answered from parametric knowledge instead, which is a clean illustration of why
the floor exists but not the measurement being sought.

## The parser differential, observed between two of our own readers

The scanner that produced the first pass of this entry found the root's refs by
regex — `\x0a\x20` followed by 32 bytes, keying on the *shape* of a protobuf
length-delimited field-1 entry. It reported a **dangling reference** in `a6681e9d`:
9 refs, 8 resolvable.

There is no dangling reference. A reader that walks varint keys properly finds **8
field-1 refs, 8 resolvable**, and 8 JSON message blobs — no ninth message exists for a
ninth ref to point at. The phantom was a frame-shifted window straddling a field
boundary:

```
scanner's 9th "ref"  e31a4220 1d682844c0c70597…db740764
real field-8 hash             1d682844c0c70597…1ac67556
```

The scanner's window begins four bytes early, swallowing `e3 1a 42 20` — where `42 20`
is itself the key for *field 8, wiretype 2, length 32* — and truncating the real hash
by four bytes at the tail. Field 8 carries a genuine 32-byte hash that resolves in
10/10 stores.

**The differential is the finding.** Two readers, the same 718 bytes, no vendor change,
and both reported success in their own terms — one of them holding a hash that names no
blob. This is what the failure mode actually looks like, and it is not the one that was
anticipated: not *empty* results read as nothing-fetched, but *partial* ones.

With a correct parser, across 10 stores: **82/82 refs resolve, 26/26 tool calls pair
with results, and `blob id == sha256(data)` on 264/264 blobs** — sha1, md5 and blake2b
all 0/264. The store is content-addressed under the vendor's own digest, so a derived
artifact can carry a commitment to the original that anyone holding the store can
recheck without trusting whoever derived it.

Unexplained: **one of 11 session directories has no `store.db` at all.** The store is
not guaranteed per session.

## The experiment that separates the two predicates

Copy a store, delete one ingress `tool-result` blob, leave its root ref and its
`tool-call` in place, and read it back. Two candidate predicates for
`ingress_verifiable`:

- **full lift** — `external_texts` is non-empty
- **conditional** — every root ref resolves *and* ingress calls reconcile with results

On a session with **one** ingress call the tamper is caught by both, because deleting
the only result empties `external_texts`. It takes **two** calls to separate them:

| | refs | unresolvable | ingress calls | results | `external_texts` | full lift | conditional |
|---|---|---|---|---|---|---|---|
| baseline | 8 | 0 | 2 | 2 | 2 (1,178 chars) | `True` | `True` |
| one result deleted | 8 | 1 | 2 | **1** | 1 (825 chars) | **`True`** | `False` |

Under full lift the floor runs `_echoes` against a corpus **missing an entire fetched
page** and reports success; every claim derived from that page keeps tier 1. Non-empty
is not complete, and full lift has no predicate that can tell the difference.

The conditional predicate holds on **10/10** untampered stores, so on this corpus the
two produce identical output and the conditional costs nothing.

## The store keeps its own consistency proof

The prior root revisions are not dead weight. Each root's message list is a **strict
prefix** of the next — measured across **10/10 stores and 52 prior revisions**. That is
RFC 6962's consistency-proof shape, already present in the vendor's own data, so the
check is *read it*, not *build it*.

What that buys, and does not, follows from the structure rather than from a
measurement: an interior deletion or a reorder breaks the prefix relation against every
later root and is caught, while **truncating the tail is not** — a shortened list is
still a valid prefix, indistinguishable from an earlier honest state. Tail truncation is
exactly the shape of "the last fetch is missing", so the prefix chain does not on its
own replace reconciling calls against results.

## `external_texts` is not two-valued, and the discriminator is the frame

Of 26 tool results, 6 are ingress. Four carry fetched content; **two carry vendor prose
in the same field** — `"result": "Web fetch rejected: User Rejected"`.

| class | count |
|---|---|
| ingress, content | 4 |
| ingress, refused | 2 |
| local (`Glob` 8, `Grep` 6, `Read` 5, `Shell` 1) | 20 |

A discriminator exists, and it is not the prose. A successful result is **framed, and
the frame binds to the call**:

| tool | frame |
|---|---|
| `WebFetch` | `"# Content from " + args.url + "\n\n"` then the payload |
| `WebSearch` | `"Title: Web search results\nContent: "` |

Refusals carry no frame. Classifying on frame-prefix: **6/6 correct.**

**The polarity is the whole point.** A rule that matched the refusal *text* would be an
attacker-controlled channel in the lifting direction — a fetched page whose body opens
with `Web fetch rejected: User Rejected` would be discarded from the corpus, removing
the very evidence a claim should have been judged against. Matching the frame inverts
that: the attacker would have to forge a prefix containing `args.url`, which is our
record of our own call, not theirs.

## The caveat that stands

The archive retains the JSONL and not the store, so the provenance chain does not reach
these bytes. That is the real work, and it is not a measurement problem.

## Reproduction

Walk varint keys. Do **not** key on byte shape — that is the differential above.

```python
import sqlite3, json, glob, os

def varint(b, i):
    r = s = 0
    while True:
        x = b[i]; r |= (x & 0x7f) << s; i += 1; s += 7
        if not (x & 0x80): return r, i

def f1refs(b):                      # the message ids, in order
    i, out = 0, []
    while i < len(b):
        k, i = varint(b, i); fn, wt = k >> 3, k & 7
        if wt == 0:   _, i = varint(b, i)
        elif wt == 2:
            ln, i = varint(b, i)
            if fn == 1:
                # Refuse, don't skip: a field-1 entry of another length means the
                # shape assumed here is wrong, and skipping it returns a short list
                # that looks complete. Lengths other than 32 DO occur elsewhere in
                # the blob population — 40 distinct ones on this box.
                if ln != 32: raise ValueError(f"field 1 length {ln}, expected 32")
                out.append(b[i:i+ln].hex())
            i += ln
        elif wt == 5: i += 4
        elif wt == 1: i += 8
        else: raise ValueError(f"unhandled wiretype {wt}")   # never `break`
    return out

for p in sorted(glob.glob(os.path.expanduser("~/.cursor/chats/*/*/store.db"))):
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    blobs = {b: d for b, d in con.execute("SELECT id, data FROM blobs")}
    meta = json.loads(bytes.fromhex(con.execute("SELECT value FROM meta").fetchone()[0]))
    for r in f1refs(blobs[meta["latestRootBlobId"]]):
        if r not in blobs:
            print("DANGLING", r[:12]); continue
        try: msg = json.loads(blobs[r])
        except Exception: continue
        for blk in msg.get("content") or []:
            if isinstance(blk, dict) and blk.get("type") in ("tool-call", "tool-result"):
                print(blk["type"], blk.get("toolName"), blk.get("toolCallId"))
```

## Scope of these measurements

One machine, one CLI version, 10 stores, 26 tool calls, 6 of them ingress. Six sessions
are Thalamus's own test and extraction runs and four are probes written to produce these
exact rows. The counts are exact for that set and are a sample of nothing wider.

What generalizes is structural: the store has an explicit index, the id join is exact,
blob ids are `sha256` of their contents, and a reader can be wrong about all of it while
reporting success.
