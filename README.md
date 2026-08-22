# Thalamus

**Persistent, auditable memory for coding agents.**

Your agent forgets everything when the session ends. The usual fix is to stuff a
vector store with chunks and hope the right ones come back. Thalamus takes the other
road: sessions are distilled into a **property graph** where every node carries its
provenance — where the belief came from, how much it can be trusted, and which
messages in which transcript produced it. You can ask the graph what your agent
believes, and it can show you why.

In the brain, the thalamus is the relay: nearly every signal bound for a specialized
cortical region passes through it, and it gates what gets through. Same job here.

```
Session ends → distilled into the graph → next session opens with its threads
                        ↓
              every claim traceable to the message it came from
```

## What makes it different

**The graph is federated, not one pile.** Specialist knowledge lives in **expert
subgraphs** — a curated domain graph plus its own episodic memory, one per scope.
A session is *pinned* to exactly one scope and cannot widen its own view. Crossing
between scopes is an explicit, recorded event rather than a lucky retrieval.

**One contract does three jobs.** The federation contract is simultaneously a data
schema, a permission system, and a trust boundary. Orphans and violations are
rejected when they are written, not filtered when they are read.

**Trust is structural.** Every node carries a tier, and `DERIVED_FROM` edges make a
node's effective trust the *floor* over its whole derivation chain. A claim resting
on a fetched web page cannot end up trusted like a claim you made yourself —
distillation does not launder. Retrieved knowledge comes back blockquoted with its
citation and tier: it informs, it never instructs.

**Memory builds itself.** You don't curate it. A session ends, a hook distills the
retained transcript into claims and open threads, and the next session opens already
knowing where you left off.

**You can audit all of it.** The main scope is dense and connective, referencing
expert nodes by ID and copying nothing. A live dashboard prices what retrieval
actually cost.

## Quick start

**Your graph starts empty and stays yours.** Thalamus ships no seed graph, no export
and no fixture corpus — a graph is one operator's session history, so every install is
fresh, for everyone.

### Prerequisites

| | Why |
|---|---|
| **Docker** | runs the graph (Gremlin Server on TinkerGraph) |
| **Python ≥3.11** and [**uv**](https://docs.astral.sh/uv/) | the package and its CLI |
| **jq** | every hook parses its stdin with it; without it the hook layer dies silently |
| **tmux** | the roster and the console drive pinned sessions as tmux windows |
| **A coding-agent CLI** — Claude Code (`claude`), Cursor (`agent`), codex (`codex`), or any mix | distillation shells out to it |

### Install

```bash
git clone https://github.com/Ybx-jp/thalamus && cd thalamus

docker compose up -d           # the graph, on 127.0.0.1:8182 — no licence, no account
uv sync --extra dev            # creates .venv with the package and its CLI
uv run thalamus init           # wire your editor, then verify what it wired
```

`thalamus init` installs at **user scope**, so the harness arms in every directory
rather than only inside this checkout. It wires every supported harness by default;
use `--harness claude`, `--harness cursor` or `--harness codex` for one. `--dry-run`
reports without writing, and `--check` re-verifies any time.

Because user scope means *outside this checkout*, it lists what it will write and asks
before writing — `~/.claude/settings.json`, `~/.cursor/hooks.json` and
`~/.codex/hooks.json`, `~/.claude.json` (the MCP server), plus skill symlinks and one
derived agent per expert. Pass `--yes` to
skip the prompt in a script; a non-interactive stdin declines rather than assumes.
**`thalamus init --uninstall` takes all of it back out**, removing only what it can
prove it installed, and leaving your graph, `~/.thalamus/` and the transcript archive
alone.

### Then relaunch your editor

Hooks and the MCP server arm **per process**, so an already-running session picks up
nothing. Quit and reopen your editor; `/clear` is not enough.

A new session should greet you with a memory prompt and its pinned scope. From there,
memory builds itself.

**Full walkthrough, including what the first run looks like:**
[docs/getting-started.md](docs/getting-started.md).

## What this release is

**0.1.0 runs from a checkout.** There is no `pip install thalamus` yet — several
modules resolve paths from the repo root, and the expert manifests in `config/` live
outside the package, so an installed wheel would look for paths that only exist in a
clone. Installing without a clone is the 0.2.0 milestone.

Two features are **experimental and off by default**, each behind a flag on
`thalamus console`:

| | Flag | Off means |
|---|---|---|
| `say` — reads the active window aloud | `--voice URL` | no control, no endpoints. Needs a separate TTS unit (`--extra voice`) |
| Frame themes — the pane inside artwork | `--frames PATH` | no controls and no key bindings; no artwork ships |

## What's live

- **The substrate** — a property graph (Apache TinkerPop / TinkerGraph) of `Session` /
  `Claim` / `Thread` / `Source` / `Artifact` nodes, every one carrying provenance and a
  scope. Orphans and contract violations are rejected at write time.
- **The evidence archive** — memory is bootstrapped from retained session transcripts,
  held in an immutable content-addressed store outside the repo. The graph is a
  materialized view over that log: re-extract, never migrate.
- **The expert roster** — each scope declared by a manifest in `config/experts/` and
  nothing else. Five ship as examples; write a YAML file and you have a sixth.
- **Structural role boundaries** — where a scope is defined by what it must *not*
  produce, its manifest declares a `write_boundary` and a PreToolUse hook enforces it
  against the file-editing tools. The shipped `qe` manifest is the worked example: it
  holds the adversarial suite and is denied `src/`, so the scope that asserts against
  an implementation cannot quietly repair it. The reverse denial is in the ownership
  table, so no other scope can soften what it asserts either.
- **Session pinning** — one OS process, one immutable pin. The MCP server reads the
  scope from its environment at startup and no tool accepts a scope argument, so a
  model cannot widen its own view by asking.
- **The console** — because a pin is a process in a tmux window, the whole roster is
  addressable from one place. `thalamus console` serves it to a browser: a tab per
  window, the live pane, a composer, and one tap to spawn an expert in a project.
  Installable as a PWA on a phone over a tailnet.
- **The consultation protocol** — cross-expert questions ride single-use tickets where
  minting the ticket *is* writing the exchange record, and answers must cite nodes
  inside the consulted scope. Beside it, `thalamus quick ask` forks an expert's live
  session rather than cold-starting one.
- **Rooms** — a private roster whose members see and message each other and nobody
  else, enforced by a per-room config directory and an outbound guard.
- **The eval loop** — every memory-tool call is trace-tapped, landed as `Trace` nodes,
  judged used-vs-ignored against the retained transcript, and priced in injected
  tokens. Above it, a counterfactual harness runs one task memory-on / memory-off /
  degraded in a confined worktree, graded by an oracle whose rungs are validated
  against a mutant set before any run is scored.
- **Trust enforcement, first pass** — the transcript-ingress floor down-tiers distilled
  claims that rest on fetched web content.

## Status

Built and running: the substrate, the archive, the roster and pinning, the
consultation protocol, rooms, and the eval loop's trace, attribution and cost layers.

In progress: counterfactual measurement at a scale that can settle whether recalled
memory changes task outcomes. What the instrument shows today is that memory gets
*surfaced* — that it improves results is not yet demonstrated, and saying so is part
of the design. Full trust-model enforcement and end-to-end audit chains come after.

Roadmap and open work live in
[GitHub issues and milestones](https://github.com/Ybx-jp/thalamus/issues).

## Documentation

| | |
|---|---|
| [Getting started](docs/getting-started.md) | Install, first run, and what each step should look like |
| [Concepts](docs/concepts.md) | Scopes, experts, the federation contract, trust tiers, distillation |
| [CLI reference](docs/cli.md) | Every command |
| [The console](docs/console.md) | Driving the roster from your phone — the PWA, reaching it off the box, keeping it up |
| [Contributing](CONTRIBUTING.md) | Tests, conventions, how the pieces fit |

## Layout

```
src/thalamus/
  substrate/   storage kernel — schema, Gremlin writer, Gremlin reader
  contract/    the federation boundary — ontology, expert manifests, conformance
  console/     the browser/PWA control plane over the tmux roster
  archive/     immutable content-addressed store for retained evidence
  harness/     where it meets the agent — MCP server, hooks, skills, bootstrap
  eval/        trace tap, attribution, cost — the live-serving half of the eval loop.
               The counterfactual harness (task battery, arms, oracle) is research
               instrumentation; it lives in the private thalamus-eval companion repo
  pulse/       live telemetry dashboard over the eval loop
config/        expert manifests
docs/          user documentation
```

## License

MIT — see [LICENSE](LICENSE).
