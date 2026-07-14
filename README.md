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

**M0 complete** — the base graph memory system is ported and running. **Everything
that makes Thalamus *Thalamus* is still design**: there is no contract, no provenance,
no trust tier, no expert scoping, and no knowledge-side ontology yet. What exists is a
working episodic memory substrate.

- [`docs/index.md`](docs/index.md) — doc tracker, status board, decision log
- [`docs/00-mission.md`](docs/00-mission.md) — mission and high-level design
- [`docs/09-schema-and-federation.md`](docs/09-schema-and-federation.md) — **what the
  ported code owes the contract**: seven concrete gaps and the order to close them

## What's here

```
src/thalamus/
  substrate/   storage kernel — schema, Gremlin writer, Gremlin reader
               (below the contract: knows nodes and edges, not experts or tiers)
  contract/    the federation boundary — today, one conformance check
               (this is where the M1 work lands)
  plane/       the connective plane — FastAPI read layer + React/Cytoscape viewer
  harness/     where it meets the agent — MCP server, hooks, skills
frontend/      viewer source; builds into plane/static
docs/          design docs
lab/           harness-limit notebook (starts at M2)
```

Both **Claude Code** and **Cursor** are supported; their hook contracts differ, so
there is one hook script for each under `src/thalamus/harness/hooks/`.

## Quick start

Requires Docker and Python ≥3.11.

```bash
# 1. TinkerGraph needs an enterprise feature key (a free single-node dev key
#    exists). Keep it OUT of the repo — config/features.conf is gitignored.
export THALAMUS_FEATURE_KEY=/path/to/features.conf     # see config/features.conf.example

# 2. Infrastructure
docker compose up -d

# 3. Install
uv sync                        # or: python -m venv .venv && .venv/bin/pip install -e '.[dev]'

# 4. Use it
thalamus validate session.yaml     # check an extraction against the schema
thalamus visualize                 # open the persisted memory explorer
thalamus visualize session.yaml    # preview a pending extraction, no graph needed
thalamus write session.yaml        # write to the graph
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
      "env": { "THALAMUS_GRAPH_URL": "ws://localhost:8182/gremlin" }
    }
  }
}
```

## The loop

```
Session ends → extract (skill) → validate → memorize
                                                ↓
New session → session-start hook → memory_open_threads → context
```

The extraction skill is at `src/thalamus/harness/skills/extract-session/SKILL.md`.
The session-start hook asks the agent for the current project's open threads; it is
the mechanism that generalizes into **expert pinning**
([docs/02](docs/02-expert-subgraphs.md)).

## Schema

`Session`, `Artifact`, `Decision`, `Problem`, `Solution`, `Thread`, joined by
`CONTAINS` / `TOUCHES` / `SPAWNS` / `BLOCKS` / `CONTINUES` / `RESOLVES` / `SOLVED_BY`.
Every node must have at least one edge — orphans are rejected at write time, not
filtered at read time. Run `thalamus schema` for the JSON schema.

This is the **episodic half** of what the design calls an expert. The knowledge half
(claims, entities, sources — with provenance and trust tiers) does not exist yet; see
[docs/09](docs/09-schema-and-federation.md).

## Development

```bash
.venv/bin/pytest              # 18 tests
cd frontend && npm test       # 7 tests
cd frontend && npm run build  # -> src/thalamus/plane/static
```
