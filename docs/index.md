# Thalamus — Doc Index & Status Board

Design docs for Thalamus: federated graph memory for coding agents, with a trust
model and a measured utility loop. Start at [00-mission.md](00-mission.md).

## Docs

| Doc | Covers | Status | Last touched |
|---|---|---|---|
| [00-mission.md](00-mission.md) | Mission, high-level design, principles, milestone ladder | ✅ drafted | 2026-07-13 |
| [01-federation-contract.md](01-federation-contract.md) | The schema contract: data schema + permissions + trust boundary | ✅ drafted | 2026-07-13 |
| [02-expert-subgraphs.md](02-expert-subgraphs.md) | Specialist roster, session pinning, inter-expert subagent protocol | ✅ drafted | 2026-07-13 |
| [03-master-plane.md](03-master-plane.md) | The main scope: connective plane, observability → audit, contradiction surface | 🔍 revised (no-copy, not no-store) | 2026-07-14 |
| [04-eval-loop.md](04-eval-loop.md) | Retrieval traces, counterfactuals, utility-driven forgetting | ✅ drafted | 2026-07-13 |
| [05-trust-model.md](05-trust-model.md) | Provenance tiers, write-gating, memory-poisoning defense | ✅ drafted | 2026-07-13 |
| [06-ingestion.md](06-ingestion.md) | Curated feeds; the crawler, deliberately demoted | ✅ drafted | 2026-07-13 |
| [07-harness-integration.md](07-harness-integration.md) | MCP / hooks / CLAUDE.md / skills, pinning mechanics, the limit lab | ✅ drafted | 2026-07-13 |
| [08-roster-candidates.md](08-roster-candidates.md) | Granularity rule (spine vs. consultant), skill-vs-expert boundary, parked candidate list | ✅ drafted | 2026-07-13 |
| [09-schema-and-federation.md](09-schema-and-federation.md) | The ported schema vs. the contract: 7 gaps, sequencing, open questions | ✅ drafted (written against real code) | 2026-07-14 |
| [appendix/interactive-memory-graph-spec.md](appendix/interactive-memory-graph-spec.md) | As-built spec for the viewer (historical; predates Thalamus) | 📦 shipped | 2026-07-10 |

Status legend: 💭 idea → ✅ drafted → 🔍 reviewed → 🏗️ implementing → 📦 shipped
(doc reflects built reality). A doc doesn't reach 📦 until the code exists and the
doc has been corrected against it.

## Milestones

| Milestone | Deliverable | Status |
|---|---|---|
| M0 | Port base graph memory system into this repo | ✅ **done** (2026-07-14) — 18 Python + 7 frontend tests green; MCP server, CLI, viewer all run |
| M0.5 | Provenance envelope + scope segment + stable claim IDs, before more data lands | ⬜ not started — [09](09-schema-and-federation.md); cheap now, expensive later |
| M1 | Federation contract v0 + literature expert (curated/manual ingest) | ⬜ not started |
| M2 | Retrieval instrumentation + eval loop v0; start `lab/` notebook | ⬜ not started |
| M3 | Second expert + session pinning + consultation protocol (**two proves N**) | ⬜ not started |
| M4 | Counterfactual harness + utility-driven maintenance | ⬜ not started |
| M5 | Trust-model enforcement + canary red-team pass | ⬜ not started |
| M6 | Master-plane visualizer + end-to-end audit chains | ⬜ not started |

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-07-13 | Name: **Thalamus** | The brain's gating relay to specialized cortex — routing, gating, and federation in one metaphor; matches the project's anchor concepts (substrate, structural, gating). |
| 2026-07-13 | Routing = **session-granular expert pinning**, not per-query classification | Human-legible, honest to how coding sessions work, keeps episodic memory coherent per expert; pin quality is graded by the eval loop instead of trusting a router. |
| 2026-07-13 | Inter-expert communication rides the **harness subagent protocol**, exchanges preserved as episodic memory on both sides | No bespoke bus; consultations become first-class memory events and form a collaboration graph. |
| 2026-07-13 | ~~Master plane is a **read-only projection** (god-object constraint)~~ **Superseded 2026-07-14** | Copying memories upward would make every contract and trust boundary decorative. |
| 2026-07-14 | Master plane is **`scope=main`**: a real session scope with its own episodic memory. The surviving constraint is **no-copy, not no-store** — it references expert nodes by ID. Its distinction is **topological**: dense/connective vs. experts as sparse leaves. | "Owns nothing" was overstated — sessions in the main scope, and direct conversations with expert subagents, are real sessions producing memory worth keeping. The topological claim is strictly better because it is *measurable* (cross-scope edge density), which turns [08](08-roster-candidates.md)'s split/merge rule from a judgment call into a number. See [03](03-master-plane.md), [09](09-schema-and-federation.md). |
| 2026-07-14 | **One graph store**, expert scoping by `expert_id`/`scope` on nodes and in VIDs; the contract is enforced in a layer *above* the substrate | Sovereignty pulls toward separate stores, but [08](08-roster-candidates.md)'s split/merge discipline needs cheap logical repartitioning. One store keeps split/merge cheap; enforcing the boundary above the substrate (and never letting substrate code see across a scope) keeps it load-bearing and mechanically testable. |
| 2026-07-14 | **M0.5 inserted**: provenance + scope + stable IDs land before M1 writes data | [05](05-trust-model.md) already says retrofitting provenance is "the canonical mistake." The graph currently holds a handful of dev sessions — the migration is ~a day now and grows linearly with every session written. |
| 2026-07-13 | Crawler **demoted** to minimal curated/manual feed | Commodity component in a saturated genre; sophistication only when measurement pulls for it. |
| 2026-07-13 | Trust model designed in from M1 (provenance fields), enforced at M5 | Retrofitting provenance onto an existing graph is the canonical mistake. |
| 2026-07-13 | No memory-utility claims until counterfactuals run (M4) | The project's whole identity is measuring hard-to-measure quality; it doesn't get to exempt itself. |
| 2026-07-13 | Expert granularity = **spine vs. consultant**, decided by pinning; **split top-down, don't merge bottom-up** | Granularity is instrumented by the collaboration graph, not chosen up front; splitting preserves per-session episodic coherence that merging destroys. See [08](08-roster-candidates.md). |

## Backlog / parked ideas

- Consultation depth > 1 (parked until a real failure demands it).
- Auto-pin suggestion from working directory + session history (needs M4 pin-quality data).
- Semantic (non-exact) contradiction detection (post-M6; rabbit-hole risk).
- Agent self-knowledge queries over the master plane's episodic layer.
- Tier-3 (wild) ingestion — possibly never.
