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

## What the grounding pass added

Run before the build this time. Four of its findings were already handled by the
time it returned — the `render_digest` double-coupling (it re-parses the archived
bytes in the Claude Code dialect, and is the half the model actually sees), the
anchor problem, the ingress trust decision, and reusing `tests/test_cursor_hooks.py`'s
conformance shape. Three landed.

**It refuted a novelty claim before one was made.** "One intermediate, many
harness dialects" is published: HarnessFix's harness-aware Trace Intermediate
Representation (arXiv 2606.06324) and the Agent Data Protocol's interlingua over
thirteen datasets (arXiv 2510.24702). Both measure downstream gains and **neither
measures IR fidelity**, so they are cited for the pattern, not the schema. Also
settled: targeting OpenTelemetry GenAI conventions instead is the wrong move on
documented grounds rather than effort — Development status, no released schema
URL, no reasoning content part, and Claude Code's own OTel export redacts
extended thinking and truncates tool content, so routing through it would *lower*
the evidence floor docs/10 exists to raise. docs/11 §4 now records the refutation.

**It found a defect in what had shipped: the parser was silently tolerant.**
Malformed lines, unknown roles and unusable content were skipped without a sound,
so a Cursor format change would have degraded to "that session had fewer turns" —
the silent-failure mode this repo keeps rediscovering. RFC 9413's virtuous
intolerance and LangSec (Momot et al., IEEE SecDev 2016) both reject Postel's law
outside pre-declared extension points. Fixed: `TranscriptFacts.unrecognized`
counts what the grammar could not classify and the sweep prints it. Content
*blocks* stay the one tolerated extension point — Cursor may add block types
without changing the record grammar — so an unknown block does not condemn its
record, and a test pins that asymmetry.

**It named the premise this whole adapter rests on, which is unverified.**
`transcript_path` is assumed to resolve to JSONL. Cursor also keeps chat state in
SQLite (`state.vscdb`, `cursorDiskKV`, community-reverse-engineered and not
vendor-documented), and the sessionEnd ledger has been recording whatever the hook
was handed. The premise was not verifiable here, so what was verified instead is
the **failure mode**: handed a `state.vscdb`, the parser yields zero turns and a
non-zero unrecognized count, so the session is skipped *and* the mismatch is
reported. Nothing half-parses. A missing path is dropped at discovery. Both are
now tests, and they are the most valuable ones in the file — they hold whatever
the premise turns out to be.

Absence handling picked up a vocabulary rather than inventing one: FHIR's
`dataAbsentReason` three-way split — `not-applicable` / `unknown` / `unsupported`
— puts Cursor's missing tool results squarely at `unsupported`, a value that
exists in a format that cannot carry it. Rubin's MCAR/MAR/MNAR is explicitly not
the frame, since every category presupposes a latent value that could have been
observed. Information-capacity theory (Miller et al., VLDB 1993) argues for a
*static per-format capability table* over a per-record manifest, which is what
`ingress_verifiable` already is.

One deferred item worth its own thread: **the cheapest publishable measurement in
this area is sitting in our own archive.** Nobody has measured extraction quality
as a function of which trace *fields* are present — every held ablation varies
modality, volume or representation instead. Re-running the existing extractor over
archived Claude Code transcripts with `tool_use_id` linkage stripped, and diffing
the claims, would answer directly how much the Cursor gap costs. We hold the
corpus.

## Each harness distills through its own agent

Extraction shelled out to `claude -p` unconditionally, which meant a Cursor-only
work machine still needed Claude Code installed and authenticated before any of
its sessions could become memory — a cross-tool dependency nobody asked for, and
one that also sent that machine's session digests to a vendor the operator had not
chosen for it.

Cursor's CLI is a drop-in for the purpose. Binary `agent`, same `-p`, `--model`
and `--output-format json`, and an envelope carrying `result`, `is_error` and
`duration_ms` under those exact names — so `EXTRACTION_CLIS` models only what
actually differs: binary, default model, and whether the envelope prices the call.
Default is Composer 2.5, non-fast, on the batch argument: a distillation sweep has
nothing waiting on it, so the quality/latency trade runs opposite to interactive
use.

Two things the port had to be honest about:

- **Cursor reports no cost or token fields at all.** `cost_usd` became
  `float | None`, and the sweep counts unpriced runs separately rather than adding
  0.0. This is the same absent-vs-negative trap as the ingress floor two sections
  up, found in a second place within the same component — a zero that means "not
  reported" is indistinguishable from one that means "free", and it would have
  quietly under-reported the extraction spend `eval cost` exists to total.
- **The Composer identifier is a guess.** Cursor documents `--model` and
  `--list-models` but publishes no identifier strings, and Composer 2.5 has no
  public API model id — it is Cursor-platform-only. A wrong string fails at
  invocation rather than silently selecting another model, and the error message
  carries `agent --list-models`, so the failure comes with its own fix. Verifying
  it is one command on a machine that has Cursor.

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
