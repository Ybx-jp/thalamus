# Federation Contract

**Status:** implementing. The manifest is `config/experts/<scope>.yaml` (identity,
tier, declared claim kinds, fetch allowlist — see `contract/manifest.py`), the core
ontology is `contract/ontology.py`, and conformance is enforced twice: at write time
(`check_session`/`check_knowledge`) and against the live graph
(`thalamus contract check`). Query interface and projection grants remain design.

## What it is

The federation contract is the single artifact that governs how any subgraph joins
the system. It is three things at once, and the design refuses to split them:

1. **A data schema** — what node and edge types a subgraph may expose, and the shape
   of the entrypoints it must publish.
2. **A permission system** — what operations a subgraph may perform against other
   parts of the system, especially what it may project into the master plane.
3. **A trust boundary** — the enforcement point for provenance tagging and the
   informs-never-instructs rule (detailed in [05-trust-model.md](05-trust-model.md)).

The one-sentence test: **a new expert subgraph plugs in by conforming to the
contract, with zero bespoke glue.** If integrating expert #2 requires touching code
outside that expert's own package, the contract is wrong — fix the contract, not the
integration.

## Contract surface (v0 sketch)

Every federated subgraph MUST publish:

- **Manifest** — identity, domain description, provenance tier of its content
  sources, declared node/edge types, and the contract version it conforms to.
- **Entrypoints** — the subgraph's equivalents of session summaries and open
  threads: a small, stable set of high-level nodes a consumer can start traversal
  from. No entrypoints, no federation. This generalizes the base system's design:
  entrypoints are *how a graph makes itself legible*.
- **Query interface** — traversal + retrieval over MCP, scoped to the subgraph.
  Cross-subgraph traversal does not exist at this layer (that's an inter-expert
  exchange; see [02-expert-subgraphs.md](02-expert-subgraphs.md)).
- **Provenance obligations** — every node carries origin metadata (source, ingestion
  event, trust tier, timestamp). Contract-invalid nodes are rejected at write time,
  not filtered at read time.
- **Projection grants** — which node/edge types the master plane may project, and at
  what detail level. Projection is pull-based and read-only; a subgraph cannot push
  into the master.

## Node/edge type discipline

The contract defines a small **core ontology** (`contract/ontology.py`: Session,
Claim, Thread, Source, Artifact, Entity and their edges) that all subgraphs share, plus a
namespaced extension mechanism for domain-specific types. Consumers (the agent, the
master plane, the eval loop) may depend on core types only; extension types are
visible but never load-bearing for cross-subgraph features. This is what keeps the
roster hot-swappable.

## Versioning

Contracts version explicitly (`contract/v0`, `contract/v1`, …). A subgraph declares
the version it conforms to; the system federates mixed versions during migration
windows. Breaking the contract is allowed — this is a design-phase project — but it
must be *visible* in the manifest, never silent.

## Why this is the architecturally load-bearing component

Most GraphRAG systems have one graph and an embedding soup around it; "federation"
is usually a euphemism for "we merged the data." Thalamus keeps subgraphs sovereign
and makes the boundary the product. Everything distinctive downstream — the
specialist roster, the trust model, the audit plane — is only possible because the
boundary exists and is enforced. Design pressure on this doc is design pressure on
the whole project.

## Open questions

- Projection grants — which node/edge types the master plane may project per expert,
  and at what detail level. Declared above, unbuilt; blocking for M6.
- A declared (rather than hardcoded) query interface per subgraph.
