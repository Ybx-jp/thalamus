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
thalamus status                    # is memory being written? sessions, and the last distillation
thalamus rescope <scope>           # redirect this session's distillation, before it distills
```

`init --check` and `status` answer different questions and neither answers the
other's. `--check` verifies the **wiring** — hooks armed, skills readable, an MCP
entry that matches this checkout — all of which can be correct while nothing is being
written. `status` reports what was **written**: sessions in the graph, the newest one,
when distillation last ran and how its log ended, and any sessions the hooks recorded
as lost. It exits non-zero only when the graph will not answer; an empty graph is a
pass, because that is what every install starts as.

## Building memory

```bash
thalamus bootstrap                 # list session transcripts available to ingest
thalamus bootstrap -- <project>    # stage 1 dry run: retain + derive (add --write to persist)
thalamus extract                   # stage 2: Claims and Threads, via a model
thalamus extract --harness cursor  # same, sweeping Cursor's sessionEnd log
thalamus extract --harness codex   # same, sweeping $CODEX_HOME/sessions by session id
thalamus extract --extract-with codex   # read Claude Code transcripts, pay codex for the pass
thalamus write session.yaml        # write a session graph from a file
thalamus validate session.yaml     # check an extraction against the contract
thalamus ingest <url|path> --scope <expert> --check   # verify the source, no model call
thalamus ingest <url|path> --scope <expert>  # feed one document to an expert (dry run; --write to persist)
thalamus backfill-chunks           # co-index already-ingested documents as Chunk vertices
```

`--harness` and `--extract-with` are two questions, not one. `--harness` says who
*wrote* the transcripts, which decides how the digest is rendered and where sessions are
discovered. `--extract-with` says which CLI runs the extraction pass — a digest is plain
text by the time a model reads it, so any CLI can read any harness's session. `ingest` has
no transcript and so no source harness: its `--harness` is the extractor choice outright.

**Two passes, two budgets.** Distillation is one model call per ended session, arriving at
whatever rate you work at. Ingestion is one call *per chunk*, so a single paper can cost
what a day of distillation does. They are therefore chosen separately, in the console
(⚙ → Extraction, stored at `~/.thalamus/extractor/policy.json`). With no flag, `extract`
reads the distillation setting and falls back to the session's own harness; `ingest` reads
the ingestion setting, falls back to the distillation setting, and failing both to `claude`
— so setting one answer for everything is still one tap, and splitting them costs nothing
until you ask for it. Every ingest prints the CLI and model it is about to bill.

Only Claude Code prices its own headless run, and `thalamus eval cost` buckets both passes'
spend by finding the sandbox's transcript under `~/.claude/projects/-tmp-thalamus-extract*`.
Routing a pass to another CLI therefore does not shrink the extraction spend that report
shows — it removes it from the report. Every change to either setting lands a row in
`~/.thalamus/extractor/policy.jsonl`, which is the only record of which model produced a
given week's claims: the graph stores the harness that *wrote* a session, not the one that
extracted it, and a Source stores no extractor at all.

`ingest` reads HTML, plain text, and PDF. **PDF needs the `pdf` extra** (`uv sync
--extra pdf`); without it the format is refused and the message names the extra. The
document is the positional argument — `--url` on this command is the Gremlin endpoint,
as it is on `write`, `bootstrap` and `extract`, and a document passed there is refused
before anything is fetched.

**`--check` verifies a source for no model spend.** It runs the ingest path — same
request, same User-Agent, same redirects, same allowlist gate, same text extraction —
and stops at the model call, reporting the host that actually served the bytes, the
content-type, the title read from the document itself, and its opening 400 chars.
Because it is the ingest path rather than a description of it, a source that passes
`--check` cannot then fail the gate. A run *without* `--write` is not this: it extracts
and reports, so using one as a pre-check bills the model twice for one document.

**An ingest within a day of a check writes the bytes that check verified**, and says so.
A check indexes what it fetched (`~/.thalamus/index/fetched.jsonl`, beside the archive
it indexes), and a later ingest of the same address reads them back rather than asking
again. The saved request is the smaller half: the gap between checking a source and
writing it is where a document can change, so re-requesting can write something other
than what was confirmed. Past a day the address is asked again, because a URL is not a
document; `--refetch` asks again inside the window. The allowlist gate re-runs on reused
bytes against the manifest as it stands *now* — the index supplies bytes, never
permission.

A batch is accepted per claim. A claim whose kind only misspells a declared one — wrong
namespace, plural, case — is repaired; one that names something the scope's manifest
does not declare leaves the batch and the rest is written. Every rejection is printed
and retained in `~/.thalamus/logs/rejected-claims.jsonl` against the document's content
hash, because the extraction is paid for either way.

`arxiv.org/abs/<id>` is refused before anything is fetched: the abstract page extracts
into abstract-level claims that read exactly like paper-level ones, so the failure
would be silent. Feed `arxiv.org/html/<id>` where a rendering exists, or
`arxiv.org/pdf/<id>`, which always does.

A local path bypasses the allowlist, because hand-feeding is itself the curation
decision. Prefer a URL where one works: a hand-fed file archives your conversion rather
than the document, and its `Source.origin` is a path on one machine rather than a
citable address.

## Inspecting the graph

```bash
thalamus schema                    # the session graph JSON schema
thalamus contract check            # audit the live graph against the federation contract
                                   #   violations exit 1; advisories print and do not
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
thalamus eval profile              # gremlin query cost: wall time per traversal shape
```

`eval profile` reads the span tap: every traversal issued through `connect()` and
every `memory_query` is timed at its own seam and aggregated by traversal shape into
`~/.thalamus/profiles/`, flushed once per process. The report ranks shapes by total
time and gives each one its call count and p50/p95/max, never a bare mean; it also
states the tap's own measured overhead rather than calling it negligible. Set
`THALAMUS_PROFILE=0` to stop recording.

Two flags switch it from wall time to the server's own per-step metrics, via
TinkerPop's `profile()`:

```bash
thalamus eval profile --query "g.V().hasLabel('Trace').outE('RETURNS')..."
thalamus eval profile --corpus     # every gremlin-lang recipe the skills store
```

Those milliseconds are read against each other and never against a span-ledger
figure — profiling impedes the traversal it measures, which is why it is on demand
only. Element counts sit beside the durations because the counts are the half of a
reading that transfers off this machine. Nothing here gates: with one machine and
small n, a regression threshold would be a false-alarm generator.

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
thalamus arch scan                 # measure the tree; --write updates the model file
thalamus arch show                 # the declared model and the last scan's numbers
thalamus arch diff <commit-ish>    # re-scan both sides and compare
thalamus arch rules                # measured edges against the declared layers
thalamus arch growth               # unreferenced stock first, then rate
```

All five measure this checkout by default, from any working directory — the model
they read (`arch/model.yaml`) belongs to a repository, not to wherever you are
standing. `--repo <path>` points them at another tree.

`diff` takes a commit-ish, not a stored scan, and re-scans both sides under one
policy: reading the other commit's recorded number would compare a measurement
against a report. `growth` leads with unreferenced stock because a trend statistic
scores a flat 894 MB of stranded worktrees as healthy.

A scan reads two declared channels, each with its own policy block and digest in
`arch/model.yaml`. `extractor` walks Python imports. `routes` matches client request
literals against the routes a server defines, which is how the console's browser
surface enters the graph at all — it reaches the server over HTTP, so no import
relation exists to extract. The route channel is off unless the model file enables
it; turning it on forks the scan key, because a propagation cost measured with those
edges is not comparable to one measured without them.

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

`thalamus init` registers it at **user** scope for every harness, so it is available
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
| `THALAMUS_TMUX_SOCKET` | The tmux server the roster, `spawn`, `dispatch` and the console address (`tmux -L …`), default `thalamus`. Two checkouts on one box get separate control planes by setting it differently |
