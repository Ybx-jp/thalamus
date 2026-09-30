# Thalamus

Memory for coding agents that can show where each thing it remembers came from.

When a Claude Code, Cursor or codex session ends, Thalamus reads the transcript and
writes what happened into a graph database: the decisions and the reasons for them, the
problems and how they were fixed, and the work left unfinished. The next session starts
with the unfinished work in front of it and can search the rest.

Every stored item points back to the session or document it came from, and that
transcript or document is kept unedited outside the graph. Each item also records whose
word it rests on: yours, the agent's own reasoning, or a document the agent read. That
record is what lets you ask the agent why it believes something and get an answer you
can check.

What it does not show yet is that recalled memory makes an agent finish tasks better.
It shows that memory gets surfaced; the [status](#status) section says what would
settle the rest.

The name is from the brain: the thalamus relays nearly every signal bound for a
specialized region of the cortex, and gates what gets through.

```
session ends → transcript read → decisions, fixes and open work written to the graph
                                              ↓
                  next session starts with the open work and can search the rest
```

## How it works

The project has its own vocabulary, and every term below is defined in
[Concepts](docs/concepts.md). This section uses as little of it as it can.

### Memory writes itself when a session ends

You don't curate it. A hook reads the retained transcript and extracts claims (a
decision, a problem, a fix) and open threads (work the session did not finish). The
next session opens already knowing where you left off.

### Where an item came from decides how far it is trusted

Every item carries a trust tier: 0 for what you wrote down yourself, 1 for what an agent
observed or worked out in its own sessions, 2 for outside documents from sources you
approved, and 3 for outside content from anywhere else.

The data model defines an item's effective trust as the lowest tier anywhere in what it
was derived from, so an agent's summary of a paper is trusted like the
paper.<!-- (A0051, cites-as-live) -->
No code computes that rule across a whole chain of derivations yet.

What is enforced today is narrower. When a session fetched pages with the agent's web
tools, the claims that rest on those pages are stored at outside-document
trust.<!-- (A0052, cites-as-live) -->
The extractor marks them, and a mechanical check also catches a claim that repeats the
page's wording when the mark is missing. A page fetched through the shell, and a claim
that restates a page in different words, are not caught.

Recalled items come back quoted, with their source and tier attached: they inform the
agent and never instruct it.<!-- (A0054, cites-as-live) -->

### Each specialist keeps its own memory

Knowledge is split by domain. Each specialist, called an expert (a literature reviewer,
a quality engineer, an architect), has its own graph of curated documents plus its own
session history, and the pair is called a scope. A session runs as exactly one scope,
fixed when the session starts.<!-- (A0001, cites-as-live) -->
Asking another expert is a recorded consultation, never a search that happens to reach
across.<!-- (A0094, cites-as-live) -->

### A bad write is refused, not filtered later

One set of rules, the federation contract, is at once the data schema, the permission
system and the trust boundary. A write that breaks it is rejected when it is written,
rather than filtered out when it is read.<!-- (A0025, cites-as-live) -->

### You can see what memory cost

Every memory lookup is logged<!-- (A0097, cites-as-live) -->
and priced. `thalamus pulse` serves a live dashboard of what retrieval actually
cost.<!-- (A0085, cites-as-live) -->

## Quick start

Your graph starts empty and stays yours. Thalamus ships no seed graph, no export and
no fixture corpus: a graph is one operator's session history, so every install is
fresh, for everyone.

### Prerequisites

| | Why |
|---|---|
| **Docker** | runs the graph (Gremlin Server on TinkerGraph) |
| **Python ≥3.11** and [**uv**](https://docs.astral.sh/uv/) | the package and its CLI |
| **jq** | every hook parses its stdin with it; without it the hook layer dies silently |
| **tmux** | the roster and the console drive pinned sessions as tmux windows |
| **A coding-agent CLI**: Claude Code (`claude`), Cursor (`agent`), codex (`codex`), or any mix | distillation shells out to it |

### Install

```bash
git clone https://github.com/Ybx-jp/thalamus && cd thalamus

docker compose up -d           # the graph, on 127.0.0.1:8182; no licence, no account
uv sync --extra dev            # creates .venv with the package and its CLI
uv run thalamus init           # wire your editor, then verify what it wired
```

The graph answers a few seconds after `up -d` returns, because Docker publishes the
port before the server finishes starting. `docker compose ps` says `healthy` when it is
actually serving.

`thalamus init` installs at user scope, so the harness arms in every directory rather
than only inside this checkout. It wires every supported harness by default; use
`--harness claude`, `--harness cursor` or `--harness codex` for one. `--dry-run`
reports without writing, and `--check` re-verifies any time.

Because user scope means outside this checkout, it lists what it will write and asks
before writing: `~/.claude/settings.json`, `~/.cursor/hooks.json` and
`~/.codex/hooks.json`, `~/.claude.json` (the MCP server), plus skill symlinks and one
derived agent per expert. Pass `--yes` to skip the prompt in a script; a
non-interactive stdin declines rather than assumes. `thalamus init --uninstall` takes
all of it back out, removing only what it can prove it installed, and leaving your
graph, `~/.thalamus/` and the transcript archive alone.

### Then relaunch your editor

Hooks and the MCP server arm per process, so an already-running session picks up
nothing. Quit and reopen your editor; `/clear` is not enough.

A new session should greet you with a memory prompt and its pinned scope. From there,
memory builds itself. Distillation runs when a session ends, detached, and says nothing
in your terminal. So have a real session, quit the editor, and ask:

```bash
uv run thalamus status         # sessions in the graph, and the last distillation run
```

The count going from 0 to 1 is the confirmation that it works. `thalamus init --check`
answers the other half: whether the wiring that writes it is armed.

The full walkthrough, including what the first run looks like, is
[docs/getting-started.md](docs/getting-started.md).

## What this release is

Thalamus runs from a clone, and the clone is the distribution. There is no
`pip install thalamus`: several modules resolve paths from the repo root and the
expert manifests in `config/` live outside the package, so a wheel would look for
paths only a checkout has. `git pull` is the upgrade path. `pyproject.toml` carries
`Private :: Do Not Upload`, which makes the closed index mechanical rather than a
stated intention.

One feature is experimental and off by default: frame themes, which render the pane
inside artwork, behind `thalamus console --frames PATH`. Without the flag there are no
controls and no key bindings, and no artwork ships.

## What's live

- **The graph.** A property graph (Apache TinkerPop / TinkerGraph) with ten node kinds:
  `Session`, `Claim`, `Thread`, `Source`, `Artifact`, `Chunk`, `Entity`, `Exchange`,
  `Trace` and `Agent`, every one carrying provenance and a
  scope.<!-- (A0086, cites-as-live) -->
  Orphans and contract violations are rejected at write time.
- **The evidence archive.** Memory is bootstrapped from retained session transcripts,
  held in an immutable content-addressed store outside the
  repo.<!-- (A0087, cites-as-live) -->
  The graph is a view over that log that can be rebuilt from it: re-extract, never
  migrate.
- **Curated ingestion.** An expert's document half is fed one document at a time.
  `thalamus ingest <url|path> --scope <expert>` refuses bytes whose serving origin the
  scope's manifest does not allowlist<!-- (A0088, cites-as-live) -->,
  retains what survives the gate in the archive, and on `--write` lands it as a `Source`
  with the text indexed as `Chunk` vertices beside the claims drawn from it.
  `--check` runs that same path and stops at the model call, reporting the host that
  actually served the bytes for no model spend.<!-- (A0089, cites-as-live) -->
  The bytes are retained either way; the graph is what `--write` gates.
- **The expert roster.** Each scope is declared by a manifest in `config/experts/` and
  nothing else.<!-- (A0004, cites-as-live) -->
  Five ship as examples; write a YAML file and you have a sixth.
- **Role boundaries.** Where a scope is defined by what it must not produce, its
  manifest declares a `write_boundary` and a PreToolUse hook enforces it against the
  file-editing tools.<!-- (A0091, cites-as-live) -->
  The shipped `qe` manifest is the worked example: it holds the adversarial suite and is
  denied `src/`, so the scope that asserts against an implementation cannot quietly
  repair it.<!-- (A0092, cites-as-live) -->
  The reverse denial is in the ownership table, so no other scope can soften what it
  asserts either.<!-- (A0093, cites-as-live) -->
- **Session pinning.** One OS process, one immutable pin. `thalamus pin <scope>`
  launches a session into a scope; `thalamus roster` brings up the `main` anchor, and
  experts are spawned on demand (`--all` opens one window per manifest). The MCP server
  reads the scope from its environment at startup and no tool accepts a scope argument,
  so a model cannot widen its own view by asking. Nor by shelling out: the graph client
  reaches the whole graph<!-- (A0148, cites-as-live) -->,
  so a PreToolUse guard keeps a pinned session off it and on the tools that confine a
  read to the pin.
- **The console.** Because a pin is a process in a tmux window, the whole roster is
  addressable from one place. `thalamus console` serves it to a browser: a tab per
  window, the live pane, a composer, and one tap to spawn an expert in a project. It
  installs as a PWA on a phone over a tailnet.
- **Consultations.** Cross-expert questions ride single-use tickets where minting the
  ticket is writing the exchange record, and answers must cite nodes inside the
  consulted scope.<!-- (A0094, cites-as-live) -->
  Beside it, `thalamus quick ask` forks an expert's live session rather than
  cold-starting one.<!-- (A0063, cites-as-live) -->
- **Rooms.** A private roster whose members see and message each other and nobody else,
  enforced by a per-room config directory and an outbound
  guard.<!-- (A0096, cites-as-live) -->
- **The eval loop.** Every memory-tool call is logged as a `Trace` node, judged used or
  ignored against the retained transcript, and priced in injected
  tokens.<!-- (A0097, cites-as-live) -->
  Above it, a counterfactual harness runs one task with memory on, off and degraded in
  a confined worktree, graded by an oracle whose rungs are validated against a mutant
  set before any run is scored.
- **Trust enforcement, first pass.** The transcript-ingress floor down-tiers distilled
  claims that rest on pages fetched with the agent's web tools.

## Status

Built and running: the graph, the archive, curated ingestion, the roster and pinning,
consultations, rooms, and the eval loop's trace, attribution and cost layers.

In progress: counterfactual measurement at a scale that can settle whether recalled
memory changes task outcomes. What the instrument shows today is that memory gets
surfaced; that it improves results is not yet demonstrated, and saying so is part of
the design. Computing trust across whole derivation chains, closing the shell-fetch
and paraphrase gaps, and end-to-end audit chains come after.

Roadmap and open work live in
[GitHub issues and milestones](https://github.com/Ybx-jp/thalamus/issues).

## Documentation

| | |
|---|---|
| [Getting started](docs/getting-started.md) | Install, first run, and what each step should look like |
| [Concepts](docs/concepts.md) | Scopes, experts, the federation contract, trust tiers, distillation |
| [CLI reference](docs/cli.md) | Every command |
| [The console](docs/console.md) | Driving the roster from your phone: the PWA, reaching it off the box, keeping it up |
| [Contributing](CONTRIBUTING.md) | Tests, conventions, how the pieces fit |

## Layout

```
src/thalamus/
  substrate/   storage kernel: schema, Gremlin writer, Gremlin reader, query span tap
  contract/    the federation boundary: ontology, expert manifests, conformance
  console/     the browser/PWA control plane over the tmux roster
  archive/     immutable content-addressed store for retained evidence
  harness/     where it meets the agent: MCP server, hooks, skills, bootstrap, ingest
  eval/        trace tap, attribution, cost: the live-serving half of the eval loop.
               The counterfactual harness (task battery, arms, oracle) is research
               instrumentation; it lives in the private thalamus-eval companion repo
  arch/        the `architect` scope's instrument: a declared-policy import extractor
               and the structural metrics computed over it, gated in CI
  pulse/       live telemetry dashboard over the eval loop
arch/          model.yaml, the committed architecture model the gates check against
config/        expert manifests
ledger/        the claims ledger: one entry per documented commitment, pinned by
               digest to the section of source that keeps it true
docs/          user documentation
docker/        the confinement image a counterfactual arm runs inside
tools/         frame-theme authoring scripts (`--extra frames`)
tests/         the suite, including `tests/qe/`, the adversarial suite owned by `qe`
```

## License

MIT. See [LICENSE](LICENSE).
