# Thalamus

**Federated graph memory for coding agents — with a trust model and a measured utility loop.**

In the brain, the thalamus is the relay: nearly every signal bound for a specialized
cortical region passes through it, and it gates what gets through. Same job here.
Specialist knowledge lives in **expert subgraphs** (a curated domain graph + its own
episodic memory), federated behind a **schema contract** that is simultaneously a data
schema, a permission system, and a trust boundary. The **master plane** — the main
session scope, dense and connective, which references expert nodes but never copies
them — gives the human full observability into everything the agent remembers,
believes, and retrieved, with provenance down to the ingestion event. An **eval loop**
measures whether any of it actually makes the agent better.

## What's live

- **The substrate**: a property graph (TinkerGraph) of `Session` / `Claim` /
  `Thread` / `Source` / `Artifact` nodes, every one carrying provenance (trust tier,
  source, ingestion time) and a scope. Orphans and contract violations are rejected
  at write time ([docs/09](docs/09-schema-and-federation.md)).
- **The evidence archive**: memory is bootstrapped from retained session transcripts,
  held in an immutable content-addressed archive outside the repo. The graph is a
  materialized view over that log — re-extract, never migrate
  ([docs/10](docs/10-evidence-archive.md)).
- **Two experts**: technical-literature and evaluation-methodology, each declared by
  an operator-owned manifest in `config/experts/` and nothing else — the zero-glue
  contract test ([docs/01](docs/01-federation-contract.md),
  [docs/02](docs/02-expert-subgraphs.md)). Knowledge is fed by `thalamus ingest`
  (allowlist-gated, evidence-first) and returns blockquoted with citation and tier:
  it informs, it never instructs ([docs/05](docs/05-trust-model.md)).
- **Session pinning**: one OS process = one immutable pin. `thalamus pin` / `thalamus
  roster` launch scope-pinned sessions; the MCP server reads the scope from its
  environment at startup and no tool accepts a scope argument
  ([docs/07](docs/07-harness-integration.md)).
- **The consultation protocol**: cross-expert questions ride single-use tickets where
  minting the ticket *is* writing the exchange record, and answers must cite nodes
  inside the consulted scope ([docs/02](docs/02-expert-subgraphs.md)).
- **The eval loop, layers 1 + 1b**: every memory-tool call is trace-tapped, landed as
  `Trace` nodes, judged used-vs-ignored against the session's retained transcript,
  and priced in injected tokens — decay candidates rank by wasted tokens
  ([docs/04](docs/04-eval-loop.md)). Utility claims wait for counterfactuals.
- **First trust enforcement**: the transcript-ingress floor down-tiers distilled
  claims that rest on fetched web content, so a poisoned page can't launder into
  tier-1 memory ([docs/05](docs/05-trust-model.md)).

Start at [`docs/index.md`](docs/index.md) — doc tracker, status board, milestone
table, and the binding decision log. [`docs/11-related-work.md`](docs/11-related-work.md)
places the design in the 2026 literature.

## What's here

```
src/thalamus/
  substrate/   storage kernel — schema, Gremlin writer, Gremlin reader
               (below the contract: knows nodes and edges, not experts or tiers)
  contract/    the federation boundary — the ontology, expert manifests, and the
               checks a subgraph must pass before it may be written
  plane/       the connective plane — FastAPI read layer + React/Cytoscape viewer
  archive/     immutable content-addressed store for retained primary evidence
  harness/     where it meets the agent — MCP server, hooks, skills, transcript bootstrap
  eval/        the eval loop — trace tap reader, used-vs-ignored attribution,
               Trace-node sync, per-scope utility and cost reports
frontend/      viewer source; builds into plane/static
config/        expert manifests (tier-0, operator-owned)
docs/          design docs
lab/           harness-limit notebook — what broke, why, workaround or wall
```

Both **Claude Code** and **Cursor** are supported; their hook contracts differ, so
there is one hook script for each under `src/thalamus/harness/hooks/`.

## Quick start

Requires Docker and Python ≥3.11.

```bash
# 1. TinkerGraph needs an enterprise feature key (a free single-node dev key
#    exists). Keep it OUT of the repo — config/features.conf is gitignored.
export THALAMUS_FEATURE_KEY=/path/to/features.conf     # or drop it at config/features.conf

# 2. Infrastructure
docker compose up -d

# 3. Install
uv sync                        # or: python -m venv .venv && .venv/bin/pip install -e '.[dev]'

# 4. Use it
thalamus bootstrap                 # list session transcripts available to ingest
thalamus bootstrap -- <project>    # dry-run: retain + extract (add --write to persist)
thalamus validate session.yaml     # check an extraction against the contract
thalamus contract check            # audit the live graph against the contract
thalamus ingest <url|file>         # feed one document to an expert (dry-run; --write to persist)
thalamus pin <scope>               # launch a claude session pinned to an expert
thalamus roster                    # one pinned tmux window per expert (plus main)
thalamus visualize                 # open the persisted memory explorer
thalamus visualize session.yaml    # preview a pending extraction, no graph needed
thalamus write session.yaml        # write to the graph
thalamus eval sync --write         # land retrieval traces + used-vs-ignored verdicts
thalamus eval report               # per-scope retrieval-utility numbers, priced
thalamus eval cost                 # session/operation token-cost buckets
thalamus-mcp                       # run the MCP server
```

TinkerGraph data lives in the named `thalamus-graph-data` Docker volume and survives
restarts. Don't `docker compose down -v` unless you mean to delete the graph.

## MCP tools

| Tool | Input | Purpose |
|---|---|---|
| `memory_recall` | `query`, `limit` | Keyword search across session memories |
| `memory_recall_by_artifact` | `identifier`, `limit` | Sessions that touched a file/class/dep |
| `memory_recall_by_project` | `project`, `limit` | Recent sessions for a project |
| `memory_recall_recent` | `limit` | Most recent sessions |
| `memory_open_threads` | `project`, `limit` | Active continuation points — **the entrypoint** |
| `memory_thread` | `thread_id` | Full context on one thread |
| `memory_query` | `query` | One read-only Gremlin traversal (main scope only) |
| `consult_request` | `expert`, `question` | Mint a consultation ticket = open the exchange record |
| `consult_answer` | `ticket`, `answer` | Close a consultation; citations validated, ticket burned |
| `memory_visualize` | `session_yaml` | Mermaid render of a pending extraction |
| `memorize` | `session_yaml` | Write an extraction to the graph |

Register the server (`.mcp.json` for Claude Code, `.cursor/mcp.json` for Cursor):

```json
{
  "mcpServers": {
    "thalamus": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/thalamus", "thalamus-mcp"],
      "env": {
        "THALAMUS_GRAPH_URL": "ws://localhost:8182/gremlin",
        "THALAMUS_SCOPE": "${THALAMUS_SCOPE:-main}"
      }
    }
  }
}
```

**`THALAMUS_SCOPE` is the session's pin, and no tool accepts a scope argument.** The
server decides what the session can see; the model cannot widen its own view by asking,
and `memorize` writes to the pinned scope regardless of what the extraction claims. That
is deliberate — [docs/07](docs/07-harness-integration.md) requires scope enforcement to
live server-side, because the model is never trusted to self-limit its own retrieval
scope.

## The loop

```
Session ends → extract (skill) → validate → memorize
                                                ↓
New session → session-start hook → memory_open_threads → context
```

The extraction skill is at `src/thalamus/harness/skills/extract-session/SKILL.md`.
The session-start hook asks the agent for the current project's open threads, and it
is the same mechanism that carries **expert pinning**
([docs/02](docs/02-expert-subgraphs.md)).

## Bootstrapping from transcripts

Claude Code persists every session as JSONL. `thalamus bootstrap` retains those in an
immutable, content-addressed archive and derives memory from them:

- **Stage 1 (deterministic, no model):** `Source`, `Session`, `Artifact`, and `TOUCHES`
  edges **anchored to the exact messages** that touched each file — recovered from
  tool-call records. Exact and free; an LLM would only add error.
- **Stage 2 (`thalamus extract`):** `Claim`s and `Thread`s, which genuinely need
  judgement — extracted via headless `claude -p`, replayed chronologically so threads
  resolve forward in time.

The retained transcript is what gives the provenance chain a **floor** — without it, a
belief's source is a Session whose content is a summary of itself. It also makes
extraction *reversible*: the graph is a materialized view over an immutable log, so a
better skill or a changed schema means re-extract, not migrate. See
[docs/10](docs/10-evidence-archive.md).

⚠️ **Transcripts contain whatever was on screen, credentials included.** The archive lives
at `~/.thalamus/archive/` — outside the repo, not merely gitignored. `bootstrap` scans for
secrets and **reports**; it never redacts, because evidence that has been quietly
rewritten is not evidence.

## Schema

Five node types — `Session`, `Claim`, `Thread`, `Source`, `Artifact` — joined by
`CONTAINS` / `TOUCHES` / `SPAWNS` / `BLOCKS` / `CONTINUES` / `RESOLVES` / `SOLVED_BY` /
`DERIVED_FROM`, plus the knowledge side an expert manifest declares (`Entity`,
literature claims, `KnowledgeBatch`) and the eval loop's `Trace` / `Exchange` records.
Declared once in [`contract/ontology.py`](src/thalamus/contract/ontology.py);
everything else derives from it. Run `thalamus schema` for the JSON schema.

Four properties are load-bearing:

- **Claims are one label, discriminated by `kind`.** Decisions, problems, and solutions
  are claim *subtypes*, not sibling labels. A decision is an assertion with a rationale
  from the agent; a literature claim is an assertion with a citation from a source —
  same node, different provenance. Consumers query `Claim`, so a future expert adding
  `kind: literature/finding` breaks nobody. Claim identity is
  **(kind, normalized description)**, so the same claim in two sessions converges on
  one node.
- **Every node carries provenance** — trust tier, source, ingestion time — and
  `DERIVED_FROM` edges make effective trust the *floor* over a node's derivation chain.
  Distillation does not launder.
- **`Source` is retained primary evidence** — a transcript or an ingested paper. Same
  node type; only the tier differs. It is the floor of the provenance chain, and
  `DERIVED_FROM` edges carry `anchors`: the precise messages a belief came from.
- **Every node carries a scope, except `Artifact`.** Scope is which *expert*; `project`
  is which *repo*; they are orthogonal. `Artifact` is deliberately **global** — one
  vertex per identifier, shared by every scope. It is the join key between experts.

Orphans are rejected at write time, not filtered at read time. `thalamus validate` runs
the full contract check.

## Development

```bash
uv run pytest
uv run ruff check src tests
cd frontend && npm test
cd frontend && npm run build  # -> src/thalamus/plane/static
```
