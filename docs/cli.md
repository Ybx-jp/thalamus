# CLI reference

Every command. Setup is covered in [Getting started](getting-started.md); this is the
rest of the surface.

All commands are shown bare. Prefix them with `uv run` unless you have activated the
virtualenv. `thalamus <command> --help` gives the full flag list for any of them.

## Install and session wiring

```bash
thalamus init                      # wire your editor at user scope
thalamus init --check              # verify the install, or report what is not installed yet
thalamus init --check --json       # the same verification as rows, for a program to gate on
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

`--json` prints that same verification as data rather than prose: one row per check,
each carrying a stable `key`, the `surface` it belongs to (`claude`, `cursor`,
`codex`, `runtime`), its `state` (`ok`, `failed`, `pending`, `advisory`, `blocked`)
and the same `detail` the prose line shows, under a `report` schema version. It only
means anything with `--check`, and is refused otherwise. The reader is a program
deciding something: the counterfactual arm runner in the companion repo runs it inside
a confinement cell before the cell spends anything, to establish that the treatment it
is about to measure was actually installed there.

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
thalamus eval withholding          # the randomized-withholding ledger, read as an outcome
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
`thalamus-eval` companion repo, run via its own `thalamus-eval` CLI (`rooms`,
`legibility`, `randomize`, `rakes`, `rake-audit`, `gold`, `tasks`, `corpus`, `rescore`,
`oracle`, `run`, `calibration`). They moved out because they run research campaigns and
produce findings that inform future versions, not live-serving behavior.

`eval withholding` is the one outcome measure here that rests on a real randomization
rather than on a judge. With `THALAMUS_WITHHOLD` set, `memory_recall` suppresses each
offered node independently at the policy rate and logs the draw; the command asks
whether a suppressed node comes back — is re-surfaced by a later retrieval in the same
session — against the kept nodes of the same event as its control. Kept and withheld
came out of one offered set against one query, so under the null they recur alike, and
the test is an exact within-event permutation with the event's withheld count held
fixed. Three design predicates decide eligibility, none of them a function of the
outcome: the offered set must be larger than one (a singleton offer's realized
withholding probability is 0, not the nominal rate, because the policy never withholds
everything), both arms must be non-empty, and the session must hold a later retrieval.

The offered list comes from `~/.thalamus/policy/*.jsonl`, joined to the Trace by
`policy_seed`. It is not reconstructible from the graph: `eval sync` lands
`offered_count` and drops the ids, and a trace's `RETURNS` edges are a *superset* of
what the draw covered, because a rendered response is assembled from more retrieval
than the one call the policy sees.

What it measures is the ranker re-surfacing a node, which is evidence the session
returned to that ground — not evidence anyone noticed a gap. The report prints the
effect the design could have detected at 80% power beside the p-value, so a null
arrives with a magnitude attached.

`eval report` gives the used-vs-ignored rate one ranker window at a time and refuses to
pool across a dial change, because a rate averaged over two settings measures neither.
Each window's interval resamples **sessions** rather than verdicts — verdicts inside one
session share an output window, a topic and an operator — so a window with fewer than
two sessions gets no interval rather than a narrow one.

It reports no null. The permutation null re-judges each retrieval against an
uncorrelated session's output, which needs the transcript archive rather than the graph,
so it belongs to `thalamus-eval calibration`. Measured there on 2026-08-29 it was 69.2%
(v3), 76.5% (v1) and 72.1% (v2) — high enough that a used rate is read as its distance
above that window's null, never as a rate on its own.

## Repository analysis

```bash
thalamus arch scan                 # measure the tree; --write updates the model file
thalamus arch scan --check         # exit 1 if the committed model is stale
thalamus arch show                 # the declared model and the last scan's numbers
thalamus arch diff <commit-ish>    # re-scan both sides and compare
thalamus arch rules                # measured edges against the declared layers
thalamus arch rules --gate         # exit nonzero on an edge the model does not accept
thalamus arch dead                 # definitions nothing outside tests/ refers to
thalamus arch refs                 # names a comment points at that the tree no longer holds
thalamus arch refs --limits        # what the recognizer did not consume, and what it declined to judge
thalamus arch growth               # unreferenced stock first, then rate
```

`refs` reports and never gates: it has no `--gate` flag, because its precision has
not been measured and a checker that acts on an unmeasured precision leaves no
record of the calls it got wrong. A name the surrounding sentence asserts the
*absence* of is not a finding — those are listed under `--limits` so the
suppression can be audited — and backticked dotted names and bare `.json`/`.yaml`
names are counted but never judged, since their referents are as often a graph
property or another program's file as they are ours.

All seven measure this checkout by default, from any working directory — the model
they read (`arch/model.yaml`) belongs to a repository, not to wherever you are
standing. `--repo <path>` points them at another tree.

### The gates

`rules`, `scan --check` and `dead` run in CI on every push. The three of them exist
because the instrument they wrap had no trigger: `arch/model.yaml` reached 25 commits
past the code it claimed to measure, and nothing said so.

`--gate` adds a verdict without filtering the report — every violation still prints,
accepted or not, because an architect reading `rules` wants the design's real shape and
not the subset that is still news. Exit codes follow `tests/qe/run.py`:

| code | meaning |
|------|---------|
| 0 | clean, or exactly what `arch/model.yaml`'s `accepted` list declares |
| 1 | a violation, unplaced module or dead end the model does not accept |
| 2 | an `accepted` entry that no longer happens — delete it |

Exit 2 is the half that keeps the exception list honest. An entry that has stopped
firing is not a pass; left in place it goes on describing a design that moved. Every
`accepted` entry carries a required `reason`, because a list whose entries do not say
why is a list that only grows.

`scan --check` compares a fresh scan against the committed file rather than against a
recorded commit stamp: a stamp says which tree was measured and not whether the numbers
beside it are still true.

`diff` takes a commit-ish, not a stored scan, and re-scans both sides under one
policy: reading the other commit's recorded number would compare a measurement
against a report. `growth` leads with unreferenced stock because a trend statistic
scores a flat 894 MB of stranded worktrees as healthy.

A scan reads three declared channels, each with its own policy block and digest in
`arch/model.yaml`. `extractor` walks Python imports. `routes` matches client request
literals against the routes a server defines, which is how the console's browser
surface enters the graph at all — it reaches the server over HTTP, so no import
relation exists to extract. The route channel is off unless the model file enables
it; turning it on forks the scan key, because a propagation cost measured with those
edges is not comparable to one measured without them.

`deadends` is the third, and it measures definitions rather than edges, which is why it
carries its own digest and stays out of the scan key: it changes no number that key
names. Its `reference_extensions` list is what stops it accusing live code — the hook
scripts under `harness/hooks/` embed Python heredocs that import from the package, so a
symbol whose only caller is `role-guard.sh` is reached, not dead. Those blocks are
parsed as Python and walked by the same reference pass the `.py` files get; a text match
would not do, because this repo has a real call to `WriteBoundary.denies` and a comment
mentioning `ownership.fallback_markers()` in the same file, and only one of them is a
caller.

The census states its own reach limits as findings rather than dropping them: a
`getattr()` with a computed name, a name that appears in a string, a star re-export and
an unparsed file can each hide a caller, and each is reported beside the findings it
could refute. What it reports is that no reference was found outside the test roots —
never that a symbol is unused, which is a verdict a static census is not entitled to.

## Maintenance

One-shot repairs against a graph that already has history in it. **None of them is
listed in `thalamus --help`** — a graph that has just been created can never need one,
so listing them puts six commands in front of a first-time reader before the ones they
came for. Each still answers `--help`, and each is a dry run unless `--write` is
passed.

```bash
thalamus backfill-chunks           # co-index already-ingested documents as Chunk vertices
thalamus audit-artifacts           # measure how fragmented Artifact identity is (read-only)
thalamus repair-projects           # re-anchor project values that named a directory, not a repo
thalamus derive-artifact-paths     # project Artifact identifiers onto (repo, path)
thalamus retire-scans              # remove graph records of architecture scans
thalamus repair-claim-addresses    # move Claims back to the address their content produces
```

`repair-claim-addresses` is the repair half of `contract check`'s content-address
audit, and it treats the audit's two groups differently. A stale duplicate — one whose
twin at the recomputed id holds the `CONTAINS` — has its edges moved to the twin before
it is dropped, so the record that retrieval or a consultation ever surfaced that
content survives the vertex. A vertex with no twin is the live record at a wrong
address: it is re-minted at the correct id with every edge moved, never renamed in
place, which is the rewrite that produces this class.

Where the far endpoint already holds the same edge to the destination, the move
**collapses**: one trace returned the same claim twice under two ids, and its fan-out
was counted as two. The dry run prints those separately, because merging them changes
a number the eval loop has already reported.

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
| `THALAMUS_CONFIG_DIR` | Where `experts/` and `mcp/` are read from, instead of the checkout's `config/`. The eval battery in the companion repo reads its own `tasks/` from the same variable |
| `THALAMUS_GRAPH_URL` | The Gremlin endpoint, read by `status`, `init`, `init --check` and the MCP server. **Every other command ignores it** and takes `--url`, defaulting to `ws://localhost:8182/gremlin` — so setting this and running `ingest` or `extract` still writes to localhost ([#60](https://github.com/Ybx-jp/thalamus/issues/60)) |
| `THALAMUS_ARCHIVE_DIR` | Where retained transcripts and their indexes live, instead of `~/.thalamus/archive`. The index follows the archive; it has no override of its own |
| `THALAMUS_LOG_LEVEL` | Log level for the MCP server process (`thalamus-mcp`), default `WARNING`. Set it to `INFO` or `DEBUG` when a recall is returning something you cannot explain |
| `THALAMUS_TMUX_SOCKET` | The tmux server the roster, `spawn`, `dispatch` and the console address (`tmux -L …`), default `thalamus`. Two checkouts on one box get separate control planes by setting it differently |
| `THALAMUS_WITHHOLD` | The per-node suppression rate `memory_recall` applies, read at each call. Absent or unparseable means off, and an unrandomized session logs nothing — so the intervention leaves no trace when it is not running. Every draw appends to `~/.thalamus/policy/`; `thalamus eval withholding` reads them |
