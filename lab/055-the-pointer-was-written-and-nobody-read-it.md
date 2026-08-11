# 055 — The pointer was written three times and nobody read it

**Date:** 2026-08-10 · **Verdict:** retrieval caps, read as completeness — not a capture
failure of any kind

A three-round architect consultation designed a five-state harness capability contract.
The next session opened the same question, ran three more rounds, and re-derived it. The
attractive explanation — that a design which changes no file leaves no trace — is wrong,
and so is the weaker version, that the conclusion survived but the reasoning did not.
The design was captured **redundantly**, on three separate surfaces, and every read that
should have found it was capped.

## What was captured, and where

**A Thread, still open.** `scope:main:thread:harness-capability-negotiation-contract-unbuilt`:

> **title:** Build the full five-state capability-negotiation contract designed with the
> architect
>
> **description:** Three consultation rounds with the architect produced a design for a
> declarative capability contract (`contract/capabilities.py`, dotted keyspace, five
> states including UNKNOWN, `Evidence{kind,at,where,probe}`, a non-negotiable floor.\*
> set, `Requirement.mode='provider'` for provider-selected capabilities). Only the
> detection layer (sentinel flag probes + DERIVED rows in probes.py) was actually built
> this session; the declarative schema itself remains unbuilt.

That is the design, in a thread title and description, on the recall surface.

**A Claim**, on session `dcf15078`: *"Chose 'detection first, contract second': build
sentinel flag probes and DERIVED declaration rows before building the full five-state
capability-negotiation contract (`contract/capabilities.py`, `Requirement`/`Evidence`
model)."*

**The Exchange bodies**, 33,823 and 32,468 characters, holding the reasoning.

## Why three reads missed three records

**`memory_open_threads` returned 15 of 325.** The graph holds 259 `open` and 66
`in_progress` main-scope threads. The call passed `limit=15` and got fifteen
`in_progress` rows; the capability thread is `open` and did not appear. Nothing was
hidden — a page was requested and a page was returned. The reader supplied the
completeness.

**`memory_recall` capped claims at eight** and said so: *"22 more claim(s) in this
session: 13 matched but exceeded the 8-claim render cap"*, printing the remedy in the
same breath. The pointer claim was among the thirteen.

**`ground-in-literature` A0 searched the wrong corpus.** A0 exists for this failure
(lab/025) and was executed as `grep -rn negotiat` over `docs/`, `src/`, `lab/` and
`README.md` — the **repo**. Both the thread title and the claim contain the word.

So the asking side is one defect wearing three hats: **a capped list read as the whole
list.** Every surface reported its own truncation, and truncation was read as absence.

## The one thing genuinely unreachable

The expert's own answers. Scope `architect` holds 0 Sessions, 0 Threads and 0 episodic
Claims against 10 Exchanges and 210 tier-2 claims, because an Exchange is written to the
*asking* scope. Exchange text is on no lexical surface either — `recall()` searches
`Session`, `Claim` and `Chunk` labels only. The expert was told twice to recall its prior
answers by ticket and returned findings as though the question were new, correctly, given
what it could see.

That is a real structural gap and it is narrower than the one this entry first claimed.
The next *builder* could have found the design three ways. The consulted *expert* could
not find it at all.

## The fix, and the argument against the obvious version of it

`consultation._assemble_brief` now opens with the expert's own answered exchanges,
ranked against the question being asked rather than by recency — recency re-creates the
failure, since the exchange holding the design was the sixth most recent of seven, and
against the question that re-derived it the same exchange ranks fifth of eight.

Headers carry the **question and the node id, never an excerpt of the answer**. A header
restating an expert's own prior conclusion into every later brief is self-anchoring (the
2026-08-09 decision-log entry), and tier-2 informs rather than instructs
([docs/05](../docs/05-trust-model.md)). Round 3 of this consultation overturned round 2
on measured facts — precisely the move a conclusion quoted back at an expert makes less
likely. Discoverability is the goal; agreement is not.

The asking side has no code fix here. A0 has to name the graph as the thing it searches,
and a printed elision notice has to be read as an unread result. The open question this
leaves is whether `memory_open_threads` should rank against the work at hand the way the
brief now does, since fifteen of three hundred and twenty-five is a sample, not a list.

## Found while verifying an expert rather than by any recall

`AgentCLI.argv()` had exactly one production caller; `eval/arms.py` and
`harness/quick.py` each rebuilt the headless invocation from `cli.binary`, so
`headless_preconditions` reached extraction and nothing else — the lab/054 seam, open in
two more places, inert only because arms refuse Cursor and `quick` names `claude`
outright. Fixed in `1c3df11`.

`pin.py:463` and `pin.py:626` both open `argv = ["claude"]` and `_entered_room` takes no
harness, so there is no Cursor launch path and the harness-keyed room refusal designed in
round 2 could not have been built as specified.
