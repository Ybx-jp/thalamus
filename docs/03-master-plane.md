# Master Plane — Observability & Audit

**Status:** design. **Revised 2026-07-14** — the original framing ("a read-only
projection, never a store") overstated the case. See *What it actually is*, below;
the constraint that survives is **no-copy**, not **no-store**.

## What it is

The master plane is the human's window into the whole system: one place to answer
*what does my agent believe, where did each belief come from, which expert served
it, and has it earned its keep?*

## What it actually is (revised)

The master plane is **the main session scope** — the one the operator talks to when
no expert is pinned. It is not a separate species of thing. It has its own episodic
memory, written the same way an expert's is, conforming to the same contract, under
`scope=main` ([09-schema-and-federation.md](09-schema-and-federation.md)).

Its defining property is **topological, not structural**:

> The main scope is **dense and connective** — high-level structure, working memory,
> and the edges that tie everything together. Expert scopes are **leaves**: rich
> internally, sparsely interconnected with each other.

This is a better claim than the original, for one specific reason: it is
**measurable**. Cross-scope edge density per scope is a number, the eval loop can
compute it, and it directly grades the roster's granularity — a "leaf" expert with
high inter-expert density is mis-cut, which is exactly the split/merge test
[08-roster-candidates.md](08-roster-candidates.md) needs and previously had to make
by judgment.

## The no-copy rule (the part that survives)

**The master plane copies nothing.** It references expert nodes by ID; it never
embeds their content. This is the constraint that was doing the real work all along.

If memories were *copied* upward into a master store, every boundary in the system
would become decorative: the trust model would be theater (untrusted content
laundered into a trusted store), the contract would be a suggestion, and the soup
would be back with extra steps.

What was wrong with the original framing: "the master plane owns nothing" implied it
has no memory of its own, which is false and unhelpful. Sessions in the main scope
are real sessions and produce real episodic memory worth keeping. Likewise, expert
subagents can be talked to **directly** (pin one and have a session with it) as well
as invoked through the harness's subagent protocol — and either way those exchanges
are sessions worth remembering. What the plane must never do is *duplicate* what a
scope already owns.

## What it projects

- **Roster state** — the experts, their manifests, entrypoints, sizes, trust-tier
  composition, and health (staleness, utility trend).
- **Session ledger** — every session: which expert was pinned, summary, open
  threads. The base memory system's entrypoint design, elevated one level.
- **Exchange graph** — the inter-expert consultation edges
  ([02-expert-subgraphs.md](02-expert-subgraphs.md)): who asked whom, about what,
  and whether the answer was used. The operator literally watches the roster
  collaborate.
- **Provenance chains** — for any belief the agent acted on: node → expert →
  ingestion event → source, with trust tier at every hop. This is where
  "observability" upgrades to **audit**: a complete, traversable answer to *why did
  the agent believe that?* ([05-trust-model.md](05-trust-model.md)).
- **Contradiction surface** — when projections from two experts disagree on a claim,
  the master plane does not resolve the conflict; it **surfaces** it as an epistemic
  event for the operator (and as eval-loop input). Cross-expert contradiction is a
  signal, not an error to be silently merged.
- **Eval verdicts** — per-node and per-expert utility summaries from
  [04-eval-loop.md](04-eval-loop.md), so "is this expert earning its keep?" is
  answerable from the same pane as "what does it know?"

## The visualizer

The base memory system already has a visualizer; the master plane is its natural
upgrade target. Views, in build order: roster overview → session ledger →
provenance-chain inspector (click a belief, walk to its source) → exchange graph →
contradiction queue. The inspector is the demo: *pick any thing my agent believes
and walk, hop by hop, to where it came from.* Nobody else's memory demo can do that.

## Why it matters

Memory systems fail socially before they fail technically: the operator stops
trusting what's in there and stops maintaining it. The master plane is the trust
instrument — full observability into the memory madness, by design rather than by
grepping JSON. It is also the audit substrate the trust model needs: gating
decisions and poisoning post-mortems are only possible because every belief is
traceable end-to-end.

## Open questions

- Projection freshness: on-demand vs. scheduled materialization. Start on-demand;
  cache when the visualizer makes it slow.
- Contradiction detection scope at M-early: exact-claim conflicts on core-ontology
  nodes only. Semantic/soft contradiction is a research rabbit hole — do not enter
  before M6.
- Whether master-plane episodic events are themselves queryable by the agent
  (self-knowledge: "which expert usually helps here?"). Powerful, but defer until
  the eval loop can measure whether it helps.
