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

## Status

**M0 + M0.5 complete.** The base graph memory system is ported and running, and the
schema is now federation-ready: provenance and trust tiers on every node, expert scoping,
content-addressed claims, and a single-source ontology.

Memory is bootstrapped from **retained session transcripts**, held in an immutable
content-addressed archive that gives the provenance chain a floor
([docs/10](docs/10-evidence-archive.md)).

**The first expert is live (M1):** the technical-literature graph — a scoped knowledge
subgraph of tier-2 `Claim`/`Entity`/`Source` nodes, populated by `thalamus ingest`
(allowlist-gated, evidence-first, contract-gated) and declared by an operator-owned
manifest at `config/experts/literature.yaml`. Recalled knowledge returns blockquoted
with citation and tier: it informs, it never instructs ([docs/05](docs/05-trust-model.md)).

**The eval loop's first layer is live (M2):** every memory-tool call is trace-tapped by
a PostToolUse hook, landed in the graph as `Trace` nodes, and each returned node is
judged used-vs-ignored against the session's retained transcript — crude lexical
attribution, deliberately ([docs/04](docs/04-eval-loop.md)). The numbers say
"instrumented, measuring"; utility claims wait for counterfactuals (M4).

**Still design:** the contract enforces connectivity, provenance, and scope legality, but
there is no manifest, no projection grant, no second expert, and no literature feed.
What exists is a working episodic memory substrate with the boundary drawn, instrumented
from its first expert onward.

- [`docs/index.md`](docs/index.md) — doc tracker, status board, decision log
- [`docs/00-mission.md`](docs/00-mission.md) — mission and high-level design
- [`docs/09-schema-and-federation.md`](docs/09-schema-and-federation.md) — **what the
  ported code owes the contract**: seven concrete gaps and the order to close them
- [`docs/11-related-work.md`](docs/11-related-work.md) — **where Thalamus sits in the
  2026 literature**: per-pillar prior work, what's convergence vs. what survives as
  ours, and the open challenges the research puts to the design

## What's here

```
src/thalamus/
  substrate/   storage kernel — schema, Gremlin writer, Gremlin reader
               (below the contract: knows nodes and edges, not experts or tiers)
  contract/    the federation boundary — the ontology, and the checks a subgraph
               must pass before it may be written
  plane/       the connective plane — FastAPI read layer + React/Cytoscape viewer
  archive/     immutable content-addressed store for retained primary evidence
  harness/     where it meets the agent — MCP server, hooks, skills, transcript bootstrap
  eval/        the eval loop, layer 1 — trace tap reader, used-vs-ignored attribution,
               Trace-node sync, per-scope utility report
frontend/      viewer source; builds into plane/static
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
thalamus ingest <url|file>         # feed one document to the literature expert
thalamus visualize                 # open the persisted memory explorer
thalamus visualize session.yaml    # preview a pending extraction, no graph needed
thalamus write session.yaml        # write to the graph
thalamus eval sync --write         # land retrieval traces + used-vs-ignored verdicts
thalamus eval report               # per-scope retrieval-utility numbers
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
        "THALAMUS_SCOPE": "main"
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
The session-start hook asks the agent for the current project's open threads; it is the
mechanism that generalizes into **expert pinning**
([docs/02](docs/02-expert-subgraphs.md)).

## Bootstrapping from transcripts

Claude Code persists every session as JSONL. `thalamus bootstrap` retains those in an
immutable, content-addressed archive and derives memory from them:

- **Stage 1 (built, no model):** `Source`, `Session`, `Artifact`, and `TOUCHES` edges
  **anchored to the exact messages** that touched each file — recovered from tool-call
  records. Exact and free; an LLM would only add error. 62 sessions in ~5s.
- **Stage 2 (deferred):** `Claim`s and `Thread`s, which genuinely need judgement.

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
`DERIVED_FROM`. Declared once in
[`contract/ontology.py`](src/thalamus/contract/ontology.py); everything else derives
from it. Run `thalamus schema` for the JSON schema.

Three properties are load-bearing:

- **Claims are one label, discriminated by `kind`.** Decisions, problems, and solutions
  are claim *subtypes*, not sibling labels. A decision is an assertion with a rationale
  from the agent; a literature claim is an assertion with a citation from a source —
  same node, different provenance. Consumers query `Claim`, so a future expert adding
  `kind: literature/finding` breaks nobody. Claim identity is **content-addressed**, so
  the same claim in two sessions converges on one node.
- **Every node carries provenance** — trust tier, source, ingestion time — and
  `DERIVED_FROM` edges make effective trust the *floor* over a node's derivation chain.
  Distillation does not launder.
- **`Source` is retained primary evidence** — a transcript today, a paper at M1. Same node
  type; only the tier differs. It is the floor of the provenance chain, and `DERIVED_FROM`
  edges carry `anchors`: the precise messages a belief came from.
- **Every node carries a scope, except `Artifact`.** Scope is which *expert*; `project`
  is which *repo*; they are orthogonal. `Artifact` is deliberately **global** — one
  vertex per identifier, shared by every scope. It is the join key between experts.

Orphans are rejected at write time, not filtered at read time. `thalamus validate` runs
the full contract check.

Still missing (this is the **episodic half** of an expert): the knowledge-side ontology
— entities and sources, and a feed to populate them. See
[docs/09](docs/09-schema-and-federation.md).

## Development

```bash
.venv/bin/pytest              # 48 tests
.venv/bin/ruff check src tests
cd frontend && npm test       # 10 tests
cd frontend && npm run build  # -> src/thalamus/plane/static
```
