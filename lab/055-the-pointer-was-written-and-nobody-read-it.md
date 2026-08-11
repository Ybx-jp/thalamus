# 055 — The pointer was written and nobody read it

**Date:** 2026-08-10 · **Verdict:** retrieval, on both sides of the ticket, plus a
protocol defect in the check built to catch exactly this

A three-round architect consultation designed a harness capability contract. The next
session opened the same question, ran three more rounds, and re-derived the same data
model under different names. The first instinct — that a design which changes no file
leaves no trace — is wrong, and the graph says so.

## What was re-derived

The 2026-08-10 22:17 exchange holds `src/thalamus/contract/capabilities.py` as a
stdlib-only leaf module and this enum:

```python
class Provision(StrEnum):
    PROVIDED = "provided"
    ABSENT   = "absent"
    NATIVE   = "native"    # the harness already does it; a Thalamus adapter MUST decline
    OPAQUE   = "opaque"
    UNKNOWN  = "unknown"   # never measured; not a synonym for ABSENT
```

plus an `Evidence` type, the "features declare requirements; harnesses carry measured
provisions" split, and `holds_under` in the 23:18 round. The 2026-08-11 05:39 exchange
re-derived the same five states as `State`, the same split, the same `holds_under`, and
added `unmet()`. The second derivation cited `scope:architect:claim:2ae84c25c99a6191`
for the same reasoning as the first — the asking session handed that claim over as a
fresh objection, and the expert took it as one.

## The claim existed

Distillation did not miss it. Session `dcf15078` carries 30 claims, and one of them is:

> **decision** — Chose 'detection first, contract second': build sentinel flag probes
> and DERIVED declaration rows before building the full five-state
> capability-negotiation contract (`contract/capabilities.py`, `Requirement`/`Evidence`
> model).

That names the module path, the five-state shape, both type names, and the word
*negotiation*. It is the right claim at the right granularity, and it was written
automatically. Any of three cheap acts would have surfaced it.

## Why nobody read it

**The asking side — the render cap.** Two `memory_recall` calls returned the correct
session and capped their claim lists at eight, reporting the elision honestly: *"22 more
claim(s) in this session: 13 matched but exceeded the 8-claim render cap"*, with the
remedy printed alongside — recall the session node to expand. The pointer was in the
elided thirteen. The surface told the truth and was not believed enough to act on.

**The asking side — the wrong haystack.** `ground-in-literature` step A0 exists for this
failure (lab/025). It was run as `grep -rn negotiat` over `docs/`, `src/`, `lab/` and
`README.md`, which returned four irrelevant hits and read as *no prior design*. That
searched the **repo**. The claim was in the **graph**, and it contains the search term.
A0 is written as a question about the system and was executed as a question about the
checkout.

**The answering side — the expert cannot see its own work.** Scope `architect` holds 0
Sessions, 0 Threads and 0 episodic Claims against 10 Exchanges and 210 tier-2 claims.
Exchanges are written to the *asking* scope, so an expert's own answers are not in the
scope it recalls from, and the server-assembled brief carried none of its prior rounds
across all three. It was told twice to recall its prior answers by ticket and returned
findings as though the question were new — correctly, given what it could see.

## Why the workaround did not hold

`consult-an-expert`'s eleven lines telling the asker that `memory_consultations` returns
empty from a feature session are accurate and were followed. They route around the hole
rather than closing it, and the channel they route to is the one that capped its output.
A documented dead end is still a dead end.

Note that `mcp_server.py:258-260` passes the pin scope to `recall_exchanges`
deliberately: a ticket grant resolves to the consulted scope and dies when the answer
lands, so a ticket can never reach the record it just closed. Any fix that hands
`memory_consultations` a ticket argues against that, and has to say so.

## The shape of the fix

The brief is assembled server-side at mint time, where the consulted scope is known and
no ticket is needed — `consultation._assemble_brief` can carry prior-exchange *headers*
(never bodies; these run 15k–40k characters) for the expert being consulted. That closes
the answering side without touching the ticket-scope decision.

The asking side is not a code fix. A0 has to name the graph as the thing it searches,
and an elision notice has to be treated as an unread result rather than a footnote.

## What it cost, and what it did not

Six consultation rounds where three would have done, and one data model derived twice.
Not wasted: the second pass bought MDN feature detection, POSIX `sysconf` and Autoconf
caching — none of which appears in any earlier exchange — and those produced the
staleness model, the options-before-limits shape, and a decision on Cursor rooms the
first consultation never reached. Grounding was new. The types were rework.

## Found while verifying the expert rather than by any recall

`AgentCLI.argv()` had exactly one production caller. `eval/arms.py` and
`harness/quick.py` each rebuilt the headless invocation from `cli.binary`, so
`headless_preconditions` reached extraction and nothing else — the lab/054 seam, still
open in two places, inert only because arms refuse Cursor and `quick` names `claude`
outright. Fixed in `1c3df11`.

`pin.py:463` and `pin.py:626` both open `argv = ["claude"]`, and `_entered_room` takes no
harness: there is no Cursor launch path at all, so a refusal keyed on harness capability
could not have been implemented as designed. `hooks/cursor/session-start.sh` writes no
`room` field, so the false capture that refusal was meant to prevent cannot occur on the
path it was aimed at.
