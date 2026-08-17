# CLI reference

Every command. Setup is covered in [Getting started](getting-started.md); this is the
rest of the surface.

All commands are shown bare. Prefix them with `uv run` unless you have activated the
virtualenv. `thalamus <command> --help` gives the full flag list for any of them.

## Install and session wiring

```bash
thalamus init                      # wire your editor at user scope
thalamus init --check              # verify the install, or report what is not installed yet
thalamus init --dry-run            # report what would be written
thalamus init --uninstall          # remove what it can prove it installed
thalamus rescope <scope>           # redirect this session's distillation, before it distills
```

## Building memory

```bash
thalamus bootstrap                 # list session transcripts available to ingest
thalamus bootstrap -- <project>    # stage 1 dry run: retain + derive (add --write to persist)
thalamus extract                   # stage 2: Claims and Threads, via a model
thalamus extract --harness cursor  # same, sweeping Cursor's sessionEnd log
thalamus write session.yaml        # write a session graph from a file
thalamus validate session.yaml     # check an extraction against the contract
thalamus ingest <url> --scope <expert>   # feed one document to an expert (dry run; --write to persist)
thalamus backfill-chunks           # co-index already-ingested documents as Chunk vertices
```

## Inspecting the graph

```bash
thalamus schema                    # the session graph JSON schema
thalamus contract check            # audit the live graph against the federation contract
thalamus pulse                     # live telemetry dashboard over the eval loop
thalamus snapshot                  # flush the in-memory graph to disk now
```

## Running experts

```bash
thalamus pin <scope>               # launch a session pinned to an expert scope
thalamus roster                    # bring up the tmux roster (--all for every expert)
thalamus spawn <scope>             # one on-demand pinned tmux window
thalamus console                   # drive the roster from a browser or phone
thalamus quick ask <scope> "<q>"   # consult a live expert by forking its own session
thalamus quick targets             # which experts are forkable, and how warm each is
thalamus quick delta               # what a fork contributed back
```

### Rooms

A room is a private roster whose members see and message only each other.

```bash
thalamus room create <name>        # create a room's config directory
thalamus room list                 # every room that has a config dir
thalamus room show <name>          # what one room's config dir holds
thalamus dispatch <room> "<msg>"   # deliver to live room members; refuses on `waiting`
```

### Ceremonies

An append-only ledger of occasions, written at the start so an aborted occasion still
leaves a row.

```bash
thalamus ceremony start|end|skip   # an occasion, its close, its non-occurrence
thalamus ceremony mint|revise      # a deliverable_id, and the revisions under it
thalamus ceremony assign           # deal deliverables to arms from a seed, before the run
thalamus ceremony commit|resolve   # bind and settle an assignment
thalamus ceremony show|audit       # the ledger, and its obligations checked against it
thalamus ceremony ack              # acknowledge a delivery
```

## Threads

Threads are minted only by distillation. An agent may propose a close; you approve it.

```bash
thalamus thread propose <id>       # an agent's whole reach: propose a close
thalamus thread pending            # proposals awaiting you
thalamus thread approve <id>       # close it
thalamus thread reject <id>        # decline the proposed close
thalamus thread audit              # the close ledger
```

## The eval loop

Layer 1 measures what retrieval did, from what the harness already logs — this is the
whole of what `thalamus eval` runs.

```bash
thalamus eval sync --write         # land retrieval traces and used-vs-ignored verdicts
thalamus eval report               # per-scope retrieval-utility numbers, priced
thalamus eval cost                 # session and operation token-cost buckets
thalamus eval pins                 # per-expert routing signal: pinned vs consulted utility
thalamus eval conditioning         # per-firing behavioural join on injected reminders
thalamus eval gremlin              # gremlin fluency: guard rescue rate, rejection classes
thalamus eval recipes              # smoke-run every stored gremlin recipe, read-only
```

Layer 2 — counterfactual campaigns that ask whether retrieval mattered (the task
battery, the graded oracle, arms, corpora, calibration, the gold label set, rakes) —
and the room-manipulation and diagram-legibility checks live in the private
[`thalamus-eval`](https://github.com/Ybx-jp/thalamus-eval) companion repo, run via its
own `thalamus-eval` CLI (`rooms`, `legibility`, `randomize`, `rakes`, `rake-audit`,
`gold`, `tasks`, `corpus`, `rescore`, `oracle`, `run`). They moved out because they run
research campaigns and produce findings that inform future versions, not live-serving
behavior — see that repo's README for the split line and setup.

## Repository analysis

```bash
thalamus arch scan                 # structural instrument over a repo's imports
thalamus arch show                 # the current model
thalamus arch diff                 # against a previous scan
thalamus arch rules                # the rules a scan applies
thalamus arch growth               # change over time
```

All five measure this checkout by default, from any working directory — the model
they read (`arch/model.yaml`) belongs to a repository, not to wherever you are
standing. `--repo <path>` points them at another tree.

## Maintenance

Each of these is a dry run unless `--write` is passed.

```bash
thalamus audit-artifacts           # measure how fragmented Artifact identity is (read-only)
thalamus repair-projects           # re-anchor project values that named a directory, not a repo
thalamus derive-artifact-paths     # project Artifact identifiers onto (repo, path)
thalamus retire-scans              # remove graph records of architecture scans
```

## The MCP server

```bash
thalamus-mcp                       # run the MCP server (normally launched by your editor)
```

`thalamus init` registers it at **user** scope for both harnesses, so it is available
in every directory. The registration carries no scope: `main` is the default for a
plainly launched process, and a pinned session takes its scope from the agent that
launched it. Baking a scope into the user-scope config would pin every session on the
box to one expert.

### Tools

| Tool | Input | Purpose |
|---|---|---|
| `memory_open_threads` | `project`, `limit`, `topic` | Active continuation points — **the entrypoint**. Pass `topic`; a bare call returns one page of many |
| `memory_recall` | `query`, `limit` | Keyword search across session memories |
| `memory_recall_by_artifact` | `identifier`, `limit` | Sessions that touched a file, class or dependency, under any spelling of its name — an absolute path answers for the repo-relative one and back |
| `memory_recall_by_project` | `project`, `limit` | Recent sessions for a project |
| `memory_recall_recent` | `limit` | Most recent sessions |
| `memory_open_problems` | `project`, `limit` | Problems with no recorded solution, recurrence-ranked |
| `memory_thread` | `thread_id` | Full context on one thread |
| `memory_query` | `query` | One read-only Gremlin traversal (main scope only) |
| `memory_consultations` | `limit` | This expert's own answered consultations |
| `memory_exchanges` | `query`, `limit`, `read_ticket` | Consultations this scope asked or answered, by topic |
| `consult_request` | `expert`, `question` | Mint a consultation ticket — this *is* opening the exchange record |
| `consult_answer` | `ticket`, `answer` | Close a consultation; citations validated, ticket burned |

Recall tools also accept a `ticket` argument: under a consultation ticket they search
the consulted expert's memory instead of the session's own scope.

**No tool accepts a scope argument.** The server decides what the session can see.

## Environment

| Variable | Effect |
|---|---|
| `THALAMUS_SCOPE` | The session's pin. Read once at server startup |
| `THALAMUS_CONFIG_DIR` | Where `experts/` and `tasks/` are read from, instead of the checkout's `config/` |
