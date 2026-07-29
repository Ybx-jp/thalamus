# 028 — The transcript that keeps no receipts: Cursor distills, and the trust floor had to be told

**Date:** 2026-07-29 · **Component:** harness (`cursor_transcripts.py`, extraction ingress floor) · **Status:** built, contract-tested against documentation; still no live-Cursor validation

## What broke

lab/010's wall 2: `thalamus extract` parsed Claude Code JSONL only, so Cursor
sessions retrieved, traced and were conditioned but left no episodic memory. This
entry is the adapter that closes it — and the trust-model defect that building it
exposed.

## What Cursor's transcript actually contains

Cursor publishes no schema. The shape below is what its staff and users describe
(forum threads 157311 and 166592, the latter confirmed by Cursor staff, read
2026-07-29):

    {"role": "user", "message": {"content": [{"type": "text", "text": "..."}]}}

- top level: `role` and `message`, **no timestamps, no `type` control rows**
- `message`: `content` only — no `id`, no `usage`, no model
- blocks: `text` and `tool_use` only; `tool_use` has `type`/`name`/`input`, **no `id`**
- **`tool_result` blocks absent entirely** — Cursor excludes tool outputs on
  purpose, because they can be very large. Extended thinking arrives `[REDACTED]`.

Tool *inputs* surviving is the load-bearing good news: the deterministic TOUCHES
layer — which files a session edited, in which messages — crosses intact, which is
most of what the no-model stage exists to produce.

## The defect: an absence that could not be told from a negative

docs/05's ingress floor has four layers. Layer 1 collects the verbatim text of
`WebFetch`/`WebSearch` *results*; layer 3 forces any claim echoing that text to
tier-2 **regardless of the model's mark**, and is explicitly the layer no prompt
content can lift. Layer 2 — the extractor's own `external: true` marks — is the
one docs/05 says not to trust, because a poisoned page can argue the model out of
marking.

Cursor transcripts carry no tool results for any tool. So `external_texts` is
always empty, and `apply_ingress_floor` opened with:

```python
if not external_texts and not any(c.external for c in graph.claims()):
    return graph
```

A naive adapter would therefore have distilled every Cursor session with layers 1
and 3 silently inert, leaving only the layer designed not to be trusted — while
the code path reported success. The failure is not that a defence is missing; it
is that **an empty list meant "nothing was fetched" in one harness and "we cannot
know" in the other**, and nothing distinguished them.

Fix: `TranscriptFacts` carries `ingress_verifiable`, and when false the floor
**floors the whole session** — every claim external, stamped
`transcript-ingress-unverifiable` rather than `transcript-ingress` so the two
remain separable in the graph afterwards. Ingress tool calls are still counted
(`ingress_detected`) because their inputs survive: we can see a session fetched,
just not what came back.

Heavy-handed on purpose. It takes the trade the floor already prices — first-party
memory rendering as tier 2 informs, and costs nothing but emphasis — at the one
moment the cheap mechanical check is unavailable. It also puts the incentive in
the right place: capturing tool outputs out-of-band becomes the way to earn tier-1
back, rather than something to remember to do.

## Two smaller gaps, both carried rather than inferred

- **No message ids**, so Touch anchors are positional: `cursor:msg:<row>`,
  namespaced so a synthesized anchor can never pass for a real UUID. The archived
  transcript is the retained bytes, so a row index still addresses it.
- **No timestamps, no cwd.** Both come from our own ledgers — `pins.jsonl` for the
  start and workspace, the sessionEnd log for the end. The hooks shipping nine
  days before the adapter is what makes backfilling everything logged since
  possible at all; the `distilled: false` pointer was written for exactly this.

## Why extraction is a sweep, not a sessionEnd action

Cursor is not documented to flush the transcript before firing `sessionEnd` — an
open request asks it to fsync first or add a `transcript_ready` field, and Cursor
staff answered "no implementation timeline yet". Distilling inline would race an
async writer and silently distill a truncated session, which is a corrupted memory
rather than a missing one. The sweep sidesteps the race entirely and costs only
latency.

## One change to the primary harness

`render_digest` discriminated rows on `type`, which Cursor rows do not have, and
rendered user text only from bare-string content, which is not how Cursor writes
prompts. Both fixed by falling back to `role` and rendering user `text` blocks —
so one renderer serves both dialects. A regression test pins that Claude Code
digests are byte-identical, because a silent change there would alter every future
extraction on the primary harness.

## Wall or workaround

**Workaround**, and lab/010's last structural wall is down — Cursor sessions now
distill, at honestly-reduced fidelity rather than pretended parity.

The standing caveat is unchanged and now carries more weight than before: this
parser has never seen a real Cursor transcript. The tests split deliberately into
assertions about what we *believe* Cursor emits (revisable) and assertions about
how the adapter behaves when the format disappoints it — unknown blocks, missing
fields, malformed lines, bare strings — which hold regardless. That second half is
the part worth trusting until a live session arrives.

**Next:** the `postToolUse` ingress capture that would restore tier-1 eligibility.
The mechanism exists; the blocker is that Cursor's built-in web-tool names are
undocumented and unobserved, so the ingress set would be a guess — and a guess
that misses is the silent-weakening failure this entry is about. One live session
settles it.
