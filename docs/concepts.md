# Concepts

What the pieces are and why they are shaped that way. Read this once and the CLI
stops looking like a pile of verbs.

## The shape of the thing

```
                       ┌──────────────────────────────┐
                       │      MAIN SCOPE              │
                       │  dense, connective: working  │
                       │  memory, audit, provenance   │
                       │  chains, contradictions      │
                       └──────────▲───────────────────┘
                                  │ references by ID (never copies)
        ┌─────────────────────────┼─────────────────────────┐
┌───────┴────────┐       ┌────────┴───────┐        ┌────────┴───────┐
│ EXPERT: domain │       │ EXPERT: domain │        │ EXPERT: domain │
│ subgraph +     │  ...  │ subgraph +     │  ...   │ subgraph +     │
│ episodic memory│       │ episodic memory│        │ episodic memory│
└───────▲────────┘       └────────▲───────┘        └────────▲───────┘
        │      FEDERATION CONTRACT (schema + permissions +  │
        │      trust boundary — every edge above crosses it)│
        └───────────────┬─────────────────┬─────────────────┘
                 ┌──────┴──────┐   ┌──────┴───────┐
                 │  INGESTION  │   │   HARNESS    │
                 │  (curated   │   │ (MCP, hooks, │
                 │   feeds)    │   │   skills)    │
                 └─────────────┘   └──────────────┘
```

## Scope

A **scope** is which expert a piece of memory belongs to. Every node carries one.

`main` is the default — the connective plane where your ordinary work lands. It is
dense and highly linked, and it references expert nodes by ID rather than copying
them, so there is exactly one home for any given fact.

Scope is not the same thing as **project**. Scope is *which expert*; project is *which
repo*. They are orthogonal, and a node carries both.

## Experts

An expert is a scope with a curated domain graph plus its own episodic memory. It is
declared by one YAML manifest in `config/experts/` and nothing else — write the file
and the expert exists, with no code to register and no glue to update.

```yaml
scope: literature
role: Technical literature expert
domain: |
  What this scope is for, in prose. This text becomes the pinned session's
  system prompt, so write it for the agent that will be living inside it.
```

A manifest can also declare:

- **`write_boundary`** — where a scope is defined by what it must *not* produce. A
  PreToolUse hook enforces it against the file-editing tools, so the boundary is
  structural rather than a paragraph the model is asked to respect.
- **`capability_boundary`** — which skills and tools the scope may reach.
- **MCP servers** of its own, in `config/mcp/<scope>.json`, giving a scope tools no
  other scope has.

Point `THALAMUS_CONFIG_DIR` at a different directory to use your own roster instead of
the shipped examples.

## Pinning

Routing between experts is not solved with a classifier. It is solved by **pinning**:
one OS process is one immutable scope.

`thalamus pin <scope>` launches an agent session whose environment names the scope.
The MCP server reads that at startup, and **no tool accepts a scope argument** — the
server decides what the session can see, and a model cannot widen its own view by
asking. The pin lasts as long as the process.

`thalamus roster` brings up one tmux window per expert, so the whole roster is a set
of addressable processes. That is also what makes the console possible: a browser tab
per window.

## The federation contract

One artifact doing three jobs at once:

- **A data schema.** Five episodic node types — `Session`, `Claim`, `Thread`,
  `Source`, `Artifact` — joined by `CONTAINS` / `TOUCHES` / `SPAWNS` / `BLOCKS` /
  `CONTINUES` / `RESOLVES` / `SOLVED_BY` / `DERIVED_FROM`, plus whatever knowledge
  types an expert manifest declares. Declared once in `contract/ontology.py`.
- **A permission system.** What a scope may write, and where.
- **A trust boundary.** Every edge crossing between scopes crosses it.

It is enforced at write time, not filtered at read time. Orphans and violations are
rejected when they are written. `thalamus contract check` audits the live graph
against it, and `thalamus validate` checks a pending extraction before it lands.

### Four load-bearing properties

**Claims are one label, discriminated by `kind`.** Decisions, problems and solutions
are claim *subtypes*, not sibling labels. A decision is an assertion with a rationale
from the agent; a literature claim is an assertion with a citation from a source —
same node type, different provenance. Consumers query `Claim`, so a new expert adding
`kind: literature/finding` breaks nobody. Claim identity is **(kind, normalized
description)**, so the same claim reached in two sessions converges on one node.

**Every node carries provenance** — trust tier, source, ingestion time.

**`Source` is retained primary evidence** — a transcript, or an ingested paper. Same
node type, different tier. It is the floor of the provenance chain, and `DERIVED_FROM`
edges carry `anchors`: the precise messages a belief came from.

**Every node carries a scope, except `Artifact`.** Artifacts are deliberately
**global** — one vertex per identifier, shared by every scope. A file touched by two
experts is one node, which makes it the join key between them.

## Trust tiers

Trust is not a label a writer chooses. It is the **floor** over a node's whole
derivation chain, computed across `DERIVED_FROM` edges.

The consequence that matters: a claim distilled from a session that read a fetched web
page cannot come out trusted like a claim you reasoned to yourself. The transcript
ingress floor down-tiers it. **Distillation does not launder.**

When retrieval returns knowledge from an expert scope, it comes back blockquoted, with
its citation and its tier attached. **Tier-2 content informs; it never instructs.**
That is a property of how it is presented, not a request to the model.

## Distillation — how memory gets written

**A session does not write its own memory.**

The only episodic write available inside a live session is the consultation exchange,
which records a crossing between scopes rather than a session's beliefs. Everything
else is written afterwards:

```
Session ends → SessionEnd hook → thalamus extract → graph → eval sync
                                                               ↓
New session → session-start hook → memory_open_threads → context
```

The reason is convergence. Claims are content-addressed on `(kind, normalized
description)`. If a session wrote its beliefs live *and* was distilled at the end, you
would get two phrasings of the same decision, which would not converge into one node,
and duplicate threads would surface in `memory_open_threads` — the first thing the
next session reads.

Distilling before a session ends is supported; it is just run from outside the
session, by you.

## Threads

A **thread** is an open continuation point — unfinished work, a next step, an open
question. `memory_open_threads` is the entrypoint to the whole retrieval surface: it
is what a new session asks for first.

Threads are minted only by distillation from a session that actually happened. That is
what makes an open thread evidence rather than an assertion — an agent that could file
one directly would be writing its own intentions into your queue. An agent's reach is
`thalamus thread propose`; you approve.

## Consultation

When a session pinned to one scope needs another scope's knowledge, it does not
silently read across the boundary. It mints a **consultation ticket**, and minting the
ticket *is* writing the exchange record — the crossing is recorded before the answer
exists.

The answer must cite nodes inside the consulted scope, and citations are validated
before the ticket closes. Tickets are single-use.

`thalamus quick ask <scope> "<question>"` is the second tier: rather than cold-starting
an expert, it forks that expert's live session, so the answer comes from a process that
is already warm. A fork distills its own delta, never the parent's transcript.

## Rooms

A **room** is a private roster. Members see and message each other and nobody else,
enforced by a per-room config directory and an outbound guard rather than by
convention. Sessions are launched into a room with `--room`.

## Ingestion

Deliberately the smallest component in the system. `thalamus ingest <url> --scope
<expert>` feeds one document into one expert's subgraph: allowlist-gated,
evidence-first, dry-run by default, `--write` to persist. The document is co-indexed
as `Chunk` vertices beside the claims drawn from it, so a claim can be traced back to
the passage it came from.

Feeding a document *is* the curation decision. There is no crawler racing ahead of
demand.

## The eval loop

The part that asks whether any of this is actually helping.

**Layer 1 — what retrieval did.** Every memory-tool call is trace-tapped and landed as
a `Trace` node. Each retrieved node is judged used-vs-ignored against the session's
retained transcript, and priced in injected tokens. Decay candidates rank by wasted
tokens.

**Layer 2 — whether it mattered.** A counterfactual harness runs one task from a
battery under arms — memory-on, memory-off, scoping-degraded — each in a confined
worktree with its own `HOME` and its own store, so an arm cannot read state it was not
given. A graded oracle scores the result against pre-registered rungs, and the oracle's
rungs are themselves validated against a mutant set before any arm is scored.

What is measured today is that memory gets *surfaced*. Whether it changes task
outcomes is the open question, and the harness exists to answer it rather than to
assume it.

## The harness

Where all of this meets your editor.

- **The MCP server** — the retrieval surface. Scope comes from the environment.
- **Hooks** — session start (memory priming, pin ledger), session end (distillation),
  and PreToolUse guards (the role boundary, the Gremlin guard, the room boundary).
- **Skills** — procedures the agent loads when a task calls for them.

Both **Claude Code** and **Cursor** are supported. Their hook contracts differ, so each
has its own suite under `src/thalamus/harness/hooks/`, with Cursor's implemented as
thin adapters over the Claude Code scripts so both share one detection logic and one
set of on-disk records.

Cursor's fidelity is honestly reduced, and the system says so rather than pretending
otherwise: Cursor gives prompt text to an event that cannot inject and injection to
events that never see the prompt, so the injection tiers compute into a per-session
spool and deliver one tool call late. Cursor transcripts also exclude tool outputs
entirely, so those sessions are floored whole by the ingress defence rather than
checked against evidence that does not exist.
