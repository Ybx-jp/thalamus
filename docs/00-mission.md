# Mission & High-Level Design

## Mission

Build the memory substrate a coding agent deserves — federated, inspectable,
trustworthy, and **measured** — and push it until the harness breaks, then engineer
around the break, and repeat.

Three claims this project exists to earn, in priority order:

1. **Evaluation.** "Does agent memory actually make the agent better?" is an open
   question the industry answers with vibes. Thalamus answers it with instrumentation:
   every retrieval is traced, utility is measured against downstream outcomes, and the
   graph maintains itself from that signal. *Memory that measures itself.*
2. **Platform.** Specialization does not require fine-tuning or prompt-cosplay
   multi-agent theater. A specialist is a **retrieval scope**: a curated domain
   subgraph plus its own episodic history, hot-swappable behind a schema contract.
   The contract is proven the day the second expert plugs in with no bespoke glue.
3. **Structural safety.** A crawler pipes third-party internet content into the
   persistent memory of an agent that runs with the operator's credentials. That is a
   memory-poisoning attack surface, and the contract is where it gets defended:
   provenance on every node, trust tiers, write-gating, data-informs-but-never-
   instructs. Almost no memory system in the wild has a trust model. This one is
   designed around it.

One sentence for the roster: **an in-context, memory-learned specialist roster** —
each expert carries its own knowledge network and episodic memory, a master plane
gives the human full observability, and the whole thing is governed by contracts
rather than convention.

## What exists today

The **base graph memory system** is ported and running (**M0 complete**, 2026-07-14):
graph memory for coding agents over MCP (8 tools), a React/Cytoscape viewer over a
FastAPI read layer, and a tight schema that exposes **session summaries** and **open
threads** as entrypoints into the graph. It generalizes the refresh-skill
memory-maintenance scheme from stepmania-chart-generator. It lives in
`src/thalamus/{substrate,plane,harness}`.

What it is **not** yet: it has no provenance, no trust tiers, no expert scoping, no
contract, and no knowledge-side ontology — it implements only the *episodic* half of
what [02](02-expert-subgraphs.md) calls an expert. The gap between the ported schema
and the federation contract, and the order in which to close it, is
[09-schema-and-federation.md](09-schema-and-federation.md). Everything else in this
directory is still design.

## The architecture in one pass

```
                       ┌──────────────────────────────┐
                       │   MASTER PLANE = scope:main   │
                       │   dense, connective: working  │
                       │   memory, audit, provenance   │
                       │   chains, contradictions      │
                       └──────────▲───────────────────┘
                                  │ references by ID (never copies)
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
┌───────┴────────┐       ┌────────┴───────┐        ┌────────┴───────┐
│ EXPERT: domain │       │ EXPERT: domain │        │ EXPERT: domain │
│ subgraph +     │  ...  │ subgraph +     │  ...   │ subgraph +     │
│ episodic memory│       │ episodic memory│        │ episodic memory│
└───────▲────────┘       └────────▲───────┘        └────────▲───────┘
        │      FEDERATION CONTRACT (schema + permissions +  │
        │      trust boundary — every edge above crosses it)│
        └───────────────┬─────────────────┬─────────────────┘
                 ┌──────┴──────┐   ┌──────┴───────┐
                 │  INGESTION  │   │ HARNESS      │
                 │  (curated   │   │ (MCP, hooks, │
                 │  feeds, e.g.│   │ CLAUDE.md,   │
                 │  literature │   │ skills,      │
                 │  crawler)   │   │ subagents)   │
                 └─────────────┘   └──────────────┘
```

- **Federation contract** — the schema contract every subgraph conforms to. Data
  schema + permission system + trust boundary in one artifact.
  → [01-federation-contract.md](01-federation-contract.md)
- **Expert subgraphs** — the specialist roster. Routing is solved by **pinning one
  expert to a session**; cross-domain needs go expert-to-expert through the harness's
  own subagent protocol, and those exchanges land in episodic memory as first-class
  events. → [02-expert-subgraphs.md](02-expert-subgraphs.md)
- **Master plane** — the human's window, and the main session scope (`scope=main`).
  It has episodic memory like any other scope, but it **copies nothing**: it
  references expert nodes by ID. Its distinction is topological — dense and
  connective, where experts are leaves. Observability upgrades to *audit*: a complete
  provenance chain for everything the agent believes.
  → [03-master-plane.md](03-master-plane.md)
- **Eval loop** — hook-instrumented retrieval traces, used-vs-ignored attribution,
  counterfactual runs (memory on / off / degraded), and a utility-driven forgetting
  policy. The differentiating artifact. → [04-eval-loop.md](04-eval-loop.md)
- **Trust model** — provenance tiers, write-gating, poisoning defense,
  contradiction detection. → [05-trust-model.md](05-trust-model.md)
- **Ingestion** — deliberately the smallest component. Curated feeds populating
  expert subgraphs; the literature crawler is a data feed, not the project.
  → [06-ingestion.md](06-ingestion.md)
- **Harness integration** — MCP surface, hooks, CLAUDE.md directives, skills, and the
  session-pinning mechanics; plus the harness-limit lab notebook.
  → [07-harness-integration.md](07-harness-integration.md)

## Design principles

1. **Contracts over convention.** If adding an expert requires bespoke glue, the
   architecture has failed. Two experts prove N; the contract is the product.
2. **The master plane copies nothing.** It references; it does not duplicate. The
   moment memories are copied upward, the boundaries are decorative and the soup is
   back. (It does *own* its own episodic memory — it is the main session scope, not a
   bodiless view. See [03](03-master-plane.md).)
3. **Untrusted content informs, never instructs.** Crawled text can be retrieved as
   *data*; it can never author directives the agent follows. Enforced at the
   contract, not by politeness.
4. **No unmeasured quality claims.** "It feels smarter" is not a result. The eval
   loop ships before any claim about memory utility does. (Same discipline as the
   taste critic: when the standard signal can't see the quality that matters, build
   the missing metric — don't assert it.)
5. **Failure-driven iteration.** The best outcome is that it works brilliantly *and
   then breaks somewhere honest* — each break gets written up in the lab notebook and
   engineered around, until we hit the genuine limits of the Claude Code harness.
6. **Human-legible always.** Session summaries and open threads stay the entrypoints.
   The operator can always answer: what does my agent believe, where did that belief
   come from, and has it earned its keep?

## Milestone ladder

| Milestone | Deliverable | Proves |
|---|---|---|
| **M0** | Port the base graph memory system into this repo ✅ | working substrate |
| **M0.5** | Provenance envelope + scope segment + stable claim IDs, *before* more data lands ([09](09-schema-and-federation.md)) | the retrofit never has to happen |
| **M1** | Federation contract v0 + first expert (literature graph, manual/curated ingest) | the contract exists |
| **M2** | Retrieval instrumentation + eval loop v0 (traces, used-vs-ignored) | measurement exists |
| **M3** | Second expert + session pinning + inter-expert subagent protocol | **two proves N** |
| **M4** | Counterfactual harness (on/off/degraded) + utility-driven maintenance | memory earns its keep |
| **M5** | Trust model enforcement (provenance tiers, write-gating) | the boundary is real |
| **M6** | Master plane visualizer + end-to-end audit chains | full observability |
| **∞** | Harness-limit lab notebook (ongoing from M2) | the senior story |

## Non-goals

- A general-purpose vector-soup RAG framework. Thalamus is graph-first, contract-first.
- Crawler sophistication. Ingestion stays minimal until something downstream demands more.
- Model-side learning. All specialization is in-context and memory-borne, by design —
  that's the thesis, not a limitation.
- Multi-user / hosted service. Single-operator, local-first, one human's agent fleet.
