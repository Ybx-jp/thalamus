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
