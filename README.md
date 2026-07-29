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

## Quick start

**Your graph starts empty and stays yours.** Thalamus ships no seed graph, no
export and no fixture corpus — a graph is one operator's session history, so
every install is fresh, for everyone. Memory accumulates as you work.

### Prerequisites

| | Why |
|---|---|
| **Docker** | runs the graph (Gremlin Server on TinkerGraph) |
| **Python ≥3.11** and [**uv**](https://docs.astral.sh/uv/) | the package and its CLI |
| **jq** | every hook parses its stdin with it; without it the hook layer dies silently |
| **A coding-agent CLI** — Claude Code (`claude`), Cursor (`agent`), or both | distillation shells out to it. Sessions from a harness whose CLI is missing will retrieve and trace, but never become memory |

### Install

```bash
git clone https://github.com/Ybx-jp/thalamus && cd thalamus

docker compose up -d           # the graph, on 127.0.0.1:8182 — no licence, no account
uv sync --extra dev            # or: python -m venv .venv && .venv/bin/pip install -e '.[dev]'
thalamus init                  # wire both editors, then verify what it wired
```

`thalamus init` installs at **user scope**, so the harness arms in every
directory rather than only inside this checkout. It wires Claude Code and Cursor
by default; use `--harness claude` or `--harness cursor` for one. `--dry-run`
reports without writing, and `--check` re-verifies any time.

### Read what it tells you

Install ends by *exercising* what it wired rather than asserting it — it spawns
the real interpreter from a foreign directory, round-trips the Cursor injection
spool, and reads each skill back through its user-scope path:

```
Verification (exercised, not assumed):
  ✓ hook scripts present: all 9 wired scripts found
  ✓ distillation entry point: `thalamus` resolves from a foreign cwd
  ✓ graph reachable: 0 vertices at ws://localhost:8182/gremlin (fresh — every install starts empty)
  ! cursor distillation CLI: `agent` not on PATH — cursor sessions will retrieve
    and trace but never distill (install it, or extract with `--harness claude`)
```

Three markers, and the difference matters:

- **`✓`** — verified by running it, not by checking that a file exists.
- **`✗`** — the install itself is broken. Exits non-zero; fix before relying on it.
- **`!`** — an *advisory* about your environment, with the command that fixes it.
  Install wires configuration; it does not start your containers or install other
  vendors' binaries. Advisories never fail the install, and a graph reporting
  **0 vertices is a pass** — that is what a fresh install looks like.

### Then relaunch your editor

Hooks and the MCP server arm **per process**, so an already-running session
picks up nothing. Quit and reopen Claude Code or Cursor; `/clear` is not enough.

A new session should greet you with a memory prompt and its pinned scope. From
there, memory builds itself: sessions distill at exit on Claude Code, and
`thalamus extract --harness cursor` sweeps Cursor sessions afterwards
([docs/07](docs/07-harness-integration.md) explains why Cursor is a later sweep).

Working outside this repo is the normal case — that is what user-scope install
buys. See [Command reference](#command-reference) for everything else.

## What's live

- **The substrate**: a property graph (Apache TinkerPop / TinkerGraph) of `Session` / `Claim` /
  `Thread` / `Source` / `Artifact` nodes, every one carrying provenance (trust tier,
  source, ingestion time) and a scope. Orphans and contract violations are rejected
  at write time ([docs/09](docs/09-schema-and-federation.md)).
- **The evidence archive**: memory is bootstrapped from retained session transcripts,
  held in an immutable content-addressed archive outside the repo. The graph is a
  materialized view over that log — re-extract, never migrate
  ([docs/10](docs/10-evidence-archive.md)).
- **Four experts**: technical-literature, evaluation-methodology, homelab, and
  teacher — each declared by an operator-owned manifest in `config/experts/` and
  nothing else — the zero-glue contract test
  ([docs/01](docs/01-federation-contract.md), [docs/02](docs/02-expert-subgraphs.md)).
  Knowledge is fed by `thalamus ingest`
  (allowlist-gated, evidence-first) and returns blockquoted with citation and tier:
  it informs, it never instructs ([docs/05](docs/05-trust-model.md)).
- **Session pinning**: one OS process = one immutable pin. `thalamus pin` / `thalamus
  roster` launch scope-pinned sessions; the MCP server reads the scope from its
  environment at startup and no tool accepts a scope argument
  ([docs/07](docs/07-harness-integration.md)).
- **The consultation protocol**: cross-expert questions ride single-use tickets where
  minting the ticket *is* writing the exchange record, and answers must cite nodes
  inside the consulted scope ([docs/02](docs/02-expert-subgraphs.md)).
- **The eval loop, layers 1–2**: every memory-tool call is trace-tapped, landed as
  `Trace` nodes, judged used-vs-ignored against the session's retained transcript,
  and priced in injected tokens — decay candidates rank by wasted tokens
  ([docs/04](docs/04-eval-loop.md)). Above that sits the counterfactual harness: a
  task battery (`thalamus eval tasks`), an arm runner that executes one task
  memory-on / memory-off / scoping-degraded in a confined worktree with its own
  `HOME` and its own store (`thalamus eval run --sandbox --isolate-store`), and a
  graded oracle whose rungs are validated against a mutant set before any arm is
  scored (`thalamus eval oracle`). Fourteen campaigns are written up in
  [`lab/`](lab/) (011–024). What is measured so far is retrieval *surfacing*;
  retrieval *use* remains unevidenced, so the utility claim is still open.
- **First trust enforcement**: the transcript-ingress floor down-tiers distilled
  claims that rest on fetched web content, so a poisoned page can't launder into
  tier-1 memory ([docs/05](docs/05-trust-model.md)).

Start at [`docs/index.md`](docs/index.md) — doc tracker, status board, milestone
table, and the binding decision log. [`docs/11-related-work.md`](docs/11-related-work.md)
places the design in the 2026 literature.

## Results

Every campaign is written up in [`lab/`](lab/) — the negative ones especially. In
the order the evidence arrived:

- **Layer 1: retrieval is priced.** The first priced run found **half the injected
  retrieval tokens were never used** ([006](lab/006-priced-verdicts-first-run.md)).
  The autopsy cleared the suspect the operator had in mind — the blanket
  session-start recall — and convicted the query shape instead
  ([007](lab/007-query-shape-refinement.md)).
- **Layer 2: the harness got debugged before any number was trusted.** The first
  three counterfactual campaigns surfaced three bugs in the runner itself — project
  scoping, worktrees freezing the runner's own hooks at a pre-fix ref, and a fresh
  worktree venv silently running the wrong `pytest`
  ([012](lab/012-post-distillation-rerun-found-a-harness-bug.md),
  [013](lab/013-the-fix-lands-but-recall-goes-unused.md)). No campaign that ran
  before those fixes is cited as a memory-utility result;
  [014](lab/014-the-first-clean-campaign-and-a-split-verdict-on-recall.md) is the
  first with zero infra faults. The runner now classifies infra faults apart from
  candidate defects.
- **A hypothesis died on replication.** [015](lab/015-three-models-and-the-recall-gradient.md)
  read a model×task recall pattern across 12 arms;
  [016](lab/016-the-replication-that-killed-the-hypothesis.md) inverted both sonnet
  cells and showed the pattern is substantially stochastic within a fixed cell. The
  falsification criterion was written down before the run.
- **The instrument is validated before it grades anything.** The graded oracle's
  rungs are checked against a pre-registered mutant set with no model in the loop —
  7/7 ([017](lab/017-the-mutant-gate-and-the-suite-that-rewarded-imitation.md)), and
  6/6 for the withholding task at zero model cost
  ([019](lab/019-the-task-that-withholds-something.md)).
- **The first campaign where memory-on could actually reach memory**
  ([023](lab/023-the-first-valid-memory-contrast.md)): 24 confined arms, treatment
  cleanly separated, zero contaminated. On the pre-registered endpoint — share of
  arms reaching rung ≥ 4 — it is **null**, 1/12 vs 0/12. The informative half is
  the negative one: repairing the hook layer took recall engagement from 6/13 to
  **11/12** and the graded outcome did not move. Engagement with memory is not the
  bottleneck on this task.
- **The stopping rule earned its keep.** An interim look at arm 19 of 24 showed
  P(on > off) = 0.789, one-sided p = 0.015. By arm 24 it had decayed to p = 0.085
  ([024](lab/024-the-endpoint-was-in-the-wrong-place.md)). Stopping early would have
  recorded an effect the completed campaign does not support.
- **Two audits changed already-published numbers.** A review from the
  `eval-methodology` pin found the answer-key leak undercounted and `mean rung` used
  without measurement-scale warrant
  ([021](lab/021-the-escape-detector-and-three-corrections.md)); a scan of all 88
  recorded arms then found a second leak channel — the git object store, 9 of 88 —
  that the new detector could not see
  ([022](lab/022-confinement-and-the-leak-nobody-was-watching.md)). Confinement
  closed both.

**The utility claim is open.** What is measured is that memory gets *surfaced*; that
it changes task outcomes is not yet evidenced. This section says so until a campaign
says otherwise.

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
               Trace-node sync, per-scope utility and cost reports, and the
               counterfactual harness (task battery, arm runner, graded oracle)
  pulse/       live telemetry dashboard over the eval loop's measurements
frontend/      viewer source; builds into plane/static
config/        expert manifests (tier-0, operator-owned)
docs/          design docs
lab/           harness-limit notebook — what broke, why, workaround or wall
```

Both **Claude Code** and **Cursor** are supported; their hook contracts differ, so
each has its own hook suite under `src/thalamus/harness/hooks/`. Claude Code is the
primary harness: eight scripts across five events (wired by `thalamus init` into
`~/.claude/settings.json`, so they arm in any directory), over a
shared scope-resolution helper, cover memory priming, the pin ledger, distillation,
the trace taps, the gremlin guard, and the conditioning/timestamp injections. The Cursor suite
(`~/.cursor/hooks.json`, written by the same `thalamus init`) ports everything
portable — session-start priming + pin ledger, engagement marking, the gremlin
guard (`beforeShellExecution`), both trace taps (`afterShellExecution`,
`afterMCPExecution`), and the timestamp/conditioning injections — as thin
adapters over the Claude Code scripts, so both harnesses share one detection
logic and one set of on-disk records. Cursor gives the prompt text to an event
that cannot inject and injection to events that never see the prompt, so the
two injection tiers compute on `beforeSubmitPrompt` into a per-session spool and
deliver on the next `postToolUse`, one tool call late (lab/027). Cursor sessions
distill too, at honestly-reduced fidelity: `thalamus extract --harness cursor`
sweeps the sessionEnd log, and because Cursor's transcripts exclude tool outputs
entirely, those sessions are floored whole by the ingress defence rather than
checked against evidence that does not exist (lab/028, docs/05).

## Command reference

Setup lives in [Quick start](#quick-start); this is the rest of the surface.

```bash
thalamus init --check              # verify an existing install without writing
thalamus bootstrap                 # list session transcripts available to ingest
thalamus bootstrap -- <project>    # dry-run: retain + extract (add --write to persist)
thalamus extract                   # bootstrap stage 2: Claims + Threads via a model
thalamus extract --harness cursor  # same, sweeping Cursor's sessionEnd log via `agent -p`
thalamus validate session.yaml     # check an extraction against the contract
thalamus contract check            # audit the live graph against the contract
thalamus ingest <url|file>         # feed one document to an expert (dry-run; --write to persist)
thalamus pin <scope>               # launch a claude session pinned to an expert
thalamus roster                    # bring up the control plane (--all for every expert)
thalamus spawn <scope>             # one on-demand pinned tmux window
thalamus rescope <scope>           # redirect this session's distillation (before it distills)
thalamus visualize                 # open the persisted memory explorer
thalamus visualize session.yaml    # preview a pending extraction, no graph needed
thalamus write session.yaml        # write to the graph
thalamus pulse                     # live telemetry dashboard over the eval loop
thalamus snapshot                  # flush the graph to disk now
thalamus-mcp                       # run the MCP server
```

The eval loop has its own surface — layer 1 measures what retrieval did, layer 2
asks whether it mattered:

```bash
# layer 1 — traces, priced
thalamus eval sync --write         # land retrieval traces + used-vs-ignored verdicts
thalamus eval report               # per-scope retrieval-utility numbers, priced
thalamus eval cost                 # session/operation token-cost buckets
thalamus eval pins                 # per-expert routing signal: pinned vs consulted utility
thalamus eval conditioning         # per-firing behavioral join on injected reminders
thalamus eval gremlin              # gremlin fluency: guard rescue rate, rejection classes
thalamus eval recipes              # smoke-run every stored gremlin recipe read-only

# layer 2 — counterfactuals
thalamus eval tasks                # validate and list the task battery (config/tasks/)
thalamus eval oracle               # grade anchors + mutants against pre-registered rungs
thalamus eval run <task>           # run one task under arms (worktree + headless session)
thalamus eval rescore              # apply new detectors backwards over past campaigns
thalamus eval rakes                # solved problems later sessions could have re-stepped on
thalamus eval rake-audit           # draw/score the hand-audited precision sample
```

### Where your memory lives

The graph is in the named `thalamus-graph-data` Docker volume; the evidence
archive — your session transcripts, retained verbatim — is in
`~/.thalamus/archive`. Both sit outside the checkout by construction, which is
what makes "[the graph is never shipped](#quick-start)" structural rather than a
promise: there is nothing in the tree to ship, and `.gitignore` guards the paths
against a stray `snapshot --path ./…` anyway.

Don't `docker compose down -v` unless you mean to delete it.

TinkerGraph holds the graph in memory and writes it back only on a clean
shutdown, so every write path flushes to disk when it finishes and `thalamus
snapshot` does it on demand. `docker compose stop` is safe; `docker kill` costs
you whatever was written since the last flush.

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

Recall tools also accept a `ticket` argument: under a consultation ticket they
search the consulted expert's memory instead of the session's own scope.

For Claude Code, `thalamus init` registers the server at **user** scope, so it is
available in every directory rather than only inside this checkout. Cursor still
takes a `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "thalamus": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/thalamus", "thalamus-mcp"],
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
Session ends → SessionEnd hook → thalamus extract → memorize → eval sync
                                                                  ↓
New session → session-start hook → memory_open_threads → context
```

Distillation is automatic on Claude Code: the SessionEnd hook runs `thalamus
extract` (headless, detached) over the retained transcript, then `eval sync
--write` lands the session's retrieval traces as priced Trace nodes. The
extraction prompt is `_PROMPT_TEMPLATE` in `src/thalamus/harness/extraction.py`.
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

## License

MIT — see [LICENSE](LICENSE).
