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
| [09-schema-and-federation.md](09-schema-and-federation.md) | The ported schema vs. the contract: 7 gaps, sequencing, decisions | 🏗️ implementing — G2/G3/G6/G7 closed at M0.5 | 2026-07-14 |
| [10-evidence-archive.md](10-evidence-archive.md) | Retained transcripts as the floor of the provenance chain; the two-stage bootstrap | 🏗️ implementing — stage 1 built | 2026-07-14 |
| [appendix/interactive-memory-graph-spec.md](appendix/interactive-memory-graph-spec.md) | As-built spec for the viewer (historical; predates Thalamus) | 📦 shipped | 2026-07-10 |

Status legend: 💭 idea → ✅ drafted → 🔍 reviewed → 🏗️ implementing → 📦 shipped
(doc reflects built reality). A doc doesn't reach 📦 until the code exists and the
doc has been corrected against it.

## Milestones

| Milestone | Deliverable | Status |
|---|---|---|
| M0 | Port base graph memory system into this repo | ✅ **done** (2026-07-14) — 18 Python + 7 frontend tests green; MCP server, CLI, viewer all run |
| M0.5 | Federation-ready schema: provenance envelope, scope, stable IDs, unified `Claim`, type registry | ✅ **done** (2026-07-14) — 40 Python + 10 frontend tests green. Gaps G1(partial), G2, G3, G6, G7 closed; see [09](09-schema-and-federation.md). |
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
| 2026-07-14 | **`Artifact` is global** — one shared vertex per identifier, the only unscoped node type | Artifacts are the join key between scopes and much of why the main plane is connective at all; they're tier-1 observations of the operator's own repo, so sharing them is not a poisoning vector. **Consequence:** the cross-scope density metric must count *direct edges between scoped nodes only* — paths through shared Artifacts would otherwise make every expert that touched the same repo look densely connected, confounding [08](08-roster-candidates.md)'s split/merge signal. See [09](09-schema-and-federation.md) G3. |
| 2026-07-14 | **`project` and `scope` are orthogonal axes; both survive** | `project` = which repo, `scope` = which expert. [08](08-roster-candidates.md)'s "Serves" column is the many-to-many between them. Session/Thread/Claim carry both; Artifact carries `project` only. |
| 2026-07-14 | **Transcripts are retained as tier-1 `Source` nodes; the graph is a materialized view over an immutable log** | Three reasons, ascending in force. (a) The provenance chain had **no floor**: a tier-1 claim's source pointed at a Session whose stored content is a *summary of itself*, so [03](03-master-plane.md)'s inspector terminated in fog. (b) It makes **extraction reversible** — [04](04-eval-loop.md) demands that of *forgetting*, but extraction was the lossy irreversible step and nobody had noticed; now a bad skill or a changed schema means re-extract, not migrate. (c) [04](04-eval-loop.md)'s used-vs-ignored attribution is defined against "the session's outputs", which **are** the transcript — the eval loop is *impossible* without it. See [10](10-evidence-archive.md). |
| 2026-07-14 | Locators are **anchors on the edge** (message UUIDs), not `Chunk` nodes | Answers "where in the transcript" without a ~100× node explosion. Chunk nodes only earn their keep with per-chunk retrieval or embeddings, which [00](00-mission.md)'s non-goals rule out for now. |
| 2026-07-14 | The archive lives **outside the repo** (`~/.thalamus/archive/`), scanned but **never redacted** | Transcripts are the highest-risk artifact in the project — the first run found 13 occurrences of the signed database licence key inside this repo's own transcript, *after* it had been purged from git. A `.gitignore` is one `git add -f` from a leak. And evidence that has been quietly rewritten is not evidence: the scan warns, the operator decides. |
| 2026-07-14 | **`Decision`/`Problem`/`Solution` become subtypes of `Claim`** — one graph label, discriminated by `kind` | A Decision is an assertion with a rationale from the agent; a literature Claim is an assertion with a citation from a source. Same node, different provenance. This is what makes the trust model expressible (tier as a floor over the `DERIVED_FROM` chain) and collapses contradiction detection into **one** mechanism: "the agent decided X, the literature says not-X" becomes the same query as "expert A and expert B disagree." One label (not one per subtype) so consumers depend on core types only and a new expert's `kind` is not a breaking change. See [09](09-schema-and-federation.md) G1. |
| 2026-07-13 | Crawler **demoted** to minimal curated/manual feed | Commodity component in a saturated genre; sophistication only when measurement pulls for it. |
| 2026-07-13 | Trust model designed in from M1 (provenance fields), enforced at M5 | Retrofitting provenance onto an existing graph is the canonical mistake. |
| 2026-07-13 | No memory-utility claims until counterfactuals run (M4) | The project's whole identity is measuring hard-to-measure quality; it doesn't get to exempt itself. |
| 2026-07-13 | Expert granularity = **spine vs. consultant**, decided by pinning; **split top-down, don't merge bottom-up** | Granularity is instrumented by the collaboration graph, not chosen up front; splitting preserves per-session episodic coherence that merging destroys. See [08](08-roster-candidates.md). |

## Bootstrapping memory

The prior project's memories were deliberately **not** carried over; memory is being
re-derived from this machine's own session transcripts. See
[10-evidence-archive.md](10-evidence-archive.md).

**Stage 1 is built** (`thalamus bootstrap`): transcripts are retained in an immutable,
content-addressed archive at `~/.thalamus/archive/`, and `Source` / `Session` /
`Artifact` / anchored `TOUCHES` are derived from tool-call records with no model in the
loop. Dry run over the real corpus: **62 sessions, ~1,463 nodes, 4.9 seconds, zero
contract rejections.** Stage 2 (model-extracted claims and threads) is deferred to M2.

Allowlisted: `stepmania-chart-generator` (69 transcripts) and `thalamus`. **Not** the
home-directory sessions — they contain résumé/personal history and the media-server work,
which carries VPN credentials.

Ordering was load-bearing, and it is why M0.5 came first: bootstrapping against the old
schema would have produced a corpus with no provenance, tier, or scope — the retrofit
[05](05-trust-model.md) calls the canonical mistake, reached by a different road.

## Backlog / parked ideas

- Consultation depth > 1 (parked until a real failure demands it).
- Auto-pin suggestion from working directory + session history (needs M4 pin-quality data).
- Semantic (non-exact) contradiction detection (post-M6; rabbit-hole risk).
- Agent self-knowledge queries over the master plane's episodic layer.
- Tier-3 (wild) ingestion — possibly never.
