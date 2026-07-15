# Ingestion — Feeds for Expert Subgraphs

**Status:** v0 shipped (M1, 2026-07-15) as designed below — `thalamus ingest <url|file>`,
allowlist-gated by the expert manifest, evidence-first (archive before extraction),
model-extracted claims/entities, contract-gated writes. PDFs refused, not half-parsed.
Deliberately the **smallest** component in the system.

## Position: the crawler is a data feed, not the project

"Crawl papers and RAG over them" is the most saturated demo genre in the field; the
crawler earns zero differentiation and carries real plumbing cost (fetching, dedup,
PDF parsing, rate limits). Thalamus therefore demotes ingestion to the minimum that
populates an expert subgraph, and it stays demoted until something downstream —
the eval loop showing stale coverage, an expert with demonstrated utility but thin
knowledge — *demands* more. Sophistication here is pulled by measurement, never
pushed by enthusiasm.

## v0: curated, manual-first (M1)

The first feed populates the technical-literature expert:

- **Allowlisted sources only** (tier 2 — see [05-trust-model.md](05-trust-model.md)):
  a short, operator-maintained list of publishers/feeds relevant to active projects
  and learning efforts (agent-memory literature, RAG evaluation, harness
  engineering, audio ML, …).
- **Manual ingestion is a first-class path, not a stopgap:** `thalamus ingest <url>`
  — the operator finds something worth remembering and feeds it in. Weeks of
  real usage can run on this alone, and probably should: manual curation *is*
  tier-2 trust in practice.
- **Extraction over archival:** an ingested article becomes a small set of typed
  nodes — claims, techniques, references, links to entities already in the graph —
  not a blob with an embedding. Graph-first is the point; if a document only ever
  needs similarity search, it doesn't need Thalamus.

## Procurement protocol (v0.1 — multi-project curation into one expert)

How source material is chosen and fed when several projects draw on the same
literature expert. Added 2026-07-15 alongside the first stepmania/nodeglass feeds.

1. **One consultant, per-project feeds.** Papers serving another project go into
   the existing literature expert under a project-named feed
   (`thalamus ingest <url> --feed stepmania-chart-generator`), never into a new
   scope — docs/08: technical-literature is a consultant serving everything, and
   splitting happens top-down only when retrievals measurably bifurcate. Feed
   identity persists on the Source vertex, so "what was procured for project X"
   stays a one-hop query and the eval loop can attribute knowledge utility per feed.
2. **Demand-driven selection.** A document earns ingestion by bearing on a question
   the project has actually asked — an open thread, a recorded problem, a design
   decision in flight. Procure against the target project's open threads, not
   against the operator's reading list; "interesting" is a tier-3 instinct wearing
   tier-2 clothes.
3. **Entity hygiene is the linking discipline.** Articles relate to each other only
   through shared Entity vertices, so ingestion feeds the scope's existing entity
   names into the extraction prompt (the same convergence mechanism as the episodic
   known-claims feed). When curating a batch for a new domain, ingest the anchor
   document first — it mints the entity vocabulary the rest of the batch converges on.
4. **Dry-run, verify, then write.** Every ingest runs without `--write` first and
   the operator confirms the extracted title matches the document intended —
   mis-resolved references are a measured failure mode (docs/10), and the archive
   retains whatever was fetched either way.

## Contract obligations (every feed, forever)

Ingestion is a federation-contract client like everything else:

- Every node written carries **full provenance**: source URL, retrieval timestamp,
  feed identity, trust tier. No provenance, no write — rejected at the contract,
  not cleaned up later.
- Feeds write **only into their designated expert's knowledge subgraph** — never
  into episodic memory, never toward the master plane.
- Ingested content is **data**: nothing a feed writes can carry directives
  (informs-never-instructs is enforced from the first node).
- Re-ingestion of a changed source creates a **new version linked to the old**, so
  staleness and supersession stay visible to the eval loop.

## Later, only if pulled

Roughly in order of likely demand, each gated on a measured need:

1. Scheduled refresh of allowlisted feeds (staleness flags from the eval loop).
2. Reference-chasing one hop out from high-utility nodes (a paper's citations),
   still within the allowlist tiering rules.
3. New feed types for new experts (e.g., repo/PR ingestion for a code-context
   expert — Nodeglass-GraphRAG's ingestion experience is directly reusable here).
4. Anything tier-3 (wild crawling) — possibly never; see the trust model's open
   question on whether v1 wants tier 3 at all.

## Open questions

- Extraction quality: how much structure per article is worth it at M1? Start with
  title/claims/refs and let retrieval-utility data argue for more.
- Dedup across feeds (same paper, two sources) — content-hash first, fancy later.
- Whether ingestion runs as a skill inside sessions or a standalone CLI. Leaning
  CLI: ingestion shouldn't consume agent context.
