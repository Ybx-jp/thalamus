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

Because user scope means *outside this checkout*, it lists what it will write
and asks before writing — `~/.claude/settings.json` and `~/.cursor/hooks.json`
(hook entries that then run in every session on the box), `~/.claude.json` (the
MCP server), plus skill symlinks and one derived agent per expert. Pass `--yes`
to skip the prompt in a script; a non-interactive stdin declines rather than
assumes. **`thalamus init --uninstall` takes all of it back out**, removing only
what it can prove it installed, and leaving your graph, `~/.thalamus/` and the
transcript archive alone.

### What this release is

**0.1.0 runs from a checkout, and only from a checkout.** There is no
`pip install thalamus` — `harness/pin.py` and `contract/manifest.py` anchor on
the repo root, and the expert manifests in `config/` live outside the package, so
an installed wheel would resolve paths that exist only in a clone. The package
metadata says so mechanically (`Private :: Do Not Upload`). Real packaging is a
later milestone.

Two features are **experimental and off by default**, each behind a flag on
`thalamus console`:

| | Flag | Off means |
|---|---|---|
| `say` — reads the active window aloud | `--voice URL` | no control, no endpoints. Needs a separate TTS unit (`--extra voice`, [docs/console.md](docs/console.md)) |
| Frame themes — the pane inside artwork | `--frames PATH` | no controls and no key bindings; no artwork ships ([docs/frame-themes.md](docs/frame-themes.md)) |

### Read what it tells you

Install ends by *exercising* what it wired rather than asserting it — it spawns
the real interpreter from a foreign directory, round-trips the Cursor injection
spool, and reads each skill back through its user-scope path:

```
Verification (exercised, not assumed):
  ✓ hook scripts present: all 11 wired scripts found
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
- **The expert roster**, each scope declared by an operator-owned manifest in
  `config/experts/` and nothing else — the zero-glue contract test. That directory
  is the roster; [docs/02](docs/02-expert-subgraphs.md) records what each scope is
  for
  ([docs/01](docs/01-federation-contract.md), [docs/02](docs/02-expert-subgraphs.md),
  [docs/08](docs/08-roster-candidates.md)). Knowledge is fed by `thalamus ingest`
  (allowlist-gated, evidence-first), co-indexed as `Chunk` vertices beside the claims
  drawn from it, and returns blockquoted with citation and tier: it informs, it never
  instructs ([docs/05](docs/05-trust-model.md)).
- **Role boundaries are structural**: where a scope is defined by what it must *not*
  produce, its manifest declares a `write_boundary` and the `role-guard` PreToolUse
  hook enforces it — `qe` writes `tests/` and `lab/` but not `src/`; `designer` writes
  markup, markdown, SVG and token files but not executable source; `architect` carries
  no boundary, by charter. MAST names "disobey role specification" as a failure mode
  whose recorded repair was structural authority rather than a better prompt, so a
  boundary that exists only as a paragraph in `domain` is the configuration that was
  measured failing ([docs/08](docs/08-roster-candidates.md)). The guard governs the
  file-editing tools only — Bash still writes.
- **Session pinning**: one OS process = one immutable pin. `thalamus pin` / `thalamus
  roster` launch scope-pinned sessions; the MCP server reads the scope from its
  environment at startup and no tool accepts a scope argument
  ([docs/07](docs/07-harness-integration.md)).
- **The console**: because a pin is a process in a tmux window, the whole
  roster is addressable from one place. `thalamus console` serves it to a browser —
  a tab per window, the live pane, a composer, the terminal keys a phone keyboard
  lacks, and one tap to spawn an expert in a project or to restart one so a wiring
  change arms. It binds `127.0.0.1` and carries no authentication; reaching it from a
  phone is `tailscale serve` connecting to that loopback port and publishing it at
  `/console/` on your tailnet, which is also what makes it installable as a PWA. It
  never moves the active window, so the terminal on your desk stays where you left it
  ([docs/console.md](docs/console.md)).
- **The consultation protocol**: cross-expert questions ride single-use tickets where
  minting the ticket *is* writing the exchange record, and answers must cite nodes
  inside the consulted scope ([docs/02](docs/02-expert-subgraphs.md)). Beside it, the
  **quick protocol** (`thalamus quick ask`) forks an expert's own live session rather
  than cold-starting one: a warm parent answered for **$0.037 against $0.595 cold**,
  and cost is bimodal on the parent's recency, not on how the question is phrased
  (lab/049–050). A fork distills its delta, never the parent's transcript.
- **Rooms**: a room is a private roster — members see and message each other and
  nobody else, enforced by a per-room `CLAUDE_CONFIG_DIR` and an outbound guard rather
  than by convention. The boundary is built (`--room`, `thalamus room`, and
  `thalamus eval rooms` as its manipulation check), and so is the capture layer the
  lifecycle needs first — `thalamus ceremony` records occasions at their **start**, the
  ceremonies that were skipped, a `deliverable_id` stable across revisions, and the
  arm assignment with its seed *before* the ceremony runs, since none of those four can
  be reconstructed afterwards. The ceremonies themselves, Contract-Net dispatch and the
  promotion path are not built ([docs/12](docs/12-room-lifecycle.md)). Rooms have never
  been measured for efficacy, and room-level causal inference is out of reach at this
  corpus size.
- **The eval loop, layers 1–2**: every memory-tool call is trace-tapped, landed as
  `Trace` nodes, judged used-vs-ignored against the session's retained transcript,
  and priced in injected tokens — decay candidates rank by wasted tokens
  ([docs/04](docs/04-eval-loop.md)). Above that sits the counterfactual harness: a
  task battery (`thalamus eval tasks`), an arm runner that executes one task
  memory-on / memory-off / scoping-degraded in a confined worktree with its own
  `HOME` and its own store (`thalamus eval run --sandbox --isolate-store`), and a
  graded oracle whose rungs are validated against a mutant set before any arm is
  scored (`thalamus eval oracle`). Every campaign is written up in [`lab/`](lab/) —
  52 entries, each classified by what it ends in. What is measured so far is retrieval
  *surfacing*; retrieval *use* remains unevidenced, so the utility claim is still open.
- **Two genres of write-up, and one wins ties.** [`lab/`](lab/) is this project's own
  voice — what broke, why, workaround or wall. [`experiments/`](experiments/) is
  written for a reader outside the project: seven pre-registered studies, each stating
  what it committed to before the data was seen and regenerating every number from a
  **pinned** graph state and a seed, since a figure computed against the live graph is
  not reproducible even by its own author. When a lab figure and an experiment
  disagree, the experiment wins — it is the one that can be re-run.
- **First trust enforcement**: the transcript-ingress floor down-tiers distilled
  claims that rest on fetched web content, so a poisoned page can't launder into
  tier-1 memory ([docs/05](docs/05-trust-model.md)).

Start at [`docs/index.md`](docs/index.md) — doc tracker, status board, milestone
table, and the binding decision log. [`docs/11-related-work.md`](docs/11-related-work.md)
places the design in the 2026 literature.

## Results

Every campaign is written up in [`lab/`](lab/) — the negative ones especially — and
the load-bearing figures are re-derived in [`experiments/`](experiments/) against
pinned state. In the order the evidence arrived:

- **Layer 1: retrieval is priced.** Against a pinned graph state, **33.8% of injected
  retrieval tokens go unused**, 95% CI [27.2, 40.5], of which ~17.5% is
  chance-corrected as demonstrably earned
  ([experiments/002](experiments/002-what-the-waste-figure-means/)). The autopsy of
  where the waste comes from cleared the suspect the operator had in mind — the
  blanket session-start recall — and convicted the query shape instead: the trust
  floor cut 1% of fan-out, the detail cap 8%, and query shape **28%**
  ([030](lab/030-the-miss-rate-was-the-consultation.md)).
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
- **Distillation was distilling itself.** A census of `Session` vertices by cwd found
  **307 of 445 (69%)** were extraction sandboxes — the harness's own headless
  invocations, recorded as if they were work
  ([033](lab/033-the-graph-was-mostly-remembering-itself.md)). Fixed and purged; every
  per-`Session` count taken before 2026-07-29 is recalibrated by it.
- **The used-vs-ignored judge is a topic detector.** Rotated against a permutation
  null it scores **63.3% used on its own output against a 57.3% null, κ = 0.140
  [0.028, 0.272]** ([experiments/001](experiments/001-the-topic-detector/)) — a few
  points of discrimination on a very high floor. It is reported as what it is.
- **Calibration withdrew more numbers than it produced.**
  [034](lab/034-the-corrections-the-instrument-forced.md) re-derived the
  layer-1 figures against pinned state and published a standing **withdrawal list**
  covering earlier headline magnitudes, including the original "half the injected
  tokens are wasted". Withdrawn figures carry a stamp pointing at the entry that
  killed them; the arm-level results, the zero-model gates, and the null conclusions
  survive.
- **The ceiling campaign cancelled the programme it was built to feed.** Twelve arms
  handed a candidate the *exact* right memory against memory-off
  ([036](lab/036-the-ceiling-that-lost.md)). It was null on the pre-registered endpoint — 0/6
  vs 0/6 reaching rung ≥ 4 — and the ceiling arm **lost every pair** at rung ≥ 3.
  A perfect memory could not clear this task's gate, so the battery is the binding
  constraint, and the work queued behind it was cancelled rather than rescheduled.
- **A proposed feature was falsified before it was built.** Across all **307,720**
  problem-claim pairs, only 14 cleared the similarity threshold belief-revision would
  need, and the measure ranks contradictions *more* similar (0.812) than duplicates
  (0.800) — so the feature would preferentially merge the pairs it must keep apart
  ([041](lab/041-three-proposals-and-the-audit-nobody-ran.md)). Build nothing.
- **A citation anchors provenance and carries no fidelity.** A pre-registered coverage
  assay over 154 literature `Source`s put verbatim-literal placement at **0.9% against
  a pre-registered 31% bar, 0/46 sources clearing it**: the stored `citation` field
  adds 52% more text for 0.8pp of coverage ([051](lab/051-the-representation-we-never-measured.md)).
  Co-indexed `Chunk` vertices replaced it as the fidelity mechanism, at 0.35× vertex
  growth ([052](lab/052-the-passage-the-note-came-from.md)).

**The utility claim is open, and the instrument is the reason.** What is measured is
that memory gets *surfaced*; that it changes task outcomes is not. The ceiling
campaign is why that gap has not closed: a task whose gate a *perfect* memory cannot
clear measures the battery, not the memory. Building a battery that can register the
difference comes before any utility claim, and this section says so until a campaign
says otherwise.

## What's here

```
src/thalamus/
  substrate/   storage kernel — schema, Gremlin writer, Gremlin reader
               (below the contract: knows nodes and edges, not experts or tiers)
  contract/    the federation boundary — the ontology, expert manifests, and the
               checks a subgraph must pass before it may be written
  viewer/      the graph viewer — FastAPI read layer + React/Cytoscape frontend
  console/     the mobile PWA over the tmux roster, published tailnet-only at /console/
  archive/     immutable content-addressed store for retained primary evidence
  harness/     where it meets the agent — MCP server, hooks, skills, transcript bootstrap
  eval/        the eval loop — trace tap reader, used-vs-ignored attribution,
               Trace-node sync, per-scope utility and cost reports, and the
               counterfactual harness (task battery, arm runner, graded oracle)
  pulse/       live telemetry dashboard over the eval loop's measurements
frontend/      viewer source; builds into viewer/static
config/        expert manifests (tier-0, operator-owned)
deploy/        self-hosted services an expert's tooling needs (the designer's Penpot)
docs/          design docs
lab/           harness-limit notebook — what broke, why, workaround or wall
experiments/   pre-registered studies, regenerated from pinned state and a seed
```

Both **Claude Code** and **Cursor** are supported; their hook contracts differ, so
each has its own hook suite under `src/thalamus/harness/hooks/`. Claude Code is the
primary harness: eleven scripts across five events (wired by `thalamus init` into
`~/.claude/settings.json`, so they arm in any directory), over a
shared scope-resolution helper, cover memory priming, the pin ledger, distillation,
the trace taps, the gremlin guard, the role and room boundaries, and the
conditioning/timestamp injections. The Cursor suite
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
thalamus ingest <url> --scope <expert>  # feed one document to an expert (dry-run; --write to persist)
thalamus backfill-chunks           # co-index already-ingested documents as Chunk vertices
thalamus pin <scope>               # launch a claude session pinned to an expert
thalamus roster                    # bring up the tmux roster (--all for every expert)
thalamus spawn <scope>             # one on-demand pinned tmux window
thalamus room create|list|show     # rooms: the private rosters sessions are launched into
thalamus ceremony start|end|skip   # the ceremony ledger: an occasion, its close, its non-occurrence
thalamus ceremony mint|revise      # a deliverable_id, and the revisions carried under it
thalamus ceremony assign           # deal deliverables to arms from a seed, before the ceremony runs
thalamus ceremony show|audit       # the ledger, and its own obligations checked against it
thalamus dispatch <room> "<msg>"   # deliver to live room members; refuses on `waiting`
thalamus quick ask <scope> "<q>"   # consult a live expert by forking its own session
thalamus quick targets             # which experts are forkable, and how warm each is
thalamus console                   # drive the roster from a browser or phone (docs/console.md)
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
thalamus eval rooms                # manipulation check on the room boundary
thalamus eval gold --draw|--score  # hand-labelled sample the attribution judge is scored against

# layer 2 — counterfactuals
thalamus eval tasks                # validate and list the task battery (config/tasks/)
thalamus eval oracle               # grade anchors + mutants against pre-registered rungs
thalamus eval run <task>           # run one task under arms (worktree + headless session)
thalamus eval rescore              # apply new detectors backwards over past campaigns
thalamus eval corpus --name        # seal the current run log as a citable corpus pin
thalamus eval randomize            # design-only feasibility check on a clustered assignment
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
| `memory_open_threads` | `project`, `limit`, `topic` | Active continuation points — **the entrypoint**. Pass `topic`: the graph holds hundreds, and a bare call returns one page of them |
| `memory_open_problems` | `project`, `limit` | Problems with no recorded solution, recurrence-ranked |
| `memory_thread` | `thread_id` | Full context on one thread |
| `memory_query` | `query` | One read-only Gremlin traversal (main scope only) |
| `memory_consultations` | `limit` | This expert's own answered consultations |
| `memory_exchanges` | `query`, `limit`, `read_ticket` | Consultations this scope asked **or** answered, by topic — index lines, then one in full |
| `consult_request` | `expert`, `question` | Mint a consultation ticket = open the exchange record |
| `consult_answer` | `ticket`, `answer` | Close a consultation; citations validated, ticket burned |
| `memory_visualize` | `session_yaml` | Mermaid render of a pending extraction (read-only) |

Recall tools also accept a `ticket` argument: under a consultation ticket they
search the consulted expert's memory instead of the session's own scope.

**A session does not write its own memory.** The only episodic write on this surface
is the consultation exchange, which records a crossing rather than a session's
beliefs. Beliefs are distilled after the session ends, by `thalamus extract` reading
the retained transcript — one pass, one phrasing, one set of thread ids. Writing the
same session live as well would produce a second phrasing of the same decisions;
claims are content-addressed on (kind, description), so the two would not converge,
and duplicate threads would surface in `memory_open_threads`, which is the first
thing the next session reads. Distilling a session before it ends is supported — it
is `thalamus extract --session <id> --force --write`, run by the operator from
outside the session.

`thalamus init` registers the server at **user** scope for both harnesses, so it is
available in every directory rather than only inside this checkout. Claude Code takes
the registration through `claude mcp add`; Cursor has no equivalent CLI, so init writes
`~/.cursor/mcp.json` itself. A project-scope copy in the checkout is removed on both
legs: with the server registered at user scope a surviving project entry is a second
definition of the same server, and Cursor ranks project above user, so it would
silently outrank the one init just wrote.

The registration carries no `THALAMUS_SCOPE`. `main` is the default for a plainly
launched process, and a pinned session takes its scope from the picked agent
(`harness/pin.resolve_pin`), which a static user-scope config cannot express — baking
one in would pin every session on the box to a single expert.

**`THALAMUS_SCOPE` is the session's pin, and no tool accepts a scope argument.** The
server decides what the session can see; the model cannot widen its own view by asking.
That is deliberate — [docs/07](docs/07-harness-integration.md) requires scope
enforcement to live server-side, because the model is never trusted to self-limit its
own retrieval scope.

## The loop

```
Session ends → SessionEnd hook → thalamus extract → graph → eval sync
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

Five episodic node types — `Session`, `Claim`, `Thread`, `Source`, `Artifact` — joined
by `CONTAINS` / `TOUCHES` / `SPAWNS` / `BLOCKS` / `CONTINUES` / `RESOLVES` /
`SOLVED_BY` / `DERIVED_FROM`, plus the knowledge side an expert manifest declares
(`Entity`, literature claims, `KnowledgeBatch`, and the `Chunk` vertices an ingested
document is co-indexed into) and the eval loop's `Trace` / `Exchange` records.
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
cd frontend && npm run build  # -> src/thalamus/viewer/static
```

## License

MIT — see [LICENSE](LICENSE).
