# Harness Integration — MCP, Hooks, Directives, and the Limit Lab

**Status:** design. The base memory system already runs over MCP; this doc covers
how Thalamus meets the Claude Code harness specifically, and how we find the
harness's limits on purpose.

## Surfaces

- **MCP server** — the primary runtime surface: scoped retrieval/traversal for the
  pinned expert, consultation requests, episodic writes. The subgraph-scoping rule
  is enforced *server-side* (the session's pin determines the visible scope) — the
  model is never trusted to self-limit its own retrieval scope.
- **Hooks** — the instrumentation and enforcement layer:
  - *Session start:* resolve and record the expert pin (from directory-scoped
    CLAUDE.md directive or operator choice); stamp the session into the ledger.
  - *Post-tool-use on memory calls:* write retrieval traces — the eval loop's
    layer-1 feed ([04-eval-loop.md](04-eval-loop.md)).
  - *Session stop:* distill the session — summary + open threads into the pinned
    expert's episodic subgraph (the base system's maintenance scheme, now
    per-expert and eventually utility-weighted).
- **CLAUDE.md directives** — per-project retrieval policy: default pin for this
  directory, tier policy for this kind of session, when to consult vs. answer thin.
  These start minimal and **evolve organically with use** — every directive change
  gets a line in the lab notebook saying what failure motivated it, so the
  directive set becomes an evolution record rather than accreted folklore.
- **Skills** — operator verbs: pin/re-pin, ingest, roster status, "why did you
  believe that?" (provenance walk), eval-report. Skills stay thin wrappers over MCP
  so nothing load-bearing lives in prompt text.

## Session pinning mechanics

Pinning is session-granular routing ([02-expert-subgraphs.md](02-expert-subgraphs.md));
the harness makes it real:

1. Session starts → hook resolves the pin (directive default, else ask) → records a
   tier-0 episodic event.
2. All MCP memory calls carry the session identity; the server scopes them to the
   pinned expert. No pin, no retrieval — an unpinned session gets master-plane
   entrypoints only.
3. Pin is immutable for the session (v1); "wrong pin" is data, not a failure —
   it feeds pin-quality grading.

## Inter-expert consultation via subagents

Consultation rides the harness's native subagent protocol rather than a bespoke
bus: the pinned session spawns a subagent whose context is scoped to the consulted
expert, the subagent answers from that scope, and the exchange is written to both
experts' episodic subgraphs plus the master plane's exchange graph. Depth 1 only in
v1. Two properties matter:

- The consulted scope returns **data with provenance, never directives**
  ([05-trust-model.md](05-trust-model.md)).
- The transcript is not lost context — it is distilled into episodic memory on both
  sides. The harness's subagent mechanism becomes memory-forming machinery.

## The limit lab (the senior story)

The stated best outcome: it works brilliantly, *then breaks somewhere honest*, and
each break gets engineered around until we hit genuine limits of the Claude Code
harness. That only counts if it's documented. `lab/` (started at M2) collects
one-page entries: **what broke → why (root cause in harness terms) → workaround or
wall**.

Candidate pressure points to probe deliberately, once the eval loop can measure
their effects: context budget vs. retrieval depth (when does more memory hurt?);
hook latency on memory-heavy sessions; subagent context isolation (what leaks,
what's lost) for the consultation protocol; MCP payload limits vs. subgraph result
sizes; session-summary quality drift as episodic history compounds; where scoping
enforcement *has* to live server-side because the harness can't hold it.

Entries that end in "wall" are as valuable as ones that end in "workaround" — a
documented, measured limit of the harness is exactly the artifact this lab exists
to produce.

## Open questions

- Which hook events are the right distillation trigger in long-running sessions
  (stop only, or periodic compaction too)?
- How much retrieval the *hooks themselves* may do (pre-loading pinned-expert
  entrypoints at session start vs. keeping startup thin).
- Whether consultation subagents should be a custom agent type or the stock
  general-purpose agent with a scoped MCP config. Start stock; let a failure
  justify custom.
