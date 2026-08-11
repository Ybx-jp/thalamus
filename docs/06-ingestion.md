# Ingestion — Feeds for Expert Subgraphs

**Status:** v0 shipped — `thalamus ingest <url|file>`,
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

## v0: curated, manual-first

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
literature expert.

1. **One consultant, per-project feeds.** Papers serving another project go into
   the existing literature expert under a project-named feed
   (`thalamus ingest <url> --feed stepmania-chart-generator`), never into a new
   scope — docs/08: technical-literature is a consultant serving everything, and
   splitting happens top-down only when retrievals measurably bifurcate. Feed
   identity persists on the Source vertex, so "what was procured for project X"
   stays a one-hop query and the eval loop can attribute knowledge utility per feed.
   *Scope note:* this rule forbids scopes created as a side effect of
   procurement, not scopes created as deliberate roster decisions — a new expert
   declared in docs/08's terms with its own manifest (e.g. `eval-methodology`)
   procures its anchors into its own scope, because a scope with nothing to cite
   refuses the consultation mint (docs/02). A manifest's `claim_kinds` must be
   kinds its feed actually writes (the ingest extractor writes
   `literature/finding|technique`); declaring kinds no writer produces makes the
   manifest aspirational, and the contract rejects the batch.
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
4. **Feed the full text, not the landing page.** For arXiv, ingest
   `arxiv.org/html/<id>`; `/abs/<id>` is a landing page whose only prose is the
   abstract, so it yields abstract-level claims and the paper's actual numbers —
   distributions, ablations, effect sizes — never enter the graph. The failure is
   silent: extraction succeeds, the title resolves, the claim count looks normal,
   and the gap only surfaces when an expert is asked for a figure it cannot cite.
   Where no HTML rendering exists, hand-feed the relevant sections as a local file
   (`~/.thalamus/hand-fed/`) rather than settling for the abstract.
   **Full text is necessary and not sufficient.** A whole-document pass extracts a
   fixed handful of claims and chooses which — so a paper can be held complete while
   the one mechanism it was procured for never becomes citable. Measured 2026-08-08:
   the CDSS precursor was ingested in full, and neither its trust-evaluation rule nor
   its delegation rule distilled, forcing an expert to quote them from source and cite
   adjacent claims instead. When a *specific* mechanism has to be citable, feed that
   section as its own file. The excerpt's header names the parent file and what the
   pass missed, so the two are never mistaken for independent sources.
   **A document longer than one pass is chunked, not truncated.** Text over the
   ~24,000-character digest budget is split into overlapping ~9,600-char windows and
   each is extracted in its own pass, so the whole document reaches the model. Chunk
   size is a recall decision with a measurement behind it: GraphRAG found GPT-4
   extracting almost twice as many entity references at 600-token chunks as at 2,400
   (`scope:literature:claim:16cd76dd0d63ea12`), so extraction recall falls as chunks
   grow — and a single 24,000-char pass (~6,000 tokens) sits past the right edge of
   that curve. 9,600 chars is the *worse* of the two measured sizes, taken to bound
   claim volume and cost rather than because it is the recall optimum; the overlap
   exists so a claim spanning a boundary is not cut in half, and its size is
   ungrounded — nothing in the literature scope measures overlap or boundary policy.
   Chunked passes thread the document's own entity vocabulary forward (each chunk's
   prompt carries the names earlier chunks minted), which is the cross-article
   convergence feed pointed inward at one document. Claims are **retained, never
   merged** across passes, and entities dedup on exact name only — see
   [11 §3f](11-related-work.md).
   Extraction emits claims and entities as two independent lists and does not keep them
   in step, so a batch can arrive with a claim `about` a name nothing declared, or an
   entity no claim reaches. Both violate the contract, and the contract judges a batch
   whole — one stray name would reject all seventeen passes of a long document. So the
   batch is **narrowed to close it**: the unresolvable reference is dropped from the
   claim that made it, then any entity left unreachable is dropped too, and the run says
   which names it lost. Narrowing only — an unknown name is never resolved by inventing
   a description, because the write path may discard what it cannot verify and never
   manufacture what the model did not assert. A claim stripped of every entity is still
   kept: `about` is a retrieval affordance, not the claim's identity.
   **The run reports what was read**, rather than leaving it to be remembered: every
   ingest prints the extracted text length, and either the number of chunked passes or
   what fraction fell inside the budget, warning with the discarded count when a
   document really is truncated. Payload bytes cannot carry this — markup-to-text
   ratio swings by an order of magnitude, so a 508,263-byte arXiv HTML page and a
   44,256-byte `/abs/` page say nothing about which was read in full (90,025 and 4,862
   chars of text respectively). Section feeds are still the answer for the *specific
   mechanism* case above and wherever no HTML rendering exists; they are no longer the
   default for mere length.
5. **Dry-run, verify, then write.** Every ingest runs without `--write` first and
   the operator confirms the extracted title matches the document intended —
   mis-resolved references are a measured failure mode (docs/10), and the archive
   retains whatever was fetched either way. Since the dry run and the write are two
   fetches, a host serving per-request content mints **two archive entries with
   different hashes for one document** (measured on `pmc.ncbi.nlm.nih.gov`). The
   written Source points at the `--write` fetch, which is the one its claims were
   extracted from, so the pair is a duplicate blob and never a provenance break —
   but do not read two hashes for one URL as evidence the document changed.

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
  staleness and supersession stay visible to the eval loop. The lineage keys on the
  **origin URL within a scope**: a re-fetch of the same URL supersedes the prior head,
  and a fetch of the same document at a *different* URL does not — it writes a second,
  independent Source. Supersession therefore tracks the address, not the work.

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
- A document reached at several addresses writes several Sources, and that is settled
  (decision log, 2026-08-10): **72 arXiv ids hold more than one Source origin**, one
  paper holds four — abstract, full text, and two section excerpts. Convergence between
  an abstract-derived Source and its full-text twin is 5 claims of 436, because claims
  are content-addressed on the description and a claim written from the whole paper is
  a different string. No `SUPERSEDES` edge is written across the address change and none
  should be; a section excerpt is a *proper part* of the work, and one edge cannot mean
  both "richer rendering of" and "excerpt from".

  Both tiers sitting in one flat pool is the configuration RAPTOR chooses for its main
  results (`scope:literature:claim:b035e16d6aa3af7e`), and measured on 1,047 real
  queries the abstract tier takes 17.2% of knowledge slots while never outranking a
  full-text claim. What remains is a tie-break: 15.4% of queries resolve a mixed-tier
  tie by graph iteration order (lab/053). That is a **ranking** question, not an
  ingestion one, and rank-time diversification is where it is open.
- Whether ingestion runs as a skill inside sessions or a standalone CLI. Leaning
  CLI: ingestion shouldn't consume agent context.
