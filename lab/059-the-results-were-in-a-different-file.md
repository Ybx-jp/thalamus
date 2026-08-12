# 059 — The results were in a different file

**Date:** 2026-08-11 · **Harness:** Cursor CLI `2026.08.04-aaa8809`, 6 sessions on one
box · **Verdict:** wall closed, plus a withdrawal

Two things about Cursor's on-disk stores, one closed and one overturned. Both were
settled by opening a file nobody had opened.

## The wall that closed

lab/054 ended on an asymmetry: Claude Code discovers sessions by globbing the
filesystem, Cursor by reading our own sessionEnd hook log, so a Cursor session that
ran before the hooks existed was undiscoverable while its transcript sat at a
perfectly globbable path — **lost by policy rather than by format**, on exactly the
machine Thalamus arrives at late.

`discover()` now reads both surfaces and merges them per-field. The rule is
**PerRule** in TOKI's taxonomy (arXiv 2606.06240) rather than last-writer-wins: the
hook row supplies `scope`, because it is the only surface that can know a routing
decision a hook made, and the filesystem supplies existence and `cwd`. LWW across the
whole record would let an unresolved scope overwrite a resolved one. Provenance
semirings (Green, Karvounarakis & Tannen, PODS 2007) were the framing proposed and
were declined for the field-level half: the construction is conditional on positive
relational algebra, a preference rule between disagreeing records is not in that
algebra, and the semiring never ranks its sources — which is the whole content of the
rule. For the *set* of surfaces that saw a session it fits exactly, and there it
reduces to set union.

Measured on this box: 6 transcripts on disk, 2 extraction sandboxes refused, 4 real
sessions, of which the hook log had ever seen **2**.

A globbed session has no scope and **does not get `main`**. Scope is part of the
vertex ID, so defaulting an unattested session into the operator's own subgraph is an
unmade routing decision that cannot be walked back; `--assign-scope` claims them, on
both `extract` and `bootstrap`. This is `not-asked` in FHIR R4's `DataAbsentReason`
("the workflow didn't lead to this value being known"), which is a different code from
the `unsupported` this adapter already records for fields the format cannot carry.
Hand-feeding that value set also corrected the repo's description of it: it is **15
concepts in a two-level hierarchy**, Normative since R4, not the three-way split named
in `cursor_transcripts.py`.

Stage 1 reached Cursor in the same change. `bootstrap.py` had named one reader module
in three places (`parse`, `retain`, `to_session_graph`) — an abstraction gap, not a
wall: both readers already emit one `TranscriptFacts`, `retain` is harness-agnostic,
and Cursor's builder delegates to Claude Code's. The one real asymmetry is that
`cursor_transcripts.parse` must be *handed* cwd and times, which discovery now
carries.

## The confirmation that did not hold

lab/054 recorded, under "confirmed rather than overturned":

> **`tool_result` blocks are absent for every tool.** A live tool-use probe recorded
> the `tool_use` block with its full `input` and then jumped straight to the
> assistant's final text. The ingress floor's reasoning stands exactly as docs/05
> states it.

The observation was right and the conclusion drawn from it was too broad. Tool results
**are** persisted — in `~/.cursor/chats/<hash>/<session-id>/store.db`, a SQLite
content-addressed blob store, as plain JSON:

```json
{"role":"tool","content":[{"type":"tool-result","toolCallId":"tool_d73008ed…",
  "toolName":"Shell","result":"Exit code: 0\n\nCommand output:\n\n```\ncanary-content-9f3a\n```…"}],
 "providerOptions":{"cursor":{"highLevelToolCallResult":{"output":{"success":{
   "command":"cat …/probe-target.txt","stdout":"canary-content-9f3a\n"}},"isError":false}}}}
```

Measured across all 6 sessions: tool-result blobs 10, 9, 1, 0, 0, 0, and the three
zeros are the sessions that made no tool calls. Result text, `toolName`, `isError` and
the echoed input all present; for `Shell`, `stdout` and the exit code.

**Why the confirmation held anyway.** The probe read the *transcript*, which is the
file the adapter parses and the only file anyone had reason to open. "Cursor excludes
tool outputs from transcripts" is Cursor staff's own statement (forum thread 157311)
and it is true — of the transcript. Restating it as "Cursor does not record tool
outputs" is a claim about the product that the evidence never supported, and it
arrived carrying a citation. This is the same shape lab/054 diagnosed in its own five
wrong declarations: *nothing ever asked a second time.*

**What it costs.** docs/05 floors every Cursor session whole on the stated grounds
that the ingress floor's evidence does not exist. The evidence exists. That does not
by itself lift the floor — three things stand between:

- The archive retains the JSONL and not `store.db`, so the provenance chain does not
  reach these bytes. Lifting the floor means retaining a second file per session.
- `meta` carries a `blobEncryptionKey`. Every blob read here was plaintext; the
  conditions under which it is not are unknown. *(Inference from the field's presence,
  not a measurement.)*
- `store.db` is undocumented and private — a weaker dependency than the JSONL, which
  at least has staff confirmation behind its shape.

Joining results to calls is possible but not by id: JSONL `tool_use` blocks carry
`input`, `name`, `type` and nothing else (re-confirmed). The store's blobs appear in
the same order as the calls **and** echo the call's input, so a join can be
corroborated on (name, input) rather than assumed from position.

## Scope of these measurements

6 sessions, one machine, one CLI version, and 4 of the 6 were Thalamus's own test and
extraction runs. The counts above are exact for that set and are not a sample of
anything wider. What generalizes is the structural fact — there is a second store, and
it holds what the transcript drops.
