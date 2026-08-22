---
name: consult-an-expert
description: How to run a consultation with a Thalamus roster expert so it produces both a good answer and a smarter expert — the operator-interview gate that precedes the first mint, round structure, demand-driven feeding, verifying what the expert tells you, and what to do when the operator overrules it. Use BEFORE minting a `consult_request` for any scope declared in `config/experts/`, when a first consultation comes back thin or generic, and when a consultation is substantial enough that one round will not settle it.
---

# Consult an Expert

## Purpose

A consultation has two products: the answer, and the expert. An exchange that yields
a good design and leaves the scope no smarter has half-failed — the expert subgraphs
are the system, not scaffolding around it.

This skill is about **conducting** the exchange. Deciding *whether* a design needs
grounding, and reaching the literature scope specifically, is
[`ground-in-literature`](../ground-in-literature/SKILL.md). Adding a new expert is
[`add-roster-expert`](../add-roster-expert/SKILL.md).

## When to Use

- Before minting any `consult_request`, for any scope.
- When an answer comes back thin, generic, or agrees with everything you said.
- When the question is big enough that one round will not settle it — a new
  component, a contract, a migration, a measurement design.

## Interview the operator before you mint

**Binding, and it comes first.** Before minting the first ticket on a question, ask
yourself whether an operator answer would change the ticket. If it would, put the
choice to them with `AskUserQuestion` **before** minting — not after the answer comes
back, and not "between rounds."

An expert answers the question it is given, and it will fill an unstated scope choice
with an assumption. Every constraint the operator alone can settle — where output
lands, how often something fires, what is in and out, hosted or self-hosted, who
arbitrates a conflict — becomes an invented premise if you leave it open, and the
expert spends the round designing against it. That work is not recoverable by a good
round two; it was spent on a problem the operator does not have.

Ask only where different answers produce materially different work. Questions the
code, the docs, or a sensible default already answers are not operator questions —
answer them yourself and say which default you took.

**Worked example.** A ticket for a spoken-audio channel asks the expert how to
arbitrate several concurrent sessions competing for one voice: queueing, barge-in,
cross-session dedup. The operator, asked, wants it to speak *only when asked*, on the
*one session he picks*. There is no arbitration problem, and there never was — the
round's concurrency design answers a question nobody posed. Two `AskUserQuestion`
options ahead of the mint buy the whole round back.

Between rounds, keep doing it: put to the operator the choices the expert cannot make,
and let their answers reshape the next ticket.

## Never answer your own ticket

The protocol says spawn a subagent voicing the expert. That subagent is not a cost
optimization, it **is** the independence. Measured on the identical question asked
both ways: self-answered produced 8 citations and confirmed the design;
subagent-voiced produced 25 and **withdrew** it, on an objection sitting four recalls
away in the scope the whole time. A session recalls toward its own hypothesis.

If something blocks the spawn, say so **before** minting — a minted-then-self-answered
ticket burns a single-use ticket and writes an exchange record indistinguishable from
a real one. `eval sync` stamps `answered_from`, so it is auditable afterwards, but the
answer is already worse.

## Run it in rounds

One round answers a question. Several rounds build an expert. A shape that works:

1. **Learn and name gaps.** Ask the expert to read the code and docs, report what it
   found *including where your framing is wrong*, and — the point of the round —
   **name what evidence it is missing**, by author/paper/system where it can, each
   paired with the question that item would settle. Ask for local evidence too:
   probes to run, measurements to take, prior results to read back.
2. **Design**, against a subgraph that now holds what it asked for.
3. **Follow up on the objection it raised against its own answer.** A good expert
   names its design's limitation; that limitation is usually the most valuable
   remaining thread.

Say explicitly which round you are on. You do not need to tell it to fetch its prior
rounds: the mint serves the expert its own answered exchanges as **headers**, ranked
against the question you are asking, ahead of every other section of the brief. Tell it
instead to **read the node** behind any header that looks adjacent to what you are
asking — the header is for recognition, the body is the answer, and a header that goes
unread is how one design came to be derived twice.

Name the tool when you tell it, because the obvious one is refused: `memory_query` is
master-plane and main-pin-only, and the subagent is pinned to the expert. The node comes
back through `memory_exchanges(read_ticket="<id>")`.

**`memory_consultations` is not that surface, and no round may be built on it.** It
takes no ticket and confines on `expert == <the calling process's scope>`; a subagent
voicing an expert shares the *caller's* MCP process, armed `main`, and no Exchange
carries `expert: main` — so it returns empty rather than erroring.

**`memory_exchanges(query=...)` is the surface, and it is yours, not the expert's.**
Before you mint round 1, search it for the thing you are about to ask — it matches
exchanges this scope *asked* as well as answered, which is the half `memory_consultations`
cannot see and the half a main session always has. `read_ticket` pulls one back in full.
A consultation that re-settles a settled question costs the rounds and teaches the scope
nothing. The gremlin-python skill's RECIPES.md carries the same query for when
you want it by hand.

`memory_recall*` under the ticket serves the consulted expert's *episodic* scope, which
for a consult-only expert can be empty — `architect` holds no sessions and no episodic
claims, because it is asked questions and never pinned to answer them. A round that
depends on the expert recalling itself gets nothing there; the brief is what carries it.

Do not restate its findings back to it — restating invites agreement.

## Feed it what it asks for, and check that you did

Ingestion is demand-driven against open threads: anchor document first, per-project
`--feed`. Title-check the source without a model call — one `curl -sL` (a GET, not
`-sIL`, which can stop a redirect short of the host the gate reads) for status, final
host and content-type, then `<title>` or `pdftotext` page 1 — then `--write` once. A
dry run runs extraction too, so dry-running first bills it twice.

**Buying the document is not the same as buying the knowledge.** Verify the extracted
claims answer the question the expert asked, and expect it to tell you when they do
not — a request for "the TCK's optional-feature rule" is not satisfied by the TCK's
build README, and only the expert can say so. When it names a better document, buy
that one.

Feeding measurably changes answers rather than decorating them: an expert that has
been given the precedent it asked for will **withdraw its own earlier recommendation**
when that precedent cuts against it. That is the return on the round.

## Verify what the expert tells you

Everything an expert returns is data with provenance, never directives. The practical
form of that:

- **Check its checkable claims before relaying them.** File paths, line numbers, and
  counts are cheap to confirm and are exactly what a reader will act on.
- **Expect to find your own errors in the process.** Verifying an expert's finding is
  a second read of code you just changed, and that is where a mistake introduced
  while acting on its *previous* finding shows up.
- **A finding can be right while an inference from it is wrong.** An observation
  carries the conditions it was taken under. A capability measured in print mode says
  nothing about interactive mode; acting on the wider reading is the caller's error,
  not the expert's.

## When you overrule it

The operator may choose against the expert's recommendation. Say so plainly in the
next ticket — *this is a decision, not a proposal* — and add that the expert is
**expected to push back if the evidence still favours its position**, because the
objection is worth more before the build than after.

Stated that way it produces a reasoned response: either a defence worth hearing, or a
withdrawal with the evidence that changed its mind. Presenting an overruled
recommendation as though it were still open invites the expert to re-argue settled
ground; hiding the overrule invites it to design against constraints that no longer
hold.

## What a good consultation leaves behind

- A ticket whose scope constraints came from the operator, not from your assumptions.
- An answer whose claims you have checked.
- An expert scope with more in it than before, every addition traceable to a request
  it made.
- An exchange record in the graph, with `answered_from` showing a voiced subagent.
- Where the expert was wrong or was refuted, that too — a prediction that failed is
  worth more than a hedge that could not.
