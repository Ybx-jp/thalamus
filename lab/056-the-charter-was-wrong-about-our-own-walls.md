# lab/056 — The charter was wrong about our own walls

**Date:** 2026-08-11 · **Room:** `atlas` (`designer`, `architect`, `teacher`) · driver `main`

The first real room. Five deliverables shipped ([docs/primer.md](../docs/primer.md) and
four aids under `docs/visual/`), and they are not the interesting part.

## What was asked

Visual aids that give a software engineer with no context an accurate mental model of
Thalamus and enough grip to use it. Three differently-pinned experts, one artifact set.

## The topology, declared at open

```
main ──announce──▶ designer, architect, teacher   (dispatch, one-way, from outside the boundary)
designer ──review request──▶ both reviewers       (fan-out: a diverging node)
each reviewer ──verdict──▶ designer               (direct-routed, durable files)
architect ✗ teacher                               (NO EDGE)
anyone ──▶ main                                   (FILE ONLY — main has no pane in the room)
```

The reviewers do not confer. Two independent verdicts over one artifact is the reason the
room exists, and letting them agree first collapses two into one.

## Finding 1 — the charter was false about the isolation boundary

`main` wrote D2's stated idea as *"the subgraphs are disjoint, and consultation is the only
legal door."* `designer` found it false while procuring ground truth, before drawing.
`architect` and `teacher` each verified it independently; `main` verified it before ruling.

- `mcp_server.py:80` — `KNOWLEDGE_SCOPES = [s for s in available_scopes() if s != SCOPE]`
- `reader.py:621` — `claim_scopes = [scope, *knowledge_scopes]`, applied at `665-673`
  (Claims, under `.not_(__.in_e("CONTAINS"))`) and `687-691` (**Chunks, with no `CONTAINS`
  filter at all** — the larger population, 6,881 against 7,818, and the one `designer`
  missed)
- `mcp_server.py:109` — under a ticket, `_granted_scope` returns `(granted, [])`

So: **episodic memory is private; knowledge is an ambient commons every session already
reads.** The partition falls on one edge, not between experts. And the ticket is the
reverse of a door — it *drops* the commons and returns one scope in full. A consultation
buys depth by giving up breadth.

### Why the error was reachable

```
$ grep -rn "ambient" docs/*.md     # nothing
$ grep -rn "commons" docs/*.md     # nothing
```

The behaviour was documented **only as a comment in `mcp_server.py:74-79`**. `main` wrote
the charter from `docs/`, the deliverable table from the charter, and `teacher`'s
pre-registered answer key from the table. Every link read its most authoritative available
source. The source was incomplete.

The key being **pre-registered** is what made this a public amendment rather than a silent
post-hoc adjustment — the instrument working, not a mark against it. Fixed in
[docs/02](../docs/02-expert-subgraphs.md).

## Finding 2 — the accessibility hole was exactly the shape of the absent scope

`qe` was not in the room; the charter said so at open and the primer records it. The
executed acceptance gate found two dashed markers **carrying meaning** at **2.07:1** and
**2.97:1**, against WCAG 1.4.11's 3:1 floor for non-text content. Both were load-bearing:
one marked which tiers have no writer (the amended C1 doing its job), the other carried the
elapsed time between two sessions.

Two reviewers and three rounds missed it because **everyone checked text contrast**, which
is a different success criterion. `architect`'s close note diagnosed its own method: it had
grepped `fill="#…"` and never `stroke="#…"`, and — worse — had flagged both colours in
earlier verdicts before writing a summary that erased them.

> A reviewer who contradicts his own earlier findings in a later summary is doing more
> damage than one who missed them, because the summary is what gets read.

Fixed at `#6e7781`, 4.24:1.

## Instrument defects, found only by running a room

1. **`room-guard.sh` was declared in `install.py:88` and never armed.** It had never run.
   `eval/rooms.py` builds a room's realized edges exclusively from its rows, so every real
   room read *"TREATMENT DID NOT OCCUR — a set of solo sessions wearing a room label"* —
   the manipulation check reporting on the hook's installation while appearing to report on
   the room. `verify()` already checked the script was present and executable, which it
   was. **Present-and-runnable and actually-wired are different questions.** Closed by
   `install.verify_armed()` with two regression tests.
2. **`thalamus roster` is a write verb that reads as a status verb.** A member cataloguing
   the CLI surface ran it; with `THALAMUS_ROOM` set it opened a fourth member, which
   inflated the manipulation-check denominator and put a write-capable session in a
   checkout three members were working in. It sits in `--help` beside read-only verbs.
3. **`--to main` can never address a room's `main`.** `preflight` filters on
   `LiveSession.scope`, derived from `--agent`, which `main` has no manifest for;
   `eval/rooms.py:peer_scope()` parses the name and works. The refusal also reports "no
   live members" against a room with four.
4. **`thalamus dispatch <room> --sender X "<msg>"` fails** — only the message-adjacent form
   parses, and the error blames the text rather than its position.

## An isolated HOME splits the archive from the graph

`thalamus contract check` failed after the room closed:

```
Evidence floor: `scope:teacher:source:77c7d0e2…` points at archive://77c7d0e2… but no
such blob is retained
```

`teacher`'s cold-read instrument runs each reader with **no repo access and no Thalamus
context**, which it achieved with an isolated `HOME=/tmp/coldhome` and `cwd=/tmp/coldroom`.
That isolation is correct and load-bearing: a reader that can grep `docs/` scores the repo
instead of the picture.

But the isolation is not symmetric, and the asymmetry is the defect:

- `archive_dir()` derives from `Path.home()`, so `retain()` wrote the blob to
  **`/tmp/coldhome/.thalamus/archive/77/…`**.
- The graph is reached over the network (`ws://localhost:8182`), which `HOME` does not
  move, so the `Source` vertex landed in **the real graph**.

The result is a tier-1 `Source` in the durable graph whose evidence pointer resolves only
inside a temp directory — a dangling evidence floor the moment `/tmp` is cleaned, and one
that reads as retained until the audit runs. Verified rather than assumed: the live
transcript still on disk hashes to exactly the vertex's `content_hash`, and the blob was
found under the isolated home's own shard. Recovered by copying it into
`~/.thalamus/archive/`; `contract check` is clean again.

**The general form: any instrument that isolates a subagent with `HOME` separates the
archive from the graph, because one is path-derived and the other is a network address.**
Every isolated-HOME run has this shape, so it would have recurred silently. The candidate
fixes are to derive the archive location from the same configuration that names the graph,
or to have the write path refuse a `Source` whose blob is not readable from the archive the
writing process will actually use.

Nothing about this was visible from inside the room. It surfaces only when the contract is
audited from outside it, which is the argument for auditing after a room rather than
trusting its close notes.

## The manipulation check, and what its number means

```
before: atlas: TREATMENT DID NOT OCCUR — 3 members, no permitted message between any two
after:  atlas: treatment occurred — 4 permitted send(s) over 2 directed pair(s), density 0.33
```

First non-fixture pass in this system's history. Two bounds recorded with it:

- **A guard row records permission, not delivery.** Four rows, three deliveries — one
  attempt used the bare room-mate name, which the guard passed and SendMessage then
  refused. PreToolUse cannot know the call failed. `permitted sends` is an **upper bound**,
  and a room whose members fumble the address scores *higher* than one that does not.
- **An accidental member enlarges the denominator.** Density 0.33 across 4; the three real
  members give 0.5.

**SendMessage between two live room members delivers** — closing docs/12's open question.
Never on the bare `<room>-<scope>` name at first contact: the refusal names the exact ref
and the retry carrying ` [ref]` succeeds. lab/045's hazard again, and
`eval/rooms.py:peer_scope()` already normalizes both forms — the design anticipated it and
only the instruction did not.

## What the room did with `main` being wrong

`main` ruled "theme-neutral ink" off `architect`'s finding that a GitHub-rendered SVG
cannot see the page theme. `designer` swept all 256 neutral greys and showed the best
possible single ink scores **4.35:1** against both canvases, under AA's 4.5. `main`
reproduced the sweep before withdrawing the instruction. The aids now paint their own
opaque surface at 14.73:1.

`architect` found the mechanism; `designer` found the arithmetic that killed the obvious
remedy. Neither gets there alone.

## Correlated witnesses

Three members independently verified the same code and converged. The verifications were
genuinely independent — but it is **one room reading one file**, which is not three
independent confirmations of a claim about the world. `witnesses.py` should flag and leave
counted, per docs/09.

## What did not happen

The failure this room was built against — a fan-in discarding the minority branch while
producing output that reads as consensus — did not occur. Two `teacher` minorities are
left standing unresolved rather than tidied away at close.

`teacher`'s own withdrawn minority is worth more than the ones that held. It predicted both
reviewers would want *less* text than novices need (expertise reversal). Measured against
pre-registered forecasts, the signed gap was **−3, every error an under-prediction**. The
replacement claim is sharper and has a number: **16/16 forecasts correct with the artifact
in hand, 0/3 forecasting blind.** Do not let a reviewer estimate an aid's teaching power
from a description of it.
