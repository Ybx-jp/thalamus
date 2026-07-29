# 025 — The expert you don't spawn, and the component you already had

**Date:** 2026-07-28 · **Component:** consultation protocol, exchange record,
literature scope · **Status:** four measurements, all from one design session that
went wrong twice and was corrected both times by the operator rather than by the
loop.

Grounding consultations: exchange `scope:main:exchange:65ecf89959c5445b` (self-answered,
8 citations) and `scope:main:exchange:34578b4b214941b4` (subagent-voiced, 25 citations)
— the same question, asked twice, which is what makes §1 a measurement rather than an
anecdote.

---

## §1 — Self-answering a consultation ticket costs the answer

The consultation protocol (docs/02) says to spawn a subagent voicing the expert. A
session-level constraint discouraged spawning agents unprompted, so the first
consultation was run **inline**: the asking session recalled under its own ticket and
filed its own answer. The citation gate passed. The record looked normal.

Re-run properly after the operator challenged the constraint, same question verbatim:

| | inline (`65ecf899`) | subagent-voiced (`34578b4b`) |
|---|---|---|
| Validated citations | 8 | **25** |
| Recall calls | 4 | 19 tool uses |
| Anchors surfaced | GraphRAG, RAPTOR, Always-OnAgents | + **BudgetMem**, MemoryBank, KnowU-Bench, Self-RAG |
| Effect on the design | confirmed it | **withdrew it** |

The inline run missed **BudgetMem (arXiv 2602.06025)**, which was already in the scope
and which argues that offline, query-agnostic memory construction discards
query-critical information — the direct objection to the design being written. It was
four recalls away and the design shipped to `docs/` without it.

The mechanism is not laziness. The asking session recalls *toward its own hypothesis*:
it queries the terms its design already uses, reads confirmation, and stops. A subagent
given the question and no design to defend queries the space instead. The disposable
context is not just a cost optimization — **it is the independence**, and
`recall-strategy` L4 already said so in a sentence that did not survive contact with a
plausible-looking reason to skip it.

Second-order: the inline answer also **overclaimed**. It wrote that adopting community
detection here "would be cargo-culting the mechanism past its motivating condition,"
which reads as grounded and is not — the scope holds no measurement of either method on
a small corpus. The voiced expert flagged exactly this about its own reasoning ("this is
my reading of the cited claim's logic, not something the paper measures"). An expert
with no design at stake polices the strength of its own claims; an author defending one
does not.

## §2 — The exchange record could not tell the two apart

Both exchanges are byte-identical in shape: `answer`, `status`, `answered_at`,
validated `REFERENCES {role: citation}` edges. The citation gate proves an answer rests
on the expert's own memory. It proves nothing about **who assembled it**, so "the expert
said so" and "I said so under a ticket" were indistinguishable in the graph — and §1
says that difference is worth 17 citations and a withdrawn design.

Measured while looking for a signal: **a subagent shares its parent's `session_id`**, so
neither the MCP server (which cannot see its caller at all, lab/001) nor the trace tap
could separate them. The hook payload *does* carry `agent_id` and `agent_type`; the tap
was discarding both.

| call | `agent_id` | `agent_type` |
|---|---|---|
| main loop | *(empty)* | *(empty)* |
| probe subagent | `a2d8a918…` | `general-purpose` |
| voiced expert | `a8ab4240…` | `thalamus-literature` |

The tap now keeps them and `eval sync` stamps `answered_from` on the Exchange —
`voiced` / `self` / `agent:<type>` / `unknown`. Absent stays distinct from empty: a
pre-tap trace records no fact about who answered, and folding that into `self` would
manufacture provenance.

## §3 — The design already existed, in two places

The withdrawn design was a precomputed per-document "contribution to scope" summary
layer. Two things already answered it:

1. The teach workspace's literature map has carried a per-paper `position` field —
   *"what it shows / where we stand"* — since 2026-07-18. Fifty-eight of them.
2. The graph answers it at **runtime, in earned terms**: an `Exchange` holds the
   question, its citation edges hold the claims the answer rested on, so a `Source`
   walks out to the questions it was actually cited to answer. Verbatim, no
   summarization step. Query in the `recall-strategy` skill.

That is better evidence than any precomputed summary, because it records what a paper
was *used for* rather than what someone anticipated at ingest — which is BudgetMem's
point, arrived at from the other direction.

**The general failure:** `ground-in-literature` gates designs on *external* prior art
and has no step for internal prior art. A component was designed, cited, consulted on,
committed and documented before anyone asked whether the system already did it. The
literature check fired correctly and still could not catch this, because it was pointed
outward.

## §4 — Cold sources make the lane violation visible

Counting sources with no exchange attribution at all: **10 of 37** in the `literature`
scope. Some are another project's feed. But `arXiv:2605.17830` is among them — the paper
whose readiness run recorded that it *changed the design in three places*.

Zero exchanges, three design changes. It entered through a briefing aside instead of a
consultation ticket, so it changed the design and left no citation trail. The lane
violation found in the ledger this morning is independently visible in the graph as a
hole in attribution, which makes **cold-source count a two-population metric**:
literature nobody has needed yet, and literature that reached a design through a channel
that leaves no record. Separable by asking whether any decision cites the paper.

## What changed

- `ground-in-literature`: an internal prior-art step before the external one; the
  self-answering prohibition with §1's numbers; a claim-strength rule.
- `recall-strategy`: L4 sharpened — the disposable context is the independence.
- Tap keeps `agent_id`/`agent_type`; `eval sync` stamps `answered_from` (§2).
- Contribution layer withdrawn (docs/02, docs/11 §3e, decision log).

## Open

- `answered_from` is **not yet verified live** — this session is undistilled, so its
  traces are pending and the first stamp lands on the next sync.
- Cold-source count is a hand-run traversal, not a reported metric.
- Both corrections in this session came from the operator, not from the loop. The
  readiness advisor cannot catch design capture it is downstream of, and nothing else
  was watching.
